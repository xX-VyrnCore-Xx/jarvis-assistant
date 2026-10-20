"""Accesso al pannello interno di FreeLLMAPI (solo loopback, mai esposto) per leggere budget e quote.

Nello stesso container JARVIS crea da solo l'account del pannello (dal loopback il primo account non richiede
codice) con una password derivata da ENCRYPTION_KEY: niente da configurare, e dopo un ripristino del database
la password è la stessa.
"""
import hashlib
import hmac

import httpx

from .config import Settings
from .llm import LLMError, read_unified_key

EMAIL = "jarvis@jarvis.local"


class AdminError(RuntimeError):
    pass


def derive_password(secret: str) -> str:
    return hmac.new(secret.encode(), b"jarvis-freellm-dashboard", hashlib.sha256).hexdigest()[:48]


class FreeLLMAdmin:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.base = settings.freellm_internal_url.rstrip("/")
        secret = settings.encryption_key or settings.jarvis_api_token
        self.password = derive_password(secret) if secret else ""
        self.db_path = settings.freellm_db_path
        self._client = client or httpx.AsyncClient(timeout=20)
        self._token = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.password)

    async def _login(self) -> None:
        body = {"email": EMAIL, "password": self.password}
        r = await self._client.post(f"{self.base}/api/auth/login", json=body)
        if r.status_code == 401:  # primo avvio: l'account non esiste ancora
            r = await self._client.post(f"{self.base}/api/auth/setup", json=body)
            if r.status_code == 409:
                raise AdminError("l'account del pannello FreeLLMAPI esiste con una password diversa")
        if r.status_code not in (200, 201):
            raise AdminError(f"accesso al pannello FreeLLMAPI fallito (HTTP {r.status_code})")
        self._token = r.json()["token"]

    async def get(self, path: str) -> dict:
        if not self.enabled:
            raise AdminError("FreeLLMAPI non è in questo container")
        for attempt in (1, 2):
            if not self._token:
                await self._login()
            r = await self._client.get(f"{self.base}{path}", headers={"Authorization": f"Bearer {self._token}"})
            if r.status_code == 401 and attempt == 1:
                self._token = ""  # sessione scaduta o database ripristinato
                continue
            if r.status_code != 200:
                raise AdminError(f"{path}: HTTP {r.status_code}")
            return r.json()
        raise AdminError("autenticazione fallita")

    async def ready(self) -> bool:
        try:
            r = await self._client.get(f"{self.base}/api/ping", timeout=3)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def usage(self) -> dict:
        """Consumo del mese: /v1/usage accetta solo la chiave unificata (letta dal database, stesso container)."""
        try:
            key = read_unified_key(self.db_path)
        except LLMError as e:
            raise AdminError(str(e)) from e
        r = await self._client.get(f"{self.base}/v1/usage", headers={"Authorization": f"Bearer {key}"})
        if r.status_code != 200:
            raise AdminError(f"/v1/usage: HTTP {r.status_code}")
        return r.json()
