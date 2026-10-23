"""Ponte verso il telefono Android: il server chiede, l'app risponde con ciò che sta SOLO sul telefono (la rubrica).

Perché così: la rubrica non viene mai copiata sul server. Quando JARVIS deve trovare un contatto, il server manda un ordine all'app aperta (flusso SSE),
l'app cerca in locale e risponde con nomi e codici opachi (mai i numeri); per chiamare, il modello usa il codice e il numero lo risolve il telefono.
L'utente può spegnere la funzione dall'app, e con l'app chiusa il ponte non risponde (niente accessi in sottofondo)."""
import asyncio
import json
import re
import secrets
import time
from collections import deque

MAX_PENDING, MAX_BYTES = 8, 20_000
MAX_ASKS_PER_MIN = 12  # un modello fuori controllo non può scorrere la rubrica a raffica
PHONE_LIKE = re.compile(r"\+?\d[\d ()./-]{5,}\d")
CONTROL = re.compile(r"[\x00-\x1f\x7f\u2028\u2029\[\]<>{}`]")
SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")


def clean_contacts(rows: object, limit: int = 8) -> list[dict]:
    """Difesa in profondità: anche se l'app (o chi la imita) mandasse altro, al modello arrivano solo nome, codice e due indicazioni.
    Numeri nei nomi, a capo e simboli che servono a iniettare istruzioni vengono tolti."""
    out: list[dict] = []
    for c in rows if isinstance(rows, list) else []:
        if not isinstance(c, dict):
            continue
        name = PHONE_LIKE.sub("[numero]", CONTROL.sub(" ", str(c.get("name", ""))))
        name = " ".join(name.split())[:60]
        cid = SAFE_ID.sub("", str(c.get("id", "")))[:20]
        if not name or not cid:
            continue
        n = c.get("numbers", 1)
        out.append({"id": cid, "name": name, "numbers": n if isinstance(n, int) and 0 < n < 20 else 1, "whatsapp": c.get("whatsapp") is True})
        if len(out) >= limit:
            break
    return out


class BridgeError(RuntimeError):
    """Messaggio sicuro da mostrare al modello e all'utente."""


class PhoneBridge:
    def __init__(self, notifier_of):
        self._notifier_of = notifier_of
        self._waiting: dict[str, asyncio.Future] = {}
        self._recent: deque[float] = deque(maxlen=MAX_ASKS_PER_MIN)
        self.log: deque[dict] = deque(maxlen=50)  # solo in memoria: chi, quando, quanti risultati (mai i numeri)
        self.enabled = True  # interruttore lato server: spento, nessun ordine parte verso il telefono

    async def ask(self, cmd: str, args: dict | None = None, timeout: float = 20.0) -> dict:
        if not self.enabled:
            raise BridgeError("L'accesso ai contatti è disattivato dall'utente.")
        now = time.monotonic()
        if len(self._recent) == self._recent.maxlen and now - self._recent[0] < 60:
            raise BridgeError("Troppe ricerche in rubrica in poco tempo: riprova tra un minuto.")
        self._recent.append(now)
        if len(self._waiting) >= MAX_PENDING:
            raise BridgeError("Troppe richieste al telefono in corso: riprova tra poco.")
        notifier = self._notifier_of()
        if not notifier.listeners:
            raise BridgeError("Il telefono non è collegato: apri l'app JARVIS e riprova.")
        rid = secrets.token_urlsafe(8)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiting[rid] = fut
        try:
            notifier.broadcast({"event": "command", "id": rid, "cmd": cmd, "args": args or {}})
            try:
                res = await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError:
                raise BridgeError("Il telefono non ha risposto: l'app JARVIS deve essere aperta.") from None
        finally:
            self._waiting.pop(rid, None)
        if not res.get("ok"):
            raise BridgeError(str(res.get("error") or "Il telefono ha rifiutato la richiesta.")[:200])
        return res.get("data") or {}

    def resolve(self, rid: str, ok: bool, data: object = None, error: str = "") -> bool:
        fut = self._waiting.get(rid)
        if not fut or fut.done():
            return False
        if len(json.dumps(data, default=str)) > MAX_BYTES:
            ok, data, error = False, None, "Risposta troppo grande."
        fut.set_result({"ok": ok, "data": data, "error": error})
        return True

    def audit(self, what: str, query: str, found: int) -> None:
        self.log.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "what": what, "query": query[:60], "found": found})
