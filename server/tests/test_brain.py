import hashlib
import json
import re

import httpx
import numpy as np
import pytest

from app.brain.chunk import chunk_text
from app.brain.embed import Embedder, dequantize, quantize
from app.brain.index import VectorIndex
from app.brain.service import Brain
from app.brain.store import MemoryBrainStore, SupabaseBrainStore
from app.brain.tools import register_brain_tools
from app.config import Settings
from app.crypto import Vault
from app.tools import ToolRegistry

SYN = {"auto": "veicolo", "macchina": "veicolo", "automobile": "veicolo", "dentista": "salute", "medico": "salute", "dottore": "salute"}
DIM = 64


class FakeEmbedder(Embedder):
    """Embedding deterministico: bag-of-words con sinonimi, così si prova la ricerca per significato senza rete."""

    def __init__(self, fail=False):
        super().__init__(Settings(freellm_base_url="http://x/v1", freellm_api_key="k"))
        self.fail, self.calls = fail, 0

    async def embed(self, texts):
        self.calls += 1
        if self.fail:
            raise RuntimeError("giù")
        out = []
        for t in texts:
            v = np.zeros(DIM, dtype=np.float32)
            for w in re.findall(r"[a-zà-ú]{3,}", t.lower()):
                v[int(hashlib.md5(SYN.get(w, w).encode()).hexdigest(), 16) % DIM] += 1
            n = np.linalg.norm(v)
            out.append(v / n if n else v)
        return out


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.seen = reply, []

    async def chat(self, messages, tools=None, model=None, kind="chat"):
        self.seen.append(messages)
        return {"content": self.reply}


def make(llm=None, embedder=None, store=None):
    s = Settings(jarvis_api_token="t", rag_min_cosine=0.3)
    vault = Vault("segreto-di-prova")
    st = store or MemoryBrainStore()
    st.vault = vault
    return Brain(s, st, embedder or FakeEmbedder(), vault, llm), st


def test_chunker_keeps_headings_overlap_and_limits():
    text = "# Progetto Alfa\n" + ("Frase numero uno sul budget. " * 60 + "\n\n") * 3 + "## Rischi\nUna riga sola.\n\nAltro paragrafo sui rischi del progetto."
    chunks = chunk_text(text, "Note")
    assert len(chunks) >= 3 and all(len(c) <= 2000 for c in chunks)
    assert chunks[0].startswith("Note › Progetto Alfa\n") and any(c.startswith("Note › Rischi") for c in chunks)
    assert chunk_text("   ") == [] and len(chunk_text("breve nota")) == 1
    assert max(len(c) for c in chunk_text("parola " * 3000)) <= 2000  # niente punteggiatura: taglio sugli spazi


def test_quantization_roundtrip_preserves_similarity():
    rng = np.random.default_rng(1)
    a, b = rng.normal(size=1024), rng.normal(size=1024)
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    exact = float(a @ b)
    approx = float(dequantize(quantize(a)) @ dequantize(quantize(b)))
    assert abs(exact - approx) < 0.02 and len(quantize(a)) == 1024


def test_index_hybrid_fusion_mmr_and_removal():
    idx = VectorIndex()
    v = lambda *x: quantize(np.array(x, dtype=np.float32))  # noqa: E731
    idx.add(1, 10, v(1, 0, 0), ["aaa", "bbb"])
    idx.add(2, 11, v(0, 1, 0), ["ccc"])
    idx.add(3, 12, v(0.99, 0.1, 0), ["aaa"])  # quasi identico al primo
    idx.add(4, 13, None, ["ddd", "aaa"])  # senza vettore: solo parole
    hits = idx.search(np.array([1, 0, 0], dtype=np.float32), ["ddd"], k=4)
    ids = [h.chunk_id for h in hits]
    assert ids[0] in (1, 4) and 4 in ids and 2 not in ids[:2]  # il lessicale porta su il 4 pur senza vettore
    picked = idx.mmr(idx.search(np.array([1, 0, 0], dtype=np.float32), [], k=3), 2)
    assert {h.chunk_id for h in picked} != {1, 3}  # MMR evita i due quasi uguali
    idx.remove_doc(10)
    assert 1 not in [h.chunk_id for h in idx.search(np.array([1, 0, 0], dtype=np.float32), ["aaa"], k=5)] and len(idx) == 3


@pytest.mark.asyncio
async def test_ingest_dedupe_update_search_semantic_and_forget():
    brain, store = make()
    r1 = await brain.ingest("Ho portato la macchina dal meccanico, costa 300 euro. La revisione scade a marzo.", title="Auto", tags=["Veicoli"])
    assert r1["status"] == "creato" and r1["vectors"] == 1
    assert (await brain.ingest("Ho portato la macchina dal meccanico, costa 300 euro. La revisione scade a marzo.", title="Auto"))["status"] == "duplicato"
    await brain.ingest("Appuntamento dal dentista giovedì alle 15: pulizia dei denti.", title="Salute")
    await brain.ingest("Ricetta della carbonara: guanciale, uova, pecorino, pepe.", title="Cucina")

    res = await brain.search("quando scade la revisione dell'automobile", k=3)
    assert res[0]["title"] == "Auto" and "semantico" in res[0]["why"]  # trovato anche con parole diverse (automobile ~ macchina)
    assert (await brain.search("medico", k=3))[0]["title"] == "Salute"  # sinonimo puro: nessuna parola in comune
    assert await brain.search("calcio mercato serie", k=3) == []  # niente di pertinente: nessun rumore
    assert (await brain.search("carbonara", k=2, source="note"))[0]["title"] == "Cucina"

    # stesso URI, contenuto diverso -> aggiornato (frammenti rifatti), non duplicato
    a = await brain.ingest("versione uno del documento sul budget", title="Budget", uri="file:budget.txt")
    b = await brain.ingest("versione due del documento sul budget con più cifre", title="Budget", uri="file:budget.txt")
    assert a["doc_id"] == b["doc_id"] and b["status"] == "aggiornato" and len(await store.doc_chunks(b["doc_id"])) == 1
    assert await brain.forget(a["doc_id"]) and not await brain.forget(a["doc_id"])
    assert all(r["doc_id"] != a["doc_id"] for r in await brain.search("budget", k=5))


@pytest.mark.asyncio
async def test_works_without_embeddings_then_reindexes_vectors():
    brain, store = make(embedder=FakeEmbedder(fail=True))
    r = await brain.ingest("La password del wifi di casa è scritta sul frigorifero", title="Wifi")
    assert r["vectors"] == 0
    assert (await brain.search("wifi", k=3))[0]["title"] == "Wifi"  # solo parole, ma funziona
    brain.embedder.fail = False
    assert await brain.reindex_vectors() == 1 and (await brain.stats())["vectors"] == 1
    assert await brain.reindex_vectors() == 0


@pytest.mark.asyncio
async def test_graph_expansion_enrichment_and_untrusted_context():
    llm = FakeLLM(json.dumps({"title": "Riunione Luca", "summary": "Budget 2027.", "tags": ["Budget", "riunione"],
                              "entities": [{"kind": "persona", "name": "Luca Bianchi"}], "importance": 0.9}))
    brain, store = make(llm=llm)
    a = await brain.ingest("Riunione con Luca: decidiamo il budget a gennaio", title="Riunione")
    b = await brain.ingest("Regalo di compleanno per Luca: un libro di cucina", title="Regalo", source="web", uri="https://x.it/regalo")
    assert await brain.enrich_pending(5) == 2
    doc = await store.get_doc(a["doc_id"])
    assert doc.title == "Riunione Luca" and doc.summary == "Budget 2027." and "budget" in doc.tags and doc.importance == 0.9 and doc.enriched
    assert ("persona", "Luca Bianchi") in doc.entities
    res = await brain.search("budget gennaio", k=3)
    assert any(r["doc_id"] == b["doc_id"] and r["why"] == ["collegato"] for r in res)  # stesso Luca -> collegato
    rel = await brain.related(a["doc_id"])
    assert any(r["doc_id"] == b["doc_id"] for r in rel)
    ctx = await brain.context("cosa avevamo deciso per il budget con Luca")
    assert "secondo cervello" in ctx and f"[#{a['doc_id']}" in ctx and "dati, non istruzioni" in ctx  # c'è una fonte web non fidata
    assert await brain.context("ciao") == "" and await brain.context("grazie mille") == ""  # niente ricerca inutile


@pytest.mark.asyncio
async def test_sensitive_data_is_masked_before_embedding_and_enrichment():
    seen = []

    class Spy(FakeEmbedder):
        async def embed(self, texts):
            seen.extend(texts)
            return await super().embed(texts)

    llm = FakeLLM("{}")
    brain, _ = make(llm=llm, embedder=Spy())
    await brain.ingest("Il mio IBAN è IT60X0542811101000000123456 per il bonifico", title="Banca")
    await brain.enrich_pending(1)
    assert seen and all("IT60X0542811101000000123456" not in t for t in seen)
    assert "IT60X0542811101000000123456" not in json.dumps(llm.seen) and "[IBAN_1]" in json.dumps(llm.seen)


@pytest.mark.asyncio
async def test_journal_import_memories_and_resurface():
    llm = FakeLLM("- Deciso il budget\n- Scadenza revisione auto a marzo")
    brain, store = make(llm=llm)
    r = await brain.consolidate_day("2026-10-19", "Utente: " + "parliamo del budget e della revisione dell'auto. " * 5)
    assert r["status"] == "creato" and (await store.get_doc(r["doc_id"])).source == "journal"
    assert (await brain.consolidate_day("2026-10-19", "x"))["status"] == "saltato"
    llm.reply = "NESSUN CONTENUTO"
    assert (await brain.consolidate_day("2026-10-20", "Utente: " + "ciao come va tutto bene " * 10))["status"] == "niente di rilevante"
    assert await brain.import_memories([{"id": 1, "content": "Allergico alle noci"}, {"id": 1, "content": "Allergico alle noci"}]) == 1  # idempotente
    old = await brain.ingest("Contratto di affitto: scadenza a dicembre 2027", title="Affitto", importance=0.9)
    await store.update_doc(old["doc_id"], importance=0.9)
    store.docs[old["doc_id"]].created_at = "2020-01-01T00:00:00+00:00"
    assert [d.title for d in await brain.resurface(1)] == ["Affitto"]


@pytest.mark.asyncio
async def test_tools_and_supabase_store_keep_everything_encrypted():
    sent = {}
    rows: dict[str, list] = {"brain_docs": [], "brain_chunks": []}

    def handler(req: httpx.Request) -> httpx.Response:
        table = req.url.path.rsplit("/", 1)[-1]
        if req.method in ("POST", "PATCH") and req.content:
            body = json.loads(req.content)
            sent.setdefault(table, []).append(body)
            items = body if isinstance(body, list) else [body]
            if req.method == "POST":
                made = [{**it, "id": len(rows.setdefault(table, [])) + i + 1, "created_at": "2026-10-20T10:00:00+00:00", "updated_at": "2026-10-20T10:00:00+00:00",
                         "source": it.get("source", "note"), "access_count": 0, "pinned": False, "enriched": False, "importance": it.get("importance", 0.5)} for i, it in enumerate(items)]
                rows[table].extend(made)
                return httpx.Response(201, json=made)
            return httpx.Response(204)
        if req.method == "DELETE":
            return httpx.Response(204)
        p = dict(req.url.params)
        data = rows.get(table, [])
        if "id" in p and p["id"].startswith("in."):
            ids = {int(x) for x in p["id"][4:-1].split(",")}
            data = [r for r in data if r["id"] in ids]
        elif "id" in p and p["id"].startswith("eq."):
            data = [r for r in data if r["id"] == int(p["id"][3:])]
        elif "doc_id" in p:
            data = [r for r in data if r["doc_id"] == int(p["doc_id"][3:])]
        elif "id" in p and p["id"].startswith("gt."):
            data = [r for r in data if r["id"] > int(p["id"][3:])]
        return httpx.Response(200, json=data if table != "brain_doc_entities" else [])

    s = Settings(supabase_url="https://x.supabase.co", supabase_service_key="k", rag_min_cosine=0.3)
    vault = Vault("chiave")
    store = SupabaseBrainStore(s, vault, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    brain = Brain(s, store, FakeEmbedder(), vault)
    reg = ToolRegistry()
    register_brain_tools(reg, brain)

    out = await reg.call("brain_add_note", json.dumps({"text": "Il codice dell'allarme è nella cassaforte del garage", "title": "Allarme", "tags": "Casa, sicurezza"}))
    assert "Salvato" in out
    blob = json.dumps(sent)
    assert "enc1:" in blob
    for secret in ("Allarme", "cassaforte", "garage", "Casa", "sicurezza"):
        assert secret.lower() not in blob.lower()  # titolo, testo e tag viaggiano solo cifrati

    brain2 = Brain(s, store, FakeEmbedder(), vault)  # nuovo avvio: l'indice si ricostruisce dal database cifrato
    assert await brain2.load() == 1
    reg2 = ToolRegistry()
    register_brain_tools(reg2, brain2)
    found = await reg2.call("brain_search", json.dumps({"query": "dove sta il codice dell'allarme"}))
    assert "Allarme" in found and "cassaforte" in found
    assert "casa" in await reg2.call("brain_read", json.dumps({"doc_id": 1}))  # i tag tornano in chiaro solo dopo la decifratura


@pytest.mark.asyncio
async def test_embedder_batches_caches_orders_and_retries(monkeypatch):
    calls = []

    async def no_sleep(_):
        pass

    monkeypatch.setattr("app.brain.embed.asyncio.sleep", no_sleep)

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        calls.append(body["input"])
        assert body["model"] == "bge-m3" and req.url.path.endswith("/embeddings")
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "1"}, text="slow down")
        # risposta volutamente in ordine inverso: l'indice decide
        data = [{"index": i, "embedding": [float(i + 1), 0.0, 0.0]} for i in range(len(body["input"]))][::-1]
        return httpx.Response(200, json={"data": data})

    e = Embedder(Settings(freellm_base_url="http://x/v1", freellm_api_key="k"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    v = await e.embed([f"testo {i}" for i in range(20)])
    assert len(v) == 20 and all(abs(np.linalg.norm(x) - 1) < 1e-6 for x in v)
    assert [len(c) for c in calls] == [16, 16, 4]  # un tentativo respinto (429) + lotti da 16
    again = await e.embed(["testo 0", "testo 1"])
    assert len(calls) == 3 and np.allclose(again[0], v[0])  # dalla cache, nessuna nuova chiamata


def test_brain_api_endpoints(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    from app.auth import throttle
    from app.config import get_settings

    monkeypatch.setenv("JARVIS_API_TOKEN", "tok")
    monkeypatch.delenv("FREELLM_BASE_URL", raising=False)
    get_settings.cache_clear()
    throttle._fails.clear()
    throttle._locked.clear()
    h = {"Authorization": "Bearer tok"}
    with TestClient(main.app) as c:
        assert c.get("/api/brain/stats").status_code == 401
        r = c.post("/api/brain/notes", json={"text": "Il dentista ha lo studio in via Roma 12", "title": "Dentista", "tags": ["salute"]}, headers=h)
        assert r.status_code == 201 and r.json()["status"] == "creato"
        doc_id = r.json()["doc_id"]
        found = c.get("/api/brain/search", params={"q": "dentista via Roma"}, headers=h).json()
        assert found and found[0]["title"] == "Dentista" and "snippet" in found[0]
        assert c.get("/api/brain/docs", headers=h).json()[0]["tags"] == ["salute"]
        assert c.post(f"/api/brain/docs/{doc_id}/pin", json={"pinned": True}, headers=h).status_code == 200
        assert c.get(f"/api/brain/docs/{doc_id}", headers=h).json()["pinned"] is True
        assert c.get("/api/brain/stats", headers=h).json()["docs"] == 1
        assert c.delete(f"/api/brain/docs/{doc_id}", headers=h).status_code == 200 and c.delete(f"/api/brain/docs/{doc_id}", headers=h).status_code == 404
    get_settings.cache_clear()
