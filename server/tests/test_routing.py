import json

import httpx
import pytest

from app.config import Settings
from app.llm import LLMClient
from app.routing import BALANCED, FAST, RELIABLE, SMART, Router


def msgs(text, system="Sei JARVIS"):
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def test_classification_by_kind_of_request():
    r = Router()
    assert r.pick(msgs("ciao come stai")).profile == FAST
    assert r.pick(msgs("che ore sono?"), tools=True).profile == RELIABLE
    assert r.pick(msgs("Perché il mio script python lancia Traceback in main.py:42?")).profile == SMART
    assert r.pick(msgs("scrivi una funzione che ordina una lista")).task == "code"
    assert r.pick(msgs("Analizza pro e contro di due strategie e motiva la scelta"), tools=True).profile == SMART
    assert r.pick(msgs("x" * 200)).profile == BALANCED
    assert r.pick(msgs("ok", system="Sei JARVIS\nSessione di coding attiva")).profile == SMART
    assert r.pick(msgs("riassumi"), kind="enrich").profile == FAST and r.pick(msgs("riassumi"), kind="journal").profile == BALANCED


def test_profile_in_trouble_is_skipped_then_recovers():
    r = Router()
    for t in (1, 2, 3):
        r.report(SMART, False, now=100 + t)
    assert not r.usable(SMART, now=200) and r.usable(SMART, now=500)
    for _ in range(3):
        r.report(SMART, False)
    assert r.pick(msgs("Debug di questo codice in app.py")).profile == BALANCED  # ripiego mentre è in difficoltà
    r.report(FAST, False)
    r.report(FAST, True, 800)
    assert r.summary()[FAST]["ok"] == 1 and r.usable(FAST)


@pytest.mark.asyncio
async def test_llm_sends_profile_and_task_type_but_respects_explicit_model():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((json.loads(req.content)["model"], req.headers.get("x-freellm-task-type")))
        return httpx.Response(200, json={"model": "x/y", "choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}})

    llm = LLMClient(Settings(jarvis_api_token="t", freellm_base_url="http://x/v1", freellm_api_key="k"), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await llm.chat(msgs("scrivi una funzione in python"))
    await llm.chat(msgs("ciao"))
    await llm.chat(msgs("ciao"), model="groq/llama")
    assert seen == [("auto:smart", "code"), ("auto:fast", "chat"), ("groq/llama", None)]
    off = LLMClient(Settings(jarvis_api_token="t", freellm_base_url="http://x/v1", freellm_api_key="k", llm_routing=False), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    seen.clear()
    await off.chat(msgs("ciao"))
    assert seen == [("auto", None)]
