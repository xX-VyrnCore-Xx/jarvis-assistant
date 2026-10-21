"""Tool del secondo cervello esposti al modello."""
import re

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

    async def brain_search(query: str, top_k: int = 5, source: str = "", since: str = "", until: str = "") -> str:
        res = await brain.search(query, k=max(1, min(top_k, 10)), source=source or None, since=since[:10], until=until[:10])
        return format_results(res) if res else "Nessun risultato nel secondo cervello."

    async def brain_deep_search(question: str, since: str = "", until: str = "") -> str:
        queries, res = await brain.deep_search(question, k=8, since=since[:10], until=until[:10])
        if not res:
            return "Nessun risultato nel secondo cervello, neanche riformulando la domanda."
        return f"Ricerche provate: {' | '.join(queries)}\n" + format_results(res)

    async def brain_about(name: str) -> str:
        d = await brain.dossier(name.strip())
        if not d["docs"]:
            return f"Non trovo nulla su «{name}» nel secondo cervello."
        rows = [f"[#{x.id}] {x.created_at[:10]} · {SOURCE_LABEL.get(x.source, x.source)} · {x.title}" + (f" — {x.summary}" if x.summary else "") for x in d["docs"]]
        head = f"Cosa so di «{name}» ({len(d['docs'])} documenti, dal più vecchio al più recente)"
        rel = f"\nCollegato a: {', '.join(n for _, n in d['related'])}" if d["related"] else ""
        untrusted = any(x.source in UNTRUSTED_SOURCES for x in d["docs"])
        return (UNTRUSTED if untrusted else "") + head + ":\n" + "\n".join(rows) + rel

    async def brain_learn(topic: str, lang: str = "it", full: bool = False) -> str:
        k = getattr(brain, "knowledge", None)
        if not k:
            return "Errore: conoscenza di base non disponibile."
        if not re.fullmatch(r"[a-z]{2,3}", lang):
            return "Errore: lingua non valida."
        r = await k.learn(topic, lang, full)
        if r["status"] == "non trovato":
            return f"Nessuna voce di Wikipedia per «{topic}»."
        verb = "Già nel secondo cervello" if r["status"] == "duplicato" else "Imparato e salvato nel secondo cervello"
        return f"{verb}: {r['title']} (#{r['doc_id']}, {r['chars']} caratteri, {r['url']})."

    async def brain_profile(refresh: bool = False) -> str:
        if refresh:
            await brain.refresh_profile(force=True)
        text = await brain.profile_text()
        return text or "Non ho ancora abbastanza ricordi per un profilo: più parli con me, più imparo."

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
    reg.register("brain_search", "Cerca nel secondo cervello (note, ricordi, pagine, file, diario) per significato e parole. Restituisce frammenti con id [#n]: citali. 'source' opzionale: note, memory, journal, web, file, drive, gmail. 'since'/'until' (YYYY-MM-DD) limitano il periodo.",
                 obj({"query": s, "top_k": {"type": "integer"}, "source": s, "since": s, "until": s}, ["query"]), brain_search, available=on, cache_ttl=30)
    reg.register("brain_deep_search", "Ricerca approfondita per domande vaghe o difficili: riformula la domanda in più modi e fonde i risultati. Più lenta di brain_search: usala quando questa non basta. Cita gli id [#n].",
                 obj({"question": s, "since": s, "until": s}, ["question"]), brain_deep_search, available=on, cache_ttl=30)
    reg.register("brain_about", "Tutto ciò che il secondo cervello sa di una persona, progetto, luogo o argomento (nome), in ordine di tempo, con i collegamenti. Per «cosa so di Luca?».",
                 obj({"name": s}, ["name"]), brain_about, available=on, cache_ttl=30)
    reg.register("brain_learn", "Impara un argomento da Wikipedia e lo salva nel secondo cervello (cultura generale: persone, luoghi, concetti, eventi). full=true carica la voce intera. Usalo quando l'utente vuole 'studiare' o tenere una voce.",
                 obj({"topic": s, "lang": s, "full": {"type": "boolean"}}, ["topic"]), brain_learn, available=on)
    reg.register("brain_profile", "Il profilo dell'utente compilato dal secondo cervello (chi è, persone, progetti, preferenze). refresh=true lo ricompila ora.",
                 obj({"refresh": {"type": "boolean"}}), brain_profile, available=on)
    reg.register("brain_read", "Legge per intero un documento del secondo cervello dato il suo id.", obj({"doc_id": {"type": "integer"}}, ["doc_id"]), brain_read, available=on)
    reg.register("brain_related", "Documenti collegati a uno dato (simili per significato o con le stesse persone/argomenti).", obj({"doc_id": {"type": "integer"}}, ["doc_id"]), brain_related, available=on)
    reg.register("brain_forget", "Elimina un documento dal secondo cervello (id da brain_search). Solo su richiesta dell'utente.", obj({"doc_id": {"type": "integer"}}, ["doc_id"]), brain_forget, available=on)
    reg.register("brain_pin", "Fissa (o stacca) un documento: i fissati pesano di più nelle ricerche.", obj({"doc_id": {"type": "integer"}, "pinned": {"type": "boolean"}}, ["doc_id"]), brain_pin, available=on)
    reg.register("brain_save_url", "Salva nel secondo cervello il contenuto di una pagina web pubblica (per leggerla o cercarla più avanti).", obj({"url": s, "tags": s}, ["url"]), brain_save_url, available=on)
    reg.register("brain_resurface", "Ripropone documenti importanti che non rivedi da tempo (ripasso a intervalli).", obj({"count": {"type": "integer"}}), brain_resurface, available=on)
    reg.register("brain_stats", "Statistiche del secondo cervello: documenti, frammenti, entità, fonti.", obj({}), brain_stats, available=on)
