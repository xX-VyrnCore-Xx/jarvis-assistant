import json

import pytest

from app.edgetts import VOICES, EdgeTTS
from app.pc import PCBridge
from app.toolwatch import FAILS, ToolWatch
from app.tools import ToolRegistry
from app.voice import TTSError, VoiceService


class Pc:
    connected = False
    caps: dict = {}


@pytest.mark.asyncio
async def test_neural_voice_speaks_when_the_pc_is_off_and_backs_off_after_a_failure(monkeypatch):
    e = EdgeTTS()
    calls = []

    async def fake(text, voice):
        calls.append(voice)
        return b"ID3" + b"x" * 600

    monkeypatch.setattr(e, "_stream", fake)
    v = VoiceService(Pc(), e)
    assert v.enabled
    audio, mime = await v.speak_any("Buongiorno, signore")
    assert mime == "audio/mpeg" and audio.startswith(b"ID3") and calls == [VOICES["isabella"][0]]
    await v.speak_any("Buongiorno, signore")
    assert len(calls) == 1  # la seconda volta viene dalla cache
    assert e.set_voice("diego") and not e.set_voice("inesistente")

    async def boom(text, voice):
        raise OSError("rete")

    monkeypatch.setattr(e, "_stream", boom)
    with pytest.raises(TTSError):
        await v.speak_any("un'altra frase")
    assert not e.enabled and not v.enabled  # per qualche minuto non si riprova: l'app usa la voce del dispositivo


@pytest.mark.asyncio
async def test_broken_tools_leave_the_list_and_come_back():
    reg, state = ToolRegistry(), {"ok": False}

    async def meteo(city: str) -> str:
        return "Sereno, 21°" if state["ok"] else "Errore: servizio meteo non raggiungibile"

    reg.register("get_weather", "meteo", {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}, meteo)
    sent = []

    class N:
        async def push(self, kind, title, body="", telegram=None, meta=None):
            sent.append(title)

    w = ToolWatch(reg, N(), {"get_weather": {"city": "Roma"}})
    for _ in range(FAILS - 1):
        await w.run()
    assert "get_weather" in reg.names and not sent
    await w.run()
    assert "get_weather" not in reg.names and "fuori servizio" in await reg.call("get_weather", json.dumps({"city": "Roma"})) and sent == ["Strumento fuori servizio"]
    await w.run()
    assert len(sent) == 1  # un solo avviso finché resta rotto
    state["ok"] = True
    await w.run()
    assert "get_weather" in reg.names and not reg.down and sent[-1] == "Strumento ripristinato" and w.status["get_weather"]["ok"]
