"""Consumo dei modelli: richieste, token e latenza per giorno, tipo e modello. In RAM e salvato su Supabase ogni pochi minuti."""
import time
import logging
from datetime import datetime, timezone

DAY = "%Y-%m-%d"


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


log = logging.getLogger("jarvis.llm")


class UsageTracker:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], dict] = {}
        self._flushed: dict[tuple[str, str, str], dict] = {}
        self.recent_ms: list[float] = []
        self.last_error = ""

    def record(self, kind: str, model: str = "", prompt: int = 0, completion: int = 0, ms: float = 0.0, ok: bool = True) -> None:
        key = (datetime.now(timezone.utc).strftime(DAY), kind, (model or "")[:80])
        r = self.rows.setdefault(key, {"requests": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0})
        r["requests"] += 1
        r["errors"] += 0 if ok else 1
        r["prompt_tokens"] += int(prompt)
        r["completion_tokens"] += int(completion)
        r["latency_ms"] += int(ms)
        (log.info if ok else log.warning)("modello %s %s: %s in %.1f s (%d+%d token)", kind, model or "auto", "ok" if ok else "ERRORE", ms / 1000, prompt, completion)
        if ok:
            self.recent_ms = (self.recent_ms + [ms])[-50:]

    def today(self) -> dict:
        d = datetime.now(timezone.utc).strftime(DAY)
        tot = {"requests": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
        for (day, _, _), r in self.rows.items():
            if day == d:
                for k in tot:
                    tot[k] += r[k]
        tot["avg_latency_ms"] = int(tot["latency_ms"] / max(1, tot["requests"] - tot["errors"]))
        return tot

    async def flush(self, store) -> int:
        """Aggiunge al database solo ciò che è cambiato dall'ultimo salvataggio (somma incrementale)."""
        n = 0
        for key, r in list(self.rows.items()):
            prev = self._flushed.get(key, {k: 0 for k in r})
            delta = {k: r[k] - prev.get(k, 0) for k in r}
            if not any(delta.values()):
                continue
            await store.add_usage(key[0], key[1], key[2], delta)
            self._flushed[key] = dict(r)
            n += 1
        return n


class Timer:
    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *a):
        self.ms = (time.monotonic() - self.t0) * 1000
