"""Ponte verso il telefono Android: il server chiede, l'app risponde con ciò che sta SOLO sul telefono (la rubrica).

Perché così: la rubrica non viene mai copiata sul server. Quando JARVIS deve trovare un contatto, il server manda un ordine all'app aperta (flusso SSE),
l'app cerca in locale e risponde con nomi e codici opachi (mai i numeri); per chiamare, il modello usa il codice e il numero lo risolve il telefono.
L'utente può spegnere la funzione dall'app, e con l'app chiusa il ponte non risponde (niente accessi in sottofondo)."""
import asyncio
import json
import secrets

MAX_PENDING, MAX_BYTES = 8, 20_000


class BridgeError(RuntimeError):
    """Messaggio sicuro da mostrare al modello e all'utente."""


class PhoneBridge:
    def __init__(self, notifier_of):
        self._notifier_of = notifier_of
        self._waiting: dict[str, asyncio.Future] = {}

    async def ask(self, cmd: str, args: dict | None = None, timeout: float = 20.0) -> dict:
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
