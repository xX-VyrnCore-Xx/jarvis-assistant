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

    async def add_reminder(text: str, when: str) -> str:
        tz = ZoneInfo(settings.timezone)
        due = datetime.fromisoformat(when)
        due = due.replace(tzinfo=tz) if due.tzinfo is None else due.astimezone(tz)
        if due <= datetime.now(tz):
            return "Errore: la data del promemoria è nel passato. Usa get_datetime e riprova."
        await store.add_reminder(text, due)
        return f"Promemoria fissato per {due:%d/%m/%Y %H:%M}."

    async def list_reminders() -> str:
        rows = await store.list_reminders()
        return "\n".join(f"- {r['due_at']}: {r['text']}" for r in rows) or "Nessun promemoria attivo."

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
    reg.register(
        "add_reminder",
        "Crea un promemoria: l'utente riceverà un messaggio all'ora indicata. Calcola 'when' partendo da get_datetime.",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Cosa ricordare"},
                "when": {"type": "string", "description": "Data/ora locale ISO 8601, es. 2026-10-21T09:30:00"},
            },
            "required": ["text", "when"],
        },
        add_reminder,
    )
    reg.register(
        "list_reminders", "Elenca i promemoria attivi.", {"type": "object", "properties": {}}, list_reminders
    )
