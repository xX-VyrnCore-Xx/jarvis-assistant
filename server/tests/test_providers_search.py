import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.llm import LLMClient, LLMError
from app.tools import ToolRegistry
from app.tools.basic import register_basic_tools
from app.tools.web import register_web_tools
from app.memory import MemoryStore

spec = importlib.util.spec_from_file_location("merge_providers", Path(__file__).parents[2] / "deploy" / "merge_providers.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)


def platforms(raw):
    return {k["platform"]: k for k in json.loads(raw)["keys"]}


def test_keyless_providers_added_without_touching_existing_config():
    out = platforms(mp.merge('{"keys":[{"platform":"groq","key":"gsk_x"}],"routing":{"strategy":"balanced"}}', {}))
    assert {"groq", "ovh", "kilo", "parallel"} <= set(out) and "siliconflow" not in out and "key" not in out["ovh"]
    assert json.loads(mp.merge('{"keys":[],"routing":{"strategy":"balanced"}}', {}))["routing"] == {"strategy": "balanced"}


def test_empty_config_gets_keyless_and_siliconflow_only_with_key():
    assert set(platforms(mp.merge("", {}))) == {"ovh", "kilo", "parallel"}
    sf = platforms(mp.merge("", {"SILICONFLOW_API_KEY": " sk-1 "}))["siliconflow"]
    assert sf["key"] == "sk-1"
    assert platforms(mp.merge('{"keys":[{"platform":"siliconflow","key":"mia"}]}', {"SILICONFLOW_API_KEY": "altra"}))["siliconflow"]["key"] == "mia"


def test_opt_out_and_invalid_json_untouched():
    assert mp.merge("", {"AUTO_KEYLESS_PROVIDERS": "0"}) == '{"keys":[]}'
    assert mp.merge('{"keys": [oops', {}) == '{"keys": [oops'


def make_llm(handler):
    s = Settings(jarvis_api_token="t", freellm_base_url="http://x/v1", freellm_api_key="k")
    return LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_llm_search_posts_to_gateway_and_raises_on_errors():
    seen = {}

    def ok(req):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"results": [{"title": "T", "url": "https://a.it", "content": "c"}, {"title": "x"}], "provider": "parallel"})

    hits = await make_llm(ok).search("meteo", 3, "news")
    assert seen["url"].endswith("/v1/search") and seen["body"] == {"query": "meteo", "max_results": 3, "topic": "news"}
    assert [h["url"] for h in hits] == ["https://a.it"]
    with pytest.raises(LLMError):
        await make_llm(lambda r: httpx.Response(503)).search("x")


@pytest.mark.asyncio
async def test_web_tools_use_gateway_results():
    async def search(q, n, topic):
        return [{"title": f"{topic}:{q}", "url": "https://b.it", "content": "testo"}]

    reg = ToolRegistry()
    register_web_tools(reg, search=search)
    register_basic_tools(reg, Settings(jarvis_api_token="t"), MemoryStore(), search=search)
    for name, topic in (("web_search", "general"), ("web_news", "news")):
        out = await reg.call(name, json.dumps({"query": "ciao"}))
        assert f"{topic}:ciao" in out and "https://b.it" in out


@pytest.mark.asyncio
async def test_web_search_falls_back_when_gateway_fails(monkeypatch):
    async def broken(q, n, topic):
        raise LLMError("giù")

    class FakeDDGS:
        def text(self, q, **kw):
            return [{"title": "DDG", "href": "https://ddg.it", "body": "b"}]

    import ddgs
    monkeypatch.setattr(ddgs, "DDGS", FakeDDGS)
    reg = ToolRegistry()
    register_basic_tools(reg, Settings(jarvis_api_token="t"), MemoryStore(), search=broken)
    assert "https://ddg.it" in await reg.call("web_search", json.dumps({"query": "x"}))
