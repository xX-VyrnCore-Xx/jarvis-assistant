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


@pytest.mark.asyncio
async def test_reminder_tool_and_delivery():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.scheduler import deliver_due_reminders

    s = Settings(jarvis_api_token="t")
    store = MemoryStore()
    reg = ToolRegistry()
    register_basic_tools(reg, s, store)
    tz = ZoneInfo(s.timezone)

    past = (datetime.now(tz) - timedelta(minutes=1)).isoformat()
    assert "passato" in await reg.call("add_reminder", json.dumps({"text": "x", "when": past}))

    soon = (datetime.now(tz) + timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert "fissato" in await reg.call("add_reminder", json.dumps({"text": "chiama Luca", "when": soon}))

    class FakeTG:
        sent = []

        async def notify_owner(self, text):
            self.sent.append(text)

    tg = FakeTG()
    assert await deliver_due_reminders(store, tg, datetime.now(tz)) == 0
    assert await deliver_due_reminders(store, tg, datetime.now(tz) + timedelta(hours=2)) == 1
    assert "chiama Luca" in tg.sent[0]
    assert await deliver_due_reminders(store, tg, datetime.now(tz) + timedelta(hours=2)) == 0


def test_telegram_webhook_whitelist(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "42")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sec")
    from app import main
    from app.config import get_settings

    get_settings.cache_clear()
    handled = []

    async def fake(chat_id, text):
        handled.append((chat_id, text))

    monkeypatch.setattr(main, "_handle_telegram_text", fake)
    upd = lambda uid: {"message": {"from": {"id": uid}, "chat": {"id": uid}, "text": "ciao"}}  # noqa: E731
    with TestClient(main.app) as c:
        assert c.post("/telegram/webhook", json=upd(42)).status_code == 403
        h = {"X-Telegram-Bot-Api-Secret-Token": "sec"}
        assert c.post("/telegram/webhook", json=upd(99), headers=h).status_code == 200
        assert c.post("/telegram/webhook", json=upd(42), headers=h).status_code == 200
    assert handled == [(42, "ciao")]
    get_settings.cache_clear()


def test_pc_bridge_roundtrip(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "secret")
    from app import main
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(main.app) as c:
        # token errato: chiusura
        with c.websocket_connect("/ws/pc") as ws:
            ws.send_json({"token": "no"})
            with pytest.raises(Exception):
                ws.receive_json()
        assert not main.app.state.pc.connected

        with c.websocket_connect("/ws/pc") as ws:
            ws.send_json({"token": "secret"})
            assert ws.receive_json() == {"type": "ready"}
            import threading

            out = {}
            t = threading.Thread(
                target=lambda: out.update(r=c.portal.call(main.app.state.pc.call, "pc_lock", {}, 5))
            )
            t.start()
            cmd = ws.receive_json()
            assert cmd["action"] == "pc_lock"
            ws.send_json({"type": "result", "id": cmd["id"], "output": "Bloccato."})
            t.join(5)
            assert out["r"] == "Bloccato."
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_pc_call_without_connection():
    from app.pc import PCBridge

    assert "non è connesso" in await PCBridge().call("pc_lock", {})


@pytest.mark.asyncio
async def test_voice_flag_adds_spoken_style_instruction():
    agent, _ = make([{"content": "ok"}, {"content": "ok"}])
    await agent.reply("ciao", "v", voice=True)
    await agent.reply("ciao", "t", voice=False)
    assert "AD ALTA VOCE" in agent.llm.calls[0][0]["content"]
    assert "AD ALTA VOCE" not in agent.llm.calls[1][0]["content"]
