import httpx

from .config import Settings

MAX_LEN = 4096


class Telegram:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client or httpx.AsyncClient(timeout=30)
        self.api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    @property
    def enabled(self) -> bool:
        return bool(self.s.telegram_bot_token and self.s.telegram_owner_id)

    async def send(self, chat_id: int, text: str) -> None:
        for i in range(0, max(len(text), 1), MAX_LEN):
            r = await self._client.post(
                f"{self.api}/sendMessage", json={"chat_id": chat_id, "text": text[i : i + MAX_LEN]}
            )
            r.raise_for_status()

    async def notify_owner(self, text: str) -> None:
        await self.send(self.s.telegram_owner_id, text)

    async def typing(self, chat_id: int) -> None:
        await self._client.post(f"{self.api}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

    async def set_webhook(self, url: str) -> None:
        r = await self._client.post(
            f"{self.api}/setWebhook",
            json={
                "url": url,
                "secret_token": self.s.telegram_webhook_secret,
                "allowed_updates": ["message"],
                "drop_pending_updates": False,
            },
        )
        r.raise_for_status()
