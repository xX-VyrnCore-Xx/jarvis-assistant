"""Bot Telegram di JARVIS: comandi, pulsanti, indicatore di scrittura e risposte formattate. Risponde solo al proprietario."""
import asyncio
import html
import json
import logging
import time
from collections import OrderedDict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

from .llm import LLMError

log = logging.getLogger("jarvis.bot")

COMMANDS = [
    ("menu", "Tasti rapidi"),
    ("oggi", "Il punto di oggi: agenda, attività, promemoria"),
    ("agenda", "Impegni di oggi e domani"),
    ("email", "Email non lette importanti"),
    ("aiuto", "Cosa so fare"),
    ("stato", "Stato dei sistemi"),
    ("token", "Token gratuiti rimasti"),
    ("promemoria", "Promemoria attivi (con elimina)"),
    ("ricordi", "Cosa ricordo di te (con elimina)"),
    ("google", "Collega Gmail, Calendar e Drive"),
    ("riepilogo", "Il tuo buongiorno, adesso"),
    ("uso", "Token e consumo dei modelli"),
    ("modello", "Scegli il modello AI"),
    ("impostazioni", "Notifiche e ore silenziose"),
    ("aggiornamenti", "Nuove versioni delle app"),
    ("salute", "Stato tecnico del server"),
    ("nota", "Salva una nota nel secondo cervello"),
    ("cerca", "Cerca nel secondo cervello"),
    ("cervello", "Statistiche del secondo cervello"),
    ("impara", "Studio un argomento da Wikipedia"),
    ("skills", "Le mie competenze (programmazione, finanza, marketing...)"),
    ("skill", "Usa una competenza: /skill nome richiesta"),
    ("proattivo", "Avvisi automatici: stato e pausa"),
    ("profilo", "Cosa so di te (profilo)"),
    ("liste", "Liste e attività (spesa, da fare)"),
    ("nuova", "Azzera la conversazione"),
]

HELP = """<b>🤖 JARVIS a sua disposizione, {owner}.</b>
Mi scriva (o mi mandi un vocale) in linguaggio naturale: agenda, email, meteo, notizie in tempo reale, ricerche, promemoria, calcoli, programmazione, controllo del PC.

<b>📅 Ogni giorno</b>
/oggi · /agenda · /email · /promemoria · /liste · /riepilogo

<b>🧠 Secondo cervello</b>
/nota · /cerca · /impara · /ricordi · /profilo · /cervello

<b>🛠 Competenze</b>
/skills · /skill nome richiesta

<b>⚙️ Sistema</b>
/proattivo · /impostazioni · /modello · /uso · /token · /stato · /salute · /aggiornamenti · /nuova

<blockquote>«Che notizie ci sono oggi?» · «Ricordami alle 18 di chiamare Luca» · «Cosa so di Luca?» · «Crea un progetto Python su GitHub»</blockquote>
I tasti qui sotto portano ai comandi più usati."""

MENU = {"📅 Agenda": "agenda", "✉️ Email": "email", "✅ Attività": "liste", "🧠 Cervello": "cervello", "📊 Consumo": "uso", "⚙️ Impostazioni": "impostazioni"}
MENU_KEYBOARD = {"keyboard": [[{"text": t} for t in list(MENU)[i:i + 3]] for i in (0, 3)], "resize_keyboard": True, "is_persistent": True,
                 "input_field_placeholder": "Scriva a JARVIS…"}


class TelegramBot:
    def __init__(self, app):
        self.app = app
        self._seen: deque[int] = deque(maxlen=300)
        self._locks: OrderedDict[int, asyncio.Lock] = OrderedDict()
        self._replies: OrderedDict[tuple[int, int], tuple[str, str]] = OrderedDict()  # (chat, messaggio) -> (domanda, risposta)
        self._models: list[str] = []
        self.last_update_at = 0.0

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
        self.last_update_at = time.time()
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
        if (voice := msg.get("voice") or msg.get("audio")) and not text:
            return await self._voice(chat_id, voice)
        if (doc := msg.get("document")) and not text:
            return await self._document(chat_id, doc, (msg.get("caption") or "").strip())
        if not text:
            kind = "vocale" if "voice" in msg or "audio" in msg else "foto" if "photo" in msg else "documento" if "document" in msg else "contenuto"
            return await self.tg.send(chat_id, f"Per ora leggo solo testo, signore: il {kind} non so ancora interpretarlo.")
        if text in MENU:  # tasto della tastiera rapida
            return await self._command(chat_id, MENU[text])
        if text.startswith("/"):
            cmd = text.split()[0][1:].split("@")[0].lower()
            return await self._command(chat_id, cmd, text.partition(" ")[2].strip())
        async with self._lock(chat_id):
            await self._ask(chat_id, text, user_mid=msg.get("message_id", 0))

    async def _voice(self, chat_id: int, voice: dict) -> None:
        """Vocali: li trascrive con il router (/v1/audio/transcriptions) e poi risponde come a un messaggio scritto."""
        if (voice.get("file_size") or 0) > 8_000_000 or (voice.get("duration") or 0) > 300:
            return await self.tg.send(chat_id, "Il vocale è troppo lungo, signore: massimo 5 minuti.")
        try:
            text = await self.app.state.agent.llm.transcribe(await self.tg.download_file(voice["file_id"]), "voice.ogg", voice.get("mime_type") or "audio/ogg")
        except Exception as e:
            log.info("trascrizione non riuscita: %s", type(e).__name__)
            return await self.tg.send(chat_id, "Non sono riuscito a trascrivere il vocale, signore. Riprovi o lo scriva.")
        if not text:
            return await self.tg.send(chat_id, "Non ho sentito nulla di comprensibile, signore.")
        await self.tg.send(chat_id, f"🎤 «{text}»")
        async with self._lock(chat_id):
            await self._ask(chat_id, text)

    def _buttons(self) -> dict:
        return {"inline_keyboard": [[{"text": "🔎 Approfondisci", "callback_data": "dp"}, {"text": "✂️ Più breve", "callback_data": "sh"}],
                                    [{"text": "💾 Salva", "callback_data": "sv"}, {"text": "🔄 Rigenera", "callback_data": "rg"}]]}

    def _remember_reply(self, chat_id: int, mid: int, question: str, answer: str) -> None:
        self._replies[(chat_id, mid)] = (question, answer)
        while len(self._replies) > 60:
            self._replies.popitem(last=False)

    async def _ask(self, chat_id: int, text: str, skill: str | None = None, user_mid: int = 0) -> None:
        """Risposta in diretta: un messaggio che si riempie man mano (e mostra lo strumento in uso), poi formattato con i pulsanti.
        Il messaggio dell'utente riceve subito un 👀 («ricevuto»), tolto a risposta pronta."""
        if user_mid:
            asyncio.create_task(self.tg.react(chat_id, user_mid, "👀"))
        async def typing() -> None:
            while True:
                try:
                    await self.tg.typing(chat_id)
                except Exception:
                    pass
                await asyncio.sleep(4)

        indicator = asyncio.create_task(typing())
        mid, buf, final, status, last, shown = 0, "", "", "", 0.0, ""
        try:
            mid = await self.tg.send_id(chat_id, "💭 Ci sto pensando…", silent=True)
            model = await self.app.state.store.get_setting("tg_model") or None
            async for kind, data in self.app.state.agent.reply_stream(text, f"tg-{chat_id}", model=model, skills=[skill] if skill else None):
                if kind == "status":
                    status = data
                elif kind == "delta":
                    buf += data
                elif kind == "done":
                    final = data
                    break
                now = time.monotonic()
                view = (buf[:3600] + " ▌") if buf else f"⏳ {status}" if status else ""
                if view and view != shown and now - last > 1.4 and (len(view) - len(shown) > 24 or not buf):
                    if await self.tg.edit(chat_id, mid, view, html=False):
                        shown, last = view, now
        except LLMError:
            final = "L'intelligenza artificiale non risponde in questo momento, signore. Riprovo tra poco?"
        except Exception:
            log.exception("errore nella risposta")
            final = "Si è verificato un problema, signore. Riprovi tra un momento."
        finally:
            indicator.cancel()
            if user_mid:
                asyncio.create_task(self.tg.react(chat_id, user_mid, None))
        final = final or buf or "…"
        from .telegram import split_text

        parts = split_text(final)
        if len(parts) <= 1:
            if not await self.tg.edit(chat_id, mid, final, self._buttons()):
                mid = await self.tg.send_id(chat_id, final, self._buttons())
        else:  # risposta lunga: il primo messaggio si completa, il resto segue
            await self.tg.edit(chat_id, mid, parts[0])
            mid = await self.tg.send_id(chat_id, "\n\n".join(parts[1:]), self._buttons())
        self._remember_reply(chat_id, mid, text, final)

    # ------------------------------------------------------------------ comandi
    async def _command(self, chat_id: int, cmd: str, arg: str = "") -> None:
        st = self.app.state
        if cmd in ("start", "aiuto", "help", "menu"):
            return await self.tg.send(chat_id, HELP.format(owner=self.s.owner_name), MENU_KEYBOARD)
        if cmd in ("agenda", "oggi", "email"):
            return await self._daily(chat_id, cmd)
        if cmd == "impara":
            return await self._learn(chat_id, arg)
        if cmd in ("skills", "skill"):
            return await self._skills(chat_id, cmd, arg)
        if cmd == "proattivo":
            return await self._proactive(chat_id)
        if cmd == "stato":
            return await self._status(chat_id)
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
            today = datetime.now(tz).date()
            days: dict[str, list[str]] = {}
            for r in sorted(rows, key=lambda r: r["due_at"]):
                d = datetime.fromisoformat(r["due_at"]).astimezone(tz)
                label = "⚠️ Scaduti" if d < datetime.now(tz) else "Oggi" if d.date() == today else "Domani" if (d.date() - today).days == 1 else f"{d:%a %d/%m}"
                days.setdefault(label, []).append(f"⏰ <b>{d:%H:%M}</b>  {html.escape(r['text'])}" + (" 📅" if r.get("event_id") else ""))
            body = "\n\n".join(f"<b>{k}</b>\n" + "\n".join(v) for k, v in days.items())
            keys = [[{"text": f"🗑 {r['text'][:28]}", "callback_data": f"rd:{r['id']}"}] for r in rows[:10]]
            return await self.tg.send(chat_id, "<b>🔔 Promemoria attivi</b>  <i>(📅 = anche sul Calendario)</i>\n━━━━━━━━━━━━━━\n" + body, {"inline_keyboard": keys})
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
        if cmd == "profilo":
            if not st.brain.enabled:
                return await self.tg.send(chat_id, "Il secondo cervello è spento, signore.")
            text = await st.brain.profile_text()
            return await self.tg.send(chat_id, f"<b>Cosa so di lei</b>\n{html.escape(text)}" if text else
                                      "Non ho ancora abbastanza ricordi per un profilo: più parliamo, più imparo. Per correggere qualcosa usi /ricordi.")
        if cmd == "uso":
            return await self._usage(chat_id)
        if cmd == "salute":
            return await self._health(chat_id)
        if cmd == "riepilogo":
            from .scheduler import morning_briefing

            await self.tg.typing(chat_id)
            text = await st.agent.reply("Prepara il mio buongiorno: agenda di oggi, promemoria e attività aperte. Massimo 8 righe.", "briefing")
            return await self.tg.send(chat_id, text)
        if cmd == "aggiornamenti":
            rel = await st.updates.latest(force=True)
            if not rel:
                return await self.tg.send(chat_id, "Nessuna versione pubblicata, signore.")
            lines = [f"<b>Ultima versione: {rel['version']}</b> ({rel['published_at'][:10]})"] + [f"• {k}: {a['name']} ({a['size'] // 1_000_000} MB)" for k, a in rel["assets"].items()]
            keys = [[{"text": f"Scarica {k}", "url": a["url"]}] for k, a in rel["assets"].items()]
            return await self.tg.send(chat_id, "\n".join(lines) + "\nLe app propongono l'aggiornamento da sole.", {"inline_keyboard": keys + [[{"text": "Novità", "url": rel["page"]}]]})
        if cmd == "impostazioni":
            return await self._settings(chat_id)
        if cmd == "modello":
            try:
                self._models = ["auto"] + [m["id"] for m in await st.agent.llm.models()][:14]
            except Exception:
                return await self.tg.send(chat_id, "L'elenco dei modelli non è disponibile ora: FreeLLMAPI si sta avviando.")
            cur = await st.store.get_setting("tg_model") or "auto"
            keys = [[{"text": ("● " if m == cur else "") + m, "callback_data": f"md2:{i}"}] for i, m in enumerate(self._models)]
            return await self.tg.send(chat_id, f"<b>Modello AI</b> (ora: {cur})\nAutomatico lascia scegliere al router il migliore disponibile.", {"inline_keyboard": keys})
        if cmd in ("nota", "cerca", "cervello"):
            brain = st.brain
            if not brain.enabled:
                return await self.tg.send(chat_id, "Il secondo cervello è disattivato, signore.")
            if cmd == "cervello":
                x = await brain.stats()
                know = getattr(brain, "knowledge", None)
                prog = await know.progress() if know else None
                return await self.tg.send(chat_id, f"<b>Secondo cervello</b>\n• {x['docs']} documenti, {x['chunks']} frammenti ({x['vectors']} con vettore)\n• {x['entities']} entità\n"
                                                    f"• Fonti: {', '.join(f'{k} {v}' for k, v in x['by_source'].items()) or 'vuoto'}\n• Modello: {x['model']}"
                                                    + (f"\n• Conoscenza di base: {prog[0]}/{prog[1]} voci di Wikipedia" if prog else ""))
            if not arg:
                return await self.tg.send(chat_id, f"Scriva ad esempio: /{cmd} " + ("riunione con Luca: decidiamo il budget a gennaio" if cmd == "nota" else "budget con Luca"))
            if cmd == "nota":
                r = await brain.ingest(arg, source="note", importance=0.6)
                return await self.tg.send(chat_id, f"Annotato nel secondo cervello (#{r['doc_id']})." if r["status"] != "duplicato" else f"Già presente (#{r['doc_id']}).")
            from .brain.tools import format_results

            res = await brain.search(arg, k=5)
            return await self.tg.send(chat_id, format_results(res, 300) if res else "Non trovo nulla di pertinente, signore.")
        if cmd == "liste":
            rows = await st.store.list_tasks(None, False)
            if not rows:
                return await self.tg.send(chat_id, "Nessuna voce nelle liste, signore. Chieda ad esempio: «aggiungi il latte alla spesa».")
            out: dict[str, list[str]] = {}
            for t in rows:
                out.setdefault(t["list"], []).append(f"• {t['text']}")
            keys = [[{"text": f"✔ {t['text'][:28]}", "callback_data": f"td:{t['id']}"}] for t in rows[:10]]
            return await self.tg.send(chat_id, "\n\n".join(f"<b>{name.capitalize()}</b>\n" + "\n".join(items) for name, items in out.items()), {"inline_keyboard": keys})
        if cmd == "nuova":
            await st.store.clear_messages(f"tg-{chat_id}")
            return await self.tg.send(chat_id, "Conversazione azzerata. I ricordi a lungo termine restano, signore.")
        import difflib

        near = difflib.get_close_matches(cmd, [c for c, _ in COMMANDS], n=1, cutoff=0.6)
        await self.tg.send(chat_id, f"Comando sconosciuto, signore. Intendeva /{near[0]}?" if near else "Comando sconosciuto. /aiuto elenca ciò che so fare.")

    async def _daily(self, chat_id: int, cmd: str) -> None:
        """Agenda, email e punto del giorno: testo composto dai dati (nessuna chiamata al modello, quindi istantaneo e gratis)."""
        from zoneinfo import ZoneInfo

        from .agenda import agenda_text, unread_digest

        st, tz = self.app.state, ZoneInfo(self.s.timezone)
        await self.tg.typing(chat_id)
        if cmd == "email":
            if not st.google.enabled:
                return await self.tg.send(chat_id, "Google non è collegato, signore: usi /google.")
            try:
                rows = await unread_digest(st.google)
            except Exception:
                return await self.tg.send(chat_id, "Non riesco a leggere la posta in questo momento, signore.")
            return await self.tg.send(chat_id, ("<b>Email non lette</b>\n" + "\n".join(f"• {r}" for r in rows)) if rows else "Nessuna email nuova nella posta principale. 👌")
        parts = []
        if st.google.enabled:
            try:
                parts.append(await agenda_text(st.google, tz, days=2 if cmd == "agenda" else 1))
            except Exception:
                parts.append("(agenda non raggiungibile ora)")
        elif cmd == "agenda":
            return await self.tg.send(chat_id, "Google non è collegato, signore: usi /google.")
        if cmd == "agenda":
            return await self.tg.send(chat_id, "\n".join(parts))
        tasks = await st.store.list_tasks(None, False)
        if tasks:
            parts.append("<b>Attività aperte</b>\n" + "\n".join(f"• {t['text']}" for t in tasks[:8]) + (f"\n…e altre {len(tasks) - 8}" if len(tasks) > 8 else ""))
        today = datetime.now(tz).date()
        rems = [r for r in await st.store.list_reminders() if datetime.fromisoformat(r["due_at"]).astimezone(tz).date() == today]
        if rems:
            parts.append("<b>Promemoria di oggi</b>\n" + "\n".join(f"• {datetime.fromisoformat(r['due_at']).astimezone(tz):%H:%M} — {r['text']}" for r in rems))
        await self.tg.send(chat_id, f"<b>Il punto di oggi, {self.s.owner_name}</b>\n\n" + ("\n\n".join(parts) if parts else "Giornata libera e nessuna attività aperta. 🎯"))

    async def _skills(self, chat_id: int, cmd: str, arg: str) -> None:
        """/skills: l'elenco per ambito (pulsanti); /skill nome richiesta: usa quella competenza per la richiesta."""
        from .skills.registry import DOMAINS

        sk = self.app.state.skills
        if cmd == "skill" and arg:
            name, _, request = arg.partition(" ")
            found = sk.get(name)
            if not found:
                return await self.tg.send(chat_id, f"Non conosco la competenza «{html.escape(name)}». /skills le elenca.")
            if not request.strip():
                return await self.tg.send(chat_id, f"<b>{html.escape(found.title)}</b>\n{html.escape(found.description)}\n\nScriva: /skill {found.name} la sua richiesta")
            async with self._lock(chat_id):
                return await self._ask(chat_id, request.strip(), skill=found.name)
        keys = [[{"text": f"{label} ({len(sk.by_domain(d))})", "callback_data": f"sk:{d}"}] for d, label in DOMAINS.items() if sk.by_domain(d)]
        await self.tg.send(chat_id, f"<b>Le mie competenze</b> ({len(sk)})\nSi attivano da sole quando la richiesta le riguarda. Per forzarne una: /skill nome richiesta.", {"inline_keyboard": keys})

    async def _learn(self, chat_id: int, topic: str) -> None:
        st = self.app.state
        k = getattr(st.brain, "knowledge", None)
        if not (st.brain.enabled and k):
            return await self.tg.send(chat_id, "Il secondo cervello è spento, signore.")
        if not topic:
            done, total = await k.progress()
            return await self.tg.send(chat_id, f"Scriva ad esempio: /impara fotosintesi clorofilliana\nLa cultura di base si sta caricando da sola: {done}/{total} voci.")
        await self.tg.typing(chat_id)
        try:
            r = await k.learn(topic, full=True)
        except Exception:
            return await self.tg.send(chat_id, "Wikipedia non risponde in questo momento, signore.")
        if r["status"] == "non trovato":
            return await self.tg.send(chat_id, f"Non trovo una voce per «{topic}». Provi con un altro nome.")
        await self.tg.send(chat_id, f"{'Già nel secondo cervello' if r['status'] == 'duplicato' else 'Imparato'}: <b>{html.escape(r['title'])}</b> (#{r['doc_id']}, {r['chars']} caratteri).\nOra posso risponderle anche senza cercare sul web.")

    async def _proactive(self, chat_id: int, message_id: int = 0) -> None:
        st = self.app.state
        paused = await st.store.get_setting("proactive_paused") == "1"
        pro = getattr(st, "proactive", None)
        used = ""
        if pro and pro._state:
            used = f"\nOggi ne ho inviati {pro._state.get('n', 0)} su {self.s.proactive_max_per_day} (gli eventi imminenti non contano)."
        on = self.s.proactive_enabled and not paused
        text = ("<b>Avvisi automatici</b>\n" + ("🟢 Attivi" if on else "⏸ In pausa" if self.s.proactive_enabled else "⚫ Spenti dalla configurazione (PROACTIVE_ENABLED)")
                + "\nEventi in arrivo, email nuove, il punto della sera, il riepilogo della domenica, token in esaurimento." + used)
        keys = {"inline_keyboard": [[{"text": "▶️ Riattiva" if paused else "⏸ Metti in pausa", "callback_data": "pp"}]]} if self.s.proactive_enabled else None
        if message_id:
            await self.tg.edit(chat_id, message_id, text, keys)
        else:
            await self.tg.send(chat_id, text, keys)

    async def _usage(self, chat_id: int) -> None:
        st = self.app.state
        await st.usage.flush(st.store)
        rows = await st.store.usage_series(7)
        by_day: dict[str, int] = {}
        for r in rows:
            by_day[str(r["day"])] = by_day.get(str(r["day"]), 0) + r["prompt_tokens"] + r["completion_tokens"]
        bars = "▁▂▃▄▅▆▇█"
        peak = max(by_day.values(), default=1) or 1
        spark = "".join(bars[min(7, int(v / peak * 7))] for _, v in sorted(by_day.items())) or "—"
        t = st.usage.today()
        from .budget import fmt_tokens

        lines = [f"<b>Consumo dei modelli</b>", f"Oggi: {t['requests']} richieste, {fmt_tokens(t['prompt_tokens'] + t['completion_tokens'])} token, latenza media {t['avg_latency_ms'] / 1000:.1f} s"
                 + (f", {t['errors']} errori" if t["errors"] else ""), f"Ultimi giorni: {spark}"]
        if st.budget.enabled:
            try:
                from .api import forecast

                b = await st.budget.get()
                f = forecast(b)
                lines += ["", await st.budget.text()]
                if f["days_left"] is not None:
                    lines.append(f"Al ritmo attuale ({fmt_tokens(f['burn_per_day'])}/giorno): {f['days_left']:.0f} giorni" + (" ⚠️ finiscono prima del rinnovo" if f["runs_out_before_reset"] else ""))
            except Exception:
                lines.append("(token di FreeLLMAPI non disponibili ora)")
        await self.tg.send(chat_id, "\n".join(lines))

    @staticmethod
    def _ago(ts: float) -> str:
        if not ts:
            return "mai"
        d = max(0, int(time.time() - ts))
        return "adesso" if d < 60 else f"{d // 60} min fa" if d < 3600 else f"{d // 3600} h fa" if d < 172800 else f"{d // 86400} giorni fa"

    def tg_line(self) -> tuple[bool | None, str]:
        """(stato, testo) del collegamento con Telegram: webhook attivo, messaggi in coda, ultimo messaggio ricevuto, ultimo errore di consegna."""
        h = self.tg.health
        if not h.get("mode"):
            return None, "controllo in corso"
        last = f" · ultimo messaggio {self._ago(self.last_update_at)}" if self.last_update_at else ""
        if h["mode"] == "polling":
            return True, "lettura diretta (polling)" + last
        if not h["url_ok"]:
            return False, "webhook non corretto: lo sto ripristinando"
        if h["last_error"]:
            return False, f"errore di consegna recente ({h['last_error'][:60]}): riarmo" + last
        return True, "webhook attivo" + (f" · {h['pending']} in coda" if h["pending"] else "") + last

    async def _status(self, chat_id: int) -> None:
        st, s = self.app.state, self.s
        ic = lambda ok: "🟢" if ok else "🟡" if ok is None else "🔴"  # noqa: E731
        ai = (await st.admin.ready()) if st.budget.enabled else None
        tg_ok, tg_text = self.tg_line()
        cal = getattr(st, "reminders", None)
        cs = cal.status if cal else {}
        live = getattr(st, "live", None)
        rows = [
            f"{ic(True if ai is None else ai)} <b>Intelligenza</b> — {'pronta' if ai or ai is None else 'in avvio'}",
            f"{ic(tg_ok)} <b>Telegram</b> — {tg_text}",
            f"{ic(True if st.pc.connected else None)} <b>PC Windows</b> — {'collegato' if st.pc.connected else 'scollegato'}" + (" · voce attiva" if st.voice.enabled else ""),
            f"{ic(True if st.google.enabled else None)} <b>Google</b> — {'collegato' if st.google.enabled else 'non collegato (usa /google)' if st.google.has_client else 'non configurato'}",
        ]
        if st.google.enabled and cs.get("ok") is not None:
            rows.append(f"{ic(cs['ok'])} <b>Calendario</b> — " + ("sincronizzato" if cs["ok"] else html.escape(cs.get("detail", "errore")[:140])))
        if live is not None:
            rows.append(f"{ic(True if live.last_ingest else None)} <b>Notizie</b> — " + (f"aggiornate {live.last_ingest[11:16]} UTC · {len(live.errors)} feed non raggiungibili" if live.last_ingest else "in avvio"))
        rows += [
            f"{ic(True if st.notifier.fcm.enabled else None)} <b>Push Android</b> — {'attive' if st.notifier.fcm.enabled else 'non configurate'}",
            f"{ic(True if st.backup.enabled else None)} <b>Backup</b> — {'attivo (Hugging Face)' if st.backup.enabled else 'non configurato'}",
            f"{ic(True if s.supabase_url and s.supabase_service_key else False)} <b>Memoria</b> — {'permanente (Supabase)' if s.supabase_url and s.supabase_service_key else 'temporanea'}",
            f"🔐 <b>Conferme in attesa</b> — {len(st.pending.list_pending())}",
        ]
        await self.tg.send(chat_id, "<b>🛰 Stato di JARVIS</b>\n━━━━━━━━━━━━━━\n" + "\n".join(rows) + "\n━━━━━━━━━━━━━━\n<i>/salute per i dettagli tecnici</i>")

    async def _health(self, chat_id: int) -> None:
        from .health import deep_health

        h = await deep_health(self.app)
        m = h["memory"]
        tg_ok, tg_text = self.tg_line()
        lines = ["<b>🩺 Salute del server</b>", f"• Telegram: {tg_text}", f"• Database: {'ok' if h['db']['ok'] else 'NON RAGGIUNGIBILE'} ({h['db']['latency_ms']} ms)",
                 f"• Memoria: {m['container_mb'] or m['process_mb']} MB su {m['limit_mb']}", f"• Intelligenza: {'pronta' if h['freellm_ready'] else 'in avvio' if h['freellm_ready'] is not None else '—'}",
                 f"• Secondo cervello: {h['brain']['indexed']} frammenti in memoria", f"• App collegate in diretta: {h['realtime_listeners']}"]
        b = h["backup"]
        if b:
            lines.append(f"• Ultimo backup: {'ok' if b.get('ok') else 'FALLITO'} ({str(b.get('at', ''))[:16].replace('T', ' ')})")
        if h["update"]["last_error"]:
            lines.append(f"• Controllo aggiornamenti: errore {h['update']['last_error']}")
        await self.tg.send(chat_id, "\n".join(lines))

    async def _settings(self, chat_id: int, message_id: int = 0) -> None:
        prefs = await self.app.state.notifier.prefs()
        names = {"reminder": "Promemoria", "alert": "Avvisi", "pending": "Conferme", "update": "Aggiornamenti", "brain": "Cervello",
                 "proactive": "Suggerimenti", "info": "Informazioni"}
        keys = [[{"text": f"{'✅' if v['telegram'] else '⬜'} {names.get(k, k)} su Telegram", "callback_data": f"np:{k}"}] for k, v in prefs["kinds"].items()]
        q = prefs["quiet"]
        keys.append([{"text": f"{'🌙 Ore silenziose: ' + q['from'] + '–' + q['to'] if q['enabled'] else '🔔 Ore silenziose: spente'}", "callback_data": "nq"}])
        text = "<b>Notifiche</b>\nScegli cosa arriva anche qui. Promemoria, avvisi e conferme passano sempre, anche nelle ore silenziose."
        if message_id:
            await self.tg.edit(chat_id, message_id, text, {"inline_keyboard": keys})
        else:
            await self.tg.send(chat_id, text, {"inline_keyboard": keys})

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
        chat = (msg.get("chat") or {}).get("id") or self.s.telegram_owner_id
        if action == "rs":  # promemoria scattato: rimanda o chiudi
            nid, _, mins = ident.partition(":")
            n = await st.store.get_notification(int(nid)) if nid.isdigit() else None
            if n and n["kind"] == "reminder":
                if int(mins or 0):
                    from datetime import timedelta
                    from zoneinfo import ZoneInfo

                    await st.reminders.snooze_delivered(n["body"], int(mins))
                await st.notifier.mark_read([n["id"]])
                outcome = f"Rimandato di {mins} min." if int(mins or 0) else "Fatto."
                if msg.get("message_id"):
                    await self.tg.clear_buttons(chat, msg["message_id"], f"{n['body']} — {outcome}")
            else:
                outcome = "Promemoria non trovato."
        elif action == "sv" and (key := (chat, msg.get("message_id"))) in self._replies:
            q, a = self._replies[key]
            r = await st.brain.ingest(f"Domanda: {q}\n\nRisposta: {a}", title=q[:80], source="note", importance=0.55)
            outcome = f"Salvato nel secondo cervello (#{r['doc_id']})."
        elif action == "sk" and ident:
            from .skills.registry import DOMAINS

            rows = st.skills.by_domain(ident)
            await self.tg.answer_callback(cb["id"], "")
            return await self.tg.send(chat, f"<b>{DOMAINS.get(ident, ident)}</b>\n" + "\n".join(f"• <code>{s.name}</code> — {html.escape(s.title)}" for s in rows)
                                      + "\n\nUsi: /skill nome la sua richiesta")
        elif action in ("dp", "sh") and (chat, msg.get("message_id")) in self._replies:
            await self.tg.answer_callback(cb["id"], "Un momento…")
            ask = ("Approfondisci la tua ultima risposta: più dettagli, esempi e, se serve, i passi da fare." if action == "dp"
                   else "Riassumi la tua ultima risposta in due righe, senza perdere l'essenziale.")
            async with self._lock(chat):
                await self._ask(chat, ask)
            return
        elif action == "pp":
            paused = await st.store.get_setting("proactive_paused") == "1"
            await st.store.set_setting("proactive_paused", "0" if paused else "1")
            await self.tg.answer_callback(cb["id"], "Avvisi riattivati" if paused else "Avvisi in pausa")
            return await self._proactive(chat, msg.get("message_id", 0))
        elif action == "rg" and (key := (chat, msg.get("message_id"))) in self._replies:
            await self.tg.answer_callback(cb["id"], "Rigenero…")
            async with self._lock(chat):
                await self._ask(chat, self._replies[key][0])
            return
        elif action == "np" and ident in (await st.notifier.prefs())["kinds"]:
            cur = (await st.notifier.prefs())["kinds"][ident]["telegram"]
            await st.notifier.set_prefs({"kinds": {ident: {"telegram": not cur}}})
            await self.tg.answer_callback(cb["id"], "Aggiornato")
            return await self._settings(chat, msg.get("message_id", 0))
        elif action == "nq":
            cur = (await st.notifier.prefs())["quiet"]["enabled"]
            await st.notifier.set_prefs({"quiet": {"enabled": not cur}})
            await self.tg.answer_callback(cb["id"], "Aggiornato")
            return await self._settings(chat, msg.get("message_id", 0))
        elif action == "md2" and ident.isdigit() and int(ident) < len(self._models):
            await st.store.set_setting("tg_model", "" if self._models[int(ident)] == "auto" else self._models[int(ident)])
            outcome = f"Modello: {self._models[int(ident)]}"
        elif action == "rd" and ident.isdigit():
            await st.reminders.delete(int(ident))
            outcome = "Promemoria eliminato."
        elif action == "td" and ident.isdigit():
            await st.store.set_task_done(int(ident), True)
            outcome = "Completata."
        elif action == "md" and ident.isdigit():
            await st.store.delete_memory(int(ident))
            outcome = "Dimenticato."
        await self.tg.answer_callback(cb["id"], outcome or "")
