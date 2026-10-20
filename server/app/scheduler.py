import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .memory import Store
from .telegram import Telegram

log = logging.getLogger("jarvis.scheduler")


async def deliver_due_reminders(store: Store, tg: Telegram, now: datetime) -> int:
    sent = 0
    for r in await store.due_reminders(now):
        await tg.notify_owner(f"⏰ Promemoria, signore: {r['text']}")
        await store.mark_reminder_done(r["id"])  # solo dopo l'invio riuscito: al massimo duplica, non perde
        sent += 1
    return sent


async def reminder_loop(settings: Settings, store: Store, tg: Telegram) -> None:
    tz = ZoneInfo(settings.timezone)
    while True:
        try:
            await deliver_due_reminders(store, tg, datetime.now(tz))
        except Exception:
            log.exception("errore nel ciclo promemoria")
        await asyncio.sleep(settings.reminder_poll_s)
