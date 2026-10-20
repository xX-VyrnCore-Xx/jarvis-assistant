import asyncio
import itertools
import secrets

from fastapi import WebSocket, WebSocketDisconnect

AUTH_TIMEOUT_S = 10


class PCBridge:
    """Canale WebSocket verso l'app Windows: il server invia comandi e attende il risultato."""

    def __init__(self) -> None:
        self.ws: WebSocket | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)

    @property
    def connected(self) -> bool:
        return self.ws is not None

    async def call(self, action: str, args: dict, timeout: float = 60.0) -> str:
        if not self.ws:
            return "Il PC non è connesso: l'app JARVIS per Windows non è in esecuzione."
        cid = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[cid] = fut
        try:
            await self.ws.send_json({"type": "command", "id": cid, "action": action, "args": args})
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            return "Il PC non ha risposto in tempo."
        except Exception as e:  # connessione caduta durante l'invio
            return f"Comunicazione con il PC fallita: {e}"
        finally:
            self._pending.pop(cid, None)

    async def notify(self, text: str) -> None:
        if self.ws:
            try:
                await self.ws.send_json({"type": "notify", "text": text})
            except Exception:
                pass

    async def serve(self, ws: WebSocket, token: str) -> None:
        await ws.accept()
        try:
            hello = await asyncio.wait_for(ws.receive_json(), AUTH_TIMEOUT_S)
        except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
            await ws.close(code=4401)
            return
        if not token or not secrets.compare_digest(str(hello.get("token", "")), token):
            await ws.close(code=4401)
            return
        old, self.ws = self.ws, ws  # un solo PC alla volta: il nuovo sostituisce il vecchio
        if old:
            try:
                await old.close(code=4000)
            except Exception:
                pass
        await ws.send_json({"type": "ready"})
        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "result" and (fut := self._pending.get(msg.get("id"))) and not fut.done():
                    fut.set_result(str(msg.get("output", "")))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if self.ws is ws:
                self.ws = None
