"""Bot Telegram di JARVIS: comandi, pulsanti, indicatore di scrittura e risposte formattate. Risponde solo al proprietario."""
import asyncio
import logging
from collections import OrderedDict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

from .llm import LLMError

log = logging.getLogger("jarvis.bot")

COMMANDS = [
    ("aiuto", "Cosa so fare"),
    ("stato", "Stato dei sistemi"),
    ("token", "Token gratuiti rimasti"),
    ("promemoria", "Promemoria attivi (con elimina)"),
    ("ricordi", "Cosa ricordo di te (con elimina)"),
    ("google", "Collega Gmail, Calendar e Drive"),
    ("nuova", "Azzera la conversazione"),
]

HELP = """<b>JARVIS a sua disposizione, {owner}.</b>
Scrivetemi in linguaggio naturale: agenda, email, meteo, ricerche, promemoria, calcoli, controllo del PC.

/stato — stato dei sistemi
/token — token gratuiti rimasti
/promemoria — promemoria attivi
/ricordi — cosa ricordo di lei
/nuova — azzera la conversazione

Esempi: «Che tempo fa a Roma domani?», «Ricordami alle 18 di chiamare Luca», «Cosa ho in agenda questa settimana?»."""


class TelegramBot:
    def __init__(self, app):
        self.app = app
        self._seen: deque[int] = deque(maxlen=300)
        self._locks: OrderedDict[int, asyncio.Lock] = OrderedDict()

    @property
    def tg(self):
        return self.app.state.tg

    @property
    def s(self):
        return self.app.state.settings

    def _lock(self, chat_id: int) -> asyncio.Lock:
        lock = self._locks.setdefault(chat_id, asyncio.Lock())
        while len(self._locks) > 20:
            self._locks.popitem(last=False)
        return lock

    def accepts(self, update: dict) -> bool:
        """Solo il proprietario: chiunque altro viene ignorato in silenzio."""
        src = (update.get("callback_query") or update.get("message") or {}).get("from", {})
        return src.get("id") == self.s.telegram_owner_id

    async def handle_update(self, update: dict) -> None:
        uid = update.get("update_id")
        if uid is not None:
            if uid in self._seen:  # Telegram rinvia l'aggiornamento se la risposta tarda
                return
            self._seen.append(uid)
        try:
            if cb := update.get("callback_query"):
                await self._callback(cb)
            elif msg := update.get("message"):
                await self._message(msg)
        except Exception:
            log.exception("errore gestione aggiornamento Telegram")

    # ------------------------------------------------------------------ messaggi
    async def _message(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        if not text:
            kind = "vocale" if "voice" in msg or "audio" in msg else "foto" if "photo" in msg else "documento" if "document" in msg else "contenuto"
            return await self.tg.send(chat_id, f"Per ora leggo solo testo, signore: il {kind} non so ancora interpretarlo.")
        if text.startswith("/"):
            cmd = text.split()[0][1:].split("@")[0].lower()
            return await self._command(chat_id, cmd)
        async with self._lock(chat_id):
            await self._ask(chat_id, text)

    async def _ask(self, chat_id: int, text: str) -> None:
        async def typing() -> None:
            while True:
                try:
                    await self.tg.typing(chat_id)
                except Exception:
                    pass
                await asyncio.sleep(4)

        indicator = asyncio.create_task(typing())
        try:
            reply = await self.app.state.agent.reply(text, f"tg-{chat_id}")
        except LLMError:
            reply = "L'intelligenza artificiale non risponde in questo momento, signore. Riprovo tra poco?"
        except Exception:
            log.exception("errore nella risposta")
            reply = "Si è verificato un problema, signore. Riprovi tra un momento."
        finally:
            indicator.cancel()
        await self.tg.send(chat_id, reply or "…")

    # ------------------------------------------------------------------ comandi
    async def _command(self, chat_id: int, cmd: str) -> None:
        st = self.app.state
        if cmd in ("start", "aiuto", "help"):
            return await self.tg.send(chat_id, HELP.format(owner=self.s.owner_name))
        if cmd == "stato":
            s = self.s
            lines = [
                "<b>Stato dei sistemi</b>",
                f"• Intelligenza: {'pronta' if (await st.admin.ready() if st.budget.enabled else True) else 'in avvio'}",
                f"• PC Windows: {'collegato' if st.pc.connected else 'scollegato'}",
                f"• Voce sul PC: {'sì' if st.voice.enabled else 'no'}",
                f"• Google: {'collegato' if st.google.enabled else 'non collegato (usa /google)' if st.google.has_client else 'non configurato'}",
                f"• Notifiche push Android: {'attive' if st.notifier.fcm.enabled else 'non configurate'}",
                f"• Backup su Hugging Face: {'attivo' if st.backup.enabled else 'non configurato'}",
                f"• Memoria: {'permanente (Supabase)' if s.supabase_url and s.supabase_service_key else 'temporanea'}",
                f"• Conferme in attesa: {len(st.pending.list_pending())}",
            ]
            return await self.tg.send(chat_id, "\n".join(lines))
        if cmd == "token":
            if not st.budget.enabled:
                return await self.tg.send(chat_id, "FreeLLMAPI non è in questo server, signore.")
            try:
                return await self.tg.send(chat_id, await st.budget.text())
            except Exception:
                return await self.tg.send(chat_id, "Non riesco a leggere i token: FreeLLMAPI si sta avviando.")
        if cmd == "promemoria":
            rows = await st.store.list_reminders()
            if not rows:
                return await self.tg.send(chat_id, "Nessun promemoria attivo, signore.")
            tz = ZoneInfo(self.s.timezone)
            body = "\n".join(f"• {datetime.fromisoformat(r['due_at']).astimezone(tz):%d/%m %H:%M} — {r['text']}" for r in rows)
            keys = [[{"text": f"🗑 {r['text'][:28]}", "callback_data": f"rd:{r['id']}"}] for r in rows[:10]]
            return await self.tg.send(chat_id, "<b>Promemoria attivi</b>\n" + body, {"inline_keyboard": keys})
        if cmd == "ricordi":
            rows = await st.store.list_memories(15)
            if not rows:
                return await self.tg.send(chat_id, "La memoria è vuota, signore.")
            keys = [[{"text": f"🗑 {m['content'][:28]}", "callback_data": f"md:{m['id']}"}] for m in rows[:10]]
            return await self.tg.send(chat_id, "<b>Ricordi</b>\n" + "\n".join(f"• {m['content']}" for m in rows), {"inline_keyboard": keys})
        if cmd == "google":
            if not st.google.has_client:
                return await self.tg.send(chat_id, "Mancano GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET su Render, signore.")
            base = (self.s.public_url or self.s.render_external_url).rstrip("/")
            if not base:
                return await self.tg.send(chat_id, "Indirizzo pubblico del server non noto: imposta PUBLIC_URL su Render.")
            url = st.google.authorize_url(f"{base}/google/callback")
            return await self.tg.send(chat_id, f"Autorizzi l'accesso a Gmail, Calendar e Drive (il link vale 10 minuti). "
                                               f"Il redirect da registrare su Google Cloud è <code>{base}/google/callback</code>.",
                                      {"inline_keyboard": [[{"text": "Collega Google", "url": url}]]})
        if cmd == "nuova":
            await st.store.clear_messages(f"tg-{chat_id}")
            return await self.tg.send(chat_id, "Conversazione azzerata. I ricordi a lungo termine restano, signore.")
        await self.tg.send(chat_id, "Comando sconosciuto. /aiuto elenca ciò che so fare.")

    # ------------------------------------------------------------------ pulsanti
    async def _callback(self, cb: dict) -> None:
        st = self.app.state
        action, _, ident = (cb.get("data") or "").partition(":")
        msg = cb.get("message") or {}
        outcome = None
        if action in ("ok", "no") and ident:
            p = await st.pending.decide(ident, action == "ok")
            if p is None or p.status == "expired":
                outcome = "Richiesta scaduta o inesistente."
            else:
                outcome = {"approved": f"Approvata. {p.result}", "rejected": "Rifiutata.", "failed": p.result}.get(p.status, p.status)
            label = p.summary if p else "Richiesta"
            await self.tg.answer_callback(cb["id"], outcome[:150])
            if msg.get("message_id"):
                await self.tg.clear_buttons(msg["chat"]["id"], msg["message_id"], f"{label}: {outcome}")
            return
        if action == "rd" and ident.isdigit():
            await st.store.delete_reminder(int(ident))
            outcome = "Promemoria eliminato."
        elif action == "md" and ident.isdigit():
            await st.store.delete_memory(int(ident))
            outcome = "Dimenticato."
        await self.tg.answer_callback(cb["id"], outcome or "")
