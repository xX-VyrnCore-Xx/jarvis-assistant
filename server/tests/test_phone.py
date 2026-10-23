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
    assert kind == "call" and telegram is False and meta == {"contact": "Luca Rossi", "contact_id": "", "via": "whatsapp", "video": True}


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


class BridgeNotifier(FakeNotifier):
    def __init__(self, listeners=1):
        super().__init__()
        self.listeners, self.events = listeners, []

    def broadcast(self, payload):
        self.events.append(payload)


@pytest.mark.asyncio
async def test_contacts_are_searched_on_the_phone_and_numbers_never_reach_the_model():
    import asyncio

    from app.phonebridge import PhoneBridge

    n = BridgeNotifier()
    bridge, pending, reg = PhoneBridge(lambda: n), PendingStore(), ToolRegistry()
    register_phone_tools(reg, pending, lambda: n, bridge)

    async def phone_answers():
        while not n.events:
            await asyncio.sleep(0)
        ev = n.events[0]
        assert ev["event"] == "command" and ev["cmd"] == "contacts.search" and ev["args"] == {"query": "mamma"}
        # il telefono risponde con nomi e codici: i numeri non ci sono (restano sul telefono)
        assert bridge.resolve(ev["id"], True, {"contacts": [{"id": "k7f3a", "name": "Mamma", "numbers": 2, "whatsapp": True}]})

    task = asyncio.create_task(phone_answers())
    out = await reg.call("contacts_search", json.dumps({"query": "mamma"}))
    await task
    assert "Mamma [id: k7f3a]" in out and "2 numeri" in out and "WhatsApp" in out and "+39" not in out and "333" not in out
    # poi la chiamata porta il codice, non il numero
    await reg.call("phone_call", json.dumps({"contact": "Mamma", "contact_id": "k7f3a", "via": "whatsapp"}))
    await pending.decide(pending.list_pending()[0].id, True)
    assert n.sent[-1][4]["contact_id"] == "k7f3a"


@pytest.mark.asyncio
async def test_bridge_fails_safely_when_phone_is_offline_slow_or_refuses():
    import asyncio

    from app.phonebridge import BridgeError, PhoneBridge

    off = BridgeNotifier(listeners=0)
    with pytest.raises(BridgeError, match="non è collegato"):
        await PhoneBridge(lambda: off).ask("contacts.search", {"query": "x"})
    on = BridgeNotifier()
    b = PhoneBridge(lambda: on)
    with pytest.raises(BridgeError, match="non ha risposto"):
        await b.ask("contacts.search", {"query": "x"}, timeout=0.05)
    assert not b._waiting  # nulla resta in attesa
    on.events.clear()
    t = asyncio.create_task(b.ask("contacts.search", {"query": "y"}, timeout=2))
    while not on.events:
        await asyncio.sleep(0)
    b.resolve(on.events[-1]["id"], False, error="Funzione disattivata dall'utente")
    with pytest.raises(BridgeError, match="disattivata"):
        await t
    assert not b.resolve("inesistente", True, {})  # risposte non attese si ignorano
    reg = ToolRegistry()
    register_phone_tools(reg, PendingStore(), lambda: off, PhoneBridge(lambda: off))
    assert "Errore" in await reg.call("contacts_search", json.dumps({"query": "ma"})) and "Errore" in await reg.call("contacts_search", json.dumps({"query": "m"}))
