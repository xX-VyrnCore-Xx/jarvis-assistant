import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.brain.mirror import BrainMirror
from app.config import Settings
from app.learn import Learner
from app.memory import MemoryStore
from app.reminders import ReminderService
from tests.test_brain import FakeLLM, make

TZ = ZoneInfo("Europe/Rome")


def soon(m=60):
    return datetime.now(TZ) + timedelta(minutes=m)


async def setup():
    brain, bstore = make()
    store = MemoryStore()
    svc = ReminderService(Settings(jarvis_api_token="t", timezone="Europe/Rome"), store)
    svc.mirror = BrainMirror(brain, store)
    return brain, bstore, store, svc


@pytest.mark.asyncio
async def test_reminder_lives_in_the_brain_and_leaves_with_it_including_learned_copies():
    brain, bstore, store, svc = await setup()
    r = await svc.create("Chiamare il dentista Bianchi", soon())
    docs = await bstore.list_docs(10, 0, "reminder")
    assert len(docs) == 1 and docs[0].uri == f"reminder:{r['id']}"
    # l'apprendimento automatico aveva salvato lo stesso impegno come «fatto»: deve andarsene col promemoria
    await brain.ingest("Chiamare il dentista Bianchi", title="Chiamare il dentista", source="memory", tags=["appreso"])
    await brain.ingest("Matteo preferisce il caffè senza zucchero", title="Caffè", source="memory", tags=["appreso"])
    assert await svc.delete(r["id"]) is True
    assert await bstore.list_docs(10, 0, "reminder") == []
    left = [d.title for d in await bstore.list_docs(10, 0, "memory")]
    assert left == ["Caffè"]  # il fatto duraturo resta


@pytest.mark.asyncio
async def test_fired_snoozed_and_missing_reminders_are_reconciled():
    brain, bstore, store, svc = await setup()
    a = await svc.create("Pagare la bolletta", soon())
    b = await svc.create("Riunione con Anna", soon())
    await svc.snooze(b["id"], 120)
    await store.mark_reminder_done(a["id"])  # scattato senza passare dal servizio (es. dopo un riavvio)
    res = await svc.mirror.sync_all()
    assert res["reminders"] == 1
    assert [d.uri for d in await bstore.list_docs(10, 0, "reminder")] == [f"reminder:{b['id']}"]
    for d in await bstore.list_docs(10, 0, "reminder"):
        await brain.forget(d.id)  # divergenza: manca un promemoria attivo
    assert (await svc.mirror.sync_all())["added"] == 1


@pytest.mark.asyncio
async def test_forgotten_memories_and_done_tasks_leave_the_brain():
    brain, bstore, store, svc = await setup()
    await store.add_memory("La password del wifi è scritta sul frigo")
    mem = (await store.list_memories(5))[0]
    await brain.ingest(mem["content"], title="wifi", source="memory", uri=f"memory:{brain.vault.blind(mem['content'])}")
    await brain.ingest("Il dentista è il dottor Bianchi", title="dentista", source="memory", tags=["appreso"])  # senza URI: conoscenza autonoma
    tid = await store.add_task("Comprare il latte", "spesa")
    m = BrainMirror(brain, store)
    assert (await m.sync_all())["added"] == 1 and len(await bstore.list_docs(10, 0, "task")) == 1
    await store.delete_memory(mem["id"])
    await store.set_task_done(tid, True)
    res = await m.sync_all()
    assert res["memories"] == 1 and res["tasks"] == 1 and await bstore.list_docs(10, 0, "task") == []
    assert [d.title for d in await bstore.list_docs(10, 0, "memory")] == ["dentista"]


@pytest.mark.asyncio
async def test_learner_does_not_learn_from_a_reminder_request():
    llm = FakeLLM(json.dumps({"facts": [{"text": "L'utente deve chiamare il dentista domani alle 9.", "importance": 0.8}], "tasks": []}))
    brain, bstore = make(llm)
    lr = Learner(Settings(jarvis_api_token="t"), llm, brain, MemoryStore())
    lr.schedule("Ricordami domani alle 9 di chiamare il dentista, devo prenotare", "Promemoria fissato per 24/10/2026 09:00 (sul Calendario).")
    assert not lr._tasks and llm.seen == []


@pytest.mark.asyncio
async def test_duplicate_learned_facts_are_merged_keeping_the_important_one():
    brain, bstore, store, svc = await setup()
    await brain.ingest("L'utente abita a Torino in via Roma", title="a", source="memory", tags=["appreso"], importance=0.6)
    await brain.ingest("L'utente abita a Torino, in via Roma 12", title="b", source="memory", tags=["appreso"], importance=0.8)
    await brain.ingest("L'utente tifa per la Juventus", title="c", source="memory", tags=["appreso"], importance=0.6)
    await brain.ingest("Appunto manuale: abita a Torino in via Roma", title="d", source="memory", importance=0.5)  # non appreso: non si tocca
    assert await BrainMirror(brain, store).dedupe_facts() == 1
    assert sorted(d.title for d in await bstore.list_docs(10, 0, "memory")) == ["b", "c", "d"]
