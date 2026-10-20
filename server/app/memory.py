from typing import Protocol

import httpx

from .config import Settings


class Store(Protocol):
    async def add_message(self, session_id: str, role: str, content: str) -> None: ...
    async def recent_messages(self, session_id: str, limit: int) -> list[dict]: ...
    async def add_memory(self, content: str) -> None: ...
    async def search_memories(self, query: str, limit: int) -> list[str]: ...


class MemoryStore:
    """Store in RAM, usato in sviluppo/test quando Supabase non è configurato."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.memories: list[str] = []

    async def add_message(self, session_id, role, content):
        self.messages.append({"session_id": session_id, "role": role, "content": content})

    async def recent_messages(self, session_id, limit):
        rows = [m for m in self.messages if m["session_id"] == session_id]
        return [{"role": m["role"], "content": m["content"]} for m in rows[-limit:]]

    async def add_memory(self, content):
        self.memories.append(content)

    async def search_memories(self, query, limit):
        words = [w for w in query.lower().split() if len(w) > 2]
        hits = [m for m in self.memories if any(w in m.lower() for w in words)]
        return hits[-limit:]


class SupabaseStore:
    """Store su Supabase tramite PostgREST (solo HTTPS, nessun driver Postgres)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.base = settings.supabase_url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
        }
        self._client = client or httpx.AsyncClient(timeout=20)

    async def _get(self, table: str, params: dict) -> list[dict]:
        r = await self._client.get(f"{self.base}/{table}", params=params, headers=self.headers)
        r.raise_for_status()
        return r.json()

    async def _insert(self, table: str, row: dict) -> None:
        h = {**self.headers, "Prefer": "return=minimal"}
        r = await self._client.post(f"{self.base}/{table}", json=row, headers=h)
        r.raise_for_status()

    async def add_message(self, session_id, role, content):
        await self._insert("messages", {"session_id": session_id, "role": role, "content": content})

    async def recent_messages(self, session_id, limit):
        rows = await self._get(
            "messages",
            {
                "select": "role,content",
                "session_id": f"eq.{session_id}",
                "order": "created_at.desc",
                "limit": limit,
            },
        )
        return list(reversed(rows))

    async def add_memory(self, content):
        await self._insert("memories", {"content": content})

    async def search_memories(self, query, limit):
        rows = await self._get(
            "memories",
            {
                "select": "content",
                "content": f"wfts(italian).{query}",
                "order": "created_at.desc",
                "limit": limit,
            },
        )
        return [r["content"] for r in rows]


def build_store(settings: Settings) -> Store:
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseStore(settings)
    return MemoryStore()
