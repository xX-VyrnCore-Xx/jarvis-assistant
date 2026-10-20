import asyncio
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
        self._client = client or httpx.AsyncClient(timeout=settings.llm_timeout_s)
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
        for attempt in range(3):
            try:
                headers = {"Authorization": f"Bearer {self._api_key()}"}
                r = await self._client.post(url, json=payload, headers=headers)
                if r.status_code in RETRY_STATUS:
                    last = LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                else:
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]
            except (httpx.TransportError, LLMError) as e:
                last = e
            await asyncio.sleep(2**attempt)
        raise LLMError(f"FreeLLMAPI non raggiungibile: {last}")
