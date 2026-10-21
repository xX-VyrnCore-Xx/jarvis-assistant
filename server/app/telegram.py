import asyncio
import html
import logging
import re
import time

import httpx

from .config import Settings

MAX_LEN = 4096
CHUNK = 3500  # margine per i tag HTML aggiunti dopo la divisione
log = logging.getLogger("jarvis.telegram")


def _table(lines: list[str]) -> str:
    """Tabella markdown -> testo a colonne allineate (Telegram non ha tabelle: si usa un blocco a larghezza fissa)."""
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines if not re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", ln)]
    if not rows:
        return ""
    cols = max(len(r) for r in rows)
    rows = [r + [""] * (cols - len(r)) for r in rows]
    w = [min(28, max(len(r[i]) for r in rows)) for i in range(cols)]
    fmt = lambda r: " │ ".join(r[i][:w[i]].ljust(w[i]) for i in range(cols)).rstrip()  # noqa: E731
    out = [fmt(rows[0]), "─┼─".join("─" * x for x in w)] + [fmt(r) for r in rows[1:]]
    return "\n".join(out)


def to_html(text: str) -> str:
    """Markdown leggero del modello -> HTML di Telegram: grassetto, corsivo, barrato, spoiler, codice (con evidenziazione per linguaggio),
    link, titoli, elenchi annidati, citazioni, linee orizzontali e tabelle (a colonne allineate)."""
    stash: list[str] = []

    def keep(markup: str) -> str:
        stash.append(markup)
        return f"\x00{len(stash) - 1}\x00"

    def code_block(m: re.Match) -> str:
        lang, body = m.group(1) or "", html.escape(m.group(2).strip(chr(10)), quote=False)
        return keep(f'<pre><code class="language-{lang}">{body}</code></pre>' if re.fullmatch(r"[\w+#-]{1,20}", lang) else f"<pre>{body}</pre>")

    text = re.sub(r"```([\w+#-]*)\n?(.*?)```", code_block, text, flags=re.S)
    text = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)
    # tabelle: righe consecutive con | e una riga di separazione
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", lines[i + 1]) and "-" in lines[i + 1]:
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(keep(f"<pre>{html.escape(_table(lines[i:j]), quote=False)}</pre>"))
            i = j
        else:
            out.append(lines[i])
            i += 1
    text = html.escape("\n".join(out), quote=False)
    text = re.sub(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", "──────────", text, flags=re.M)
    text = re.sub(r"^#\s+(.+)$", r"<b>▎\1</b>", text, flags=re.M)
    text = re.sub(r"^#{2,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^(\s{2,})[-*•]\s+", lambda m: "    ◦ ", text, flags=re.M)
    text = re.sub(r"^\s*[-*•]\s+", "• ", text, flags=re.M)
    text = re.sub(r"(?:^&gt;\s?.*(?:\n|$))+", lambda m: "<blockquote>" + re.sub(r"^&gt;\s?", "", m.group(0).rstrip("\n"), flags=re.M) + "</blockquote>\n", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text, flags=re.S)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text, flags=re.S)
    text = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", lambda m: f'<a href="{m.group(2).replace(chr(34), "%22")}">{m.group(1)}</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text).strip("\n")


def split_text(text: str, size: int = CHUNK) -> list[str]:
    """Divide a fine paragrafo/riga così non si spezzano parole o formattazione; un blocco di codice tagliato a metà viene chiuso e riaperto."""
    parts: list[str] = []
    reopen = ""
    while len(text) > size:
        cut = max(text.rfind("\n\n", 0, size), text.rfind("\n", 0, size), text.rfind(" ", 0, size))
        cut = cut if cut > size // 3 else size
        part = reopen + text[:cut].rstrip()
        reopen = ""
        if part.count("```") % 2:
            lang = re.findall(r"```([\w+#-]*)", part)[-1]
            part += "\n```"
            reopen = f"```{lang}\n"
        parts.append(part)
        text = text[cut:].lstrip()
    return parts + ([reopen + text] if text.strip() else [])


class Telegram:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client or httpx.AsyncClient(timeout=30)
        self.api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self.health: dict = {"mode": "", "url_ok": None, "pending": 0, "checked_at": 0.0, "last_error": "", "last_error_at": 0}

    @property
    def enabled(self) -> bool:
        return bool(self.s.telegram_bot_token and self.s.telegram_owner_id)

    async def _post(self, method: str, **kw) -> httpx.Response:
        """POST all'API del bot, a prova di intoppi: 429 (troppi messaggi) → attende quanto richiesto; errori di rete e 5xx → fino a 4 tentativi con pausa crescente."""
        last: Exception | None = None
        for attempt in range(4):
            try:
                r = await self._client.post(f"{self.api}/{method}", **kw)
            except httpx.TransportError as e:
                last = e
                await asyncio.sleep(0.6 * (attempt + 1) ** 2)
                continue
            if r.status_code == 429:
                try:
                    wait = float(r.json().get("parameters", {}).get("retry_after", 1))
                except (ValueError, TypeError):
                    wait = 1.0
                log.info("Telegram chiede di rallentare: attendo %.0f s", wait)
                await asyncio.sleep(min(wait, 8))
                continue
            if r.status_code >= 500:
                last = httpx.HTTPStatusError("errore del server Telegram", request=r.request, response=r)
                await asyncio.sleep(0.6 * (attempt + 1) ** 2)
                continue
            return r
        if last:
            raise last
        return r  # type: ignore[possibly-undefined]

    async def send(self, chat_id: int, text: str, markup: dict | None = None) -> None:  # noqa: D401
        """Invia formattando in HTML; se Telegram rifiuta la formattazione ripiega sul testo semplice."""
        chunks = split_text(text or "…") or ["…"]
        for n, part in enumerate(chunks):
            extra = {"reply_markup": markup} if markup and n == len(chunks) - 1 else {}
            r = await self._post("sendMessage", json={
                "chat_id": chat_id, "text": to_html(part), "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}, **extra})
            if r.status_code == 400:  # HTML non valido: meglio un messaggio brutto che nessun messaggio
                r = await self._post("sendMessage", json={"chat_id": chat_id, "text": part[:MAX_LEN], **extra})
            r.raise_for_status()

    async def download_file(self, file_id: str) -> bytes:
        r = await self._client.post(f"{self.api}/getFile", json={"file_id": file_id})
        r.raise_for_status()
        path = r.json()["result"]["file_path"]
        d = await self._client.get(f"https://api.telegram.org/file/bot{self.s.telegram_bot_token}/{path}", timeout=60)
        d.raise_for_status()
        return d.content

    async def send_id(self, chat_id: int, text: str, markup: dict | None = None, silent: bool = False) -> int:
        """Come send ma restituisce l'id dell'ultimo messaggio (serve per modificarlo mentre la risposta arriva)."""
        chunks = split_text(text or "…") or ["…"]
        mid = 0
        for n, part in enumerate(chunks):
            extra = {"reply_markup": markup} if markup and n == len(chunks) - 1 else {}
            r = await self._post("sendMessage", json={
                "chat_id": chat_id, "text": to_html(part), "parse_mode": "HTML", "disable_notification": silent,
                "link_preview_options": {"is_disabled": True}, **extra})
            if r.status_code == 400:
                r = await self._post("sendMessage", json={"chat_id": chat_id, "text": part[:MAX_LEN], "disable_notification": silent, **extra})
            r.raise_for_status()
            mid = r.json()["result"]["message_id"]
        return mid

    async def edit(self, chat_id: int, message_id: int, text: str, markup: dict | None = None, html: bool = True) -> bool:
        """Modifica un messaggio (HTML, con ripiego sul testo semplice). False se non è cambiato o non si può modificare."""
        body: dict = {"chat_id": chat_id, "message_id": message_id, "text": (to_html(text) if html else text)[:MAX_LEN]}
        if html:
            body["parse_mode"] = "HTML"
        if markup is not None:
            body["reply_markup"] = markup
        r = await self._post("editMessageText", json=body)
        if r.status_code == 400 and html and "not modified" not in r.text:
            return await self.edit(chat_id, message_id, text, markup, html=False)
        return r.status_code == 200

    async def set_commands(self, commands: list[tuple[str, str]]) -> None:
        r = await self._post("setMyCommands", json={"commands": [{"command": c, "description": d} for c, d in commands]})
        r.raise_for_status()

    async def set_profile(self, description: str, short: str) -> None:
        """Testo mostrato nella schermata iniziale del bot e sul suo profilo; il tasto menu apre l'elenco dei comandi."""
        for method, body in (("setMyDescription", {"description": description[:512]}), ("setMyShortDescription", {"short_description": short[:120]}),
                             ("setChatMenuButton", {"menu_button": {"type": "commands"}})):
            await self._post(method, json=body)

    async def react(self, chat_id: int, message_id: int, emoji: str | None) -> None:
        """Reazione al messaggio dell'utente (👀 = «ricevuto, ci lavoro»); emoji=None la toglie. Mai un errore: è solo cortesia."""
        try:
            await self._post("setMessageReaction", json={"chat_id": chat_id, "message_id": message_id, "reaction": [{"type": "emoji", "emoji": emoji}] if emoji else []})
        except Exception:
            pass

    async def webhook_url(self) -> str:
        return (await self.webhook_info()).get("url", "")

    async def webhook_info(self) -> dict:
        r = await self._post("getWebhookInfo")
        r.raise_for_status()
        return r.json().get("result", {})

    async def delete_webhook(self, drop_pending: bool = False) -> None:
        r = await self._post("deleteWebhook", json={"drop_pending_updates": drop_pending})
        r.raise_for_status()

    async def get_updates(self, offset: int, timeout: int = 25) -> list[dict]:
        r = await self._client.post(f"{self.api}/getUpdates", json={"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]}, timeout=timeout + 15)
        r.raise_for_status()
        return r.json().get("result", [])

    async def send_buttons(self, chat_id: int, text: str, buttons: list[tuple[str, str]]) -> None:
        """buttons: [(testo, callback_data)] su una riga."""
        r = await self._post("sendMessage", json={"chat_id": chat_id, "text": to_html(text), "parse_mode": "HTML", "link_preview_options": {"is_disabled": True},
                                                   "reply_markup": {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}})
        if r.status_code == 400:
            r = await self._post("sendMessage", json={"chat_id": chat_id, "text": text, "reply_markup": {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}})
        r.raise_for_status()

    async def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            await self._post("answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})
        except httpx.HTTPError:
            pass  # il callback scade comunque dopo qualche secondo

    async def clear_buttons(self, chat_id: int, message_id: int, text: str) -> None:
        await self._post("editMessageText", json={"chat_id": chat_id, "message_id": message_id, "text": text})

    async def notify_owner(self, text: str) -> None:
        await self.send(self.s.telegram_owner_id, text)

    async def typing(self, chat_id: int) -> None:
        await self._client.post(f"{self.api}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=8)

    async def ensure_webhook(self, url: str) -> bool:
        """Rende questo server l'unico destinatario del bot: se un altro (vecchio) servizio ha impostato il suo
        webhook, lo sostituisce e scarta gli aggiornamenti arretrati. True se ha dovuto riprendere il controllo."""
        current = await self.webhook_url()
        if current == url:
            return False
        log.warning("webhook del bot diverso (%s): riprendo il controllo", current or "assente")
        await self.set_webhook(url, drop_pending=True)
        return True

    async def set_webhook(self, url: str, drop_pending: bool = False) -> None:
        r = await self._post("setWebhook", json={
            "url": url, "secret_token": self.s.telegram_webhook_secret, "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": drop_pending, "max_connections": 8})
        r.raise_for_status()

    async def check_webhook(self, url: str) -> str:
        """Controllo periodico del collegamento. Riprende il webhook se è di un altro servizio o assente; lo riarma se Telegram segnala
        consegne fallite da poco (server addormentato, rete, certificato). Aggiorna `self.health`. Restituisce: ok | ripreso | riarmato."""
        info = await self.webhook_info()
        now = time.time()
        err_at = int(info.get("last_error_date") or 0)
        recent_err = bool(err_at and now - err_at < 900)
        self.health = {"mode": "webhook", "url_ok": info.get("url") == url, "pending": int(info.get("pending_update_count") or 0), "checked_at": now,
                       "last_error": (info.get("last_error_message") or "") if recent_err else "", "last_error_at": err_at if recent_err else 0}
        if info.get("url") != url:
            log.warning("webhook del bot diverso (%s): riprendo il controllo", info.get("url") or "assente")
            await self.set_webhook(url, drop_pending=bool(info.get("url")))
            self.health["url_ok"] = True
            return "ripreso"
        if recent_err:
            log.warning("Telegram segnala consegne fallite (%s): riarmo il webhook", (info.get("last_error_message") or "")[:80])
            await self.set_webhook(url, drop_pending=False)
            return "riarmato"
        return "ok"
