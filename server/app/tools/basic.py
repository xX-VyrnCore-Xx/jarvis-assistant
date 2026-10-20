import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Settings
from ..memory import Store
from . import ToolRegistry

_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def register_basic_tools(reg: ToolRegistry, settings: Settings, store: Store) -> None:
    async def get_datetime() -> str:
        now = datetime.now(ZoneInfo(settings.timezone))
        return f"{_GIORNI[now.weekday()]} {now:%d/%m/%Y %H:%M} ({settings.timezone})"

    async def remember(content: str) -> str:
        await store.add_memory(content)
        return "Memorizzato."

    async def recall(query: str) -> str:
        hits = await store.search_memories(query, settings.memory_hits)
        return "\n".join(f"- {h}" for h in hits) or "Nessun ricordo trovato."

    async def web_search(query: str) -> str:
        def _search() -> list[dict]:
            from ddgs import DDGS

            return DDGS().text(query, max_results=5, region="it-it")

        results = await asyncio.to_thread(_search)
        return "\n\n".join(f"{r['title']}\n{r['href']}\n{r['body']}" for r in results) or "Nessun risultato."

    reg.register("get_datetime", "Data e ora correnti.", {"type": "object", "properties": {}}, get_datetime)
    reg.register(
        "remember",
        "Salva un fatto duraturo sull'utente (preferenze, persone, dati personali) nella memoria a lungo termine.",
        {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]},
        remember,
    )
    reg.register(
        "recall",
        "Cerca nella memoria a lungo termine informazioni rilevanti.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        recall,
    )
    reg.register(
        "web_search",
        "Cerca sul web informazioni aggiornate (notizie, meteo, fatti recenti).",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        web_search,
    )
