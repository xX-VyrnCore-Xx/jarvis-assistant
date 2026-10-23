import json

import httpx
import pytest

from app.config import Settings
from app.ctx import ContextBudget, cap_text, classify_error, fit, tokens_of
from app.llm import LLMClient, LLMError
from app.routing import BALANCED, FAST, RELIABLE, Router


def tool_round(i, text="x" * 6000):
    return [{"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "read_webpage", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": text}]


def valid_pairs(msgs):
    """Ogni risultato di tool segue l'assistente che lo ha chiesto: altrimenti i provider rifiutano la richiesta."""
    ids = set()
    for m in msgs:
        if m.get("tool_calls"):
            ids = {c["id"] for c in m["tool_calls"]}
        elif m.get("role") == "tool":
            assert m["tool_call_id"] in ids
    return True


def test_fit_leaves_small_requests_alone_and_strips_private_keys():
    msgs = [{"role": "system", "content": "s", "_opt": ["blocco"]}, {"role": "user", "content": "ciao"}]
    out, tools, saved = fit(msgs, None, 5000)
    assert saved == 0 and out[0] == {"role": "system", "content": "s"} and out[1] == msgs[1]


def test_fit_shrinks_in_steps_without_breaking_tool_pairs():
    brain = "Dal secondo cervello:\n" + "frammento utile. " * 400
    system = "Sei JARVIS.\n\n" + brain
    history = [{"role": "user", "content": "vecchia domanda " * 60}, {"role": "assistant", "content": "vecchia risposta " * 60}]
    msgs = [{"role": "system", "content": system, "_opt": [brain]}, *history, {"role": "user", "content": "e adesso?"}, *tool_round(1), *tool_round(2)]
    tools = [{"type": "function", "function": {"name": f"t{i}", "description": "d" * 300, "parameters": {"type": "object", "properties": {}}}} for i in range(20)]
    before = tokens_of(msgs, tools)
    out, tls, saved = fit(msgs, tools, 2500, {"t1"})
    assert before > 2500 and tokens_of(out, tls) <= 2500 + 200 and saved > 0
    assert valid_pairs(out) and out[-1]["role"] in ("tool", "user") and any(m["content"] == "e adesso?" for m in out if m["role"] == "user")
    assert all(len(str(m["content"] or "")) <= 2700 for m in out if m["role"] == "tool")
    assert tls is None or len(tls) <= 20


def test_cap_text_keeps_head_and_tail_and_error_classification():
    t = cap_text("A" * 5000 + "FINE", 1000)
    assert len(t) < 1100 and t.startswith("AAA") and t.endswith("FINE") and "omessi" in t
    assert classify_error(413) == "too_large"
    assert classify_error(400, "Request too large for model on tokens per minute (TPM)") == "too_large"
    assert classify_error(429, "Limit 7000, Requested 7362 tokens per minute") == "too_large"
    assert classify_error(404, "This model is no longer available") == "model_gone"
    assert classify_error(400, "Invalid tool schema in tools[3].function.parameters") == "bad_tools"
    assert classify_error(401) == "auth" and classify_error(400, "boh") == "bad_request" and classify_error(503) == "retry"


def test_budget_shrinks_on_rejection_and_recovers_slowly():
    b = ContextBudget()
    assert b.for_profile(FAST) < b.for_profile(BALANCED)
    start = b.for_profile(BALANCED)
    assert b.too_large(BALANCED) < start
    low = b.for_profile(BALANCED)
    for _ in range(30):
        b.ok(BALANCED)
    assert low < b.for_profile(BALANCED) <= start


def test_routing_is_size_and_mode_aware():
    r = Router()
    m = lambda text, system="Sei JARVIS": [{"role": "system", "content": system}, {"role": "user", "content": text}]  # noqa: E731
    assert r.pick(m("traduci questa frase in inglese: buongiorno a tutti")).profile == FAST
    assert r.pick(m("come stai?", "Sei JARVIS\nLa risposta verrà LETTA AD ALTA VOCE")).reason == "risposta parlata"
    assert r.pick(m("ciao", "Sei JARVIS " + "contesto " * 3000)).profile == BALANCED  # prompt grande: non ai profili con limiti stretti
    cont = m("che ore sono?") + [{"role": "assistant", "content": None, "tool_calls": []}, {"role": "tool", "tool_call_id": "1", "content": "10:00"}]
    assert r.pick(cont, tools=True).reason == "continuazione dei strumenti"


def client(handler, **kw):
    s = Settings(jarvis_api_token="t", freellm_base_url="http://x/v1", freellm_api_key="k", **kw)
    return LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def ok(text="ciao", model="m1"):
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"role": "assistant", "content": text}}], "usage": {"prompt_tokens": 10, "completion_tokens": 3}})


@pytest.mark.asyncio
async def test_too_large_request_is_shrunk_and_retried_automatically(monkeypatch):
    sizes = []

    def handler(req):
        body = json.loads(req.content)
        sizes.append(tokens_of(body["messages"], body.get("tools")))
        if len(sizes) == 1:
            return httpx.Response(413, json={"error": {"message": "Request too large for model: tokens per minute (TPM): Limit 7000"}})
        return ok()

    c = client(handler, llm_routing=False, llm_context_tokens=20000)
    msgs = [{"role": "system", "content": "Sei JARVIS"}, {"role": "user", "content": "domanda"}, *tool_round(1, "y" * 30000)]
    out = await c.chat(msgs, None, model="auto")
    assert out["content"] == "ciao" and len(sizes) == 2 and sizes[1] < sizes[0]


@pytest.mark.asyncio
async def test_rejected_tools_are_dropped_and_dead_models_are_replaced():
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append((body["model"], bool(body.get("tools"))))
        if body.get("tools"):
            return httpx.Response(400, json={"error": {"message": "Invalid tool schema: tools[0].function.parameters"}})
        return ok("risposta in testo")

    c = client(handler, llm_routing=False)
    tools = [{"type": "function", "function": {"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}}]
    out = await c.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], tools, model="auto")
    assert out["content"] == "risposta in testo" and seen == [("auto", True), ("auto", False)]

    models = []

    def handler2(req):
        m = json.loads(req.content)["model"]
        models.append(m)
        return httpx.Response(404, json={"error": {"message": "model no longer available"}}) if m == "auto:fast" else ok(model=m)

    c2 = client(handler2)
    c2.router = Router()
    out = await c2.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "ciao"}], None, model="auto")
    assert out["content"] == "ciao" and models[0] == FAST and models[-1] != FAST and FAST in c2._gone


@pytest.mark.asyncio
async def test_empty_completion_is_retried_on_another_model_and_auth_errors_are_not(monkeypatch):
    async def no_wait(_):
        return None

    monkeypatch.setattr("app.llm.asyncio.sleep", no_wait)
    calls = []

    def handler(req):
        calls.append(json.loads(req.content)["model"])
        return ok("") if len(calls) == 1 else ok("ora sì")

    c = client(handler)
    assert (await c.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "ciao"}], None, model="auto"))["content"] == "ora sì" and len(calls) == 2
    c3 = client(lambda req: httpx.Response(401, json={}))
    with pytest.raises(LLMError, match="rifiutato"):
        await c3.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], None, model="auto")
