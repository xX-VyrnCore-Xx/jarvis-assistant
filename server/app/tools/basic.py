import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import Settings
from ..memory import Store
from . import UNTRUSTED, ToolRegistry

_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def parse_due(when: str, tz: ZoneInfo) -> datetime:
    due = datetime.fromisoformat(when)
    return due.replace(tzinfo=tz) if due.tzinfo is None else due.astimezone(tz)


def register_basic_tools(reg: ToolRegistry, settings: Settings, store: Store, budget=None) -> None:
    """`budget`: coroutine che restituisce il testo sui token disponibili (se FreeLLMAPI è nel container)."""
    async def get_datetime() -> str:
        now = datetime.now(ZoneInfo(settings.timezone))
        return f"{_GIORNI[now.weekday()]} {now:%d/%m/%Y %H:%M} ({settings.timezone}), ISO {now:%Y-%m-%dT%H:%M:%S}, settimana {now.isocalendar().week}"

    async def date_info(date: str, add_days: int = 0) -> str:
        """Giorno della settimana e calcoli con le date: il modello sbaglia spesso a farli a mente."""
        tz = ZoneInfo(settings.timezone)
        base = parse_due(date, tz) if date else datetime.now(tz)
        target = base + timedelta(days=add_days)
        delta = (target.date() - datetime.now(tz).date()).days
        when = "oggi" if delta == 0 else f"tra {delta} giorni" if delta > 0 else f"{-delta} giorni fa"
        return f"{_GIORNI[target.weekday()]} {target:%d/%m/%Y} ({when}), settimana {target.isocalendar().week}"

    async def remind_in(minutes: int, text: str) -> str:
        tz = ZoneInfo(settings.timezone)
        due = datetime.now(tz) + timedelta(minutes=max(1, minutes))
        await store.add_reminder(text, due)
        return f"Promemoria fissato per {due:%d/%m/%Y %H:%M}."

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
        body = "\n\n".join(f"{r['title']}\n{r['href']}\n{r['body']}" for r in results)
        return UNTRUSTED + body if body else "Nessun risultato."

    async def add_reminder(text: str, when: str) -> str:
        tz = ZoneInfo(settings.timezone)
        due = parse_due(when, tz)
        if due <= datetime.now(tz):
            return "Errore: la data del promemoria è nel passato. Usa get_datetime e riprova."
        await store.add_reminder(text, due)
        return f"Promemoria fissato per {due:%d/%m/%Y %H:%M}."

    async def list_reminders() -> str:
        rows = await store.list_reminders()
        return "\n".join(f"- [id {r['id']}] {r['due_at']}: {r['text']}" for r in rows) or "Nessun promemoria attivo."

    async def delete_reminder(reminder_id: int) -> str:
        await store.delete_reminder(reminder_id)
        return "Promemoria eliminato."

    async def list_memories() -> str:
        rows = await store.list_memories(30)
        return "\n".join(f"- [id {m['id']}] {m['content']}" for m in rows) or "La memoria è vuota."

    async def forget(memory_id: int) -> str:
        await store.delete_memory(memory_id)
        return "Dimenticato."

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
    reg.register("date_info", "Giorno della settimana e distanza da oggi di una data, con eventuale somma di giorni. Usalo per ogni calcolo con le date.",
                 {"type": "object", "properties": {"date": {"type": "string", "description": "ISO 8601; vuoto = oggi"}, "add_days": {"type": "integer"}}, "required": []}, date_info)
    reg.register("remind_in", "Promemoria tra N minuti da adesso (es. 'ricordami tra 20 minuti').",
                 {"type": "object", "properties": {"minutes": {"type": "integer"}, "text": {"type": "string"}}, "required": ["minutes", "text"]}, remind_in)
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731
    reg.register("delete_reminder", "Elimina un promemoria dato il suo id (vedi list_reminders).",
                 obj({"reminder_id": {"type": "integer"}}, ["reminder_id"]), delete_reminder)
    reg.register("list_memories", "Elenca i ricordi salvati con il loro id.", obj({}), list_memories)
    reg.register("forget", "Cancella un ricordo dato il suo id (vedi list_memories). Usalo solo se l'utente lo chiede.",
                 obj({"memory_id": {"type": "integer"}}, ["memory_id"]), forget)
    if budget is not None:
        async def get_token_budget() -> str:
            return await budget()

        reg.register(
            "get_token_budget",
            "Quanti token gratuiti restano questo mese, in totale e per provider (da FreeLLMAPI).",
            {"type": "object", "properties": {}},
            get_token_budget,
        )
