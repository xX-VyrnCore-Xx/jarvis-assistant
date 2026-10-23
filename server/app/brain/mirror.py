"""Il secondo cervello rispecchia ciò che JARVIS ha di vivo: promemoria attivi, ricordi brevi e attività aperte.

Quando una di queste cose sparisce (promemoria eliminato, scattato o tolto dal Calendario; ricordo dimenticato; attività fatta) sparisce anche dal cervello,
compresi i fatti che l'apprendimento automatico aveva ricavato dalla stessa richiesta. Un controllo periodico ripara qualsiasi divergenza."""
import logging
import re
from datetime import datetime

log = logging.getLogger("jarvis.brain")
DUPLICATE_JACCARD = 0.7  # due fatti appresi con almeno il 70% di parole in comune dicono la stessa cosa
DERIVED_COSINE = 0.82  # somiglianza minima perché un fatto «appreso» si consideri nato da quel promemoria


class BrainMirror:
    def __init__(self, brain, store, tz=None):
        self.brain, self.store, self.tz = brain, store, tz

    @property
    def on(self) -> bool:
        return bool(self.brain and self.brain.enabled)

    # ------------------------------------------------------------------ promemoria
    @staticmethod
    def reminder_text(text: str, due: str | datetime) -> str:
        d = due if isinstance(due, datetime) else datetime.fromisoformat(str(due))
        return f"Promemoria: {text} (per il {d:%d/%m/%Y alle %H:%M})"

    async def reminder_put(self, rid: int, text: str, due) -> None:
        if not self.on:
            return
        try:
            await self.brain.ingest(self.reminder_text(text, due), title=f"Promemoria: {text}"[:80], source="reminder", uri=f"reminder:{rid}", tags=["promemoria"], importance=0.6)
        except Exception as e:
            log.info("promemoria non registrato nel cervello: %s", type(e).__name__)

    async def reminder_drop(self, rid: int, text: str = "") -> int:
        """Toglie il promemoria dal cervello e i fatti appresi dalla stessa richiesta. Restituisce quanti documenti ha eliminato."""
        if not self.on:
            return 0
        n = 0
        try:
            n += await self._forget_uri(f"reminder:{rid}")
            if text:
                n += await self._forget_derived(text)
        except Exception as e:
            log.info("pulizia del cervello rimandata: %s", type(e).__name__)
        return n

    async def _forget_uri(self, uri: str) -> int:
        doc = await self.brain.store.find_doc(uri_hash=self.brain.vault.blind(uri))
        return int(bool(doc and await self.brain.forget(doc.id)))

    async def _forget_derived(self, text: str) -> int:
        """Fatti ricavati in automatico («appreso») che ripetono quasi alla lettera il promemoria: non sono conoscenza duratura."""
        n = 0
        for h in await self.brain.search(text, k=4, expand=False, min_cosine=DERIVED_COSINE, source="memory"):
            doc = await self.brain.store.get_doc(h["doc_id"])
            if doc and not doc.pinned and "appreso" in doc.tags and h["cosine"] >= DERIVED_COSINE and not doc.uri:
                n += int(await self.brain.forget(doc.id))
        return n

    # ------------------------------------------------------------------ riallineamento completo
    async def _docs(self, source: str) -> list:
        out, offset = [], 0
        while True:
            page = await self.brain.store.list_docs(200, offset, source)
            out += page
            if len(page) < 200:
                return out
            offset += 200

    async def sync_all(self) -> dict:
        """Confronta cervello e archivi vivi e ripara: elimina ciò che non esiste più, aggiunge ciò che manca. Costa poco: i documenti invariati si riconoscono dall'impronta."""
        res = {"reminders": 0, "memories": 0, "tasks": 0, "added": 0}
        if not self.on:
            return res
        # promemoria attivi
        active = {r["id"]: r for r in await self.store.list_reminders()}
        have = {d.uri: d for d in await self._docs("reminder")}
        for uri, d in have.items():
            if uri not in {f"reminder:{i}" for i in active}:
                res["reminders"] += int(await self.brain.forget(d.id))
        for i, r in active.items():
            if f"reminder:{i}" not in have:
                await self.reminder_put(i, r["text"], r["due_at"])
                res["added"] += 1
        # ricordi brevi: i documenti «memory:…» il cui ricordo non esiste più
        mems = await self.store.list_memories(1000)
        wanted = {f"memory:{m['id']}" for m in mems} | {f"memory:{self.brain.vault.blind(m['content'])}" for m in mems}
        for d in await self._docs("memory"):
            if d.uri.startswith("memory:") and d.uri not in wanted:
                res["memories"] += int(await self.brain.forget(d.id))
        # attività aperte
        tasks = {t["id"]: t for t in await self.store.list_tasks(None, False)}
        have_t = {d.uri: d for d in await self._docs("task")}
        for uri, d in have_t.items():
            if uri not in {f"task:{i}" for i in tasks}:
                res["tasks"] += int(await self.brain.forget(d.id))
        for i, t in tasks.items():
            if f"task:{i}" not in have_t:
                await self.brain.ingest(f"Da fare ({t.get('list', 'attività')}): {t['text']}", title=f"Da fare: {t['text']}"[:80], source="task", uri=f"task:{i}", tags=["attività"], importance=0.5)
                res["added"] += 1
        if any(res.values()):
            log.info("cervello riallineato: %s", res)
        return res


    # ------------------------------------------------------------------ pulizia dei fatti appresi
    @staticmethod
    def _words(text: str) -> frozenset:
        return frozenset(w for w in re.findall(r"\w+", text.lower()) if len(w) > 2)

    async def dedupe_facts(self, limit: int = 300) -> int:
        """I fatti ricavati dalle conversazioni a volte si ripetono con parole diverse: tiene il più importante (a parità, il più recente) e toglie gli altri."""
        if not self.on:
            return 0
        docs = [d for d in await self._docs("memory") if "appreso" in d.tags and not d.pinned and not d.uri][-limit:]
        words = {}
        for d in docs:
            words[d.id] = self._words(" ".join(c.text for c in await self.brain.store.doc_chunks(d.id)))
        gone: set[int] = set()
        ranked = sorted(docs, key=lambda d: (d.importance, d.id), reverse=True)
        for i, a in enumerate(ranked):
            if a.id in gone or not words[a.id]:
                continue
            for b in ranked[i + 1:]:
                if b.id in gone or not words[b.id]:
                    continue
                inter = len(words[a.id] & words[b.id])
                if inter / len(words[a.id] | words[b.id]) >= DUPLICATE_JACCARD or inter / min(len(words[a.id]), len(words[b.id])) >= 0.9:
                    gone.add(b.id)
        n = 0
        for i in gone:
            n += int(await self.brain.forget(i))
        if n:
            log.info("cervello: %d fatti duplicati unificati", n)
        return n
