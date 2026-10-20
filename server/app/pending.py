"""Azioni sensibili in attesa di conferma umana.

Il modello (o un testo malevolo letto in un'email) non può eseguirle da solo: crea una richiesta, e solo
l'utente, dall'app o da Telegram, può approvarla. È una difesa lato server, non una promessa nel prompt.
"""
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class Pending:
    id: str
    kind: str
    summary: str
    executor: Callable[[], Awaitable[str]] = field(repr=False)
    expires_at: float
    status: str = "pending"  # pending | approved | rejected | expired | failed
    result: str = ""

    def public(self) -> dict:
        return {"id": self.id, "kind": self.kind, "summary": self.summary, "status": self.status,
                "expires_in": max(0, int(self.expires_at - time.time())), "result": self.result}


class PendingStore:
    def __init__(self, ttl_s: int = 600):
        self.ttl_s = ttl_s
        self._items: dict[str, Pending] = {}
        self.on_create: Callable[[Pending], None] | None = None

    def create(self, kind: str, summary: str, executor: Callable[[], Awaitable[str]]) -> Pending:
        self._prune()
        p = Pending(secrets.token_urlsafe(6), kind, summary, executor, time.time() + self.ttl_s)
        self._items[p.id] = p
        if self.on_create:
            self.on_create(p)
        return p

    def _prune(self) -> None:
        now = time.time()
        for p in list(self._items.values()):
            if p.status == "pending" and p.expires_at < now:
                p.status = "expired"
            if now - p.expires_at > 3600:  # le decise restano visibili un'ora
                del self._items[p.id]

    def list_pending(self) -> list[Pending]:
        self._prune()
        return [p for p in self._items.values() if p.status == "pending"]

    def get(self, pid: str) -> Pending | None:
        self._prune()
        return self._items.get(pid)

    async def decide(self, pid: str, approve: bool) -> Pending | None:
        p = self.get(pid)
        if p is None or p.status != "pending":
            return p
        if not approve:
            p.status = "rejected"
            return p
        p.status = "approved"
        try:
            p.result = await p.executor()
        except Exception as e:
            p.status, p.result = "failed", f"Errore: {e}"
        return p
