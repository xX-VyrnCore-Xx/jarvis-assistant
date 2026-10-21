import json
import time
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from app import health
from app.brain.knowledge import Knowledge, seed_titles
from app.config import Settings
from app.memory import MemoryStore
from app.notify import Notifier
from app.telegram import Telegram
from tests.test_brain import make
from tests.test_tools_bot import FakeApp, make_bot


def wiki(pages: dict[str, str], fail=False):
    """Wikipedia finta: `pages` = titolo -> testo (assente = voce inesistente)."""
    def handler(req: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(503)
        q = req.url.params
        if q.get("action") == "opensearch":
            hit = next((t for t in pages if q["search"].lower() in t.lower()), None)
            return httpx.Response(200, json=[q["search"], [hit] if hit else [], [], []])
        t = q["titles"]
        if t not in pages:
            return httpx.Response(200, json={"query": {"pages": [{"title": t, "missing": True}]}})
        return httpx.Response(200, json={"query": {"pages": [{"title": t, "extract": pages[t], "fullurl": f"https://it.wikipedia.org/wiki/{t}"}]}})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_knowledge_learn_seed_resume_and_retrieval_rules():
    brain, store = make()
    titles = seed_titles()
    pages = {titles[0]: "L'Italia è una repubblica parlamentare nell'Europa meridionale.", titles[1]: "La Costituzione fu promulgata nel 1947.",
             "Fotosintesi clorofilliana": "Processo con cui le piante producono zuccheri dalla luce del sole."}
    k = Knowledge(Settings(), brain, MemoryStore(), wiki(pages))
    r = await k.learn("fotosintesi", full=True)
    assert r["status"] == "creato" and r["title"] == "Fotosintesi clorofilliana"
    assert (await store.get_doc(r["doc_id"])).enriched is True and (await store.get_doc(r["doc_id"])).source == "wiki"
    assert (await k.learn("fotosintesi", full=True))["status"] == "duplicato"
    assert (await k.learn("argomento che non esiste"))["status"] == "non trovato"

    assert await k.seed_batch(3) == 2  # una voce non esiste: si salta ma si avanza
    assert await k.progress() == (3, len(titles))
    assert await k.seed_batch(3) == 0 and await k.progress() == (6, len(titles))  # le successive non esistono: si salta ma si avanza
    assert not [d for d in await store.docs_to_enrich(50) if d.source == "wiki"]  # niente arricchimento a pagamento

    # la cultura generale compare nelle ricerche ma non scavalca né inquina il contesto personale
    assert any(x["source"] == "wiki" for x in await brain.search("fotosintesi piante luce zuccheri", k=3))
    await brain.ingest("Mia sorella si chiama Giulia e lavora a Torino", source="memory", importance=0.8)
    ctx = await brain.context("Dove lavora mia sorella Giulia?")
    assert "Giulia" in ctx and ctx.count("enciclopedia") <= 1


@pytest.mark.asyncio
async def test_knowledge_outage_does_not_advance_position():
    brain, _ = make()
    store = MemoryStore()
    k = Knowledge(Settings(), brain, store, wiki({}, fail=True))
    assert await k.seed_batch(3) == 0
    assert await k.progress() == (0, len(seed_titles()))


def test_heartbeat_line_and_stale_loops():
    st = SimpleNamespace(usage=SimpleNamespace(today=lambda: {"requests": 12, "errors": 1, "avg_latency_ms": 1800}), brain=SimpleNamespace(index=[1, 2, 3]),
                         notifier=SimpleNamespace(listeners=2), pending=SimpleNamespace(list_pending=lambda: []))
    app = SimpleNamespace(state=st)
    health.PULSE.clear()
    health.beat("cervello", 300)
    health.beat("proattivo", 300)
    line = health.heartbeat_line(app)
    assert "modelli oggi 12 (1 err, 1.8 s)" in line and "cervello 3 frammenti" in line and "app in diretta 2" in line and line.endswith("cicli ok")
    later = time.monotonic() + 3 * 300 + 120
    assert {n for n, _ in health.stale_loops(later)} == {"cervello", "proattivo"}
    assert "CICLI FERMI" in health.heartbeat_line(app, later)
    health.PULSE.clear()


@pytest.mark.asyncio
async def test_telegram_retries_once_on_flood_control(monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 2}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr("app.telegram.asyncio.sleep", fake_sleep)
    tg = Telegram(Settings(telegram_bot_token="x", telegram_owner_id=1), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await tg.send_id(1, "ciao") == 7 and len(calls) == 2 and slept == [2.0]


@pytest.mark.asyncio
async def test_bot_menu_daily_commands_suggestions_and_quick_actions():
    bot, st = make_bot()
    st.google = SimpleNamespace(enabled=False, has_client=False)
    st.brain = SimpleNamespace(enabled=True, knowledge=None)
    msg = lambda text, i: {"update_id": i, "message": {"from": {"id": 42}, "chat": {"id": 42}, "text": text}}  # noqa: E731

    await bot.handle_update(msg("/start", 1))
    text, markup = st.tg.out[-1]
    assert "Secondo cervello" in text and markup["keyboard"][0][0]["text"] == "📅 Agenda"

    await bot.handle_update(msg("📅 Agenda", 2))  # tasto rapido = comando
    assert "Google non è collegato" in st.tg.out[-1][0]

    await st.store.add_task("Chiamare il commercialista", "attività")
    await bot.handle_update(msg("/oggi", 3))
    assert "Chiamare il commercialista" in st.tg.out[-1][0]

    await bot.handle_update(msg("/agnda", 4))
    assert "/agenda" in st.tg.out[-1][0]

    await bot.handle_update(msg("domanda qualunque", 5))
    mid = list(bot._replies)[-1][1]
    await bot.handle_update({"update_id": 6, "callback_query": {"id": "c", "from": {"id": 42}, "data": "sh", "message": {"chat": {"id": 42}, "message_id": mid}}})
    assert any(o[0].startswith("eco:Riassumi la tua ultima risposta in due righe") for o in st.tg.out)


@pytest.mark.asyncio
async def test_bot_proactive_toggle_learn_and_settings_with_new_kind():
    bot, st = make_bot()
    st.settings = Settings(telegram_owner_id=42)
    st.proactive = SimpleNamespace(_state={"n": 2})
    st.notifier = Notifier(st.settings, st.store)
    cb = lambda data, i: {"update_id": i, "callback_query": {"id": "c", "from": {"id": 42}, "data": data, "message": {"chat": {"id": 42}, "message_id": 5}}}  # noqa: E731
    msg = lambda text, i: {"update_id": i, "message": {"from": {"id": 42}, "chat": {"id": 42}, "text": text}}  # noqa: E731

    await bot.handle_update(msg("/proattivo", 1))
    assert "Attivi" in st.tg.out[-1][0] and "2 su 6" in st.tg.out[-1][0]
    await bot.handle_update(cb("pp", 2))
    assert await st.store.get_setting("proactive_paused") == "1" and "In pausa" in st.tg.out[-1][0]
    await bot.handle_update(cb("pp", 3))
    assert await st.store.get_setting("proactive_paused") == "0"

    await bot.handle_update(msg("/impostazioni", 4))  # il nuovo tipo di notifica non deve rompere il comando
    assert "Suggerimenti" in str(st.tg.out[-1][1])

    brain, _ = make()
    st.brain = brain
    brain.knowledge = Knowledge(Settings(), brain, st.store, wiki({"Fotosintesi": "Le piante trasformano la luce in energia."}))
    await bot.handle_update(msg("/impara fotosintesi", 5))
    assert "Imparato" in st.tg.out[-1][0] and "Fotosintesi" in st.tg.out[-1][0]


@pytest.mark.asyncio
async def test_notifier_telegram_messages_are_titled_and_reminders_keep_buttons():
    class TG:
        enabled = True
        s = SimpleNamespace(telegram_owner_id=1)

        def __init__(self):
            self.sent, self.buttons = [], []

        async def send(self, chat, text, markup=None):
            self.sent.append(text)

        async def notify_owner(self, text):
            self.sent.append(text)

        async def send_buttons(self, chat, text, buttons):
            self.buttons.append(text)

    tg = TG()
    n = Notifier(Settings(timezone="Europe/Rome"), MemoryStore(), tg)
    await n.set_prefs({"quiet": {"enabled": False}})
    await n.push("proactive", "Tra 30 minuti: Riunione", "Alle 10:30.", telegram=True)
    await n.push("reminder", "⏰ Promemoria, signore", "chiamare Luca")
    assert tg.sent == ["**💡 Tra 30 minuti: Riunione**\nAlle 10:30."]
    assert tg.buttons and tg.buttons[0].startswith("⏰ Promemoria") and "**" not in tg.buttons[0]
