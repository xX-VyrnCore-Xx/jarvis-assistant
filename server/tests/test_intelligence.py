import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.learn import Learner
from app.memory import MemoryStore
from app.proactive import Proactive
from tests.test_brain import FakeLLM, make

TZ = ZoneInfo("Europe/Rome")


class Notes:
    def __init__(self):
        self.sent = []

    async def push(self, kind, title, body="", telegram=None, meta=None):
        self.sent.append((kind, title, body, telegram))
        return {"id": len(self.sent)}


class FakeGoogle:
    enabled = True

    def __init__(self, events=(), mails=()):
        self.events, self.mails = list(events), list(mails)

    async def request(self, method, url, **kw):
        class R:
            def __init__(s, data):
                s.data = data

            def json(s):
                return s.data

        if "/events" in url:
            lo, hi = datetime.fromisoformat(kw["params"]["timeMin"]), datetime.fromisoformat(kw["params"]["timeMax"])
            return R({"items": [e for e in self.events if lo <= datetime.fromisoformat(e["start"]["dateTime"]) < hi]})
        if url.endswith("/messages"):
            return R({"messages": [{"id": m["id"]} for m in self.mails]})
        m = next(m for m in self.mails if url.endswith(m["id"]))
        return R({"payload": {"headers": [{"name": "From", "value": m["from"]}, {"name": "Subject", "value": m["subject"]}]}})


@pytest.mark.asyncio
async def test_learner_saves_facts_and_tasks_once_and_unmasks():
    llm = FakeLLM(json.dumps({"facts": [{"text": "Il dentista di Matteo è il dottor Bianchi, studio in via Roma.", "importance": 0.8}, {"text": "ok", "importance": 1}],
                              "tasks": [{"text": "Prenotare la visita dal dentista"}]}))
    brain, _ = make(llm)
    store = MemoryStore()
    s = Settings(jarvis_api_token="t")
    lr = Learner(s, llm, brain, store)
    assert not lr.eligible("ciao come va") and lr.eligible("Il mio dentista è il dottor Bianchi, devo prenotare la visita")
    r = await lr.observe("Il mio dentista è il dottor Bianchi, devo prenotare la visita", "Annotato.")
    assert r == {"facts": 1, "tasks": 1}
    assert (await store.list_tasks(None, False))[0]["text"].startswith("Prenotare")
    hits = await brain.search("chi è il mio dottore dentista", k=3)
    assert hits and hits[0]["source"] == "memory" and "appreso" in hits[0]["tags"]
    again = await lr.observe("Il mio dentista è il dottor Bianchi, devo prenotare la visita", "Annotato.")
    assert again == {"facts": 0, "tasks": 0}  # già noto: né fatti né attività doppie


@pytest.mark.asyncio
async def test_learner_respects_daily_cap_and_flag():
    llm = FakeLLM('{"facts": [], "tasks": []}')
    brain, _ = make(llm)
    lr = Learner(Settings(jarvis_api_token="t", learn_max_per_day=1), llm, brain, MemoryStore())
    await lr.observe("Domani ho una riunione importante con Luca", "ok")
    n = len(llm.seen)
    await lr.observe("Domani ho una riunione importante con Anna", "ok")
    assert len(llm.seen) == n
    assert not Learner(Settings(jarvis_api_token="t", learn_enabled=False), llm, brain, MemoryStore()).eligible("Domani ho una riunione importante")


@pytest.mark.asyncio
async def test_search_period_filter_deep_search_and_dossier():
    llm = FakeLLM(json.dumps({"queries": ["dottore studio medico", "visita medica"], "title": "t", "summary": "s", "tags": [], "entities": [{"kind": "persona", "name": "Bianchi"}], "importance": 0.7}))
    brain, store = make(llm)
    a = await brain.ingest("Il dottor Bianchi è il mio dentista, studio in via Roma", title="Dentista")
    await brain.ingest("Ricetta della carbonara con guanciale", title="Cucina")
    await brain.enrich(await store.get_doc(a["doc_id"]))
    assert await brain.search("dentista", k=3, since="2999-01-01") == []
    assert await brain.search("dentista", k=3, until="2999-01-01")
    queries, res = await brain.deep_search("a chi mi rivolgo per i denti?", k=3)
    assert len(queries) == 3 and res and res[0]["doc_id"] == a["doc_id"]
    d = await brain.dossier("Bianchi")
    assert d["entities"] == [("persona", "Bianchi")] and [x.id for x in d["docs"]] == [a["doc_id"]]
    assert (await brain.dossier("Zorro"))["docs"] == []


@pytest.mark.asyncio
async def test_profile_compiled_cached_and_hidden_from_search():
    llm = FakeLLM("- Matteo vive a Roma\n- Ha un dentista, il dottor Bianchi, e lavora a un'app di nome JARVIS")
    brain, store = make(llm)
    assert await brain.refresh_profile() == "pochi ricordi"
    for t in ("Matteo vive a Roma", "Il dentista è il dottor Bianchi", "Sta costruendo l'assistente JARVIS"):
        await brain.ingest(t, source="memory", importance=0.8)
    assert await brain.refresh_profile() == "aggiornato"
    assert "Roma" in await brain.profile_text()
    assert await brain.refresh_profile() == "aggiornato" and len(llm.seen) == 1  # entro 7 giorni non si ricompila
    assert not [r for r in await brain.search("Matteo vive a Roma", k=5) if r["source"] == "profile"]
    assert not (await store.get_doc((await brain.profile_doc()).id)).enriched is False  # il profilo non si arricchisce con altre chiamate


@pytest.mark.asyncio
async def test_proactive_heads_up_emails_evening_and_cap():
    now = datetime(2026, 10, 21, 10, 0, tzinfo=TZ)
    soon = {"id": "e1", "summary": "Riunione con Luca", "location": "Ufficio", "start": {"dateTime": (now + timedelta(minutes=30)).isoformat()}}
    far = {"id": "e2", "summary": "Cena", "start": {"dateTime": (now + timedelta(days=1, hours=10)).isoformat()}}
    g = FakeGoogle([soon], [{"id": "m1", "from": "Mario <m@x.it>", "subject": "Preventivo"}, {"id": "m2", "from": "Anna <a@x.it>", "subject": "Ciao"}])
    notes, store = Notes(), MemoryStore()
    s = Settings(jarvis_api_token="t", timezone="Europe/Rome", proactive_max_per_day=1)
    p = Proactive(s, store, notes, g)
    assert set(await p.tick(now)) == {"heads_up", "emails"}
    ev = next(n for n in notes.sent if "Riunione" in n[1])
    assert ev[1].startswith("Tra 30 minuti") and ev[3] is True and "Ufficio" in ev[2]
    assert any("2 email nuove" in n[1] for n in notes.sent)
    p._last.clear()
    assert await p.tick(now + timedelta(minutes=5)) == []  # stesso evento e stesse email: nessun doppione (anche dopo il riavvio: lo stato è nel database)
    p2 = Proactive(s, store, notes, g)
    p2._last.clear()
    assert await p2.tick(now + timedelta(minutes=6)) == []

    # tetto giornaliero: il riepilogo serale non passa dopo che la mail ha già usato la quota, l'evento urgente sì
    await store.add_task("Chiamare il commercialista", "attività")
    evening = now.replace(hour=21, minute=5)
    p3 = Proactive(s, store, notes, FakeGoogle([far]))
    assert await p3.tick(evening) == []
    notes2 = Notes()
    p4 = Proactive(Settings(jarvis_api_token="t", timezone="Europe/Rome"), MemoryStore(), notes2, FakeGoogle([far]))
    await p4.store.add_task("Chiamare il commercialista", "attività")
    assert await p4.tick(evening) == ["evening"]
    assert "Cena" in notes2.sent[0][2] and "commercialista" in notes2.sent[0][2]
    assert await p4.tick(evening + timedelta(minutes=5)) == []  # una volta sola per sera


@pytest.mark.asyncio
async def test_proactive_quiet_when_off_or_asleep():
    notes = Notes()
    g = FakeGoogle([{"id": "e1", "summary": "X", "start": {"dateTime": "2026-10-21T03:30:00+02:00"}}])
    assert await Proactive(Settings(jarvis_api_token="t", proactive_enabled=False), MemoryStore(), notes, g).tick() == []
    night = datetime(2026, 10, 21, 3, 0, tzinfo=TZ)
    assert await Proactive(Settings(jarvis_api_token="t", timezone="Europe/Rome"), MemoryStore(), notes, g).tick(night) == []
    assert notes.sent == []
