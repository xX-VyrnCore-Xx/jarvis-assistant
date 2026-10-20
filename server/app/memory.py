from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from .config import Settings
from .crypto import Vault


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
    async def list_memories(self, limit: int) -> list[dict]: ...
    async def delete_memory(self, memory_id: int) -> None: ...
    async def clear_messages(self, session_id: str) -> None: ...
    async def add_notification(self, kind: str, title: str, body: str) -> dict: ...
    async def list_notifications(self, limit: int) -> list[dict]: ...
    async def mark_notifications_read(self, ids: list[int] | None) -> None: ...
    async def upsert_device(self, platform: str, token: str, label: str) -> None: ...
    async def list_devices(self) -> list[dict]: ...
    async def delete_device(self, token: str) -> None: ...
    async def add_task(self, text: str, list_name: str) -> int: ...
    async def list_tasks(self, list_name: str | None, include_done: bool) -> list[dict]: ...
    async def set_task_done(self, task_id: int, done: bool) -> None: ...
    async def delete_task(self, task_id: int) -> None: ...
    async def messages_between(self, start: str, end: str, limit: int) -> list[dict]: ...
    async def get_setting(self, key: str) -> str: ...
    async def set_setting(self, key: str, value: str) -> None: ...
    async def prune(self) -> None: ...


class MemoryStore:
    """Store in RAM, usato in sviluppo/test quando Supabase non è configurato."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.memories: list[str] = []
        self.reminders: list[dict] = []
        self.notifications: list[dict] = []
        self.devices: dict[str, dict] = {}
        self.settings: dict[str, str] = {}
        self.tasks: list[dict] = []

    async def add_message(self, session_id, role, content):
        self.messages.append({"session_id": session_id, "role": role, "content": content, "created_at": datetime.now(timezone.utc).isoformat()})

    async def recent_messages(self, session_id, limit):
        rows = [m for m in self.messages if m["session_id"] == session_id]
        return [{"role": m["role"], "content": m["content"]} for m in rows[-limit:]]

    async def add_memory(self, content):
        self.memories.append(content)

    async def list_memories(self, limit):
        return [{"id": i + 1, "content": m} for i, m in enumerate(self.memories) if m is not None][-limit:][::-1]

    async def delete_memory(self, memory_id):
        if 0 < memory_id <= len(self.memories):
            self.memories[memory_id - 1] = None  # l'indice resta stabile

    async def clear_messages(self, session_id):
        self.messages = [m for m in self.messages if m["session_id"] != session_id]

    async def search_memories(self, query, limit):
        words = [w for w in query.lower().split() if len(w) > 2]
        hits = [m for m in self.memories if m is not None and any(w in m.lower() for w in words)]
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

    async def add_notification(self, kind, title, body):
        row = {"id": len(self.notifications) + 1, "kind": kind, "title": title, "body": body, "read": False,
               "created_at": datetime.now(timezone.utc).isoformat()}
        self.notifications.append(row)
        return row

    async def list_notifications(self, limit):
        return list(reversed(self.notifications))[:limit]

    async def mark_notifications_read(self, ids):
        for n in self.notifications:
            if ids is None or n["id"] in ids:
                n["read"] = True

    async def upsert_device(self, platform, token, label):
        self.devices[token] = {"platform": platform, "token": token, "label": label}

    async def list_devices(self):
        return list(self.devices.values())

    async def delete_device(self, token):
        self.devices.pop(token, None)

    async def add_task(self, text, list_name):
        self.tasks.append({"id": len(self.tasks) + 1, "list": list_name, "text": text, "done": False})
        return len(self.tasks)

    async def list_tasks(self, list_name, include_done):
        return [t for t in self.tasks if (list_name is None or t["list"] == list_name) and (include_done or not t["done"])]

    async def set_task_done(self, task_id, done):
        for t in self.tasks:
            if t["id"] == task_id:
                t["done"] = done

    async def delete_task(self, task_id):
        self.tasks = [t for t in self.tasks if t["id"] != task_id]

    async def messages_between(self, start, end, limit):
        return [m for m in self.messages if start <= m["created_at"] < end][:limit]

    async def get_setting(self, key):
        return self.settings.get(key, "")

    async def set_setting(self, key, value):
        self.settings[key] = value

    async def prune(self):
        pass


class SupabaseStore:
    """Store su Supabase tramite PostgREST (solo HTTPS, nessun driver Postgres)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, vault: Vault | None = None):
        self.vault = vault or Vault("")
        self.base = settings.supabase_url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
        }
        # connessioni riutilizzate: meno handshake TLS verso Supabase
        self._client = client or httpx.AsyncClient(timeout=20, limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=60))

    async def _get(self, table: str, params: dict) -> list[dict]:
        r = await self._client.get(f"{self.base}/{table}", params=params, headers=self.headers)
        r.raise_for_status()
        return r.json()

    async def _insert(self, table: str, row: dict) -> None:
        h = {**self.headers, "Prefer": "return=minimal"}
        r = await self._client.post(f"{self.base}/{table}", json=row, headers=h)
        r.raise_for_status()

    async def add_message(self, session_id, role, content):
        await self._insert("messages", {"session_id": session_id, "role": role, "content": self.vault.seal(content)})

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
        return [{"role": r["role"], "content": self.vault.open(r["content"])} for r in reversed(rows)]

    async def add_memory(self, content):
        await self._insert("memories", {"content": self.vault.seal(content), "terms": self.vault.terms(content)})

    async def search_memories(self, query, limit):
        if self.vault.enabled:  # il testo è cifrato: si cerca sull'indice cieco
            terms = self.vault.terms(query)
            if not terms:
                return []
            params = {"select": "content", "terms": "ov.{" + ",".join(terms) + "}"}
        else:
            params = {"select": "content", "content": f"wfts(italian).{query}"}
        rows = await self._get("memories", {**params, "order": "created_at.desc", "limit": limit})
        return [self.vault.open(r["content"]) for r in rows]


    async def list_memories(self, limit):
        rows = await self._get("memories", {"select": "id,content", "order": "created_at.desc", "limit": limit})
        return [{"id": r["id"], "content": self.vault.open(r["content"])} for r in rows]

    async def delete_memory(self, memory_id):
        r = await self._client.delete(f"{self.base}/memories", params={"id": f"eq.{int(memory_id)}"}, headers=self.headers)
        r.raise_for_status()

    async def clear_messages(self, session_id):
        r = await self._client.delete(f"{self.base}/messages", params={"session_id": f"eq.{session_id}"}, headers=self.headers)
        r.raise_for_status()

    async def add_reminder(self, text, due_at):
        await self._insert("reminders", {"text": self.vault.seal(text), "due_at": due_at.isoformat()})

    def _reminders(self, rows):
        return [{**r, "text": self.vault.open(r["text"])} for r in rows]

    async def list_reminders(self):
        return self._reminders(await self._get(
            "reminders", {"select": "id,text,due_at", "done": "eq.false", "order": "due_at.asc", "limit": 50}))

    async def due_reminders(self, now):
        return self._reminders(await self._get(
            "reminders",
            {"select": "id,text,due_at", "done": "eq.false", "due_at": f"lte.{now.isoformat()}", "order": "due_at.asc"}))

    async def mark_reminder_done(self, reminder_id):
        r = await self._client.patch(
            f"{self.base}/reminders", params={"id": f"eq.{reminder_id}"}, json={"done": True}, headers=self.headers
        )
        r.raise_for_status()


    async def delete_reminder(self, reminder_id):
        r = await self._client.delete(f"{self.base}/reminders", params={"id": f"eq.{reminder_id}"}, headers=self.headers)
        r.raise_for_status()

    async def add_notification(self, kind, title, body):
        h = {**self.headers, "Prefer": "return=representation"}
        r = await self._client.post(f"{self.base}/notifications", json={"kind": kind, "title": self.vault.seal(title), "body": self.vault.seal(body)}, headers=h)
        r.raise_for_status()
        return {**r.json()[0], "title": title, "body": body}

    async def list_notifications(self, limit):
        rows = await self._get(
            "notifications", {"select": "id,kind,title,body,read,created_at", "order": "created_at.desc", "limit": limit})
        return [{**n, "title": self.vault.open(n["title"]), "body": self.vault.open(n["body"])} for n in rows]

    async def mark_notifications_read(self, ids):
        params = {"id": f"in.({','.join(str(int(i)) for i in ids)})"} if ids is not None else {"read": "eq.false"}
        r = await self._client.patch(f"{self.base}/notifications", params=params, json={"read": True}, headers=self.headers)
        r.raise_for_status()

    async def upsert_device(self, platform, token, label):
        h = {**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
        row = {"platform": platform, "token": token, "label": label, "last_seen": datetime.now(timezone.utc).isoformat()}
        r = await self._client.post(f"{self.base}/devices", params={"on_conflict": "token"}, json=row, headers=h)
        r.raise_for_status()

    async def list_devices(self):
        return await self._get("devices", {"select": "platform,token,label"})

    async def delete_device(self, token):
        r = await self._client.delete(f"{self.base}/devices", params={"token": f"eq.{token}"}, headers=self.headers)
        r.raise_for_status()

    async def add_task(self, text, list_name):
        h = {**self.headers, "Prefer": "return=representation"}
        r = await self._client.post(f"{self.base}/tasks", json={"text": self.vault.seal(text), "list": list_name}, headers=h)
        r.raise_for_status()
        return r.json()[0]["id"]

    async def list_tasks(self, list_name, include_done):
        params = {"select": "id,list,text,done", "order": "created_at.asc", "limit": 100}
        if list_name:
            params["list"] = f"eq.{list_name}"
        if not include_done:
            params["done"] = "eq.false"
        return [{**t, "text": self.vault.open(t["text"])} for t in await self._get("tasks", params)]

    async def set_task_done(self, task_id, done):
        r = await self._client.patch(f"{self.base}/tasks", params={"id": f"eq.{int(task_id)}"}, json={"done": done}, headers=self.headers)
        r.raise_for_status()

    async def delete_task(self, task_id):
        r = await self._client.delete(f"{self.base}/tasks", params={"id": f"eq.{int(task_id)}"}, headers=self.headers)
        r.raise_for_status()

    async def encrypt_existing(self, batch: int = 200) -> int:
        """Cifra i dati salvati prima dell'introduzione della cifratura (un lotto per tabella a ogni avvio; idempotente)."""
        if not self.vault.enabled:
            return 0
        done = 0
        for table, cols in (("messages", ["content"]), ("memories", ["content"]), ("reminders", ["text"]), ("notifications", ["title", "body"]), ("tasks", ["text"])):
            rows = await self._get(table, {"select": "id," + ",".join(cols), cols[0]: "not.like.enc1:*", "limit": batch})
            for row in rows:
                patch = {c: self.vault.seal(row[c]) for c in cols if row.get(c) is not None}
                if table == "memories":
                    patch["terms"] = self.vault.terms(row["content"])
                r = await self._client.patch(f"{self.base}/{table}", params={"id": f"eq.{row['id']}"}, json=patch, headers=self.headers)
                r.raise_for_status()
                done += 1
        return done

    async def messages_between(self, start, end, limit):
        rows = await self._get("messages", {"select": "session_id,role,content,created_at", "and": f"(created_at.gte.{start},created_at.lt.{end})",
                                            "order": "created_at.asc", "limit": limit})
        return [{**r, "content": self.vault.open(r["content"])} for r in rows]

    async def get_setting(self, key):
        rows = await self._get("app_settings", {"select": "value", "key": f"eq.{key}"})
        return rows[0]["value"] if rows else ""

    async def set_setting(self, key, value):
        h = {**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
        r = await self._client.post(f"{self.base}/app_settings", params={"on_conflict": "key"},
                                    json={"key": key, "value": value, "updated_at": datetime.now(timezone.utc).isoformat()}, headers=h)
        r.raise_for_status()

    async def prune(self):
        # Retention applicata dal server (PostgREST): messaggi 180 gg, notifiche 90 gg, promemoria fatti 60 gg, dispositivi 90 gg.
        now = datetime.now(timezone.utc)
        for table, col, days, extra in (
            ("messages", "created_at", 180, {}),
            ("notifications", "created_at", 90, {}),
            ("reminders", "due_at", 60, {"done": "eq.true"}),
            ("devices", "last_seen", 90, {}),
        ):
            cutoff = (now - timedelta(days=days)).isoformat()
            r = await self._client.delete(f"{self.base}/{table}", params={col: f"lt.{cutoff}", **extra}, headers=self.headers)
            r.raise_for_status()


def build_store(settings: Settings) -> Store:
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseStore(settings, vault=Vault(settings.encryption_key or settings.jarvis_api_token))
    return MemoryStore()
