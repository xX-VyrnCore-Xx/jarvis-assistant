"""Sincronizzazione in tempo reale: ogni modifica ai dati, da qualunque origine (Telegram, app, strumenti, API),
avvisa subito le app aperte e fa riallineare il secondo cervello."""
import asyncio
import logging

log = logging.getLogger("jarvis.livesync")

# metodo dello Store → ambito che cambia
SCOPES = {
    "add_memory": "memories", "delete_memory": "memories",
    "add_task": "tasks", "set_task_done": "tasks", "delete_task": "tasks",
    "add_reminder": "reminders", "update_reminder": "reminders", "mark_reminder_done": "reminders", "delete_reminder": "reminders",
}
BRAIN_SCOPES = ("memories", "tasks")  # ambiti che il cervello rispecchia
DEBOUNCE_S = 1.5


class LiveStore:
    """Avvolge lo Store: inoltra tutto invariato e, dopo ogni scrittura riuscita, chiama `on_change(scope)`."""

    def __init__(self, inner, on_change=None):
        self._inner = inner
        self.on_change = on_change

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        scope = SCOPES.get(name)
        if not scope or not callable(attr):
            return attr

        async def wrapped(*a, **kw):
            result = await attr(*a, **kw)
            if self.on_change:
                try:
                    self.on_change(scope)
                except Exception:
                    log.exception("sync %s", scope)
            return result

        return wrapped


class Live:
    """Raccoglie le modifiche ravvicinate: una sola notifica alle app e un solo riallineamento del cervello."""

    def __init__(self, notifier, mirror=None, delay: float = DEBOUNCE_S):
        self.notifier, self.mirror, self.delay = notifier, mirror, delay
        self._brain: asyncio.Task | None = None

    def changed(self, scope: str) -> None:
        self.notifier.sync(scope)
        if scope in BRAIN_SCOPES and self.mirror:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            if not self._brain or self._brain.done():
                self._brain = loop.create_task(self._align())

    async def _align(self) -> None:
        await asyncio.sleep(self.delay)
        try:
            await self.mirror.sync_all()
            self.notifier.sync("brain")
        except Exception:
            log.exception("riallineamento del cervello")
