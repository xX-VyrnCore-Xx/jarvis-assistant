import json

import pytest

from app.notify import CRITICAL, TTL
from app.pending import PendingStore
from app.tools import ToolRegistry
from app.tools.phone_tools import register_phone_tools
from app.tools.select import ToolSelector


class FakeNotifier:
    def __init__(self):
        self.sent = []

    async def push(self, kind, title, body="", telegram=None, meta=None):
        self.sent.append((kind, title, body, telegram, meta))
        return {"id": 1}


@pytest.mark.asyncio
async def test_phone_call_needs_the_users_confirmation_before_anything_is_sent():
    pending, n, reg = PendingStore(), FakeNotifier(), ToolRegistry()
    register_phone_tools(reg, pending, lambda: n)
    out = await reg.call("phone_call", json.dumps({"contact": "Luca Rossi", "via": "whatsapp", "video": True}))
    assert "conferma" in out and not n.sent  # nessun ordine al telefono finché l'utente non approva
    p = pending.list_pending()[0]
    assert p.kind == "phone_call" and "videochiamata WhatsApp" in p.summary and "Luca Rossi" in p.summary
    await pending.decide(p.id, True)
    kind, title, body, telegram, meta = n.sent[0]
    assert kind == "call" and telegram is False and meta == {"contact": "Luca Rossi", "via": "whatsapp", "video": True}


@pytest.mark.asyncio
async def test_phone_call_rejection_and_validation():
    pending, n, reg = PendingStore(), FakeNotifier(), ToolRegistry()
    register_phone_tools(reg, pending, lambda: n)
    await reg.call("phone_call", json.dumps({"contact": "Anna"}))
    await pending.decide(pending.list_pending()[0].id, False)
    assert not n.sent
    assert "Errore" in await reg.call("phone_call", json.dumps({"contact": "  "}))
    assert "Errore" in await reg.call("phone_call", json.dumps({"contact": "Anna", "via": "skype"}))
    assert "solo su WhatsApp" in await reg.call("phone_call", json.dumps({"contact": "Anna", "video": True}))
    assert not pending.list_pending()


def test_call_notifications_are_critical_short_lived_and_the_tool_is_selected_by_the_request():
    assert "call" in CRITICAL and TTL["call"] <= 120  # un ordine di chiamata scaduto non deve partire dopo minuti
    sel = ToolSelector()
    assert "telefono" in sel.groups_for("chiama Luca su WhatsApp") and "telefono" in sel.groups_for("fammi una videochiamata con Anna")
    assert "telefono" not in sel.groups_for("che tempo fa domani")
