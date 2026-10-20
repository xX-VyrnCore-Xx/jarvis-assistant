from datetime import datetime
from typing import Protocol

import httpx

from .config import Settings


class Store(Protocol):
    async def add_message(self, session_id: str, role: str, content: str) -> None: ...
    async def recent_messages(self, session_id: str, limit: int) -> list[dict]: ...
    async def add_memory(self, content: str) -> None: ...
    async def search_memories(self, query: str, limit: int) -> list[str]: ...
    async def add_reminder(self, text: str, due_at: datetime) -> None: ...
    async def list_reminders(self) -> list[dict]: ...
    async def due_reminders(self, now: datetime) -> list[dict]: ...
    async def mark_reminder_done(self, reminder_id: int) -> None: ...
    async def delete_reminder(self, reminder_id: int) -> None: ...


class MemoryStore:
    """Store in RAM, usato in sviluppo/test quando Supabase non è configurato."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.memories: list[str] = []
        self.reminders: list[dict] = []

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


    async def add_reminder(self, text, due_at):
        self.reminders.append({"id": len(self.reminders) + 1, "text": text, "due_at": due_at.isoformat(), "done": False})

    async def list_reminders(self):
        return sorted((r for r in self.reminders if not r["done"]), key=lambda r: r["due_at"])

    async def due_reminders(self, now):
        return [r for r in await self.list_reminders() if datetime.fromisoformat(r["due_at"]) <= now]

    async def mark_reminder_done(self, reminder_id):
        for r in self.reminders:
            if r["id"] == reminder_id:
                r["done"] = True


    async def delete_reminder(self, reminder_id):
        self.reminders = [r for r in self.reminders if r["id"] != reminder_id]


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


    async def add_reminder(self, text, due_at):
        await self._insert("reminders", {"text": text, "due_at": due_at.isoformat()})

    async def list_reminders(self):
        return await self._get(
            "reminders", {"select": "id,text,due_at", "done": "eq.false", "order": "due_at.asc", "limit": 50}
        )

    async def due_reminders(self, now):
        return await self._get(
            "reminders",
            {"select": "id,text,due_at", "done": "eq.false", "due_at": f"lte.{now.isoformat()}", "order": "due_at.asc"},
        )

    async def mark_reminder_done(self, reminder_id):
        r = await self._client.patch(
            f"{self.base}/reminders", params={"id": f"eq.{reminder_id}"}, json={"done": True}, headers=self.headers
        )
        r.raise_for_status()


    async def delete_reminder(self, reminder_id):
        r = await self._client.delete(f"{self.base}/reminders", params={"id": f"eq.{reminder_id}"}, headers=self.headers)
        r.raise_for_status()


def build_store(settings: Settings) -> Store:
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseStore(settings)
    return MemoryStore()
