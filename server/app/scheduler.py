import asyncio
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .budget import fmt_tokens
from .health import beat, heartbeat_line, stale_loops
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
        beat("promemoria", settings.reminder_poll_s)
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
                detail = await backup.run()
                log.info("backup Supabase: %s", detail)
                await store.set_setting("backup_status", json.dumps({"ok": True, "at": datetime.now(tz).isoformat(), "detail": detail}))
            except Exception as e:
                log.warning("backup Supabase fallito: %s", type(e).__name__)
                await store.set_setting("backup_status", json.dumps({"ok": False, "at": datetime.now(tz).isoformat(), "detail": type(e).__name__}))
                await notifier.push("alert", "Backup non riuscito", "Il backup notturno su Hugging Face è fallito.")
            last_backup = time.monotonic()
        await asyncio.sleep(settings.reminder_poll_s)


async def brain_cycle(settings: Settings, store: Store, brain, state: dict) -> None:
    """Manutenzione del secondo cervello: indice, ricordi vecchi, vettori mancanti, arricchimento."""
    if not state.get("loaded"):
        log.info("secondo cervello: indice caricato (%d frammenti)", await brain.load())
        state["loaded"] = True
    if not state.get("imported"):
        done = await store.get_setting("brain_memories_imported")
        if not done:
            n = await brain.import_memories(await store.list_memories(500))
            await store.set_setting("brain_memories_imported", "1")
            log.info("secondo cervello: importati %d ricordi", n)
        state["imported"] = True
    n = await brain.reindex_vectors(32)
    if n:
        log.info("secondo cervello: %d vettori aggiunti", n)
    if settings.rag_enrich_per_cycle:
        await brain.enrich_pending()
    if settings.knowledge_seed_per_cycle and getattr(brain, "knowledge", None):
        n = await brain.knowledge.seed_batch(settings.knowledge_seed_per_cycle)
        if n:
            log.info("secondo cervello: %d voci di conoscenza di base", n)


async def consolidate_yesterday(settings: Settings, store: Store, brain, tz: ZoneInfo) -> str:
    from datetime import timedelta

    day = (datetime.now(tz) - timedelta(days=1)).date()
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    rows = await store.messages_between(start.astimezone(ZoneInfo("UTC")).isoformat(), (start + timedelta(days=1)).astimezone(ZoneInfo("UTC")).isoformat(), 400)
    transcript = "\n".join(f"{'Utente' if m['role'] == 'user' else 'JARVIS'}: {m['content']}" for m in rows if m.get("session_id") != "briefing")
    return (await brain.consolidate_day(day.isoformat(), transcript)).get("status", "")


async def morning_briefing(settings: Settings, brain, agent, notifier) -> None:
    review = await brain.resurface(1)
    extra = f" Includi in fondo un ripasso breve di questo documento del mio secondo cervello: «{review[0].title}» (#{review[0].id})." if review else ""
    text = await agent.reply("Prepara il mio buongiorno: agenda di oggi, promemoria e attività aperte, e se serve un consiglio pratico. "
                             f"Massimo 8 righe, tono da JARVIS.{extra}", "briefing")
    await notifier.push("info", "Buongiorno, signore", text[:600], telegram=True)


async def brain_loop(settings: Settings, store: Store, brain, agent, notifier) -> None:
    """Primo ciclo dopo 45 s (il risveglio di Render non va appesantito), poi ogni 5 minuti; diario alle 03:30 e buongiorno all'ora scelta."""
    tz = ZoneInfo(settings.timezone)
    state: dict = {}
    await asyncio.sleep(45)
    while True:
        beat("cervello", 300)
        try:
            if brain.enabled:
                await brain_cycle(settings, store, brain, state)
                now = datetime.now(tz)
                today = now.date().isoformat()
                if now.hour >= 3 and await store.get_setting("last_journal") != today:
                    await store.set_setting("last_journal", today)
                    log.info("diario di ieri: %s", await consolidate_yesterday(settings, store, brain, tz))
                if settings.briefing_hour and settings.briefing_hour <= now.hour < settings.briefing_hour + 4 and await store.get_setting("last_briefing") != today:
                    await store.set_setting("last_briefing", today)
                    await morning_briefing(settings, brain, agent, notifier)
        except Exception:
            log.exception("errore nel ciclo del secondo cervello")
        await asyncio.sleep(300)


async def maintenance_loop(settings: Settings, store: Store, usage, updates, notifier, reminders=None) -> None:
    """Ogni 5 minuti: salva i consumi, controlla la memoria del processo; ogni `update_check_minutes` cerca nuove Release e avvisa le app."""
    from .health import container_mb, rss_mb

    await asyncio.sleep(60)
    last_update = 0.0
    mem_alert = False
    while True:
        beat("manutenzione", 300)
        try:
            await usage.flush(store)
            if reminders is not None:  # il Calendario comanda: spostamenti ed eliminazioni arrivano nell'app, e i promemoria senza evento ne ricevono uno
                try:
                    await reminders.sync()
                except Exception as e:
                    log.info("sincronizzazione promemoria ↔ Calendario rimandata: %s", type(e).__name__)
            mem = container_mb() or rss_mb() * 1.6  # il container comprende anche FreeLLMAPI
            if mem > 440 and not mem_alert:
                mem_alert = True
                await notifier.push("alert", "Memoria quasi al limite", f"Il server usa circa {mem:.0f} MB su 512: potrebbe riavviarsi.")
            elif mem < 380:
                mem_alert = False
            if time.monotonic() - last_update >= settings.update_check_minutes * 60:
                last_update = time.monotonic()
                result = await updates.poll_and_notify()
                if result.startswith("notificata"):
                    log.info("aggiornamenti: %s", result)
        except Exception:
            log.exception("errore nella manutenzione periodica")
        await asyncio.sleep(300)


async def proactive_loop(settings: Settings, proactive) -> None:
    """Ogni 5 minuti lascia lavorare il motore proattivo (primo giro dopo 2 minuti, per non appesantire l'avvio)."""
    await asyncio.sleep(120)
    while True:
        beat("proattivo", 300)
        try:
            await proactive.tick()
        except Exception:
            log.exception("errore nel ciclo proattivo")
        await asyncio.sleep(300)


async def heartbeat_loop(app) -> None:
    """Una riga di stato al minuto nei log di Render (memoria, modelli, cervello, cicli di fondo) e un avviso se un ciclo si ferma."""
    log = logging.getLogger("jarvis.heartbeat")
    warned: set[str] = set()
    while True:
        await asyncio.sleep(60)
        try:
            log.info("%s", heartbeat_line(app))
            now_bad = {n for n, _ in stale_loops()}
            for n, mins in stale_loops():
                if n not in warned:
                    log.warning("il ciclo di fondo «%s» non risponde da %d minuti", n, mins)
            warned = now_bad
        except Exception:
            log.exception("battito del server non riuscito")
