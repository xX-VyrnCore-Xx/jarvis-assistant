"""Collegamento di Telegram sempre vivo: avvio con tentativi, controllo periodico del webhook, lettura diretta (polling) di riserva e avviso di ritorno online."""
import asyncio
import logging
import time
from datetime import datetime, timezone

from .config import Settings
from .telegram import Telegram

log = logging.getLogger("jarvis.telegram")
PROFILE = ("Sono JARVIS, l'assistente personale di cui si fida: agenda, email, notizie in tempo reale, promemoria, ricerche, programmazione. Mi scriva o mi mandi un vocale.",
           "JARVIS, il suo assistente personale.")


def base_url(s: Settings) -> str:
    return (s.public_url or s.render_external_url or "").rstrip("/")


def mode_for(s: Settings) -> str:
    """webhook (consigliato: il server dorme finché non arriva un messaggio) se c'è un indirizzo pubblico e il segreto; altrimenti polling."""
    m = (s.telegram_mode or "auto").lower()
    if m in ("webhook", "polling"):
        return m
    return "webhook" if base_url(s) and s.telegram_webhook_secret else "polling"


async def retry(fn, tries: int = 4, first: float = 1.5):
    last: Exception | None = None
    for i in range(tries):
        try:
            return await fn()
        except Exception as e:
            last = e
            await asyncio.sleep(first * 2**i)
    raise last  # type: ignore[misc]


async def setup(tg: Telegram, s: Settings, commands: list[tuple[str, str]]) -> str:
    """Prende il controllo del bot (webhook o polling), imposta comandi e profilo. Non solleva mai: in caso di errore ci pensa il controllo periodico."""
    mode = mode_for(s)
    try:
        if mode == "webhook":
            hook = f"{base_url(s)}/telegram/webhook"
            await retry(lambda: tg.check_webhook(hook))
        else:
            await retry(lambda: tg.delete_webhook(False))
            tg.health = {"mode": "polling", "url_ok": True, "pending": 0, "checked_at": time.time(), "last_error": "", "last_error_at": 0}
        await retry(lambda: tg.set_commands(commands), tries=3)
        await tg.set_profile(*PROFILE)
    except Exception as e:
        log.warning("configurazione del bot Telegram incompleta (%s): riprovo tra poco", type(e).__name__)
    return mode


async def guard_loop(tg: Telegram, s: Settings, every: int = 180) -> None:
    """Ogni 3 minuti verifica che il webhook sia quello giusto e che Telegram riesca a consegnare; se no lo ripristina."""
    from .health import beat

    hook = f"{base_url(s)}/telegram/webhook"
    while True:
        beat("telegram", every)
        await asyncio.sleep(every)
        try:
            await tg.check_webhook(hook)
        except Exception as e:
            tg.health = {**tg.health, "checked_at": time.time(), "last_error": f"controllo non riuscito ({type(e).__name__})"}
            log.warning("controllo del webhook Telegram fallito (%s)", type(e).__name__)


async def poll_loop(tg: Telegram, bot, owner_ok) -> None:
    """Riserva senza indirizzo pubblico: legge i messaggi direttamente (long polling)."""
    from .health import beat

    offset, backoff = 0, 1.0
    while True:
        beat("telegram", 60)
        try:
            for u in await tg.get_updates(offset, 25):
                offset = max(offset, u["update_id"] + 1)
                if owner_ok(u):
                    asyncio.create_task(bot.handle_update(u))
            backoff = 1.0
            tg.health = {**tg.health, "mode": "polling", "url_ok": True, "checked_at": time.time(), "last_error": ""}
        except Exception as e:
            log.warning("lettura dei messaggi Telegram non riuscita (%s)", type(e).__name__)
            tg.health = {**tg.health, "last_error": f"{type(e).__name__}"}
            await asyncio.sleep(min(30.0, backoff))
            backoff *= 2


async def announce_return(tg: Telegram, store, version: str, gap_min: int = 20) -> None:
    """Se il servizio è stato fermo a lungo (aggiornamento, riavvio, sonno) lo dice al proprietario, in silenzio; poi segna «vivo»."""
    try:
        prev = await store.get_setting("last_alive")
        now = datetime.now(timezone.utc)
        if prev:
            gap = (now - datetime.fromisoformat(prev)).total_seconds() / 60
            if gap >= gap_min:
                away = f"{int(gap // 60)} h {int(gap % 60)} min" if gap >= 60 else f"{int(gap)} min"
                await tg.send_id(tg.s.telegram_owner_id, f"🟢 <b>Sono di nuovo online</b> (v{version}).\n<i>Ero fermo da circa {away}: se mi ha scritto nel frattempo, riprovi pure.</i>", silent=True)
        await store.set_setting("last_alive", now.isoformat(timespec="seconds"))
    except Exception as e:
        log.info("avviso di ritorno online non inviato (%s)", type(e).__name__)
