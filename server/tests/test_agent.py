import json

import pytest
from fastapi.testclient import TestClient

from app.agent import Agent
from app.config import Settings
from app.main import app
from app.memory import MemoryStore
from app.tools import ToolRegistry
from app.tools.basic import register_basic_tools


class FakeLLM:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        return self.script.pop(0)


def make(script):
    s = Settings(jarvis_api_token="t")
    store = MemoryStore()
    reg = ToolRegistry()
    register_basic_tools(reg, s, store)
    return Agent(s, FakeLLM(script), store, reg), store


@pytest.mark.asyncio
async def test_plain_reply_is_persisted():
    agent, store = make([{"content": "Buongiorno, signore."}])
    assert await agent.reply("ciao", "s1") == "Buongiorno, signore."
    assert [m["role"] for m in store.messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_tool_call_roundtrip_saves_memory():
    call = {"id": "1", "type": "function",
            "function": {"name": "remember", "arguments": json.dumps({"content": "Ama il caffè"})}}
    agent, store = make([{"content": None, "tool_calls": [call]}, {"content": "Annotato."}])
    assert await agent.reply("amo il caffè", "s1") == "Annotato."
    assert store.memories == ["Ama il caffè"]


@pytest.mark.asyncio
async def test_unknown_tool_does_not_crash():
    call = {"id": "1", "type": "function", "function": {"name": "boh", "arguments": "{}"}}
    agent, _ = make([{"content": None, "tool_calls": [call]}, {"content": "ok"}])
    assert await agent.reply("x", "s1") == "ok"


@pytest.mark.asyncio
async def test_tool_loop_is_bounded():
    call = {"id": "1", "type": "function", "function": {"name": "get_datetime", "arguments": "{}"}}
    agent, _ = make([{"content": None, "tool_calls": [call]}] * 5)
    assert "limite" in await agent.reply("x", "s1")


def test_health_open_and_chat_requires_token(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "secret")
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.post("/chat", json={"message": "hi"}).status_code == 401
        assert c.post("/chat", json={"message": "hi"}, headers={"Authorization": "Bearer no"}).status_code == 401
    get_settings.cache_clear()
