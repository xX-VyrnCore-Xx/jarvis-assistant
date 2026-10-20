import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.auth import throttle
from app.budget import describe, fmt_tokens, summarize
from app.config import Settings, get_settings
from app.freellm_admin import FreeLLMAdmin, derive_password
from app.pending import PendingStore

FREE_TIER = {
    "summary": {"documentedMonthlyTokens": 150_000_000},
    "pools": [
        {"platform": "google", "kind": "documented", "documentedBudget": 100_000_000,
         "quota": {"metric": "tokens", "remaining": 60_000_000, "limit": 100_000_000}},
        {"platform": "groq", "kind": "documented", "documentedBudget": 50_000_000, "quota": None},
        {"platform": "ollama", "kind": "credits", "documentedBudget": 0, "quota": None},
    ],
}
USAGE = {"month": "2026-10", "resetsAt": "2026-11-01", "tokens": 12_000_000, "requests": 300,
         "byPlatform": [{"platform": "groq", "tokens": 8_000_000}, {"platform": "google", "tokens": 4_000_000}]}


def test_budget_prefers_live_quota_and_estimates_the_rest():
    b = summarize(FREE_TIER, USAGE)
    rows = {r["platform"]: r for r in b["providers"]}
    assert rows["google"]["remaining"] == 60_000_000 and rows["google"]["source"] == "live"
    assert rows["groq"]["remaining"] == 42_000_000 and rows["groq"]["source"] == "estimate"  # 50M - 8M usati
    assert rows["ollama"]["remaining"] is None  # a crediti: non entra nel totale
    assert b["remaining_tokens"] == 102_000_000 and b["providers_unknown"] == 1
    assert "102.0 M" in describe(b) and "groq" in describe(b)
    assert fmt_tokens(950) == "950" and fmt_tokens(12_500) == "12 k" and fmt_tokens(2.5e9) == "2.5 G"


def test_budget_never_goes_negative():
    over = {**USAGE, "byPlatform": [{"platform": "groq", "tokens": 90_000_000}]}
    rows = {r["platform"]: r for r in summarize(FREE_TIER, over)["providers"]}
    assert rows["groq"]["remaining"] == 0


@pytest.mark.asyncio
async def test_admin_creates_the_dashboard_account_then_reuses_the_session():
    seen = {"setup": 0, "login": 0, "tier": 0}

    def h(req):
        path = req.url.path
        if path == "/api/auth/login":
            seen["login"] += 1
            return httpx.Response(401, json={})
        if path == "/api/auth/setup":
            seen["setup"] += 1
            assert req.read() and b"jarvis@jarvis.local" in req.content
            return httpx.Response(201, json={"token": "T1"})
        if path == "/api/free-tier":
            seen["tier"] += 1
            assert req.headers["authorization"] == "Bearer T1"
            return httpx.Response(200, json=FREE_TIER)
        return httpx.Response(404)

    s = Settings(freellm_internal_url="http://x:3001", encryption_key="a" * 64)
    admin = FreeLLMAdmin(s, httpx.AsyncClient(transport=httpx.MockTransport(h)))
    assert admin.enabled and admin.password == derive_password("a" * 64)
    await admin.get("/api/free-tier")
    await admin.get("/api/free-tier")
    assert seen == {"setup": 1, "login": 1, "tier": 2}  # un solo accesso per due richieste


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "tok")
    monkeypatch.delenv("FREELLM_INTERNAL_URL", raising=False)
    get_settings.cache_clear()
    throttle._fails.clear()
    throttle._locked.clear()
    with TestClient(main.app) as c:
        yield c
    get_settings.cache_clear()


AUTH = {"Authorization": "Bearer tok"}


def test_api_requires_the_token_and_exposes_status(client):
    assert client.get("/api/status").status_code == 401
    st = client.get("/api/status", headers=AUTH).json()
    assert st["pc_connected"] is False and st["memory"] == "ram" and st["pending_actions"] == 0
    assert client.get("/api/tokens", headers=AUTH).status_code == 404  # FreeLLMAPI assente in questo test


def test_reminders_crud_and_history(client):
    r = client.post("/api/reminders", headers=AUTH, json={"text": "x", "when": "2020-01-01T10:00:00"})
    assert r.status_code == 422
    assert client.post("/api/reminders", headers=AUTH, json={"text": "x", "when": "boh"}).status_code == 422
    assert client.post("/api/reminders", headers=AUTH, json={"text": "bere", "when": "2999-01-01T10:00:00"}).status_code == 201
    (item,) = client.get("/api/reminders", headers=AUTH).json()
    assert item["text"] == "bere"
    client.delete(f"/api/reminders/{item['id']}", headers=AUTH)
    assert client.get("/api/reminders", headers=AUTH).json() == []
    assert client.get("/api/history?session_id=../etc", headers=AUTH).status_code == 422
    assert client.get("/api/history", headers=AUTH).json() == []


def test_pending_actions_are_decided_only_through_the_authenticated_api(client):
    ran = []

    async def action():
        ran.append(1)
        return "fatto"

    p = main.app.state.pending.create("test", "Cosa", action)
    assert client.post(f"/api/pending/{p.id}/approve").status_code == 401 and not ran
    assert [x["id"] for x in client.get("/api/pending", headers=AUTH).json()] == [p.id]
    res = client.post(f"/api/pending/{p.id}/approve", headers=AUTH).json()
    assert res["status"] == "approved" and res["result"] == "fatto" and ran == [1]
    assert client.post(f"/api/pending/{p.id}/approve", headers=AUTH).json()["status"] == "approved" and ran == [1]  # una volta sola
    assert client.post("/api/pending/nope/approve", headers=AUTH).status_code == 404


@pytest.mark.asyncio
async def test_pending_expires():
    store = PendingStore(ttl_s=-1)
    p = store.create("k", "s", lambda: None)
    assert store.list_pending() == [] and (await store.decide(p.id, True)).status == "expired"


def test_too_many_wrong_tokens_lock_the_client_even_with_the_right_one(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "tok")
    monkeypatch.setenv("AUTH_FAIL_LIMIT", "3")
    get_settings.cache_clear()
    throttle._fails.clear()
    throttle._locked.clear()
    with TestClient(main.app) as c:
        for _ in range(3):
            assert c.get("/api/status", headers={"Authorization": "Bearer no"}).status_code == 401
        r = c.get("/api/status", headers=AUTH)
        assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    throttle._fails.clear()
    throttle._locked.clear()
    get_settings.cache_clear()


def test_chat_is_rate_limited(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "tok")
    monkeypatch.setenv("CHAT_PER_MINUTE", "2")
    get_settings.cache_clear()
    throttle._fails.clear()
    with TestClient(main.app) as c:
        codes = [c.post("/chat", headers=AUTH, json={"message": "x"}).status_code for _ in range(3)]
    assert codes[2] == 429 and codes[:2] == [502, 502]  # FreeLLMAPI non è configurato nel test
    get_settings.cache_clear()


def test_security_headers_and_body_limit(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert "max-age" in r.headers["strict-transport-security"]
    big = client.post("/chat", headers={**AUTH, "Content-Length": "5000000"}, content=b"x")
    assert big.status_code == 413
    assert client.post("/chat", headers=AUTH, json={"message": "x", "session_id": "a b/c"}).status_code == 422


def test_notifications_api_and_devices(client):
    h = AUTH
    assert client.post("/api/notifications/test", headers=h).status_code == 200
    rows = client.get("/api/notifications", headers=h).json()
    assert rows[0]["title"] == "Notifica di prova" and rows[0]["read"] is False
    assert client.post("/api/notifications/read", json={"ids": None}, headers=h).status_code == 200
    assert client.get("/api/notifications", headers=h).json()[0]["read"] is True
    dev = {"platform": "android", "token": "fcm-token-123456", "label": "Pixel"}
    r = client.post("/api/devices", json=dev, headers=h)
    assert r.status_code == 201 and r.json()["push"] is False
    assert client.delete("/api/devices", params={"token": dev["token"]}, headers=h).status_code == 200
    assert client.post("/api/devices", json={**dev, "platform": "ios"}, headers=h).status_code == 422
    assert client.get("/api/notifications").status_code == 401


@pytest.mark.asyncio
async def test_notifier_fans_out_to_stream_and_fcm():
    import json as _json

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.memory import MemoryStore
    from app.notify import FCM, Notifier

    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    account = {"project_id": "proj", "client_email": "sa@proj.iam.gserviceaccount.com", "private_key": pem}
    sent = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "oauth2.googleapis.com":
            assert b"assertion=" in req.content
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        assert req.headers["authorization"] == "Bearer at"
        msg = _json.loads(req.content)["message"]
        sent.append(msg["token"])
        if msg["token"] == "stale":
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}})
        return httpx.Response(200, json={"name": "ok"})

    s = Settings(jarvis_api_token="t", firebase_service_account_json=_json.dumps(account))
    fcm = FCM(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert fcm.enabled
    store = MemoryStore()
    await store.upsert_device("android", "good", "a")
    await store.upsert_device("android", "stale", "b")
    await store.upsert_device("windows", "pc", "c")
    n = Notifier(s, store, fcm=fcm)
    q = n.subscribe()
    row = await n.push("info", "Ciao", "mondo")
    assert (await q.get())["id"] == row["id"]
    assert sorted(sent) == ["good", "stale"]  # solo Android; il token scaduto viene rimosso
    assert [d["token"] for d in await store.list_devices()] == ["good", "pc"]
    n.unsubscribe(q)
    assert n.listeners == 0
    assert not FCM(Settings(firebase_service_account_json="{bad")).enabled


@pytest.mark.asyncio
async def test_hf_backup_encrypts_commits_and_keeps_only_recent():
    import json as _json

    from app.backup import HFBackup, decrypt, derive_key, repo_from_url

    s = Settings(jarvis_api_token="t", encryption_key="k", supabase_url="https://x.supabase.co", supabase_service_key="sk",
                 freeapi_db_backup_url="https://huggingface.co/datasets/me/store/resolve/main/freellmapi.db.backup",
                 freeapi_db_backup_token="hf", hf_backup_keep=2)
    assert repo_from_url(s.freeapi_db_backup_url) == "me/store" and repo_from_url("https://x/y") is None
    commits = []

    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if "supabase.co" in u:
            return httpx.Response(200, json=[{"id": 1, "content": "segreto"}] if req.url.params["offset"] == "0" else [])
        if "/tree/main/jarvis" in u:
            return httpx.Response(200, json=[{"type": "file", "path": f"jarvis/2020-01-0{i}.json.enc"} for i in (1, 2, 3)])
        if req.method == "HEAD":
            return httpx.Response(404)
        if "/commit/main" in u:
            commits.append([_json.loads(line) for line in req.content.decode().splitlines()])
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    b = HFBackup(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert b.enabled
    await b.run()
    ops = commits[0]
    files = [o["value"] for o in ops if o["key"] == "file"]
    enc = next(f for f in files if f["path"].startswith("jarvis/"))
    import base64
    blob = base64.b64decode(enc["content"])
    assert b"segreto" not in blob  # cifrato
    assert _json.loads(decrypt(derive_key(s), blob))["tables"]["messages"][0]["content"] == "segreto"
    assert any(f["path"] == "README.md" for f in files)
    assert sorted(o["value"]["path"] for o in ops if o["key"] == "deletedFile") == ["jarvis/2020-01-01.json.enc", "jarvis/2020-01-02.json.enc"]


@pytest.mark.asyncio
async def test_voice_is_relayed_to_the_pc_and_cached():
    import base64

    from app.pc import PCBridge
    from app.voice import TTSError, VoiceService

    class FakePC(PCBridge):
        calls = 0

        async def call(self, action, args, timeout=60.0):
            self.calls += 1
            return base64.b64encode(b"RIFFwav").decode() if args["text"] == "ciao" else "Voce non installata sul PC."

    pc = FakePC()
    v = VoiceService(pc)
    with pytest.raises(TTSError):  # PC scollegato
        await v.speak("ciao")
    pc.ws, pc.caps = object(), {"voice": True}
    assert v.enabled
    assert await v.speak("ciao") == b"RIFFwav" and await v.speak("ciao") == b"RIFFwav"
    assert pc.calls == 1  # la seconda è dalla cache
    with pytest.raises(TTSError, match="non installata"):
        await v.speak("altro")


def test_tts_endpoint_without_pc(client):
    assert client.post("/api/tts", json={"text": "ciao"}, headers=AUTH).status_code == 404
    assert client.post("/api/tts", json={"text": "ciao"}).status_code == 401
