import asyncio

import pytest

from app.livesync import Live, LiveStore
from app.memory import MemoryStore


class Spy:
    def __init__(self):
        self.scopes = []

    def sync(self, scope, origin=""):
        self.scopes.append(scope)


@pytest.mark.asyncio
async def test_every_write_announces_its_scope_and_reads_do_not():
    seen = []
    st = LiveStore(MemoryStore(), seen.append)
    tid = await st.add_task("latte", "spesa")
    await st.set_task_done(tid, True)
    await st.add_memory("x")
    await st.list_tasks(None, True)
    await st.delete_task(tid)
    assert seen == ["tasks", "tasks", "memories", "tasks"]
    assert await st.list_memories(5) and st.tasks == []  # il resto passa invariato


@pytest.mark.asyncio
async def test_changes_are_batched_into_one_brain_alignment():
    class Mirror:
        calls = 0

        async def sync_all(self):
            Mirror.calls += 1

    spy = Spy()
    live = Live(spy, Mirror(), delay=0.01)
    for _ in range(3):
        live.changed("tasks")
    live.changed("reminders")
    await asyncio.sleep(0.1)
    assert spy.scopes.count("tasks") == 3 and Mirror.calls == 1 and spy.scopes[-1] == "brain"
