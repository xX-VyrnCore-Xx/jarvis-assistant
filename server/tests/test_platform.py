import hashlib
import hmac
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import Agent
from app.api import forecast
from app.auth import throttle
from app.config import Settings, get_settings
from app.llm import LLMClient, LLMError
from app.memory import MemoryStore
from app.notify import FCM, Notifier
from app.privacy import Redactor, StreamUnmasker
from app.tools import ToolRegistry
from app.updates import UpdateService, parse_version
from app.usage import UsageTracker

AUTH = {"Authorization": "Bearer tok"}


# ------------------------------------------------------------------ notifiche
class FakeFCM(FCM):
    def __init__(self):
        super().__init__(Settings())
        self.sent = []
        self.account = {"x": 1}

    async def send(self, token, title, body, kind, route="", nid=0, silent=False):
        self.sent.append((token, kind, route, nid))
        return True


@pytest.mark.asyncio
async def test_notifier_prefs_quiet_hours_dedupe_meta_and_read_sync():
    s = Settings(timezone="Europe/Rome")
    store = MemoryStore()
    await store.upsert_device("android", "dev", "p")
    fcm = FakeFCM()
    n = Notifier(s, store, fcm=fcm)
    q = n.subscribe()

    night = datetime(2026, 10, 20, 2, 0, tzinfo=ZoneInfo("Europe/Rome"))
    assert n.in_quiet_hours((await n.prefs())["quiet"], night) and not n.in_quiet_hours((await n.prefs())["quiet"], night.replace(hour=12))

    r = await n.push("reminder", "⏰ Promemoria", "chiamare Luca")
    assert fcm.sent[-1][:3] == ("dev", "reminder", "reminders") and r["meta"]["route"] == "reminders"  # i promemoria arrivano sempre
    assert (await q.get())["id"] == r["id"]
    dup = await n.push("reminder", "⏰ Promemoria", "chiamare Luca")
    assert dup.get("duplicate") and len(fcm.sent) == 1  # lo stesso avviso entro 10 minuti non si ripete

    await n.set_prefs({"kinds": {"info": {"push": False}}, "quiet": {"from": "22:00", "to": "06:00", "enabled": True}})
    await n.push("info", "Solo nell'app", "x")
    assert len(fcm.sent) == 1  # push disattivate per "info"
    assert (await n.prefs())["quiet"]["from"] == "22:00" and not (await n.set_prefs({"quiet": {"from": "ciao"}}))["quiet"]["from"] == "ciao"

    await n.mark_read([r["id"]])
    ev = [await q.get() for _ in range(2)]
    assert ev[-1] == {"event": "read", "ids": [r["id"]]}  # le altre app azzerano il contatore
    assert (await store.get_setting("notify_prefs")).startswith("{")  # le preferenze sopravvivono al riavvio
    assert (await Notifier(s, store, fcm=fcm).prefs())["kinds"]["info"]["push"] is False


# ------------------------------------------------------------------ aggiornamenti
RELEASE = {"tag_name": "v0.4.0", "body": "## Novità\n- Grafica nuova per Android e aggiornamenti dentro l'app", "published_at": "2026-10-21T10:00:00Z", "html_url": "https://github.com/o/r/releases/tag/v0.4.0",
           "assets": [{"name": "JARVIS-0.4.0.apk", "browser_download_url": "https://github.com/o/r/releases/download/v0.4.0/JARVIS-0.4.0.apk", "size": 9_000_000},
                      {"name": "JARVIS_0.4.0_x64-setup.exe", "browser_download_url": "https://github.com/o/r/releases/download/v0.4.0/JARVIS_0.4.0_x64-setup.exe", "size": 5_000_000},
                      {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/o/r/releases/download/v0.4.0/SHA256SUMS.txt", "size": 200},
                      {"name": "evil.apk", "browser_download_url": "https://evil.example/evil.apk", "size": 1}]}


def release_client():
    sums = f"{'a' * 64}  android/JARVIS-0.4.0.apk\n{'b' * 64}  windows/JARVIS_0.4.0_x64-setup.exe\n"

    older = {**RELEASE, "tag_name": "v0.3.5", "body": "## What's Changed\n* Voce neurale sempre disponibile (#42) by @utente in https://github.com/o/r/pull/42\n* Nuova chat in tutte le app (#41) by @utente in https://github.com/o/r/pull/41\n**Full Changelog**: https://github.com/o/r/compare/a...b"}

    def handler(req):
        if "per_page" in str(req.url):
            return httpx.Response(200, json=[RELEASE, older, {**RELEASE, "tag_name": "v0.3.0", "body": "- Vecchia novità già installata"}])
        if "api.github.com" in str(req.url):
            return httpx.Response(200, json=RELEASE)
        return httpx.Response(200, text=sums)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_updates_pick_assets_verify_hash_and_notify_once():
    assert parse_version("v1.10.2") > parse_version("1.9.9") and parse_version("boh") == (0, 0, 0)
    store = MemoryStore()
    n = Notifier(Settings(), store)
    u = UpdateService(Settings(github_repo="o/r"), store, n, release_client())
    a = await u.check_for("android", "0.3.0")
    assert a["available"] and a["latest"] == "0.4.0" and a["sha256"] == "a" * 64 and a["url"].endswith("JARVIS-0.4.0.apk")
    assert a["behind"] == 2 and a["changes"][1]["highlights"] == ["Voce neurale sempre disponibile", "Nuova chat in tutte le app"]  # novità di ogni versione saltata, senza autore e link
    assert not (await u.check_for("android", "0.4.0"))["available"] and (await u.check_for("windows", "0.3.0"))["sha256"] == "b" * 64
    assert "evil" not in json.dumps((await u.latest())["assets"])  # solo file della Release del repository

    assert (await u.poll_and_notify()).startswith("base")  # primo controllo: nessuna notifica a vuoto
    await store.set_setting("last_release_notified", "0.3.0")
    assert (await u.poll_and_notify(force=True)).startswith("notificata")
    assert (await store.list_notifications(5))[0]["kind"] == "update" and (await u.poll_and_notify(force=True)) == "nessuna novità"


# ------------------------------------------------------------------ consumi e previsione
@pytest.mark.asyncio
async def test_usage_tracker_flushes_increments_only():
    t, store = UsageTracker(), MemoryStore()
    t.record("chat", "m", 100, 20, 500)
    t.record("chat", "m", 50, 10, 300, ok=False)
    assert t.today()["requests"] == 2 and t.today()["errors"] == 1 and await t.flush(store) == 1
    t.record("chat", "m", 10, 5, 100)
    await t.flush(store)
    await t.flush(store)  # nessun cambiamento: nessuna scrittura
    row = (await store.usage_series(7))[0]
    assert row["requests"] == 3 and row["prompt_tokens"] == 160 and row["completion_tokens"] == 35


def test_token_forecast_projects_depletion():
    f = forecast({"used_tokens": 30_000_000, "remaining_tokens": 120_000_000, "resets_at": "2999-01-01T00:00:00Z"})
    assert f["burn_per_day"] > 0 and f["days_left"] > 0 and f["depletes_on"] and f["runs_out_before_reset"] is True  # il reset è lontanissimo
    soon = forecast({"used_tokens": 100_000_000, "remaining_tokens": 1_000, "resets_at": "2999-01-01T00:00:00Z"})
    assert soon["days_left"] < 1
    assert forecast({"used_tokens": 0, "remaining_tokens": None})["days_left"] is None


# ------------------------------------------------------------------ modelli: streaming, elenco, trascrizione
def sse(*chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_llm_stream_collects_text_tool_calls_and_usage():
    body = sse({"model": "m1", "choices": [{"delta": {"content": "Ciao "}}]}, {"choices": [{"delta": {"content": "mondo"}}]},
               {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_", "arguments": "{\"a\""}}]}}]},
               {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "weather", "arguments": ": 1}"}}]}}], "usage": {"prompt_tokens": 12, "completion_tokens": 7}})
    seen = {}

    def handler(req):
        seen["payload"] = json.loads(req.content)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    usage = UsageTracker()
    llm = LLMClient(Settings(freellm_base_url="http://x/v1", freellm_api_key="k"), httpx.AsyncClient(transport=httpx.MockTransport(handler)), usage)
    events = [e async for e in llm.chat_stream([{"role": "user", "content": "x"}], [{"type": "function"}])]
    assert [e[1] for e in events[:2]] == ["Ciao ", "mondo"]
    msg = events[-1][1]
    assert msg["content"] == "Ciao mondo" and msg["tool_calls"][0]["function"] == {"name": "get_weather", "arguments": "{\"a\": 1}"}
    assert seen["payload"]["stream"] is True and seen["payload"]["temperature"] == 0.2 and seen["payload"]["max_tokens"] == 1500  # con i tool: più preciso e con tetto
    assert usage.today()["prompt_tokens"] == 12 and usage.today()["completion_tokens"] == 7


@pytest.mark.asyncio
async def test_llm_models_cache_and_transcription():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b"}, {"id": "gemini-2.5-flash", "owned_by": "google"}]})
        assert b"voice.ogg" in req.content
        return httpx.Response(200, json={"text": " ricordami di chiamare Luca "})

    llm = LLMClient(Settings(freellm_base_url="http://x/v1", freellm_api_key="k"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert [m["id"] for m in await llm.models()] == ["llama-3.3-70b", "gemini-2.5-flash"] and await llm.models()
    assert calls.count("/v1/models") == 1  # in cache
    assert await llm.transcribe(b"OggS...", "voice.ogg") == "ricordami di chiamare Luca"
    bad = LLMClient(Settings(freellm_base_url="http://x/v1", freellm_api_key="k"), httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    with pytest.raises(LLMError):
        await bad.transcribe(b"x")


@pytest.mark.asyncio
async def test_stream_unmasker_handles_split_placeholders():
    r = Redactor("standard")
    r.mask("IBAN IT60X0542811101000000123456")
    u = StreamUnmasker(r)
    out = "".join(u.feed(c) for c in ["Il tuo IBAN è [IB", "AN_1", "] ok [non", " un segnaposto"]) + u.flush()
    assert out == "Il tuo IBAN è IT60X0542811101000000123456 ok [non un segnaposto"


class StreamLLM:
    def __init__(self):
        self.round = 0

    async def chat_stream(self, messages, tools=None, model=None):
        self.round += 1
        if self.round == 1:
            yield ("done", {"content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "get_datetime", "arguments": "{}"}}]})
        else:
            assert any(m["role"] == "tool" for m in messages)
            yield ("delta", "Sono le ")
            yield ("delta", "dieci.")
            yield ("done", {"content": "Sono le dieci."})


@pytest.mark.asyncio
async def test_agent_reply_stream_reports_tools_then_text_and_persists():
    from app.tools.basic import register_basic_tools

    s = Settings(jarvis_api_token="t")
    store, reg = MemoryStore(), ToolRegistry()
    register_basic_tools(reg, s, store)
    agent = Agent(s, StreamLLM(), store, reg)
    events = [e async for e in agent.reply_stream("che ore sono", "s1")]
    assert events[0][0] == "status" and ("delta", "Sono le ") in events and events[-1] == ("done", "Sono le dieci.")
    assert [m["role"] for m in store.messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_history_is_trimmed_to_character_budget():
    s = Settings(jarvis_api_token="t", history_chars=300)
    store = MemoryStore()
    for i in range(10):
        await store.add_message("s", "user" if i % 2 == 0 else "assistant", f"{i}" * 100)
    seen = {}

    class Spy:
        async def chat(self, messages, tools=None, model=None, kind="chat"):
            seen["n"] = len([m for m in messages if m["role"] != "system"])
            return {"content": "ok"}

    await Agent(s, Spy(), store, ToolRegistry()).reply("ciao a tutti quanti", "s")
    assert seen["n"] <= 5  # 300 caratteri di cronologia (~3 messaggi) + la domanda


# ------------------------------------------------------------------ API
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "tok")
    monkeypatch.delenv("FREELLM_INTERNAL_URL", raising=False)
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    throttle._fails.clear()
    throttle._locked.clear()
    with TestClient(main.app) as c:
        yield c
    get_settings.cache_clear()


def test_api_prefs_snooze_health_usage_update_and_stream(client):
    prefs = client.get("/api/notify/prefs", headers=AUTH).json()
    assert prefs["quiet"]["enabled"] and prefs["kinds"]["reminder"]["telegram"]
    client.post("/api/notify/prefs", json={"kinds": {"update": {"telegram": False}}}, headers=AUTH)
    assert client.get("/api/notify/prefs", headers=AUTH).json()["kinds"]["update"]["telegram"] is False

    n = client.post("/api/notifications/test", headers=AUTH).json()
    assert client.post(f"/api/notifications/{n['id']}/snooze", json={"minutes": 10}, headers=AUTH).status_code == 404  # non è un promemoria

    st = main.app.state.store
    import asyncio

    loop = asyncio.new_event_loop()
    rem = loop.run_until_complete(main.app.state.notifier.push("reminder", "⏰", "bere acqua"))
    assert client.post(f"/api/notifications/{rem['id']}/snooze", json={"minutes": 15}, headers=AUTH).status_code == 200
    assert [r["text"] for r in loop.run_until_complete(st.list_reminders())] == ["bere acqua"]
    loop.close()
    assert client.delete("/api/notifications", params={"read_only": True}, headers=AUTH).status_code == 200

    h = client.get("/api/health", headers=AUTH).json()
    assert h["db"]["ok"] and "memory" in h and "usage_today" in h
    assert client.get("/api/usage", headers=AUTH).json()["today"]["requests"] >= 0
    assert client.get("/api/app/update", params={"platform": "ios"}, headers=AUTH).status_code == 422
    assert client.get("/api/models", headers=AUTH).status_code == 503  # nessun FreeLLMAPI in questo test

    assert client.post("/chat/stream", json={"message": "ciao"}).status_code == 401


def test_github_webhook_needs_valid_signature(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "segreto")
    get_settings.cache_clear()
    body = json.dumps({"action": "created"}).encode()
    sig = "sha256=" + hmac.new(b"segreto", body, hashlib.sha256).hexdigest()
    with TestClient(main.app) as c:
        assert c.post("/github/webhook", content=body, headers={"x-hub-signature-256": "sha256=00"}).status_code == 403
        assert c.post("/github/webhook", content=body, headers={"x-hub-signature-256": sig, "x-github-event": "release"}).status_code == 200
    get_settings.cache_clear()
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET")
    with TestClient(main.app) as c:
        assert c.post("/github/webhook", content=body).status_code == 404  # senza segreto l'endpoint non esiste
    get_settings.cache_clear()
