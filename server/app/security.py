"""Difese di base: blocco dopo troppi tentativi, limite di richieste, intestazioni di sicurezza."""
import time
from collections import deque

from fastapi import Request


def client_ip(request_or_scope) -> str:
    """IP del client dietro il proxy di Render: l'ultimo elemento di X-Forwarded-For lo aggiunge il proxy stesso."""
    headers = request_or_scope.headers
    xff = headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip()
    client = getattr(request_or_scope, "client", None)
    return client.host if client else "?"


class AuthThrottle:
    """Dopo `limit` token sbagliati da uno stesso IP, lo blocca per `lock_s` secondi (anche con il token giusto)."""

    def __init__(self, limit: int = 8, lock_s: int = 900):
        self.limit, self.lock_s = limit, lock_s
        self._fails: dict[str, int] = {}
        self._locked: dict[str, float] = {}

    def retry_after(self, ip: str) -> int:
        until = self._locked.get(ip, 0)
        left = int(until - time.time())
        if left <= 0:
            self._locked.pop(ip, None)
            return 0
        return left

    def fail(self, ip: str) -> None:
        n = self._fails.get(ip, 0) + 1
        if n >= self.limit:
            self._locked[ip] = time.time() + self.lock_s
            n = 0
        self._fails[ip] = n
        if len(self._fails) > 5000:  # niente crescita illimitata sotto un flood di IP diversi
            self._fails.clear()

    def ok(self, ip: str) -> None:
        self._fails.pop(ip, None)


class RateLimiter:
    """Finestra scorrevole: al massimo `per_minute` richieste ogni 60 secondi."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: deque[float] = deque()

    def retry_after(self) -> int:
        now = time.time()
        while self._hits and now - self._hits[0] > 60:
            self._hits.popleft()
        if len(self._hits) >= self.per_minute:
            return max(1, int(60 - (now - self._hits[0])))
        return 0

    def hit(self) -> None:
        self._hits.append(time.time())


class SecurityHeaders:
    """ASGI puro (non BaseHTTPMiddleware): non interferisce con le risposte in streaming di /v1."""

    LIMITS = {"/api/stt": 4_000_000}  # il parlato registrato (30 s) pesa più di un messaggio

    def __init__(self, app, max_body: int = 1_000_000):
        self.app, self.max_body = app, max_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope["path"]
        api = not path.startswith("/v1")
        if api:
            length = dict(scope["headers"]).get(b"content-length", b"0")
            if length.isdigit() and int(length) > self.LIMITS.get(path, self.max_body):
                await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"detail":"Richiesta troppo grande"}'})
                return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                h += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"strict-transport-security", b"max-age=63072000; includeSubDomains"),
                    (b"x-frame-options", b"DENY"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                    (b"cross-origin-resource-policy", b"same-site"),
                ]
                if api:
                    h += [(b"cache-control", b"no-store"), (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")]
            await send(message)

        await self.app(scope, receive, send_wrapper)
