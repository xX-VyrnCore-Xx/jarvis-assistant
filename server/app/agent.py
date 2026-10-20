from .config import Settings
from .llm import LLMClient
from .memory import Store
from .tools import ToolRegistry

SYSTEM_PROMPT = """Sei JARVIS, l'assistente personale di {owner}, ispirato all'AI di Iron Man.
Parli sempre in italiano, con tono elegante, sobrio e con una punta di ironia sottile. Ti rivolgi all'utente come "{owner}".
Sii conciso: vai al punto, niente preamboli. Non inventare mai dati: se non sai, usa i tool o dillo.
Usa `remember` quando l'utente condivide qualcosa di duraturo su di sé, `recall` per ritrovarlo,
`web_search` per informazioni aggiornate, `get_datetime` per data e ora.
Prima di azioni irreversibili (invio email, eliminazioni) chiedi conferma esplicita."""


class Agent:
    def __init__(self, settings: Settings, llm: LLMClient, store: Store, tools: ToolRegistry):
        self.s, self.llm, self.store, self.tools = settings, llm, store, tools

    async def reply(self, user_text: str, session_id: str) -> str:
        history = await self.store.recent_messages(session_id, self.s.history_messages)
        memories = await self.store.search_memories(user_text, self.s.memory_hits)

        system = SYSTEM_PROMPT.format(owner=self.s.owner_name)
        if memories:
            system += "\n\nRicordi rilevanti:\n" + "\n".join(f"- {m}" for m in memories)

        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user_text}]
        answer = ""
        for _ in range(self.s.max_tool_rounds):
            msg = await self.llm.chat(messages, self.tools.specs)
            calls = msg.get("tool_calls") or []
            if not calls:
                answer = msg.get("content") or ""
                break
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
            for c in calls:
                result = await self.tools.call(c["function"]["name"], c["function"].get("arguments", ""))
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
        else:
            answer = "Ho superato il limite di operazioni consecutive, signore. Può riformulare la richiesta?"

        await self.store.add_message(session_id, "user", user_text)
        await self.store.add_message(session_id, "assistant", answer)
        return answer
