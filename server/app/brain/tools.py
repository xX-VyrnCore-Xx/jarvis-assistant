"""Tool del secondo cervello esposti al modello."""
import httpx

from ..tools import UNTRUSTED, ToolRegistry
from ..tools.web import fetch_page_data
from .service import SOURCE_LABEL, UNTRUSTED_SOURCES, Brain


def format_results(results: list[dict], snippet: int = 420) -> str:
    rows, untrusted = [], False
    for r in results:
        untrusted = untrusted or r["source"] in UNTRUSTED_SOURCES
        body = r["text"].strip().replace("\n", " ")
        rows.append(f"[#{r['doc_id']}] {r['title']} · {SOURCE_LABEL.get(r['source'], r['source'])} · {r['created_at'][:10]} ({', '.join(r['why'])})\n  {body[:snippet]}")
    return (UNTRUSTED if untrusted else "") + "\n".join(rows)


def register_brain_tools(reg: ToolRegistry, brain: Brain, client: httpx.AsyncClient | None = None) -> None:
    http = client or httpx.AsyncClient(timeout=20)
    on = lambda: brain.enabled  # noqa: E731
    s = {"type": "string"}
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731

    async def brain_add_note(text: str, title: str = "", tags: str = "", important: bool = False) -> str:
        r = await brain.ingest(text, title=title, source="note", tags=[t for t in tags.split(",") if t.strip()], importance=0.85 if important else 0.55)
        if r["status"] == "duplicato":
            return f"Già presente nel secondo cervello (#{r['doc_id']})."
        return f"Salvato nel secondo cervello (#{r['doc_id']}, {r['chunks']} frammenti{'' if r.get('vectors') else ', solo ricerca per parole per ora'})."

    async def brain_search(query: str, top_k: int = 5, source: str = "") -> str:
        res = await brain.search(query, k=max(1, min(top_k, 10)), source=source or None)
        return format_results(res) if res else "Nessun risultato nel secondo cervello."

    async def brain_read(doc_id: int) -> str:
        d = await brain.read(doc_id)
        if not d:
            return "Errore: documento non trovato."
        doc = d["doc"]
        head = f"#{doc.id} {doc.title} · {SOURCE_LABEL.get(doc.source, doc.source)} · {doc.created_at[:10]}" + (f"\nTag: {', '.join(doc.tags)}" if doc.tags else "") + (f"\nRiassunto: {doc.summary}" if doc.summary else "")
        body = head + "\n\n" + d["text"] + ("\n[…troncato]" if d["truncated"] else "")
        return (UNTRUSTED if doc.source in UNTRUSTED_SOURCES else "") + body

    async def brain_related(doc_id: int) -> str:
        rel = await brain.related(doc_id)
        return "\n".join(f"[#{r['doc_id']}] {r['title']} ({r['why']})" for r in rel) or "Nessun documento collegato."

    async def brain_forget(doc_id: int) -> str:
        return "Dimenticato." if await brain.forget(doc_id) else "Errore: documento non trovato."

    async def brain_pin(doc_id: int, pinned: bool = True) -> str:
        if not await brain.store.get_doc(doc_id):
            return "Errore: documento non trovato."
        await brain.store.update_doc(doc_id, pinned=pinned)
        return "Fissato in alto: avrà più peso nelle ricerche." if pinned else "Non più fissato."

    async def brain_save_url(url: str, tags: str = "") -> str:
        data = await fetch_page_data(url, http)
        if isinstance(data, str):
            return data
        title, text, final = data
        r = await brain.ingest(text, title=title or final, source="web", uri=final, tags=[t for t in tags.split(",") if t.strip()], importance=0.5)
        return f"Pagina salvata (#{r['doc_id']}: {r.get('title', '')}, {r['chunks']} frammenti)." if r["status"] != "duplicato" else f"Già salvata (#{r['doc_id']})."

    async def brain_resurface(count: int = 2) -> str:
        docs = await brain.resurface(max(1, min(count, 5)))
        return "\n".join(f"[#{d.id}] {d.title} ({d.created_at[:10]})" + (f" — {d.summary}" if d.summary else "") for d in docs) or "Niente da ripassare per ora."

    async def brain_stats() -> str:
        st = await brain.stats()
        return (f"{st['docs']} documenti, {st['chunks']} frammenti ({st['vectors']} con vettore), {st['entities']} entità. "
                f"Per fonte: {', '.join(f'{k} {v}' for k, v in st['by_source'].items()) or 'vuoto'}. Modello: {st['model']}.")

    reg.register("brain_add_note", "Salva una nota nel secondo cervello (memoria a lungo termine con ricerca per significato). Per appunti, idee, riunioni, fatti da ricordare. 'important' per ciò che conta davvero.",
                 obj({"text": s, "title": s, "tags": {"type": "string", "description": "tag separati da virgola"}, "important": {"type": "boolean"}}, ["text"]), brain_add_note, available=on)
    reg.register("brain_search", "Cerca nel secondo cervello (note, ricordi, pagine, file, diario) per significato e parole. Restituisce frammenti con id [#n]: citali. 'source' opzionale: note, memory, journal, web, file, drive, gmail.",
                 obj({"query": s, "top_k": {"type": "integer"}, "source": s}, ["query"]), brain_search, available=on, cache_ttl=30)
    reg.register("brain_read", "Legge per intero un documento del secondo cervello dato il suo id.", obj({"doc_id": {"type": "integer"}}, ["doc_id"]), brain_read, available=on)
    reg.register("brain_related", "Documenti collegati a uno dato (simili per significato o con le stesse persone/argomenti).", obj({"doc_id": {"type": "integer"}}, ["doc_id"]), brain_related, available=on)
    reg.register("brain_forget", "Elimina un documento dal secondo cervello (id da brain_search). Solo su richiesta dell'utente.", obj({"doc_id": {"type": "integer"}}, ["doc_id"]), brain_forget, available=on)
    reg.register("brain_pin", "Fissa (o stacca) un documento: i fissati pesano di più nelle ricerche.", obj({"doc_id": {"type": "integer"}, "pinned": {"type": "boolean"}}, ["doc_id"]), brain_pin, available=on)
    reg.register("brain_save_url", "Salva nel secondo cervello il contenuto di una pagina web pubblica (per leggerla o cercarla più avanti).", obj({"url": s, "tags": s}, ["url"]), brain_save_url, available=on)
    reg.register("brain_resurface", "Ripropone documenti importanti che non rivedi da tempo (ripasso a intervalli).", obj({"count": {"type": "integer"}}), brain_resurface, available=on)
    reg.register("brain_stats", "Statistiche del secondo cervello: documenti, frammenti, entità, fonti.", obj({}), brain_stats, available=on)
