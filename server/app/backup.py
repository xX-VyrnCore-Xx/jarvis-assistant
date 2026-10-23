"""Backup notturno cifrato di Supabase su un dataset privato di Hugging Face (lo stesso del DB di FreeLLMAPI)."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import zlib
from datetime import datetime, timezone

import httpx

from .config import Settings

log = logging.getLogger("jarvis.backup")
HF = "https://huggingface.co"
MAX_BLOB = 9_000_000  # oltre ~10 MB l'API di commit di Hugging Face vuole LFS: meglio saperlo prima con un messaggio chiaro
REGENERABLE = ("news", "wiki")  # notizie e Wikipedia si riscaricano: non servono nel backup (e sono la parte più grande)


class BackupError(RuntimeError):
    """Errore del backup con il passo e il motivo (mai chiavi o contenuti)."""


def explain(step: str, e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        body = ""
        try:
            body = str(e.response.json().get("error") or e.response.json().get("message") or "")[:160]
        except Exception:
            body = (e.response.text or "")[:120].replace("\n", " ")
        hint = {401: "token Hugging Face non valido", 403: "il token non può scrivere su questo dataset", 404: "dataset non trovato", 413: "file troppo grande per il commit",
                429: "troppe richieste, riprovo più tardi"}.get(e.response.status_code, "")
        return f"{step}: HTTP {e.response.status_code}{' (' + hint + ')' if hint else ''}{' – ' + body if body else ''}"
    if isinstance(e, httpx.TransportError):
        return f"{step}: rete non raggiungibile o timeout ({type(e).__name__})"
    return f"{step}: {type(e).__name__} {str(e)[:120]}"

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


def encrypt(key: bytes, data: bytes, compress: bool = False) -> bytes:
    """JV1: AES-256-GCM. JV2: come JV1 ma il testo viene prima compresso (i backup grandi restano sotto i limiti di Hugging Face)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    if compress:
        return b"JV2" + nonce + AESGCM(key).encrypt(nonce, zlib.compress(data, 9), b"jarvis-backup")
    return b"JV1" + nonce + AESGCM(key).encrypt(nonce, data, b"jarvis-backup")


def decrypt(key: bytes, blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if blob[:3] not in (b"JV1", b"JV2"):
        raise ValueError("formato sconosciuto")
    raw = AESGCM(key).decrypt(blob[3:15], blob[15:], b"jarvis-backup")
    return zlib.decompress(raw) if blob[:3] == b"JV2" else raw


class HFBackup:
    # brain_docs prima di brain_chunks e brain_doc_entities: servono per escludere ciò che si può riscaricare
    TABLES = {"messages": "created_at", "memories": "created_at", "reminders": "created_at", "notifications": "created_at", "tasks": "created_at",
              "app_settings": "key", "brain_docs": "created_at", "brain_chunks": "created_at", "brain_entities": "updated_at", "brain_doc_entities": "doc_id", "usage_daily": "day"}

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

    async def _table(self, base: str, h: dict, table: str, order: str, select: str = "*", extra: dict | None = None) -> list:
        rows: list = []
        while True:  # paginazione: PostgREST limita le risposte
            try:
                r = await self._client.get(f"{base}/{table}", headers=h, params={"select": select, "order": f"{order}.asc", "limit": 500, "offset": len(rows), **(extra or {})})
                r.raise_for_status()
            except Exception as e:
                raise BackupError(explain(f"lettura di {table} da Supabase", e)) from e
            page = r.json()
            rows += page
            if len(page) < 500:
                return rows

    async def export(self) -> bytes:
        """Tutto ciò che è insostituibile. Esclusi: notizie e Wikipedia (si riscaricano) e i vettori dei frammenti (si ricalcolano da soli)."""
        base = self.s.supabase_url.rstrip("/") + "/rest/v1"
        h = {"apikey": self.s.supabase_service_key, "Authorization": f"Bearer {self.s.supabase_service_key}"}
        out: dict = {"exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}, "excluded": {"brain_sources": list(REGENERABLE), "brain_chunks": ["emb"]}}
        skip = "(" + ",".join(REGENERABLE) + ")"
        for table, order in self.TABLES.items():
            if table == "brain_docs":
                out["tables"][table] = await self._table(base, h, table, order, extra={"source": f"not.in.{skip}"})
            elif table == "brain_chunks":
                keep = {d["id"] for d in out["tables"].get("brain_docs", [])}
                cols = "id,doc_id,idx,text,terms,emb_model,created_at"
                out["tables"][table] = [c for c in await self._table(base, h, table, order, select=cols) if c.get("doc_id") in keep]
            elif table == "brain_doc_entities":
                keep = {d["id"] for d in out["tables"].get("brain_docs", [])}
                out["tables"][table] = [r for r in await self._table(base, h, table, order) if r.get("doc_id") in keep]
            else:
                out["tables"][table] = await self._table(base, h, table, order)
        return json.dumps(out, ensure_ascii=False).encode()

    async def _existing(self) -> list[str]:
        try:
            r = await self._client.get(f"{HF}/api/datasets/{self.repo}/tree/main/{FOLDER}", headers=self._auth)
            if r.status_code == 404:
                return []
            r.raise_for_status()
        except Exception as e:
            raise BackupError(explain("elenco dei backup su Hugging Face", e)) from e
        return sorted(f["path"] for f in r.json() if f.get("type") == "file")

    async def _has_card(self) -> bool:
        try:
            r = await self._client.head(f"{HF}/datasets/{self.repo}/resolve/main/README.md", headers=self._auth, follow_redirects=True)
        except httpx.HTTPError:
            return True  # nel dubbio non si riscrive
        return r.status_code == 200

    async def _commit(self, ops: list[dict]) -> None:
        """Commit su Hugging Face con tre tentativi sui guasti passeggeri (5xx, limiti di richieste, rete)."""
        last: Exception | None = None
        for attempt in range(3):
            try:
                r = await self._client.post(f"{HF}/api/datasets/{self.repo}/commit/main", headers={**self._auth, "Content-Type": "application/x-ndjson"},
                                            content="\n".join(json.dumps(o) for o in ops))
                r.raise_for_status()
                return
            except httpx.HTTPStatusError as e:
                last = e
                if e.response.status_code not in (429, 500, 502, 503, 504, 409, 412):
                    break
            except httpx.TransportError as e:
                last = e
            await asyncio.sleep(2 * 3 ** attempt)
        raise BackupError(explain("salvataggio su Hugging Face", last or RuntimeError("sconosciuto"))) from last

    async def run(self, force: bool = False) -> str:
        now = datetime.now(timezone.utc)
        path = f"{FOLDER}/{now:%Y-%m-%d}.json.enc"
        existing = await self._existing()
        if path in existing and not force:
            return f"{path} già presente, nulla da fare"
        raw = await self.export()
        blob = encrypt(derive_key(self.s), raw, compress=True)
        if len(blob) > MAX_BLOB:
            raise BackupError(f"il backup pesa {len(blob) // 1_000_000} MB dopo la compressione: oltre il limite di {MAX_BLOB // 1_000_000} MB del commit su Hugging Face")
        stale = [p for p in existing if p != path][: max(0, len([p for p in existing if p != path]) + 1 - self.keep)]
        ops = [{"key": "header", "value": {"summary": f"Backup Supabase {now:%Y-%m-%d}"}},
               {"key": "file", "value": {"path": path, "encoding": "base64", "content": base64.b64encode(blob).decode()}}]
        if not await self._has_card():
            ops.append({"key": "file", "value": {"path": "README.md", "encoding": "base64", "content": base64.b64encode(CARD.encode()).decode()}})
        ops += [{"key": "deletedFile", "value": {"path": p}} for p in stale]
        await self._commit(ops)
        if now.weekday() == 6:  # domenica: compatta la cronologia (i backup di FreeLLMAPI ogni pochi minuti la gonfiano)
            try:
                sq = await self._client.post(f"{HF}/api/datasets/{self.repo}/super-squash/main", headers=self._auth, json={"message": "Compattazione settimanale"})
                if sq.status_code >= 400:
                    log.warning("super-squash non riuscito (%s)", sq.status_code)
            except httpx.HTTPError as e:
                log.warning("super-squash non riuscito (%s)", type(e).__name__)
        return f"{path} ({len(blob) // 1024} KB da {len(raw) // 1024} KB, eliminati {len(stale)} vecchi)"
