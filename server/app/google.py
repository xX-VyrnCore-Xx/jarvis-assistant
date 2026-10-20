import base64
import secrets
import time
import urllib.parse
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

    SETTING = "google_refresh_token"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, store=None):
        self.s = settings
        self.store = store
        self._client = client or httpx.AsyncClient(timeout=30)
        self._token = ""
        self._expires = 0.0
        self._stored = ""  # refresh token ottenuto dal collegamento guidato (cifrato nel database)
        self._states: dict[str, float] = {}

    @property
    def has_client(self) -> bool:
        return bool(self.s.google_client_id and self.s.google_client_secret)

    @property
    def refresh_token(self) -> str:
        return self.s.google_refresh_token or self._stored

    @property
    def enabled(self) -> bool:
        return self.has_client and bool(self.refresh_token)

    async def load(self) -> None:
        if not self.store:
            return
        from .backup import decrypt, derive_key

        try:
            raw = await self.store.get_setting(self.SETTING)
            if raw:
                self._stored = decrypt(derive_key(self.s), base64.b64decode(raw)).decode()
        except Exception:
            self._stored = ""  # chiave cambiata o dato illeggibile: serve ricollegare

    # ------------------------------------------------------------------ collegamento guidato
    def authorize_url(self, redirect_uri: str) -> str:
        now = time.time()
        self._states = {k: v for k, v in self._states.items() if v > now}
        state = secrets.token_urlsafe(24)
        self._states[state] = now + 600
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": self.s.google_client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state})

    async def complete(self, code: str, state: str, redirect_uri: str) -> None:
        if self._states.pop(state, 0) < time.time():
            raise ValueError("collegamento scaduto o non richiesto da te: riprova da /google")
        r = await self._client.post(TOKEN_URL, data={
            "code": code, "client_id": self.s.google_client_id, "client_secret": self.s.google_client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
        if r.status_code != 200:
            raise ValueError("Google ha rifiutato il codice (controlla l'URI di reindirizzamento)")
        refresh = r.json().get("refresh_token")
        if not refresh:
            raise ValueError("Google non ha restituito il refresh token: revoca l'accesso di JARVIS su myaccount.google.com/permissions e riprova")
        from .backup import derive_key, encrypt

        await self.store.set_setting(self.SETTING, base64.b64encode(encrypt(derive_key(self.s), refresh.encode())).decode())
        self._stored, self._token = refresh, ""

    async def _access_token(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        r = await self._client.post(
            TOKEN_URL,
            data={
                "client_id": self.s.google_client_id,
                "client_secret": self.s.google_client_secret,
                "refresh_token": self.refresh_token,
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
