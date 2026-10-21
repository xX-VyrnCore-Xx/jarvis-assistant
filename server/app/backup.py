"""Backup notturno cifrato di Supabase su un dataset privato di Hugging Face (lo stesso del DB di FreeLLMAPI)."""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone

import httpx

from .config import Settings

log = logging.getLogger("jarvis.backup")
HF = "https://huggingface.co"
FOLDER = "jarvis"
CARD = """---
license: other
pretty_name: JARVIS private backups
tags: [backup, private]
---
# JARVIS: backup privati

Dataset **privato** usato dal mio assistente personale. Non contiene dati pubblici.

| File | Contenuto |
|---|---|
| `freellmapi.db.backup` | database di FreeLLMAPI (chiavi dei provider), cifrato da FreeLLMAPI con `ENCRYPTION_KEY` |
| `jarvis/AAAA-MM-GG.json.enc` | export notturno di Supabase (messaggi, memorie, promemoria, notifiche), cifrato AES-256-GCM |

Si conservano gli ultimi export; la cronologia git viene compattata ogni settimana per non occupare spazio.
"""


def repo_from_url(url: str) -> str | None:
    m = re.match(r"^https://huggingface\.co/datasets/([^/]+/[^/]+)/", url or "")
    return m.group(1) if m else None


def derive_key(settings: Settings, purpose: bytes = b"jarvis-supabase-backup") -> bytes:
    secret = (settings.encryption_key or settings.jarvis_api_token).encode()
    return hmac.new(secret, purpose, hashlib.sha256).digest()


def encrypt(key: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return b"JV1" + nonce + AESGCM(key).encrypt(nonce, data, b"jarvis-backup")


def decrypt(key: bytes, blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if blob[:3] != b"JV1":
        raise ValueError("formato sconosciuto")
    return AESGCM(key).decrypt(blob[3:15], blob[15:], b"jarvis-backup")


class HFBackup:
    TABLES = {"messages": "created_at", "memories": "created_at", "reminders": "created_at", "notifications": "created_at", "tasks": "created_at",
              "brain_docs": "created_at", "brain_chunks": "created_at", "brain_entities": "updated_at", "brain_doc_entities": "doc_id", "usage_daily": "day"}

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self.repo = repo_from_url(settings.freeapi_db_backup_url)
        self.token = settings.freeapi_db_backup_token
        self.keep = settings.hf_backup_keep
        self._client = client or httpx.AsyncClient(timeout=60)

    @property
    def enabled(self) -> bool:
        return bool(self.repo and self.token and self.s.supabase_url and self.s.supabase_service_key)

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    async def export(self) -> bytes:
        base = self.s.supabase_url.rstrip("/") + "/rest/v1"
        h = {"apikey": self.s.supabase_service_key, "Authorization": f"Bearer {self.s.supabase_service_key}"}
        out: dict = {"exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
        for table, order in self.TABLES.items():
            rows: list = []
            while True:  # paginazione: PostgREST limita le risposte
                r = await self._client.get(f"{base}/{table}", headers=h,
                                           params={"select": "*", "order": f"{order}.asc", "limit": 1000, "offset": len(rows)})
                r.raise_for_status()
                page = r.json()
                rows += page
                if len(page) < 1000:
                    break
            out["tables"][table] = rows
        return json.dumps(out, ensure_ascii=False).encode()

    async def _existing(self) -> list[str]:
        r = await self._client.get(f"{HF}/api/datasets/{self.repo}/tree/main/{FOLDER}", headers=self._auth)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return sorted(f["path"] for f in r.json() if f.get("type") == "file")

    async def _has_card(self) -> bool:
        r = await self._client.head(f"{HF}/datasets/{self.repo}/resolve/main/README.md", headers=self._auth,
                                    follow_redirects=True)
        return r.status_code == 200

    async def run(self) -> str:
        now = datetime.now(timezone.utc)
        path = f"{FOLDER}/{now:%Y-%m-%d}.json.enc"
        existing = await self._existing()
        if path in existing:
            return f"{path} già presente, nulla da fare"
        blob = encrypt(derive_key(self.s), await self.export())
        old = existing
        stale = old[: max(0, len(old) + 1 - self.keep)]
        ops = [{"key": "header", "value": {"summary": f"Backup Supabase {now:%Y-%m-%d}"}},
               {"key": "file", "value": {"path": path, "encoding": "base64", "content": base64.b64encode(blob).decode()}}]
        if not await self._has_card():
            ops.append({"key": "file", "value": {"path": "README.md", "encoding": "base64",
                                                 "content": base64.b64encode(CARD.encode()).decode()}})
        ops += [{"key": "deletedFile", "value": {"path": p}} for p in stale]
        r = await self._client.post(f"{HF}/api/datasets/{self.repo}/commit/main", headers={**self._auth, "Content-Type": "application/x-ndjson"},
                                    content="\n".join(json.dumps(o) for o in ops))
        r.raise_for_status()
        if now.weekday() == 6:  # domenica: compatta la cronologia (i backup di FreeLLMAPI ogni pochi minuti la gonfiano)
            sq = await self._client.post(f"{HF}/api/datasets/{self.repo}/super-squash/main", headers=self._auth,
                                         json={"message": "Compattazione settimanale"})
            if sq.status_code >= 400:
                log.warning("super-squash non riuscito (%s)", sq.status_code)
        return f"{path} ({len(blob) // 1024} KB, eliminati {len(stale)} vecchi)"
