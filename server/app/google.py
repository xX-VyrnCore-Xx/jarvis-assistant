import time
from typing import Any

import httpx

from .config import Settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleClient:
    """Chiamate REST alle API Google con refresh automatico dell'access token."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client or httpx.AsyncClient(timeout=30)
        self._token = ""
        self._expires = 0.0

    @property
    def enabled(self) -> bool:
        s = self.s
        return bool(s.google_client_id and s.google_client_secret and s.google_refresh_token)

    async def _access_token(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        r = await self._client.post(
            TOKEN_URL,
            data={
                "client_id": self.s.google_client_id,
                "client_secret": self.s.google_client_secret,
                "refresh_token": self.s.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        r.raise_for_status()
        data = r.json()
        self._token, self._expires = data["access_token"], time.time() + data.get("expires_in", 3600)
        return self._token

    async def request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {await self._access_token()}"}
        r = await self._client.request(method, url, headers=headers, **kw)
        r.raise_for_status()
        return r
