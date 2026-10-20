import asyncio
import time

from .budget import describe, summarize
from .freellm_admin import FreeLLMAdmin

TTL_S = 60.0


class BudgetService:
    """Token disponibili, con una cache breve: le app lo chiedono spesso e il calcolo interroga FreeLLMAPI."""

    def __init__(self, admin: FreeLLMAdmin):
        self.admin = admin
        self._cache: tuple[float, dict] | None = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.admin.enabled

    async def get(self, force: bool = False) -> dict:
        async with self._lock:
            if not force and self._cache and time.time() - self._cache[0] < TTL_S:
                return self._cache[1]
            free_tier = await self.admin.get("/api/free-tier")
            usage = await self.admin.usage()
            result = summarize(free_tier, usage)
            self._cache = (time.time(), result)
            return result

    async def text(self) -> str:
        return describe(await self.get())
