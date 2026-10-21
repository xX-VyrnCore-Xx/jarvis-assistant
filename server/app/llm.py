import asyncio
import json
import random
import sqlite3
import time
from typing import Any

import httpx

from .config import Settings
from .usage import UsageTracker, est_tokens

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
    """Client OpenAI-compatibile verso il router FreeLLMAPI: tentativi con backoff, streaming, elenco modelli, trascrizione, consumi."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None, usage: UsageTracker | None = None):
        self.s = settings
        self.usage = usage or UsageTracker()
        # connessioni riutilizzate (keep-alive) e un numero limitato di richieste insieme: niente raffiche verso i provider gratuiti
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=10.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4, keepalive_expiry=60),
        )
        self._gate = asyncio.Semaphore(4)
        self._key = settings.freellm_api_key
        self._models: tuple[float, list[dict]] | None = None

    def _api_key(self) -> str:
        if not self._key and self.s.freellm_db_path:
            self._key = read_unified_key(self.s.freellm_db_path)
        return self._key

    def _payload(self, messages, tools, model: str | None, kind: str, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model or self.s.freellm_model, "messages": messages,
                                   "temperature": self.s.llm_temperature_tools if tools else self.s.llm_temperature, "max_tokens": self.s.llm_max_tokens}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if stream:
            payload["stream"] = True
        return payload

    def _url(self, path: str) -> str:
        if not self.s.freellm_base_url:
            raise LLMError("FREELLM_BASE_URL non configurato")
        return self.s.freellm_base_url.rstrip("/") + path

    def _record(self, kind: str, model: str, usage: dict | None, messages, out_text: str, ms: float, ok: bool = True, tools: bool = False) -> None:
        usage = usage or {}
        p = usage.get("prompt_tokens") or (sum(est_tokens(str(m.get("content") or "")) for m in messages) if messages else 0)
        c = usage.get("completion_tokens") or est_tokens(out_text) if ok else 0
        self.usage.record(kind, model, p, c, ms, ok, tools)

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, model: str | None = None,
                   kind: str = "chat") -> dict[str, Any]:
        """Ritorna il messaggio dell'assistente (con eventuali tool_calls)."""
        payload = self._payload(messages, tools, model, kind)
        url = self._url("/chat/completions")
        last: Exception | None = None
        auto = (model or self.s.freellm_model) == "auto"
        failed: list[str] = []
        async with self._gate:
            for attempt in range(3):
                delay = min(2**attempt, 4) + random.random() * 0.5  # backoff con jitter
                if attempt and auto and (fb := self.usage.best_model(bool(tools), tuple(failed))):
                    payload["model"] = fb  # il router si è bloccato: si ripiega sul modello che di recente risponde più in fretta
                t0 = time.monotonic()
                try:
                    headers = {"Authorization": f"Bearer {self._api_key()}"}
                    # primo tentativo con un limite breve: un provider bloccato (60 s) non deve tenere ferma la risposta
                    r = await self._client.post(url, json=payload, headers=headers,
                                                timeout=httpx.Timeout(self.s.llm_attempt_timeout_s if attempt == 0 else self.s.llm_timeout_s, connect=10.0))
                    if r.status_code in RETRY_STATUS:
                        # il corpo della risposta può contenere frammenti del prompt: nei messaggi d'errore va solo lo stato
                        last = LLMError(f"HTTP {r.status_code}")
                        self.usage.record(kind, payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                        failed.append(payload["model"])
                        if wait := r.headers.get("retry-after"):
                            delay = min(float(wait), 20.0) if wait.replace(".", "", 1).isdigit() else delay
                    elif r.status_code in (400, 401, 403, 404, 422):
                        raise LLMError(f"FreeLLMAPI ha rifiutato la richiesta (HTTP {r.status_code})")
                    else:
                        r.raise_for_status()
                        data = r.json()
                        msg = data["choices"][0]["message"]
                        self._record(kind, data.get("model") or payload["model"], data.get("usage"), messages, msg.get("content") or "", (time.monotonic() - t0) * 1000, tools=bool(tools))
                        return msg
                except (httpx.TransportError, LLMError) as e:
                    if isinstance(e, LLMError) and "rifiutato" in str(e):
                        raise
                    last = e
                    if isinstance(e, httpx.TransportError):
                        self.usage.record(kind, payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                        failed.append(payload["model"])
                if attempt < 2:
                    await asyncio.sleep(delay)
        self.usage.last_error = type(last).__name__
        raise LLMError(f"FreeLLMAPI non raggiungibile: {last}")

    async def chat_stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, model: str | None = None):
        """Generatore di eventi: ("delta", testo) man mano che arriva, poi ("done", messaggio completo con eventuali tool_calls).
        I tentativi automatici valgono solo prima del primo token: a flusso iniziato un errore si propaga."""
        payload = self._payload(messages, tools, model, "chat", stream=True)
        url = self._url("/chat/completions")
        last: Exception | None = None
        auto = (model or self.s.freellm_model) == "auto"
        failed: list[str] = []
        async with self._gate:
            for attempt in range(3):
                if attempt and auto and (fb := self.usage.best_model(bool(tools), tuple(failed))):
                    payload["model"] = fb  # ripiego sul modello che di recente risponde più in fretta
                t0 = time.monotonic()
                started = False
                try:
                    # il limite vale per ogni attesa di dati: se il primo token non arriva in tempo si riprova con un altro modello
                    async with self._client.stream("POST", url, json=payload, headers={"Authorization": f"Bearer {self._api_key()}"},
                                                   timeout=httpx.Timeout(self.s.llm_attempt_timeout_s if attempt == 0 else self.s.llm_timeout_s, connect=10.0)) as r:
                        if r.status_code in RETRY_STATUS:
                            last = LLMError(f"HTTP {r.status_code}")
                            self.usage.record("chat", payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                            failed.append(payload["model"])
                        elif r.status_code >= 400:
                            raise LLMError(f"FreeLLMAPI ha rifiutato la richiesta (HTTP {r.status_code})")
                        else:
                            text, calls, usage, model_id = "", {}, None, payload["model"]
                            async for line in r.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                body = line[5:].strip()
                                if body == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(body)
                                except ValueError:
                                    continue
                                model_id = chunk.get("model") or model_id
                                usage = chunk.get("usage") or usage
                                for ch in chunk.get("choices") or []:
                                    d = ch.get("delta") or {}
                                    if d.get("content"):
                                        started = True
                                        text += d["content"]
                                        yield ("delta", d["content"])
                                    for tc in d.get("tool_calls") or []:
                                        started = True
                                        c = calls.setdefault(tc.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                        c["id"] = tc.get("id") or c["id"]
                                        f = tc.get("function") or {}
                                        c["function"]["name"] += f.get("name") or ""
                                        c["function"]["arguments"] += f.get("arguments") or ""
                            msg: dict[str, Any] = {"role": "assistant", "content": text or None}
                            if calls:
                                msg["tool_calls"] = [calls[i] | {"id": calls[i]["id"] or f"call_{i}"} for i in sorted(calls)]
                            self._record("chat", model_id, usage, messages, text, (time.monotonic() - t0) * 1000, tools=bool(tools))
                            yield ("done", msg)
                            return
                except (httpx.TransportError, LLMError) as e:
                    if started or (isinstance(e, LLMError) and "rifiutato" in str(e)):
                        raise
                    last = e
                    if isinstance(e, httpx.TransportError):
                        self.usage.record("chat", payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                        failed.append(payload["model"])
                if attempt < 2:
                    await asyncio.sleep(min(2**attempt, 8) + random.random() * 0.5)
        raise LLMError(f"FreeLLMAPI non raggiungibile: {last}")

    async def models(self) -> list[dict]:
        """Modelli disponibili sul router (cache di 10 minuti)."""
        if self._models and self._models[0] > time.monotonic():
            return self._models[1]
        r = await self._client.get(self._url("/models"), headers={"Authorization": f"Bearer {self._api_key()}"})
        r.raise_for_status()
        rows = [{"id": m["id"], "owned_by": m.get("owned_by", "")} for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
        self._models = (time.monotonic() + 600, rows)
        return rows

    async def transcribe(self, audio: bytes, filename: str = "voice.ogg", mime: str = "audio/ogg") -> str:
        """Voce -> testo tramite /v1/audio/transcriptions del router."""
        t0 = time.monotonic()
        r = await self._client.post(self._url("/audio/transcriptions"), headers={"Authorization": f"Bearer {self._api_key()}"},
                                    files={"file": (filename, audio, mime)}, data={"model": self.s.stt_model, "language": "it"}, timeout=120)
        ok = r.status_code < 400
        self.usage.record("stt", self.s.stt_model, 0, 0, (time.monotonic() - t0) * 1000, ok)
        if not ok:
            raise LLMError(f"trascrizione non riuscita (HTTP {r.status_code})")
        return (r.json().get("text") or "").strip()
