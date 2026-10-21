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


def register_basic_tools(reg: ToolRegistry, settings: Settings, store: Store, budget=None, brain=None, reminders=None) -> None:
    """`budget`: coroutine che restituisce il testo sui token disponibili (se FreeLLMAPI è nel container).
    `reminders`: ReminderService (promemoria collegati al Calendario Google)."""
    if reminders is None:
        from ..reminders import ReminderService

        reminders = ReminderService(settings, store)

    def where(r: dict) -> str:
        return "e aggiunto al Calendario Google." if r["calendar"] else ("(solo nell'app: il Calendario non ha risposto, lo collego appena possibile)." if reminders.linked else "(solo nell'app: Google non è collegato).")

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
        r = await reminders.create(text, due)
        return f"Promemoria fissato per {due:%d/%m/%Y %H:%M} {where(r)}"

    async def remember(content: str) -> str:
        await store.add_memory(content)
        if brain is not None and brain.enabled:  # entra anche nel secondo cervello (ricerca per significato)
            try:
                await brain.ingest(content, title=content[:60], source="memory", uri=f"memory:{brain.vault.blind(content)}", importance=0.75)
            except Exception:
                pass
        return "Memorizzato."

    async def recall(query: str) -> str:
        if brain is not None and brain.enabled:
            from ..brain.tools import format_results

            res = await brain.search(query, k=5)
            if res:
                return format_results(res)
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
        r = await reminders.create(text, due)
        return f"Promemoria fissato per {due:%d/%m/%Y %H:%M} {where(r)}"

    async def list_reminders() -> str:
        rows = await store.list_reminders()
        return "\n".join(f"- [id {r['id']}] {r['due_at']}: {r['text']}" + (" 📅" if r.get("event_id") else "") for r in rows) or "Nessun promemoria attivo."

    async def delete_reminder(reminder_id: int) -> str:
        await reminders.delete(reminder_id)
        return "Promemoria eliminato (anche dal Calendario)." if reminders.linked else "Promemoria eliminato."

    async def reminder_snooze(reminder_id: int, minutes: int = 10) -> str:
        """Rimanda un promemoria di N minuti da adesso."""
        due = await reminders.snooze(reminder_id, minutes)
        if due is None:
            return "Errore: promemoria non trovato (controlla l'id con list_reminders)."
        return f"Promemoria rimandato a {due:%d/%m/%Y %H:%M}."

    async def task_add(text: str, list_name: str = "attività") -> str:
        tid = await store.add_task(text.strip(), list_name.strip().lower() or "attività")
        return f"Aggiunto alla lista «{list_name}» (id {tid})."

    async def task_list(list_name: str = "", include_done: bool = False) -> str:
        rows = await store.list_tasks(list_name.strip().lower() or None, include_done)
        if not rows:
            return "Nessuna voce."
        out: dict[str, list[str]] = {}
        for t in rows:
            out.setdefault(t["list"], []).append(f"- [id {t['id']}] {'✔ ' if t['done'] else ''}{t['text']}")
        return "\n".join(f"{name}:\n" + "\n".join(items) for name, items in out.items())

    async def task_done(task_id: int, done: bool = True) -> str:
        await store.set_task_done(task_id, done)
        return "Completata." if done else "Riaperta."

    async def task_delete(task_id: int) -> str:
        await store.delete_task(task_id)
        return "Eliminata."

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
        cache_ttl=600,
    )
    reg.register(
        "add_reminder",
        "Crea un promemoria: lo aggiunge anche al Calendario Google e avvisa l'utente all'ora indicata (sempre questo per «ricordami», «promemoria», «avvisami»). Calcola 'when' partendo da get_datetime.",
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
    reg.register("reminder_snooze", "Rimanda un promemoria di N minuti da adesso (id da list_reminders).",
                 obj({"reminder_id": {"type": "integer"}, "minutes": {"type": "integer"}}, ["reminder_id"]), reminder_snooze)
    reg.register("task_add", "Aggiunge una voce a una lista (attività da fare, spesa, idee...). 'list_name' di default 'attività'; usa 'spesa' per la spesa.",
                 obj({"text": {"type": "string"}, "list_name": {"type": "string"}}, ["text"]), task_add)
    reg.register("task_list", "Mostra le voci delle liste (con id). Senza 'list_name' le mostra tutte; 'include_done' include le completate.",
                 obj({"list_name": {"type": "string"}, "include_done": {"type": "boolean"}}), task_list)
    reg.register("task_done", "Segna una voce come completata (o riaperta con done=false). Id da task_list.",
                 obj({"task_id": {"type": "integer"}, "done": {"type": "boolean"}}, ["task_id"]), task_done)
    reg.register("task_delete", "Elimina una voce dalle liste (id da task_list).", obj({"task_id": {"type": "integer"}}, ["task_id"]), task_delete)
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
