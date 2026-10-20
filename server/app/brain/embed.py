"""Embedding tramite FreeLLMAPI (/v1/embeddings): a lotti, con cache, tentativi e quantizzazione a 8 bit per risparmiare RAM e spazio."""
import asyncio
import hashlib
import random
from collections import OrderedDict

import httpx
import numpy as np

from ..config import Settings
from ..llm import LLMError, read_unified_key

BATCH = 16
MAX_CHARS = 2000


class EmbedError(RuntimeError):
    pass


def quantize(vec: np.ndarray) -> bytes:
    """Vettore normalizzato -> int8 (scala fissa 127): 1 byte per dimensione, errore trascurabile per la similarità."""
    v = np.asarray(vec, dtype=np.float32)
    n = np.linalg.norm(v)
    if n == 0:
        return bytes(len(v))
    return np.clip(np.rint(v / n * 127), -127, 127).astype(np.int8).tobytes()


def dequantize(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.int8).astype(np.float32) / 127.0


class Embedder:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self.model = settings.rag_embed_model
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), limits=httpx.Limits(max_keepalive_connections=2))
        self._key = settings.freellm_api_key
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._gate = asyncio.Semaphore(2)

    @property
    def enabled(self) -> bool:
        return bool(self.s.freellm_base_url)

    def _api_key(self) -> str:
        if not self._key and self.s.freellm_db_path:
            self._key = read_unified_key(self.s.freellm_db_path)
        return self._key

    @staticmethod
    def _k(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\x00{text}".encode()).hexdigest()

    async def _call(self, texts: list[str]) -> list[list[float]]:
        url = self.s.freellm_base_url.rstrip("/") + "/embeddings"
        last: Exception | None = None
        async with self._gate:
            for attempt in range(4):
                delay = min(2**attempt, 8) + random.random() * 0.5
                try:
                    r = await self._client.post(url, json={"model": self.model, "input": texts},
                                                headers={"Authorization": f"Bearer {self._api_key()}"})
                    if r.status_code in (429, 500, 502, 503, 504):
                        last = EmbedError(f"HTTP {r.status_code}")
                        wait = r.headers.get("retry-after", "")
                        if wait.replace(".", "", 1).isdigit():
                            delay = min(float(wait), 30.0)
                    elif r.status_code >= 400:
                        raise EmbedError(f"embedding rifiutato (HTTP {r.status_code})")
                    else:
                        data = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
                        if len(data) != len(texts):
                            raise EmbedError("risposta incompleta")
                        return [d["embedding"] for d in data]
                except (httpx.TransportError, LLMError) as e:
                    last = e
                if attempt < 3:
                    await asyncio.sleep(delay)
        raise EmbedError(f"embedding non disponibile: {last}")

    async def embed(self, texts: list[str]) -> list[np.ndarray]:
        """Vettori (float32 normalizzati) nello stesso ordine; i testi già visti arrivano dalla cache."""
        texts = [t[:MAX_CHARS] for t in texts]
        out: list[np.ndarray | None] = [None] * len(texts)
        todo: list[int] = []
        for i, t in enumerate(texts):
            hit = self._cache.get(self._k(self.model, t))
            if hit is not None:
                out[i] = hit
            else:
                todo.append(i)
        for start in range(0, len(todo), BATCH):
            idxs = todo[start:start + BATCH]
            for i, vec in zip(idxs, await self._call([texts[i] for i in idxs])):
                v = np.asarray(vec, dtype=np.float32)
                n = np.linalg.norm(v)
                v = v / n if n else v
                out[i] = v
                self._cache[self._k(self.model, texts[i])] = v
                while len(self._cache) > 512:
                    self._cache.popitem(last=False)
        return out  # type: ignore[return-value]
