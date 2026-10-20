import base64
import json

import httpx
import pytest

from app.config import Settings
from app.google import GoogleClient
from app.tools import ToolRegistry
from app.tools.google_tools import register_google_tools


def make(handler):
    s = Settings(google_client_id="i", google_client_secret="s", google_refresh_token="r")
    g = GoogleClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    reg = ToolRegistry()
    register_google_tools(reg, s, g)
    return reg, g


def token_or(handler):
    def h(req):
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "AT", "expires_in": 3600})
        assert req.headers["authorization"] == "Bearer AT"
        return handler(req)

    return h


@pytest.mark.asyncio
async def test_calendar_create_event_payload():
    seen = {}

    def h(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"id": "ev1"})

    reg, _ = make(token_or(h))
    out = await reg.call("calendar_create_event", json.dumps({"summary": "Dentista", "start": "2030-01-05T10:00:00", "duration_minutes": 30}))
    assert "ev1" in out
    assert seen["start"]["dateTime"].startswith("2030-01-05T10:00:00+01:00")
    assert seen["end"]["dateTime"].startswith("2030-01-05T10:30:00")


@pytest.mark.asyncio
async def test_draft_is_created_not_sent():
    paths = []

    def h(req):
        paths.append(req.url.path)
        raw = json.loads(req.content)["message"]["raw"]
        assert b"Subject: Ciao" in base64.urlsafe_b64decode(raw)
        return httpx.Response(200, json={"id": "d1"})

    reg, _ = make(token_or(h))
    out = await reg.call("gmail_create_draft", json.dumps({"to": "a@b.it", "subject": "Ciao", "body": "x"}))
    assert "Non è stata inviata" in out
    assert not any(p.endswith("/send") for p in paths)


@pytest.mark.asyncio
async def test_token_is_cached_and_api_errors_reach_the_model():
    calls = {"token": 0}

    def h(req):
        if req.url.host == "oauth2.googleapis.com":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "AT", "expires_in": 3600})
        return httpx.Response(403, json={"error": "denied"})

    reg, _ = make(h)
    for _ in range(2):
        assert "Errore" in await reg.call("drive_search", json.dumps({"query": "tasse"}))
    assert calls["token"] == 1
