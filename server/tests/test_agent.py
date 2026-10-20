import json

import pytest
from fastapi.testclient import TestClient

from app.agent import Agent
from app.config import Settings
from app.main import app
from app.memory import MemoryStore
from app.tools import ToolRegistry
from app.tools.basic import register_basic_tools


class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        return self.script.pop(0)


def make(script):
    s = Settings(jarvis_api_token="t")
    store = MemoryStore()
    reg = ToolRegistry()
    register_basic_tools(reg, s, store)
    return Agent(s, FakeLLM(script), store, reg), store


@pytest.mark.asyncio
async def test_plain_reply_is_persisted():
    agent, store = make([{"content": "Buongiorno, signore."}])
    assert await agent.reply("ciao", "s1") == "Buongiorno, signore."
    assert [m["role"] for m in store.messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_tool_call_roundtrip_saves_memory():
    call = {"id": "1", "type": "function",
            "function": {"name": "remember", "arguments": json.dumps({"content": "Ama il caffè"})}}
    agent, store = make([{"content": None, "tool_calls": [call]}, {"content": "Annotato."}])
    assert await agent.reply("amo il caffè", "s1") == "Annotato."
    assert store.memories == ["Ama il caffè"]


@pytest.mark.asyncio
async def test_unknown_tool_does_not_crash():
    call = {"id": "1", "type": "function", "function": {"name": "boh", "arguments": "{}"}}
    agent, _ = make([{"content": None, "tool_calls": [call]}, {"content": "ok"}])
    assert await agent.reply("x", "s1") == "ok"


@pytest.mark.asyncio
async def test_tool_loop_is_bounded():
    call = {"id": "1", "type": "function", "function": {"name": "get_datetime", "arguments": "{}"}}
    agent, _ = make([{"content": None, "tool_calls": [call]}] * 5 + [{"content": "Ecco quanto trovato."}])
    assert await agent.reply("x", "s1") == "Ecco quanto trovato."  # dopo il limite chiede comunque una risposta, senza altri tool


def test_health_open_and_chat_requires_token(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "secret")
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.post("/chat", json={"message": "hi"}).status_code == 401
        assert c.post("/chat", json={"message": "hi"}, headers={"Authorization": "Bearer no"}).status_code == 401
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_reminder_tool_and_delivery():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.scheduler import deliver_due_reminders

    s = Settings(jarvis_api_token="t")
    store = MemoryStore()
    reg = ToolRegistry()
    register_basic_tools(reg, s, store)
    tz = ZoneInfo(s.timezone)

    past = (datetime.now(tz) - timedelta(minutes=1)).isoformat()
    assert "passato" in await reg.call("add_reminder", json.dumps({"text": "x", "when": past}))

    soon = (datetime.now(tz) + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert "fissato" in await reg.call("add_reminder", json.dumps({"text": "chiama Luca", "when": soon}))

    from app.notify import Notifier

    class FakeTG:
        enabled = True
        sent = []

        async def notify_owner(self, text):
            self.sent.append(text)

    tg = FakeTG()
    n = Notifier(s, store, tg)
    assert await deliver_due_reminders(store, n, datetime.now(tz)) == 0
    assert await deliver_due_reminders(store, n, datetime.now(tz) + timedelta(hours=2)) == 1
    assert "chiama Luca" in tg.sent[0]
    assert await deliver_due_reminders(store, n, datetime.now(tz) + timedelta(hours=2)) == 0


def test_telegram_webhook_whitelist(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "42")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sec")
    from app import main
    from app.config import get_settings

    get_settings.cache_clear()
    handled = []

    async def fake(self, update):
        handled.append(update["message"]["text"])

    from app.bot import TelegramBot

    monkeypatch.setattr(TelegramBot, "handle_update", fake)
    upd = lambda uid: {"message": {"from": {"id": uid}, "chat": {"id": uid}, "text": "ciao"}}  # noqa: E731
    with TestClient(main.app) as c:
        assert c.post("/telegram/webhook", json=upd(42)).status_code == 403
        h = {"X-Telegram-Bot-Api-Secret-Token": "sec"}
        assert c.post("/telegram/webhook", json=upd(99), headers=h).status_code == 200
        assert c.post("/telegram/webhook", json=upd(42), headers=h).status_code == 200
    assert handled == ["ciao"]
    get_settings.cache_clear()


def test_pc_bridge_roundtrip(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "secret")
    from app import main
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(main.app) as c:
        # token errato: chiusura
        with c.websocket_connect("/ws/pc") as ws:
            ws.send_json({"token": "no"})
            with pytest.raises(Exception):
                ws.receive_json()
        assert not main.app.state.pc.connected

        with c.websocket_connect("/ws/pc") as ws:
            ws.send_json({"token": "secret"})
            assert ws.receive_json() == {"type": "ready"}
            import threading

            out = {}
            t = threading.Thread(
                target=lambda: out.update(r=c.portal.call(main.app.state.pc.call, "pc_lock", {}, 5))
            )
            t.start()
            cmd = ws.receive_json()
            assert cmd["action"] == "pc_lock"
            ws.send_json({"type": "result", "id": cmd["id"], "output": "Bloccato."})
            t.join(5)
            assert out["r"] == "Bloccato."
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pc_call_without_connection():
    from app.pc import PCBridge

    assert "non è connesso" in await PCBridge().call("pc_lock", {})


@pytest.mark.asyncio
async def test_voice_flag_adds_spoken_style_instruction():
    agent, _ = make([{"content": "ok"}, {"content": "ok"}])
    await agent.reply("ciao", "v", voice=True)
    await agent.reply("ciao", "t", voice=False)
    assert "AD ALTA VOCE" in agent.llm.calls[0][0]["content"]
    assert "AD ALTA VOCE" not in agent.llm.calls[1][0]["content"]


@pytest.mark.asyncio
async def test_unified_key_is_read_from_freellm_db(tmp_path):
    import sqlite3

    import httpx

    from app.llm import LLMClient, LLMError

    db = tmp_path / "f.db"
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    s = Settings(freellm_base_url="http://x/v1", freellm_db_path=str(db))
    llm = LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    # DB non ancora creata: errore chiaro, nessun crash
    with pytest.raises(LLMError):
        llm._api_key()

    con = sqlite3.connect(db)
    con.execute("create table settings (key text primary key, value text)")
    con.execute("insert into settings values ('unified_api_key', 'freellmapi-abc')")
    con.commit()
    con.close()
    assert (await llm.chat([{"role": "user", "content": "x"}]))["content"] == "ok"
    assert seen["auth"] == "Bearer freellmapi-abc"


def test_gateway_forwards_only_v1_and_streams(monkeypatch):
    import httpx

    from app import main
    from app.config import get_settings

    monkeypatch.setenv("JARVIS_API_TOKEN", "t")
    monkeypatch.setenv("FREELLM_INTERNAL_URL", "http://upstream:3001")
    get_settings.cache_clear()
    seen = {}

    def upstream(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers.get("authorization"), req.content
        if req.url.path == "/v1/stream":
            return httpx.Response(200, stream=httpx.ByteStream(b"data: a\n\ndata: b\n\n"), headers={"content-type": "text/event-stream"})
        # stream=: una risposta già letta (content=/json=) non è ri-leggibile come farebbe un vero stream
        return httpx.Response(401, stream=httpx.ByteStream(b'{"error": {"message": "bad key"}}'), headers={"content-type": "application/json"})

    with TestClient(main.app) as c:
        main.app.state.gateway_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        r = c.post("/v1/chat/completions?x=1", content=b'{"m":1}', headers={"Authorization": "Bearer freellmapi-k"})
        assert r.status_code == 401 and r.json()["error"]["message"] == "bad key"
        assert seen["url"] == "http://upstream:3001/v1/chat/completions?x=1"
        assert seen["auth"] == "Bearer freellmapi-k" and seen["body"] == b'{"m":1}'
        assert c.get("/v1/stream").text == "data: a\n\ndata: b\n\n"
        # la dashboard (/api/*) non è inoltrata
        assert c.get("/api/keys").status_code == 404
    get_settings.cache_clear()


def test_gateway_disabled_and_credentials_endpoint(monkeypatch, tmp_path):
    import sqlite3

    from app import main
    from app.config import get_settings

    monkeypatch.setenv("JARVIS_API_TOKEN", "t")
    monkeypatch.delenv("FREELLM_INTERNAL_URL", raising=False)
    db = tmp_path / "f.db"
    con = sqlite3.connect(db)
    con.execute("create table settings (key text primary key, value text)")
    con.execute("insert into settings values ('unified_api_key', 'freellmapi-zzz')")
    con.commit()
    con.close()
    monkeypatch.setenv("FREELLM_DB_PATH", str(db))
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://x.onrender.com")
    get_settings.cache_clear()
    with TestClient(main.app) as c:
        assert c.get("/v1/models").status_code == 404
        assert c.get("/admin/freellm").status_code == 401
        r = c.get("/admin/freellm", headers={"Authorization": "Bearer t"})
        assert r.json() == {"base_url": "https://x.onrender.com/v1", "api_key": "freellmapi-zzz"}
    get_settings.cache_clear()


def test_cors_allows_app_origins_only(monkeypatch):
    from app import main
    from app.config import get_settings

    monkeypatch.setenv("JARVIS_API_TOKEN", "t")
    get_settings.cache_clear()
    with TestClient(main.app) as c:
        pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
        for origin in ("http://tauri.localhost", "https://localhost"):
            r = c.options("/chat", headers={"Origin": origin, **pre})
            assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
        r = c.options("/chat", headers={"Origin": "https://evil.example", **pre})
        assert "access-control-allow-origin" not in r.headers
        r = c.get("/health", headers={"Origin": "http://tauri.localhost"})
        assert r.headers["access-control-allow-origin"] == "http://tauri.localhost"
    get_settings.cache_clear()


def test_pc_tools_hidden_until_pc_connects_and_root_route():
    from app.pc import PCBridge
    from app.tools.pc_tools import register_pc_tools

    reg, pc = ToolRegistry(), PCBridge()
    register_pc_tools(reg, pc)
    assert reg.specs == []
    pc.ws = object()  # PC collegato
    assert {t["function"]["name"] for t in reg.specs} >= {"pc_open_app", "pc_lock", "pc_power"}

    from app import main

    with TestClient(main.app) as c:
        assert c.get("/").json() == {"name": "JARVIS", "status": "ok"}
        assert c.head("/").status_code == 200
