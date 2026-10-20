import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .budget import fmt_tokens
from .config import Settings
from .memory import Store
from .notify import Notifier

log = logging.getLogger("jarvis.scheduler")
PRUNE_EVERY_S = 24 * 3600
BUDGET_EVERY_S = 30 * 60


async def deliver_due_reminders(store: Store, notifier: Notifier, now: datetime) -> int:
    sent = 0
    for r in await store.due_reminders(now):
        await notifier.push("reminder", "⏰ Promemoria, signore", r["text"], telegram=True)
        await store.mark_reminder_done(r["id"])  # solo dopo l'invio riuscito: al massimo duplica, non perde
        sent += 1
    return sent


async def check_budget(settings: Settings, budget, notifier: Notifier, alerted: bool) -> bool:
    """Avvisa una sola volta quando i token residui scendono sotto soglia; si riarma quando risalgono."""
    if not settings.low_tokens_alert or not budget.enabled:
        return alerted
    remaining = (await budget.get())["remaining_tokens"]
    low = remaining < settings.low_tokens_alert
    if low and not alerted:
        await notifier.push("alert", "Token in esaurimento", f"Restano circa {fmt_tokens(remaining)} token gratuiti questo mese.",
                            telegram=True)
    return low


async def background_loop(settings: Settings, store: Store, notifier: Notifier, budget, backup=None) -> None:
    tz = ZoneInfo(settings.timezone)
    last_prune = 0.0
    last_budget = 0.0
    alerted = False
    started = time.monotonic()
    encrypted = not hasattr(store, "encrypt_existing")
    last_backup = None
    while True:
        try:
            await deliver_due_reminders(store, notifier, datetime.now(tz))
        except Exception:
            log.exception("errore nel ciclo promemoria")
        now = time.monotonic()
        if now - last_budget >= BUDGET_EVERY_S:
            last_budget = now
            try:
                alerted = await check_budget(settings, budget, notifier, alerted)
            except Exception as e:  # FreeLLMAPI può non essere ancora pronto
                log.info("controllo token saltato: %s", type(e).__name__)
        if not encrypted and now - started > 90:  # cifra i dati vecchi a lotti, una volta superato l'avvio
            try:
                n = await store.encrypt_existing()
                if n:
                    log.info("cifratura dei dati esistenti: %d righe", n)
                encrypted = n == 0
            except Exception as e:
                log.warning("cifratura dei dati esistenti rimandata: %s", type(e).__name__)
        if now - last_prune >= PRUNE_EVERY_S:
            last_prune = now
            try:
                await store.prune()
            except Exception:
                log.exception("pulizia dati vecchi fallita")
        # il primo backup parte 10 minuti dopo l'avvio, per non appesantire il risveglio del servizio
        if backup and backup.enabled and (now - started > 600 if last_backup is None else now - last_backup >= PRUNE_EVERY_S):
            try:
                log.info("backup Supabase: %s", await backup.run())
            except Exception as e:
                log.warning("backup Supabase fallito: %s", type(e).__name__)
                await notifier.push("alert", "Backup non riuscito", "Il backup notturno su Hugging Face è fallito.")
            last_backup = time.monotonic()
        await asyncio.sleep(settings.reminder_poll_s)
