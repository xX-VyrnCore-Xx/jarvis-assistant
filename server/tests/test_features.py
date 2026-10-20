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
