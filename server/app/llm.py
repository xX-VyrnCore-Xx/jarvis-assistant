import asyncio
import json
import logging
import random
import sqlite3
import time
from typing import Any

import httpx

from .config import Settings
from .ctx import TOO_LARGE, ContextBudget, classify_error, fit, tokens_of
from .routing import Router
from .tools.select import CORE
from .usage import UsageTracker, est_tokens

log = logging.getLogger("jarvis.llm")

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
        self.router = Router()
        self.ctx = ContextBudget(settings.llm_context_tokens or 9000)  # tetto di token per profilo, che si restringe da solo
        self._gone: dict[str, float] = {}  # modelli non più disponibili: esclusi per 30 minuti

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

    # ------------------------------------------------------------------ riparazione automatica degli errori
    def _dead(self) -> tuple[str, ...]:
        now = time.monotonic()
        self._gone = {m: until for m, until in self._gone.items() if until > now}
        return tuple(self._gone)

    def _attempt(self, messages, tools, model: str | None, kind: str, route, stream: bool = False) -> dict[str, Any]:
        """Stato di una richiesta: messaggi e strumenti già portati dentro il tetto di contesto del profilo, più il contatore delle riparazioni."""
        profile = route.profile if route else (model or self.s.freellm_model)
        msgs, tls, saved = self._fit(messages, tools, profile)
        payload = self._payload(msgs, tls, model, kind, stream)
        if route:
            payload["model"] = route.model
        return {"messages": messages, "tools": tools, "payload": payload, "profile": profile, "repairs": 0, "kind": kind}

    def _fit(self, messages, tools, profile: str):
        if not self.s.llm_context_tokens:
            return [{k: v for k, v in m.items() if k != "_opt"} for m in messages], tools, 0
        msgs, tls, saved = fit(messages, tools, self.ctx.for_profile(profile), CORE)
        if saved:
            self.ctx.saved += saved
            log.info("contesto ridotto di ~%d token per %s", saved, profile)
        return msgs, tls, saved

    def _repair(self, st: dict, category: str, route, failed: list[str]) -> bool:
        """Prova a riparare un errore senza disturbare l'utente. True = ritentare subito con la richiesta corretta."""
        if not self.s.llm_repair or st["repairs"] >= 3:
            return False
        p = st["payload"]
        if category == "too_large":
            budget = self.ctx.too_large(st["profile"], tokens_of(p["messages"], p.get("tools")))
            msgs, tls, saved = fit(st["messages"], st["tools"], budget, CORE)
            if not saved and tokens_of(msgs, tls) >= tokens_of(p["messages"], p.get("tools")):
                return False  # più piccolo di così non si può
            p["messages"] = msgs
            if tls:
                p["tools"] = tls
            else:
                p.pop("tools", None); p.pop("tool_choice", None)
            self.ctx.saved += saved
            log.info("richiesta troppo grande per %s: riprovo con un contesto più corto (tetto %d token)", st["profile"], budget)
        elif category == "bad_tools" and p.get("tools"):
            p.pop("tools", None); p.pop("tool_choice", None)  # un modello che non digerisce gli strumenti risponde comunque in testo
            p["temperature"] = self.s.llm_temperature
            log.info("%s ha rifiutato gli strumenti: riprovo senza", p["model"])
        elif category == "model_gone":
            self._gone[p["model"]] = time.monotonic() + 1800
            failed.append(p["model"])
            nxt = None
            if p["model"].startswith("auto:") and route:
                nxt = self.router.fallback(route, st["repairs"] + 1)
            nxt = nxt or self.usage.best_model(bool(p.get("tools")), tuple(failed) + self._dead())
            if not nxt or nxt == p["model"]:
                return False
            p["model"] = nxt
            log.info("modello non più disponibile: passo a %s", nxt)
        else:
            return False
        st["repairs"] += 1
        return True

    @staticmethod
    def _empty(msg: dict) -> bool:
        return not (msg.get("content") or "").strip() and not msg.get("tool_calls")

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, model: str | None = None,
                   kind: str = "chat") -> dict[str, Any]:
        """Ritorna il messaggio dell'assistente (con eventuali tool_calls). Gli errori recuperabili (richiesta troppo grande, strumenti rifiutati,
        modello non più disponibile, risposta vuota, guasti passeggeri) si riparano da soli senza che l'utente se ne accorga."""
        url = self._url("/chat/completions")
        last: Exception | None = None
        auto = (model or self.s.freellm_model) == "auto"
        route = self.router.pick(messages, bool(tools), kind) if auto and self.s.llm_routing else None
        st = self._attempt(messages, tools, model, kind, route)
        payload = st["payload"]
        failed: list[str] = []
        attempt = 0
        async with self._gate:
            while attempt < 3:
                delay = min(2**attempt, 4) + random.random() * 0.5  # backoff con jitter
                if attempt and auto:
                    skip = tuple(failed) + self._dead()
                    if fb := self.usage.best_model(bool(payload.get("tools")), skip):
                        payload["model"] = fb  # il router si è bloccato: si ripiega sul modello che di recente risponde più in fretta
                    elif route:
                        payload["model"] = self.router.fallback(route, attempt)
                t0 = time.monotonic()
                try:
                    headers = {"Authorization": f"Bearer {self._api_key()}", **({"X-FreeLLM-Task-Type": route.task} if route else {})}
                    # primo tentativo con un limite breve: un provider bloccato (60 s) non deve tenere ferma la risposta
                    r = await self._client.post(url, json=payload, headers=headers,
                                                timeout=httpx.Timeout(self.s.llm_attempt_timeout_s if attempt == 0 else self.s.llm_timeout_s, connect=10.0))
                    if r.status_code in RETRY_STATUS and r.status_code != 429 or r.status_code == 429 and not TOO_LARGE.search(r.text[:600] if r.content else ""):
                        # il corpo della risposta può contenere frammenti del prompt: nei messaggi d'errore va solo lo stato
                        last = LLMError(f"HTTP {r.status_code}")
                        self.usage.record(kind, payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                        failed.append(payload["model"])
                        if route and attempt == 0:
                            self.router.report(route.profile, False)
                        if wait := r.headers.get("retry-after"):
                            delay = min(float(wait), 20.0) if wait.replace(".", "", 1).isdigit() else delay
                    elif r.status_code >= 400:
                        cat = classify_error(r.status_code, r.text[:600] if r.content else "")
                        self.usage.record(kind, payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                        if cat == "too_large" and route:
                            self.router.report_error(route.profile, cat)
                        if cat != "auth" and self._repair(st, cat, route, failed):
                            continue  # riparato: si riprova subito, senza consumare un tentativo
                        raise LLMError(f"FreeLLMAPI ha rifiutato la richiesta (HTTP {r.status_code})")
                    else:
                        r.raise_for_status()
                        data = r.json()
                        msg = data["choices"][0]["message"]
                        self._record(kind, data.get("model") or payload["model"], data.get("usage"), payload["messages"], msg.get("content") or "", (time.monotonic() - t0) * 1000, tools=bool(payload.get("tools")))
                        if self._empty(msg) and attempt < 2 and self.s.llm_repair:  # risposta vuota: un altro modello
                            last = LLMError("risposta vuota")
                            failed.append(payload["model"])
                            if route:
                                self.router.report(route.profile, False)
                            attempt += 1
                            await asyncio.sleep(0.3)
                            continue
                        self.ctx.ok(st["profile"])
                        if route:
                            self.router.report(route.profile, attempt == 0, (time.monotonic() - t0) * 1000)
                        return msg
                except (httpx.TransportError, LLMError) as e:
                    if isinstance(e, LLMError) and "rifiutato" in str(e):
                        raise
                    last = e
                    if isinstance(e, httpx.TransportError):
                        self.usage.record(kind, payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                        failed.append(payload["model"])
                        if route and attempt == 0:
                            self.router.report(route.profile, False)
                attempt += 1
                if attempt < 3:
                    await asyncio.sleep(delay)
        self.usage.last_error = type(last).__name__
        raise LLMError(f"FreeLLMAPI non raggiungibile: {last}")

    async def chat_stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, model: str | None = None):
        """Generatore di eventi: ("delta", testo) man mano che arriva, poi ("done", messaggio completo con eventuali tool_calls).
        Le riparazioni e i tentativi automatici valgono solo prima del primo token: a flusso iniziato un errore si propaga."""
        url = self._url("/chat/completions")
        last: Exception | None = None
        auto = (model or self.s.freellm_model) == "auto"
        route = self.router.pick(messages, bool(tools), "chat") if auto and self.s.llm_routing else None
        st = self._attempt(messages, tools, model, "chat", route, stream=True)
        payload = st["payload"]
        failed: list[str] = []
        attempt = 0
        async with self._gate:
            while attempt < 3:
                if attempt and auto:
                    skip = tuple(failed) + self._dead()
                    if fb := self.usage.best_model(bool(payload.get("tools")), skip):
                        payload["model"] = fb  # ripiego sul modello che di recente risponde più in fretta
                    elif route:
                        payload["model"] = self.router.fallback(route, attempt)
                t0 = time.monotonic()
                started = False
                try:
                    # il limite vale per ogni attesa di dati: se il primo token non arriva in tempo si riprova con un altro modello
                    async with self._client.stream("POST", url, json=payload, headers={"Authorization": f"Bearer {self._api_key()}", **({"X-FreeLLM-Task-Type": route.task} if route else {})},
                                                   timeout=httpx.Timeout(self.s.llm_attempt_timeout_s if attempt == 0 else self.s.llm_timeout_s, connect=10.0)) as r:
                        body = ""
                        if r.status_code >= 400:
                            body = (await r.aread()).decode("utf-8", "ignore")[:600]
                        if r.status_code in RETRY_STATUS and not (r.status_code == 429 and TOO_LARGE.search(body)):
                            last = LLMError(f"HTTP {r.status_code}")
                            self.usage.record("chat", payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                            failed.append(payload["model"])
                            if route and attempt == 0:
                                self.router.report(route.profile, False)
                        elif r.status_code >= 400:
                            cat = classify_error(r.status_code, body)
                            self.usage.record("chat", payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                            if cat == "too_large" and route:
                                self.router.report_error(route.profile, cat)
                            if cat != "auth" and self._repair(st, cat, route, failed):
                                continue
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
                            self._record("chat", model_id, usage, payload["messages"], text, (time.monotonic() - t0) * 1000, tools=bool(payload.get("tools")))
                            if self._empty(msg) and attempt < 2 and self.s.llm_repair:  # flusso vuoto: nessun token è partito, si prova un altro modello
                                last = LLMError("risposta vuota")
                                failed.append(payload["model"])
                                if route:
                                    self.router.report(route.profile, False)
                                attempt += 1
                                continue
                            self.ctx.ok(st["profile"])
                            if route:
                                self.router.report(route.profile, attempt == 0, (time.monotonic() - t0) * 1000)
                            yield ("done", msg)
                            return
                except (httpx.TransportError, LLMError) as e:
                    if started or (isinstance(e, LLMError) and "rifiutato" in str(e)):
                        raise
                    last = e
                    if isinstance(e, httpx.TransportError):
                        self.usage.record("chat", payload["model"], 0, 0, (time.monotonic() - t0) * 1000, ok=False)
                        failed.append(payload["model"])
                        if route and attempt == 0:
                            self.router.report(route.profile, False)
                attempt += 1
                if attempt < 3:
                    await asyncio.sleep(min(2**(attempt - 1), 8) + random.random() * 0.5)
        raise LLMError(f"FreeLLMAPI non raggiungibile: {last}")

    async def search(self, query: str, max_results: int = 6, topic: str = "general") -> list[dict]:
        """Ricerca web tramite i motori di FreeLLMAPI (Parallel senza chiave, poi gli altri attivi). Solleva LLMError se nessuno risponde."""
        try:
            r = await self._client.post(self._url("/search"), headers={"Authorization": f"Bearer {self._api_key()}"},
                                        json={"query": query, "max_results": max_results, "topic": topic}, timeout=25)
        except httpx.HTTPError as e:
            raise LLMError(f"ricerca non raggiungibile: {type(e).__name__}") from e
        if r.status_code != 200:
            raise LLMError(f"ricerca web: HTTP {r.status_code}")
        return [h for h in r.json().get("results", []) if isinstance(h, dict) and h.get("url")]

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
