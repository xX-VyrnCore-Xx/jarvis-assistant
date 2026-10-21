import asyncio
import json
from datetime import datetime, timedelta

import httpx
import pytest

from app.config import Settings
from app.memory import MemoryStore, canonical_session
from app.notify import Notifier
from app.reminders import ReminderService, explain


def http_error(code, body):
    req = httpx.Request("GET", "https://www.googleapis.com/x")
    return httpx.HTTPStatusError("e", request=req, response=httpx.Response(code, json=body, request=req))


def test_calendar_errors_are_explained_in_italian_without_leaking_bodies():
    assert "ricollega Google" in explain(http_error(400, {"error": "invalid_grant", "error_description": "Token has been revoked"}))
    assert "non è abilitata" in explain(http_error(403, {"error": {"errors": [{"reason": "accessNotConfigured"}], "message": "Google Calendar API has not been used"}}))
    assert "Permessi insufficienti" in explain(http_error(403, {"error": {"errors": [{"reason": "insufficientPermissions"}], "message": "Insufficient Permission"}}))
    assert "Limite di richieste" in explain(http_error(403, {"error": {"errors": [{"reason": "rateLimitExceeded"}]}}))
    assert "problema" in explain(http_error(503, {})) and "non raggiungibile" in explain(httpx.ConnectTimeout("x"))
    assert "segreto" not in explain(http_error(418, {"error": {"message": "segreto"}}))


class BrokenGoogle:
    enabled = True

    async def request(self, *a, **k):
        raise http_error(403, {"error": {"errors": [{"reason": "accessNotConfigured"}]}})


@pytest.mark.asyncio
async def test_status_records_cause_and_devices_are_told_when_things_change():
    store = MemoryStore()
    svc = ReminderService(Settings(jarvis_api_token="t"), store, BrokenGoogle())
    seen = []
    svc.on_change = lambda: seen.append(1)
    due = datetime.now(svc.tz) + timedelta(hours=1)
    r = await svc.create("Chiamare Luca", due)
    assert not r["calendar"] and "non è abilitata" in r["error"] and svc.status["ok"] is False and seen == [1]
    with pytest.raises(Exception):
        await svc.sync()
    assert svc.status["failures"] >= 2 and "non è abilitata" in svc.status["detail"]
    await svc.delete(r["id"])
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_unlinked_status_and_sync_event_reaches_subscribers():
    svc = ReminderService(Settings(jarvis_api_token="t"), MemoryStore())
    assert await svc.sync() == {"created": 0, "updated": 0, "removed": 0, "imported": 0} and "solo nell'app" in svc.status["detail"]
    n = Notifier(Settings(jarvis_api_token="t"), MemoryStore(), None)
    q = n.subscribe()
    n.sync("reminders", "tel-1")
    assert q.get_nowait() == {"event": "sync", "scope": "reminders", "origin": "tel-1"}


@pytest.mark.asyncio
async def test_one_conversation_across_devices_but_telegram_stays_apart():
    s = MemoryStore()
    await s.add_message("mobile", "user", "ciao dal telefono")
    await s.add_message("desktop", "assistant", "risposta sul PC")
    await s.add_message("tg:42", "user", "su telegram")
    assert [m["content"] for m in await s.recent_messages("main", 10)] == ["ciao dal telefono", "risposta sul PC"]
    assert [m["content"] for m in await s.recent_messages("mobile", 10)] == ["ciao dal telefono", "risposta sul PC"]
    assert [m["content"] for m in await s.recent_messages("tg:42", 10)] == ["su telegram"]
    assert canonical_session("desktop") == "main" and canonical_session("tg:42") == "tg:42"
    await s.clear_messages("desktop")
    assert await s.recent_messages("main", 10) == [] and len(await s.recent_messages("tg:42", 10)) == 1
