"""Indice in RAM per il recupero ibrido: vettori int8 (similarità coseno) + indice invertito sulle parole (BM25 su HMAC), fusi con RRF.

Tutto resta in memoria del server: nel database i vettori sono solo cifrati, quindi la ricerca non rivela nulla a Supabase.
"""
import math
from dataclasses import dataclass

import numpy as np

RRF_K = 60


@dataclass
class Hit:
    chunk_id: int
    doc_id: int
    score: float  # punteggio fuso (RRF) usato per ordinare
    cosine: float  # similarità semantica grezza (0 se manca il vettore)
    lexical: float  # punteggio BM25 grezzo


class VectorIndex:
    def __init__(self) -> None:
        self.dim = 0
        self._mat = np.zeros((0, 0), dtype=np.int8)
        self.n = 0
        self.chunk_ids: list[int] = []
        self.doc_ids: list[int] = []
        self.alive: list[bool] = []
        self.terms: list[tuple[str, ...]] = []
        self.has_vec: list[bool] = []
        self.inv: dict[str, list[int]] = {}
        self.by_chunk: dict[int, int] = {}
        self.by_doc: dict[int, list[int]] = {}
        self._total_len = 0
        self._live = 0

    def __len__(self) -> int:
        return self._live

    # ------------------------------------------------------------------ aggiornamento
    def add(self, chunk_id: int, doc_id: int, vec: bytes | None, terms: list[str]) -> None:
        if chunk_id in self.by_chunk:
            self.remove_chunk(chunk_id)
        if vec:
            if not self.dim:
                self.dim = len(vec)
                self._mat = np.zeros((256, self.dim), dtype=np.int8)
            if len(vec) != self.dim:
                vec = None  # modello diverso: il frammento resta cercabile per parole finché non si reindicizza
        row = self.n
        self.n += 1
        if self.dim:
            while row >= len(self._mat):
                self._mat = np.vstack([self._mat, np.zeros((max(256, len(self._mat)), self.dim), dtype=np.int8)])
            self._mat[row] = np.frombuffer(vec, dtype=np.int8) if vec else 0
        self.chunk_ids.append(chunk_id)
        self.doc_ids.append(doc_id)
        self.alive.append(True)
        self.has_vec.append(bool(vec))
        uniq = tuple(dict.fromkeys(terms))
        self.terms.append(uniq)
        for t in uniq:
            self.inv.setdefault(t, []).append(row)
        self.by_chunk[chunk_id] = row
        self.by_doc.setdefault(doc_id, []).append(row)
        self._total_len += len(uniq)
        self._live += 1

    def remove_chunk(self, chunk_id: int) -> None:
        row = self.by_chunk.pop(chunk_id, None)
        if row is None or not self.alive[row]:
            return
        self.alive[row] = False
        self._live -= 1
        self._total_len -= len(self.terms[row])
        doc_rows = self.by_doc.get(self.doc_ids[row], [])
        if row in doc_rows:
            doc_rows.remove(row)

    def remove_doc(self, doc_id: int) -> None:
        for row in list(self.by_doc.get(doc_id, [])):
            self.remove_chunk(self.chunk_ids[row])
        self.by_doc.pop(doc_id, None)

    # ------------------------------------------------------------------ ricerca
    def dense(self, q: np.ndarray, k: int) -> list[tuple[int, float]]:
        if not self.n or not self.dim or q is None or len(q) != self.dim:
            return []
        scores = np.empty(self.n, dtype=np.float32)
        for s in range(0, self.n, 4096):  # a blocchi: niente copia float32 dell'intera matrice
            scores[s:s + 4096] = self._mat[s:min(s + 4096, self.n)].astype(np.float32) @ q / 127.0
        mask = np.array([a and h for a, h in zip(self.alive, self.has_vec)], dtype=bool)
        scores[~mask] = -2.0
        top = np.argpartition(-scores, min(k, self.n - 1))[:k]
        return [(int(i), float(scores[i])) for i in sorted(top, key=lambda i: -scores[i]) if scores[i] > -1.5]

    def lexical(self, q_terms: list[str], k: int) -> list[tuple[int, float]]:
        """BM25 (k1=1.4, b=0.75) sulle parole in HMAC."""
        if not self._live or not q_terms:
            return []
        avg = self._total_len / max(1, self._live)
        scores: dict[int, float] = {}
        for t in dict.fromkeys(q_terms):
            rows = [r for r in self.inv.get(t, []) if self.alive[r]]
            if not rows:
                continue
            idf = math.log(1 + (self._live - len(rows) + 0.5) / (len(rows) + 0.5))
            for r in rows:
                dl = len(self.terms[r])
                scores[r] = scores.get(r, 0.0) + idf * (2.4 / (1 + 1.4 * (0.25 + 0.75 * dl / max(avg, 1.0))))
        return sorted(scores.items(), key=lambda kv: -kv[1])[:k]

    def search(self, q: np.ndarray | None, q_terms: list[str], k: int = 24, w_dense: float = 1.0, w_lex: float = 0.8) -> list[Hit]:
        """Fusione RRF delle due classifiche: robusta senza dover tarare i punteggi, e funziona anche con una sola delle due."""
        dense = self.dense(q, k * 3) if q is not None else []
        lex = self.lexical(q_terms, k * 3)
        cos = dict(dense)
        lexd = dict(lex)
        fused: dict[int, float] = {}
        for rank, (row, _) in enumerate(dense):
            fused[row] = fused.get(row, 0.0) + w_dense / (RRF_K + rank + 1)
        for rank, (row, _) in enumerate(lex):
            fused[row] = fused.get(row, 0.0) + w_lex / (RRF_K + rank + 1)
        top = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [Hit(self.chunk_ids[r], self.doc_ids[r], s, cos.get(r, 0.0), lexd.get(r, 0.0)) for r, s in top]

    def vector(self, chunk_id: int) -> np.ndarray | None:
        row = self.by_chunk.get(chunk_id)
        if row is None or not self.has_vec[row]:
            return None
        return self._mat[row].astype(np.float32) / 127.0

    def mmr(self, hits: list[Hit], k: int, lam: float = 0.7) -> list[Hit]:
        """Massima rilevanza marginale: toglie i frammenti quasi identici e porta varietà nel contesto."""
        picked: list[Hit] = []
        vecs = {h.chunk_id: self.vector(h.chunk_id) for h in hits}
        pool = list(hits)
        top = max((h.score for h in pool), default=1.0) or 1.0
        while pool and len(picked) < k:
            def value(h: Hit) -> float:
                sim = 0.0
                v = vecs[h.chunk_id]
                if v is not None:
                    for p in picked:
                        pv = vecs[p.chunk_id]
                        if pv is not None:
                            n = np.linalg.norm(v) * np.linalg.norm(pv)
                            sim = max(sim, float(v @ pv / n) if n else 0.0)
                return lam * (h.score / top) - (1 - lam) * sim

            best = max(pool, key=value)
            picked.append(best)
            pool.remove(best)
        return picked
