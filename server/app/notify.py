"""Notifiche in tempo reale: archivio, flusso SSE verso le app aperte, push FCM verso Android, Telegram."""
import asyncio
import base64
import json
import logging
import time

import httpx

from .config import Settings
from .memory import Store

log = logging.getLogger("jarvis.notify")
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class FCM:
    """Firebase Cloud Messaging HTTP v1, autenticato con l'account di servizio (JWT RS256, nessun SDK)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.account: dict = {}
        raw = settings.firebase_service_account_json.strip()
        if raw:
            try:
                self.account = json.loads(raw)
                if not all(self.account.get(k) for k in ("project_id", "client_email", "private_key")):
                    raise ValueError("campi mancanti")
            except ValueError:
                log.error("FIREBASE_SERVICE_ACCOUNT_JSON non valido: push Android disattivate")
                self.account = {}
        self._client = client or httpx.AsyncClient(timeout=15)
        self._token: tuple[str, float] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.account)

    def _assertion(self, now: float) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = {"iss": self.account["client_email"], "scope": SCOPE, "aud": TOKEN_URL,
                  "iat": int(now), "exp": int(now) + 3600}
        signing = f"{head}.{_b64(json.dumps(claims).encode())}"
        key = serialization.load_pem_private_key(self.account["private_key"].encode(), password=None)
        return f"{signing}.{_b64(key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256()))}"

    async def _access_token(self) -> str:
        now = time.time()
        if self._token and self._token[1] - 60 > now:
            return self._token[0]
        r = await self._client.post(TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self._assertion(now)})
        r.raise_for_status()
        j = r.json()
        self._token = (j["access_token"], now + int(j.get("expires_in", 3600)))
        return self._token[0]

    async def send(self, device_token: str, title: str, body: str, kind: str) -> bool:
        """True se consegnata; False se il token non è più valido (da rimuovere)."""
        r = await self._client.post(
            f"https://fcm.googleapis.com/v1/projects/{self.account['project_id']}/messages:send",
            headers={"Authorization": f"Bearer {await self._access_token()}"},
            json={"message": {
                "token": device_token,
                "notification": {"title": title, "body": body[:300]},
                "data": {"kind": kind},
                "android": {"priority": "HIGH", "notification": {"channel_id": "jarvis"}},
            }},
        )
        if r.status_code in (400, 404) and ("UNREGISTERED" in r.text or "INVALID_ARGUMENT" in r.text):
            return False
        r.raise_for_status()
        return True


class Notifier:
    def __init__(self, settings: Settings, store: Store, tg=None, fcm: FCM | None = None):
        self.settings = settings
        self.store = store
        self.tg = tg
        self.fcm = fcm or FCM(settings)
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    @property
    def listeners(self) -> int:
        return len(self._subs)

    async def push(self, kind: str, title: str, body: str = "", telegram: bool = False) -> dict:
        row = await self.store.add_notification(kind, title, body)
        for q in list(self._subs):
            try:
                q.put_nowait(row)
            except asyncio.QueueFull:
                self._subs.discard(q)  # client lento: si riconnette e recupera dall'archivio
        results = await asyncio.gather(self._telegram(telegram, title, body), self._fcm(row), return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log.warning("consegna notifica fallita: %s", type(r).__name__)
        return row

    async def _telegram(self, wanted: bool, title: str, body: str) -> None:
        if wanted and self.tg and self.tg.enabled:
            await self.tg.notify_owner(f"{title}\n{body}".strip())

    async def _fcm(self, row: dict) -> None:
        if not self.fcm.enabled:
            return
        for d in await self.store.list_devices():
            if d["platform"] != "android":
                continue
            if not await self.fcm.send(d["token"], row["title"], row["body"], row["kind"]):
                await self.store.delete_device(d["token"])
