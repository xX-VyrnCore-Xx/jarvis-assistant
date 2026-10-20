import html
import logging
import re

import httpx

from .config import Settings

MAX_LEN = 4096
CHUNK = 3500  # margine per i tag HTML aggiunti dopo la divisione
log = logging.getLogger("jarvis.telegram")


def to_html(text: str) -> str:
    """Markdown leggero del modello -> HTML di Telegram (grassetto, corsivo, codice, link, titoli, elenchi)."""
    stash: list[str] = []

    def keep(markup: str) -> str:
        stash.append(markup)
        return f"\x00{len(stash) - 1}\x00"

    text = re.sub(r"```[\w+-]*\n?(.*?)```", lambda m: keep(f"<pre>{html.escape(m.group(1).strip(chr(10)))}</pre>"), text, flags=re.S)
    text = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = html.escape(text, quote=False)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^\s*[-*•]\s+", "• ", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text, flags=re.S)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", lambda m: f'<a href="{m.group(2).replace(chr(34), "%22")}">{m.group(1)}</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)


def split_text(text: str, size: int = CHUNK) -> list[str]:
    """Divide a fine paragrafo/riga così non si spezzano parole o formattazione."""
    parts: list[str] = []
    while len(text) > size:
        cut = max(text.rfind("\n\n", 0, size), text.rfind("\n", 0, size), text.rfind(" ", 0, size))
        cut = cut if cut > size // 3 else size
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return parts + ([text] if text.strip() else [])


class Telegram:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client or httpx.AsyncClient(timeout=30)
        self.api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    @property
    def enabled(self) -> bool:
        return bool(self.s.telegram_bot_token and self.s.telegram_owner_id)

    async def send(self, chat_id: int, text: str, markup: dict | None = None) -> None:
        """Invia formattando in HTML; se Telegram rifiuta la formattazione ripiega sul testo semplice."""
        chunks = split_text(text or "…") or ["…"]
        for n, part in enumerate(chunks):
            extra = {"reply_markup": markup} if markup and n == len(chunks) - 1 else {}
            r = await self._client.post(f"{self.api}/sendMessage", json={
                "chat_id": chat_id, "text": to_html(part), "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}, **extra})
            if r.status_code == 400:  # HTML non valido: meglio un messaggio brutto che nessun messaggio
                r = await self._client.post(f"{self.api}/sendMessage", json={"chat_id": chat_id, "text": part[:MAX_LEN], **extra})
            r.raise_for_status()

    async def download_file(self, file_id: str) -> bytes:
        r = await self._client.post(f"{self.api}/getFile", json={"file_id": file_id})
        r.raise_for_status()
        path = r.json()["result"]["file_path"]
        d = await self._client.get(f"https://api.telegram.org/file/bot{self.s.telegram_bot_token}/{path}", timeout=60)
        d.raise_for_status()
        return d.content

    async def set_commands(self, commands: list[tuple[str, str]]) -> None:
        r = await self._client.post(f"{self.api}/setMyCommands", json={
            "commands": [{"command": c, "description": d} for c, d in commands]})
        r.raise_for_status()

    async def webhook_url(self) -> str:
        r = await self._client.post(f"{self.api}/getWebhookInfo")
        r.raise_for_status()
        return r.json().get("result", {}).get("url", "")

    async def send_buttons(self, chat_id: int, text: str, buttons: list[tuple[str, str]]) -> None:
        """buttons: [(testo, callback_data)] su una riga."""
        r = await self._client.post(
            f"{self.api}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "reply_markup": {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in buttons]]}},
        )
        r.raise_for_status()

    async def answer_callback(self, callback_id: str, text: str = "") -> None:
        await self._client.post(f"{self.api}/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})

    async def clear_buttons(self, chat_id: int, message_id: int, text: str) -> None:
        await self._client.post(f"{self.api}/editMessageText", json={"chat_id": chat_id, "message_id": message_id, "text": text})

    async def notify_owner(self, text: str) -> None:
        await self.send(self.s.telegram_owner_id, text)

    async def typing(self, chat_id: int) -> None:
        await self._client.post(f"{self.api}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

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
        r = await self._client.post(
            f"{self.api}/setWebhook",
            json={
                "url": url,
                "secret_token": self.s.telegram_webhook_secret,
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": drop_pending,
            },
        )
        r.raise_for_status()
