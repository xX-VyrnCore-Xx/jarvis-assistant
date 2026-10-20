import asyncio
from typing import Any

import httpx

from .config import Settings

RETRY_STATUS = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Client OpenAI-compatibile verso il router FreeLLMAPI."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.s = settings
        self._client = client or httpx.AsyncClient(timeout=settings.llm_timeout_s)

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
        headers = {"Authorization": f"Bearer {self.s.freellm_api_key}"}
        url = self.s.freellm_base_url.rstrip("/") + "/chat/completions"

        last: Exception | None = None
        for attempt in range(3):
            try:
                r = await self._client.post(url, json=payload, headers=headers)
                if r.status_code in RETRY_STATUS:
                    last = LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                else:
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]
            except httpx.TransportError as e:
                last = e
            await asyncio.sleep(2**attempt)
        raise LLMError(f"FreeLLMAPI non raggiungibile: {last}")
