import asyncio
import json

import httpx
import pytest

from app.agent import Agent
from app.config import Settings
from app.llm import LLMClient
from app.memory import MemoryStore
from app.tools import ToolRegistry
from app.tools.select import CORE, GROUPS, ToolSelector
from app.usage import UsageTracker

SEL = ToolSelector()
NAMES = sorted(CORE | {"list_reminders", "delete_reminder", "reminder_snooze", "get_weather", "web_news", "read_webpage", "wikipedia", "convert_currency", "crypto_price", "unit_convert", "world_time",
                       "task_add", "task_list", "task_done", "task_delete", "list_memories", "forget", "brain_add_note", "brain_forget", "brain_pin", "brain_stats", "brain_learn", "list_skills", "use_skill",
                       "skill_save", "skill_delete", "send_notification", "get_token_budget", "calendar_list_events", "calendar_create_event", "calendar_update_event", "calendar_delete_event",
                       "calendar_find_free_time", "gmail_search", "gmail_read", "gmail_create_draft", "drive_search", "drive_read", "pc_open_app", "pc_media", "pc_power", "pc_system_info", "tool_nuovo"})
SPECS = [{"type": "function", "function": {"name": n, "description": "d" * 300, "parameters": {"type": "object", "properties": {}}}} for n in NAMES]


def names_for(text, prior=()):
    return {s["function"]["name"] for s in SEL.specs(SPECS, SEL.groups_for(text, list(prior)))}


@pytest.mark.parametrize("text,group", [
    ("che meteo fa domani a Roma?", "web"), ("metti una riunione domani alle 15 con Luca", "calendario"), ("ho email non lette importanti?", "email"),
    ("aggiungi il latte alla spesa", "liste"), ("apri spotify e alza il volume sul pc", "pc"), ("quanto sono 50 dollari in euro?", "utilita"),
    ("cosa ricordi di me? dimentica quel ricordo", "memoria"), ("salva questa nota nel cervello", "cervello"), ("quali competenze hai?", "competenze"),
    ("quanti token mi restano?", "token"), ("elimina il promemoria della palestra", "promemoria"), ("cerca il documento su drive", "drive"),
])
def test_groups_are_chosen_from_the_request(text, group):
    assert group in SEL.groups_for(text), (text, SEL.groups_for(text))


def test_small_talk_gets_only_the_core_plus_the_escape_hatch_and_prompt_shrinks_a_lot():
    got = names_for("ciao, come stai oggi?")
    assert got == CORE | {"need_tools", "tool_nuovo"}  # i tool non classificati restano sempre disponibili: nessuno si perde per un errore di elenco
    full, small = len(json.dumps(SPECS)), len(json.dumps(SEL.specs(SPECS, set())))
    assert small < 0.4 * full
    assert "calendar_create_event" in names_for("fissa una riunione domani") and "gmail_search" not in names_for("fissa una riunione domani")
    assert "get_weather" in names_for("e dopodomani?", prior=["che meteo fa domani a Roma?"])  # i seguiti mantengono il contesto
    assert "need_tools" not in {s["function"]["name"] for s in SEL.specs(SPECS, set(GROUPS))}  # con tutto attivo la scorciatoia non serve


@pytest.mark.asyncio
async def test_agent_can_ask_for_more_tools_in_the_same_turn():
    calls = []

    class LLM:
        async def chat(self, messages, tools=None, model=None, kind="chat"):
            calls.append({s["function"]["name"] for s in (tools or [])})
            if len(calls) == 1:
                return {"content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "need_tools", "arguments": json.dumps({"group": "web"})}}]}
            if len(calls) == 2:
                return {"content": None, "tool_calls": [{"id": "2", "type": "function", "function": {"name": "get_weather", "arguments": json.dumps({"city": "Roma"})}}]}
            return {"content": "Sole a Roma."}

    reg = ToolRegistry()

    async def noop(**kw):
        return "ok"

    for n in ("calculate", "get_weather", "web_news"):
        reg.register(n, "d", {"type": "object", "properties": {"city": {"type": "string"}}}, noop)
    store = MemoryStore()
    agent = Agent(Settings(jarvis_api_token="t"), LLM(), store, reg)
    out = await agent.reply("raccontami una barzelletta lunga sul mare", "s")
    assert out == "Sole a Roma." and "get_weather" not in calls[0] and "need_tools" in calls[0] and "get_weather" in calls[1]


def test_best_model_prefers_the_fast_recent_one_and_respects_tools_and_failures():
    u = UsageTracker()
    u.record("chat", "lento", 100, 10, 9000, True)
    u.record("chat", "veloce", 100, 10, 900, True, tools=True)
    u.record("chat", "medio", 100, 10, 2500, True, tools=True)
    assert u.best_model() == "veloce" and u.best_model(tools=True) == "veloce"
    assert u.best_model(exclude=("veloce",)) == "medio" and u.best_model(tools=True, exclude=("veloce", "medio")) is None
    u.record("chat", "veloce", 0, 0, 100, False)  # errore recente: per qualche minuto non è più un ripiego
    assert u.best_model() == "medio" and u.best_model("auto") != "auto"


@pytest.mark.asyncio
async def test_llm_falls_back_to_the_fastest_recent_model_when_the_router_hangs():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append(body["model"])
        if len(seen) == 1:
            raise httpx.ReadTimeout("il provider non risponde", request=req)
        return httpx.Response(200, json={"model": body["model"], "choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}})

    s = Settings(jarvis_api_token="t", freellm_base_url="http://x/v1", freellm_api_key="k")
    llm = LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    llm.usage.record("chat", "nvidia/veloce", 100, 10, 1200, True)
    msg = await llm.chat([{"role": "user", "content": "ciao"}])
    assert msg["content"] == "ok" and seen == ["auto:fast", "nvidia/veloce"]
    assert llm.usage.today()["errors"] == 1 and llm.usage.today()["requests"] == 3  # il tentativo fallito è registrato con la sua durata

    # con un modello scelto dall'utente non si cambia: si riprova con lo stesso
    seen.clear()
    llm2 = LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    llm2.usage.record("chat", "nvidia/veloce", 100, 10, 1200, True)
    await llm2.chat([{"role": "user", "content": "ciao"}], model="scelto/da-me")
    assert seen == ["scelto/da-me", "scelto/da-me"]


@pytest.mark.asyncio
async def test_prepare_reads_everything_in_parallel():
    marks = []

    class Slow(MemoryStore):
        async def recent_messages(self, session_id, limit):
            marks.append("h0")
            await asyncio.sleep(0.2)
            marks.append("h1")
            return []

    class Brain:
        enabled = True

        async def context(self, q):
            marks.append("b0")
            await asyncio.sleep(0.2)
            marks.append("b1")
            return ""

        async def profile_text(self):
            return ""

    store = Slow()
    agent = Agent(Settings(jarvis_api_token="t"), None, store, ToolRegistry(), Brain())
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    await agent._prepare("dimmi qualcosa di interessante sul mare", "s", False)
    assert loop.time() - t0 < 0.35 and marks[:2] == ["h0", "b0"]  # le due attese si sovrappongono (prima si sommavano)
