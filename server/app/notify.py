"""Notifiche in tempo reale: archivio, flusso SSE verso le app aperte, push FCM verso Android, Telegram."""
import asyncio
import base64
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .memory import Store

log = logging.getLogger("jarvis.notify")
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
# canali Android (creati dall'app): importanza e suono dipendono dal tipo
CHANNELS = {"reminder": "reminders", "alert": "alerts", "pending": "alerts", "update": "updates", "brain": "general", "proactive": "general", "info": "general"}
ROUTES = {"reminder": "reminders", "alert": "tokens", "pending": "chat", "update": "more", "brain": "brain", "proactive": "chat", "info": "chat"}
CRITICAL = {"reminder", "alert", "pending"}  # arrivano anche nelle ore silenziose
DEFAULT_PREFS = {"kinds": {k: {"inapp": True, "push": True, "telegram": k in ("reminder", "alert", "update")} for k in ("reminder", "alert", "pending", "update", "brain", "proactive", "info")},
                 "quiet": {"enabled": True, "from": "23:00", "to": "07:30"}}
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

    async def send(self, device_token: str, title: str, body: str, kind: str, route: str = "", nid: int = 0, silent: bool = False) -> bool:
        """True se consegnata; False se il token non è più valido (da rimuovere)."""
        channel = CHANNELS.get(kind, "general")
        android: dict = {"priority": "NORMAL" if silent else "HIGH", "notification": {"channel_id": channel, "tag": f"{kind}-{nid}" if nid else kind}}
        if kind == "update":
            android["notification"]["tag"] = "update"  # un solo avviso di aggiornamento alla volta
        r = await self._client.post(
            f"https://fcm.googleapis.com/v1/projects/{self.account['project_id']}/messages:send",
            headers={"Authorization": f"Bearer {await self._access_token()}"},
            json={"message": {
                "token": device_token,
                "notification": {"title": title, "body": body[:300]},
                "data": {"kind": kind, "route": route, "id": str(nid)},
                "android": android,
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
        self._recent: dict[tuple, float] = {}
        self._pushes: list[float] = []  # ultime consegne FCM: tetto orario
        self._prefs: dict | None = None

    # ------------------------------------------------------------------ preferenze
    async def prefs(self) -> dict:
        if self._prefs is None:
            try:
                saved = json.loads(await self.store.get_setting("notify_prefs") or "{}")
            except ValueError:
                saved = {}
            merged = json.loads(json.dumps(DEFAULT_PREFS))
            for k, v in (saved.get("kinds") or {}).items():
                if k in merged["kinds"] and isinstance(v, dict):
                    merged["kinds"][k].update({c: bool(v[c]) for c in ("inapp", "push", "telegram") if c in v})
            merged["quiet"].update({k: v for k, v in (saved.get("quiet") or {}).items() if k in ("enabled", "from", "to")})
            self._prefs = merged
        return self._prefs

    async def set_prefs(self, patch: dict) -> dict:
        cur = await self.prefs()
        for k, v in (patch.get("kinds") or {}).items():
            if k in cur["kinds"] and isinstance(v, dict):
                cur["kinds"][k].update({c: bool(v[c]) for c in ("inapp", "push", "telegram") if c in v})
        q = patch.get("quiet") or {}
        if "enabled" in q:
            cur["quiet"]["enabled"] = bool(q["enabled"])
        for k in ("from", "to"):
            if isinstance(q.get(k), str) and len(q[k]) == 5 and q[k][2] == ":" and q[k].replace(":", "").isdigit():
                cur["quiet"][k] = q[k]
        await self.store.set_setting("notify_prefs", json.dumps(cur))
        return cur

    def in_quiet_hours(self, quiet: dict, now: datetime | None = None) -> bool:
        if not quiet.get("enabled"):
            return False
        now = now or datetime.now(ZoneInfo(self.settings.timezone))
        cur = now.strftime("%H:%M")
        lo, hi = quiet["from"], quiet["to"]
        return lo <= cur or cur < hi if lo > hi else lo <= cur < hi

    # ------------------------------------------------------------------ flusso in tempo reale
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    @property
    def listeners(self) -> int:
        return len(self._subs)

    def broadcast(self, payload: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                self._subs.discard(q)  # client lento: si riconnette e recupera dall'archivio

    async def mark_read(self, ids: list[int] | None) -> None:
        await self.store.mark_notifications_read(ids)
        self.broadcast({"event": "read", "ids": ids})  # le altre app azzerano il contatore subito

    # ------------------------------------------------------------------ invio
    async def push(self, kind: str, title: str, body: str = "", telegram: bool | None = None, meta: dict | None = None) -> dict:
        """Salva la notifica e la consegna ai canali scelti dall'utente (app aperte, push Android, Telegram), con ore silenziose,
        deduplicazione (stesso avviso entro 10 minuti) e tetto orario alle push."""
        prefs = await self.prefs()
        kp = prefs["kinds"].get(kind, {"inapp": True, "push": True, "telegram": False})
        key = (kind, title, body)
        now = time.monotonic()
        self._recent = {k: t for k, t in self._recent.items() if now - t < 600}
        if key in self._recent and kind not in ("pending",):
            return {"id": 0, "kind": kind, "title": title, "body": body, "read": True, "duplicate": True}
        self._recent[key] = now
        meta = {**(meta or {}), "route": ROUTES.get(kind, "chat")}
        row = await self.store.add_notification(kind, title, body, meta)
        quiet = self.in_quiet_hours(prefs["quiet"]) and kind not in CRITICAL
        if kp["inapp"]:
            self.broadcast(row)
        want_tg = kp["telegram"] if telegram is None else (telegram and kp["telegram"])
        want_push = kp["push"] and not quiet
        results = await asyncio.gather(self._telegram(want_tg and not quiet, row), self._fcm(row, want_push), return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log.warning("consegna notifica fallita: %s", type(r).__name__)
        return row

    async def _telegram(self, wanted: bool, row: dict) -> None:
        if not (wanted and self.tg and self.tg.enabled):
            return
        text = f"{row['title']}\n{row['body']}".strip()
        kind, meta = row["kind"], row.get("meta") or {}
        if kind == "reminder" and row.get("id"):
            await self.tg.send_buttons(self.tg.s.telegram_owner_id, text, [("⏰ +10 min", f"rs:{row['id']}:10"), ("⏰ +1 ora", f"rs:{row['id']}:60"), ("✔ Fatto", f"rs:{row['id']}:0")])
        elif kind == "update" and meta.get("url"):
            await self.tg.send(self.tg.s.telegram_owner_id, text, {"inline_keyboard": [[{"text": "Scarica", "url": meta["url"]}]]})
        else:
            await self.tg.notify_owner(text)

    async def _fcm(self, row: dict, wanted: bool) -> None:
        if not (wanted and self.fcm.enabled):
            return
        now = time.monotonic()
        self._pushes = [t for t in self._pushes if now - t < 3600]
        if len(self._pushes) >= 30:  # tetto orario: un errore a catena non deve inondare il telefono
            return
        self._pushes.append(now)
        route = (row.get("meta") or {}).get("route", "")
        for d in await self.store.list_devices():
            if d["platform"] != "android":
                continue
            if not await self.fcm.send(d["token"], row["title"], row["body"], row["kind"], route, row.get("id", 0)):
                await self.store.delete_device(d["token"])
