"""Archivio del secondo cervello: versione in RAM (sviluppo/test) e versione Supabase con tutti i testi cifrati."""
import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from ..config import Settings
from ..crypto import Vault


@dataclass
class Doc:
    id: int
    source: str
    title: str
    uri: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    entities: list[tuple[str, str]] = field(default_factory=list)  # (tipo, nome)
    content_hash: str = ""
    importance: float = 0.5
    pinned: bool = False
    access_count: int = 0
    enriched: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Chunk:
    id: int
    doc_id: int
    idx: int
    text: str
    terms: list[str] = field(default_factory=list)
    emb: bytes | None = None
    emb_model: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryBrainStore:
    """Archivio in RAM: stessa interfaccia di quello Supabase."""

    def __init__(self) -> None:
        self.docs: dict[int, Doc] = {}
        self.uri_hash: dict[str, int] = {}
        self.chunks: dict[int, Chunk] = {}
        self.entities: dict[int, tuple[str, str, str]] = {}  # id -> (tipo, chiave, nome)
        self.doc_entities: dict[int, set[int]] = {}
        self._doc_n = self._chunk_n = self._ent_n = 0
        self.vault = Vault("")

    async def find_doc(self, uri_hash: str = "", content_hash: str = "") -> Doc | None:
        if uri_hash and uri_hash in self.uri_hash:
            return self.docs.get(self.uri_hash[uri_hash])
        if content_hash:
            return next((d for d in self.docs.values() if d.content_hash == content_hash), None)
        return None

    async def create_doc(self, doc: Doc, uri_hash: str, tag_terms: list[str]) -> int:
        self._doc_n += 1
        doc.id, doc.created_at, doc.updated_at = self._doc_n, now_iso(), now_iso()
        self.docs[doc.id] = doc
        if uri_hash:
            self.uri_hash[uri_hash] = doc.id
        return doc.id

    async def update_doc(self, doc_id: int, **fields) -> None:
        d = self.docs[doc_id]
        for k, v in fields.items():
            if k != "tag_terms":
                setattr(d, k, v)
        d.updated_at = now_iso()

    async def get_doc(self, doc_id: int) -> Doc | None:
        return self.docs.get(doc_id)

    async def get_docs(self, ids: list[int]) -> dict[int, Doc]:
        return {i: self.docs[i] for i in ids if i in self.docs}

    async def list_docs(self, limit: int = 30, offset: int = 0, source: str | None = None, pinned: bool | None = None) -> list[Doc]:
        rows = [d for d in self.docs.values() if (not source or d.source == source) and (pinned is None or d.pinned == pinned)]
        return sorted(rows, key=lambda d: d.updated_at, reverse=True)[offset:offset + limit]

    async def delete_doc(self, doc_id: int) -> None:
        self.docs.pop(doc_id, None)
        self.chunks = {k: c for k, c in self.chunks.items() if c.doc_id != doc_id}
        self.doc_entities.pop(doc_id, None)
        self.uri_hash = {h: i for h, i in self.uri_hash.items() if i != doc_id}

    async def touch(self, doc_ids: list[int]) -> None:
        for i in doc_ids:
            if i in self.docs:
                self.docs[i].access_count += 1

    async def replace_chunks(self, doc_id: int, items: list[tuple[int, str, list[str], bytes | None, str]]) -> list[int]:
        self.chunks = {k: c for k, c in self.chunks.items() if c.doc_id != doc_id}
        ids = []
        for idx, text, terms, emb, model in items:
            self._chunk_n += 1
            self.chunks[self._chunk_n] = Chunk(self._chunk_n, doc_id, idx, text, terms, emb, model)
            ids.append(self._chunk_n)
        return ids

    async def get_chunks(self, ids: list[int]) -> dict[int, Chunk]:
        return {i: self.chunks[i] for i in ids if i in self.chunks}

    async def doc_chunks(self, doc_id: int) -> list[Chunk]:
        return sorted((c for c in self.chunks.values() if c.doc_id == doc_id), key=lambda c: c.idx)

    async def index_rows(self, after_id: int, limit: int) -> list[Chunk]:
        return sorted((c for c in self.chunks.values() if c.id > after_id), key=lambda c: c.id)[:limit]

    async def chunks_without_vector(self, model: str, limit: int) -> list[Chunk]:
        return [c for c in self.chunks.values() if c.emb_model != model][:limit]

    async def set_chunk_vector(self, chunk_id: int, emb: bytes, model: str) -> None:
        self.chunks[chunk_id].emb, self.chunks[chunk_id].emb_model = emb, model

    async def docs_to_enrich(self, limit: int) -> list[Doc]:
        return [d for d in self.docs.values() if not d.enriched and d.source not in ("journal", "wiki")][:limit]

    # ---- entità e grafo
    async def upsert_entity(self, kind: str, key_hash: str, name: str) -> int:
        for i, (k, h, n) in self.entities.items():
            if h == key_hash:
                return i
        self._ent_n += 1
        self.entities[self._ent_n] = (kind, key_hash, name)
        return self._ent_n

    async def link_entities(self, doc_id: int, entity_ids: list[int]) -> None:
        self.doc_entities[doc_id] = set(entity_ids)

    async def find_entities(self, key_hashes: list[str]) -> list[tuple[int, str, str]]:
        return [(i, k, n) for i, (k, h, n) in self.entities.items() if h in set(key_hashes)]

    async def top_entities(self, limit: int = 10) -> list[tuple[int, str, str, int]]:
        """Le entità più citate: (id, tipo, nome, documenti)."""
        counts: dict[int, int] = {}
        for ents in self.doc_entities.values():
            for e in ents:
                counts[e] = counts.get(e, 0) + 1
        best = sorted(counts, key=lambda e: -counts[e])[:limit]
        return [(e, self.entities[e][0], self.entities[e][2], counts[e]) for e in best]

    async def docs_for_entities(self, entity_ids: list[int]) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for d, ents in self.doc_entities.items():
            for e in ents & set(entity_ids):
                out.setdefault(e, []).append(d)
        return out

    async def entities_of(self, doc_id: int) -> list[tuple[int, str, str]]:
        return [(e, self.entities[e][0], self.entities[e][2]) for e in self.doc_entities.get(doc_id, set())]

    async def stats(self) -> dict:
        by_src: dict[str, int] = {}
        for d in self.docs.values():
            by_src[d.source] = by_src.get(d.source, 0) + 1
        return {"docs": len(self.docs), "chunks": len(self.chunks), "entities": len(self.entities), "by_source": by_src}


class SupabaseBrainStore(MemoryBrainStore):
    """Stessa interfaccia, su PostgREST. Titoli, URI, riassunti, tag, entità, testi ed embedding sono cifrati dal server."""

    def __init__(self, settings: Settings, vault: Vault, client: httpx.AsyncClient | None = None):
        self.vault = vault
        self.base = settings.supabase_url.rstrip("/") + "/rest/v1"
        self.headers = {"apikey": settings.supabase_service_key, "Authorization": f"Bearer {settings.supabase_service_key}"}
        self._client = client or httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=60))

    # ---- utilità
    async def _get(self, table: str, params: dict) -> list[dict]:
        r = await self._client.get(f"{self.base}/{table}", params=params, headers=self.headers)
        r.raise_for_status()
        return r.json()

    async def _write(self, method: str, table: str, *, params: dict | None = None, body=None, prefer: str = "return=minimal") -> httpx.Response:
        r = await self._client.request(method, f"{self.base}/{table}", params=params, json=body, headers={**self.headers, "Prefer": prefer})
        r.raise_for_status()
        return r

    def _doc(self, r: dict) -> Doc:
        o = self.vault.open
        return Doc(id=r["id"], source=r["source"], title=o(r["title"]), uri=o(r["uri"]), summary=o(r["summary"]),
                   tags=json.loads(o(r["tags"]) or "[]"), entities=[tuple(e) for e in json.loads(o(r["entities"]) or "[]")],
                   content_hash=r["content_hash"], importance=r["importance"], pinned=r["pinned"], access_count=r["access_count"],
                   enriched=r["enriched"], created_at=r["created_at"], updated_at=r["updated_at"])

    def _seal_doc_fields(self, f: dict) -> dict:
        out = {}
        for k, v in f.items():
            if k in ("title", "uri", "summary"):
                out[k] = self.vault.seal(v)
            elif k == "tags":
                out[k] = self.vault.seal(json.dumps(v, ensure_ascii=False))
            elif k == "entities":
                out[k] = self.vault.seal(json.dumps(v, ensure_ascii=False))
            elif k in ("importance", "pinned", "enriched", "content_hash", "source", "tag_terms"):
                out[k] = v
        return out

    @staticmethod
    def _emb_enc(vault: Vault, raw: bytes | None) -> str:
        return vault.seal(base64.b64encode(raw).decode()) if raw else ""

    @staticmethod
    def _emb_dec(vault: Vault, s: str) -> bytes | None:
        if not s:
            return None
        plain = vault.open(s)
        try:
            return base64.b64decode(plain) if plain and not plain.startswith("[dato") else None
        except ValueError:
            return None

    def _chunk(self, r: dict) -> Chunk:
        return Chunk(r["id"], r["doc_id"], r["idx"], self.vault.open(r.get("text", "")), r.get("terms") or [], self._emb_dec(self.vault, r.get("emb", "")), r.get("emb_model", ""))

    # ---- documenti
    async def find_doc(self, uri_hash: str = "", content_hash: str = "") -> Doc | None:
        if uri_hash:
            rows = await self._get("brain_docs", {"select": "*", "uri_hash": f"eq.{uri_hash}", "limit": 1})
        elif content_hash:
            rows = await self._get("brain_docs", {"select": "*", "content_hash": f"eq.{content_hash}", "limit": 1})
        else:
            return None
        return self._doc(rows[0]) if rows else None

    async def create_doc(self, doc: Doc, uri_hash: str, tag_terms: list[str]) -> int:
        body = {**self._seal_doc_fields({"source": doc.source, "title": doc.title, "uri": doc.uri, "summary": doc.summary, "tags": doc.tags,
                                         "entities": [list(e) for e in doc.entities], "importance": doc.importance, "pinned": doc.pinned,
                                         "content_hash": doc.content_hash, "enriched": doc.enriched, "tag_terms": tag_terms}),
                "uri_hash": uri_hash or None}
        r = await self._write("POST", "brain_docs", body=body, prefer="return=representation")
        return r.json()[0]["id"]

    async def update_doc(self, doc_id: int, **fields) -> None:
        if "entities" in fields:
            fields["entities"] = [list(e) for e in fields["entities"]]
        await self._write("PATCH", "brain_docs", params={"id": f"eq.{doc_id}"}, body={**self._seal_doc_fields(fields), "updated_at": now_iso()})

    async def get_doc(self, doc_id: int) -> Doc | None:
        rows = await self._get("brain_docs", {"select": "*", "id": f"eq.{doc_id}"})
        return self._doc(rows[0]) if rows else None

    async def get_docs(self, ids: list[int]) -> dict[int, Doc]:
        if not ids:
            return {}
        rows = await self._get("brain_docs", {"select": "*", "id": f"in.({','.join(str(int(i)) for i in ids)})"})
        return {r["id"]: self._doc(r) for r in rows}

    async def list_docs(self, limit: int = 30, offset: int = 0, source: str | None = None, pinned: bool | None = None) -> list[Doc]:
        p = {"select": "*", "order": "updated_at.desc", "limit": limit, "offset": offset}
        if source:
            p["source"] = f"eq.{source}"
        if pinned is not None:
            p["pinned"] = f"eq.{str(pinned).lower()}"
        return [self._doc(r) for r in await self._get("brain_docs", p)]

    async def delete_doc(self, doc_id: int) -> None:
        await self._write("DELETE", "brain_docs", params={"id": f"eq.{int(doc_id)}"})  # i frammenti seguono (ON DELETE CASCADE)

    async def touch(self, doc_ids: list[int]) -> None:
        for i in doc_ids[:10]:
            rows = await self._get("brain_docs", {"select": "access_count", "id": f"eq.{i}"})
            if rows:
                await self._write("PATCH", "brain_docs", params={"id": f"eq.{i}"}, body={"access_count": rows[0]["access_count"] + 1, "accessed_at": now_iso()})

    # ---- frammenti
    async def replace_chunks(self, doc_id: int, items: list[tuple[int, str, list[str], bytes | None, str]]) -> list[int]:
        await self._write("DELETE", "brain_chunks", params={"doc_id": f"eq.{doc_id}"})
        if not items:
            return []
        body = [{"doc_id": doc_id, "idx": idx, "text": self.vault.seal(text), "terms": terms, "emb": self._emb_enc(self.vault, emb), "emb_model": model}
                for idx, text, terms, emb, model in items]
        r = await self._write("POST", "brain_chunks", body=body, prefer="return=representation")
        return [row["id"] for row in sorted(r.json(), key=lambda x: x["idx"])]

    async def get_chunks(self, ids: list[int]) -> dict[int, Chunk]:
        if not ids:
            return {}
        rows = await self._get("brain_chunks", {"select": "id,doc_id,idx,text,terms", "id": f"in.({','.join(str(int(i)) for i in ids)})"})
        return {r["id"]: self._chunk(r) for r in rows}

    async def doc_chunks(self, doc_id: int) -> list[Chunk]:
        rows = await self._get("brain_chunks", {"select": "id,doc_id,idx,text,terms", "doc_id": f"eq.{doc_id}", "order": "idx.asc"})
        return [self._chunk(r) for r in rows]

    async def index_rows(self, after_id: int, limit: int) -> list[Chunk]:
        rows = await self._get("brain_chunks", {"select": "id,doc_id,idx,terms,emb,emb_model", "id": f"gt.{after_id}", "order": "id.asc", "limit": limit})
        return [self._chunk({**r, "text": ""}) for r in rows]

    async def chunks_without_vector(self, model: str, limit: int) -> list[Chunk]:
        rows = await self._get("brain_chunks", {"select": "id,doc_id,idx,text,terms,emb_model", "emb_model": f"neq.{model}", "limit": limit})
        return [self._chunk(r) for r in rows]

    async def set_chunk_vector(self, chunk_id: int, emb: bytes, model: str) -> None:
        await self._write("PATCH", "brain_chunks", params={"id": f"eq.{chunk_id}"}, body={"emb": self._emb_enc(self.vault, emb), "emb_model": model})

    async def docs_to_enrich(self, limit: int) -> list[Doc]:
        rows = await self._get("brain_docs", {"select": "*", "enriched": "eq.false", "source": "not.in.(journal,wiki)", "order": "created_at.desc", "limit": limit})
        return [self._doc(r) for r in rows]

    # ---- entità e grafo
    async def upsert_entity(self, kind: str, key_hash: str, name: str) -> int:
        r = await self._write("POST", "brain_entities", params={"on_conflict": "key_hash"},
                              body={"kind": kind, "key_hash": key_hash, "name": self.vault.seal(name), "updated_at": now_iso()},
                              prefer="resolution=merge-duplicates,return=representation")
        return r.json()[0]["id"]

    async def link_entities(self, doc_id: int, entity_ids: list[int]) -> None:
        await self._write("DELETE", "brain_doc_entities", params={"doc_id": f"eq.{doc_id}"})
        if entity_ids:
            await self._write("POST", "brain_doc_entities", body=[{"doc_id": doc_id, "entity_id": e} for e in entity_ids])

    async def find_entities(self, key_hashes: list[str]) -> list[tuple[int, str, str]]:
        if not key_hashes:
            return []
        rows = await self._get("brain_entities", {"select": "id,kind,name", "key_hash": f"in.({','.join(key_hashes)})"})
        return [(r["id"], r["kind"], self.vault.open(r["name"])) for r in rows]

    async def top_entities(self, limit: int = 10) -> list[tuple[int, str, str, int]]:
        links = await self._get("brain_doc_entities", {"select": "entity_id", "limit": 5000})
        counts: dict[int, int] = {}
        for r in links:
            counts[r["entity_id"]] = counts.get(r["entity_id"], 0) + 1
        best = sorted(counts, key=lambda e: -counts[e])[:limit]
        if not best:
            return []
        rows = await self._get("brain_entities", {"select": "id,kind,name", "id": f"in.({','.join(str(i) for i in best)})"})
        by_id = {r["id"]: r for r in rows}
        return [(e, by_id[e]["kind"], self.vault.open(by_id[e]["name"]), counts[e]) for e in best if e in by_id]

    async def docs_for_entities(self, entity_ids: list[int]) -> dict[int, list[int]]:
        if not entity_ids:
            return {}
        rows = await self._get("brain_doc_entities", {"select": "doc_id,entity_id", "entity_id": f"in.({','.join(str(int(i)) for i in entity_ids)})"})
        out: dict[int, list[int]] = {}
        for r in rows:
            out.setdefault(r["entity_id"], []).append(r["doc_id"])
        return out

    async def entities_of(self, doc_id: int) -> list[tuple[int, str, str]]:
        links = await self._get("brain_doc_entities", {"select": "entity_id", "doc_id": f"eq.{doc_id}"})
        if not links:
            return []
        rows = await self._get("brain_entities", {"select": "id,kind,name", "id": f"in.({','.join(str(r['entity_id']) for r in links)})"})
        return [(r["id"], r["kind"], self.vault.open(r["name"])) for r in rows]

    async def stats(self) -> dict:
        async def count(table: str, extra: dict | None = None) -> int:
            r = await self._client.get(f"{self.base}/{table}", params={"select": "id", "limit": 1, **(extra or {})}, headers={**self.headers, "Prefer": "count=exact"})
            r.raise_for_status()
            return int(r.headers.get("content-range", "0/0").split("/")[-1] or 0)

        by_src = {}
        for src in ("note", "memory", "journal", "web", "file", "chat", "drive", "gmail"):
            n = await count("brain_docs", {"source": f"eq.{src}"})
            if n:
                by_src[src] = n
        return {"docs": await count("brain_docs"), "chunks": await count("brain_chunks"), "entities": await count("brain_entities"), "by_source": by_src}


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
