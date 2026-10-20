import asyncio
import random
import sqlite3
from typing import Any

import httpx

from .config import Settings

RETRY_STATUS = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


def read_unified_key(db_path: str) -> str:
    """Legge la chiave unificata di FreeLLMAPI dal suo database (stesso container, sola lettura)."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            row = con.execute("SELECT value FROM settings WHERE key = 'unified_api_key'").fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        raise LLMError(f"FreeLLMAPI non ancora pronto: {e}") from e
    if not row or not row[0]:
        raise LLMError("FreeLLMAPI non ancora pronto: chiave unificata assente")
    return row[0]


class LLMClient:
    """Client OpenAI-compatibile verso il router FreeLLMAPI."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        # connessioni riutilizzate (keep-alive) e un numero limitato di richieste insieme: niente raffiche verso i provider gratuiti
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4, keepalive_expiry=60),
        )
        self._gate = asyncio.Semaphore(4)
        self._key = settings.freellm_api_key

    def _api_key(self) -> str:
        if not self._key and self.s.freellm_db_path:
            self._key = read_unified_key(self.s.freellm_db_path)
        return self._key

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Ritorna il messaggio dell'assistente (con eventuali tool_calls)."""
        if not self.s.freellm_base_url:
            raise LLMError("FREELLM_BASE_URL non configurato")
        payload: dict[str, Any] = {"model": self.s.freellm_model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        url = self.s.freellm_base_url.rstrip("/") + "/chat/completions"

        last: Exception | None = None
        async with self._gate:
            for attempt in range(4):
                delay = min(2**attempt, 8) + random.random() * 0.5  # backoff con jitter
                try:
                    headers = {"Authorization": f"Bearer {self._api_key()}"}
                    r = await self._client.post(url, json=payload, headers=headers)
                    if r.status_code in RETRY_STATUS:
                        # il corpo della risposta può contenere frammenti del prompt: nei messaggi d'errore va solo lo stato
                        last = LLMError(f"HTTP {r.status_code}")
                        if wait := r.headers.get("retry-after"):
                            delay = min(float(wait), 20.0) if wait.replace(".", "", 1).isdigit() else delay
                    elif r.status_code in (400, 401, 403, 404, 422):
                        raise LLMError(f"FreeLLMAPI ha rifiutato la richiesta (HTTP {r.status_code})")
                    else:
                        r.raise_for_status()
                        return r.json()["choices"][0]["message"]
                except (httpx.TransportError, LLMError) as e:
                    if isinstance(e, LLMError) and "rifiutato" in str(e):
                        raise
                    last = e
                if attempt < 3:
                    await asyncio.sleep(delay)
        raise LLMError(f"FreeLLMAPI non raggiungibile: {last}")
