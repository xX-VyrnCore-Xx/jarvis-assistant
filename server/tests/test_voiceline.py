import re

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import get_settings
from app.auth import throttle
from app.voiceline import MAX_TURNS, VoiceLine, normalize, signature, valid
from app.memory import MemoryStore
from app.config import Settings

URL = "https://jarvis.test"
TOKEN = "twilio-secret"
AUTH = {"Authorization": "Bearer tok"}


class FakeNotifier:
    def __init__(self):
        self.sent = []

    async def push(self, kind, title, body="", telegram=None, meta=None):
        self.sent.append((title, body, telegram))


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    async def chat(self, messages, tools=None, model=None, kind="chat"):
        assert tools is None and kind == "call"  # la telefonata non ha strumenti
        self.seen.append(messages)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return {"content": r}


def line(replies=(), token=TOKEN):
    s = Settings(jarvis_api_token="t", twilio_auth_token=token, owner_name="Matteo")
    return VoiceLine(s, MemoryStore(), FakeLLM(replies), FakeNotifier())


def test_signature_matches_twilios_algorithm_and_rejects_tampering():
    params = {"CallSid": "CA1", "From": "+393331234567"}
    sig = signature(TOKEN, URL + "/twilio/voice", params)
    assert valid(TOKEN, URL + "/twilio/voice", params, sig)
    assert not valid(TOKEN, URL + "/twilio/voice", {**params, "From": "+39000"}, sig) and not valid("altro", URL + "/twilio/voice", params, sig) and not valid(TOKEN, URL, params, "")
    assert normalize("+39 333 123 4567") == normalize("333-1234567") == "331234567"[-9:]


@pytest.mark.asyncio
async def test_modes_off_allowed_and_all_decide_who_gets_an_answer():
    l = line()
    assert "non è attivo" in (await l.incoming({"CallSid": "1", "From": "+39333111"})).body.decode()  # spenta di default
    await l.save("allowed", [{"name": "Mamma", "number": "+39 333 123 4567"}], "")
    refused = (await l.incoming({"CallSid": "2", "From": "+39 347 000 0000"})).body.decode()
    assert "non è autorizzato" in refused and "<Hangup/>" in refused and "Gather" not in refused
    assert "non autorizzata" in l.notifier.sent[0][0]
    ok = (await l.incoming({"CallSid": "3", "From": "3331234567"})).body.decode()
    assert "<Gather" in ok and 'language="it-IT"' in ok and "Matteo" in ok
    with pytest.raises(ValueError):
        await l.save("allowed", [], "")
    await l.save("all", [], "Pronto, qui JARVIS.")
    assert "Pronto, qui JARVIS." in (await l.incoming({"CallSid": "4", "From": "anonymous"})).body.decode()


@pytest.mark.asyncio
async def test_conversation_takes_a_message_hangs_up_and_notifies_the_owner():
    l = line(["Buongiorno Mamma, dica pure.", "Perfetto, riferirò che richiami tu. Arrivederci [FINE]"])
    await l.save("all", [{"name": "Mamma", "number": "+39333111222"}], "")
    await l.incoming({"CallSid": "C1", "From": "+39333111222"})
    r1 = (await l.gather({"CallSid": "C1", "SpeechResult": "Ciao sono la mamma"})).body.decode()
    assert "<Gather" in r1 and "dica pure" in r1
    r2 = (await l.gather({"CallSid": "C1", "SpeechResult": "Digli di richiamarmi stasera"})).body.decode()
    assert "<Hangup/>" in r2 and "[FINE]" not in r2 and "Gather" not in r2
    system = l.llm.seen[0][0]["content"]
    assert "Mamma" in system and "Matteo" in system and "nulla di privato" in system  # nessun dato privato nel prompt
    await l.finished({"CallSid": "C1", "CallStatus": "completed", "CallDuration": "42"})
    title, body, tg = l.notifier.sent[-1]
    assert title == "📞 Messaggio da Mamma" and "Digli di richiamarmi stasera" in body and tg is True
    assert "C1" not in l.calls  # nulla resta in memoria


@pytest.mark.asyncio
async def test_silence_model_failures_and_limits_never_leave_the_caller_hanging():
    l = line([RuntimeError("giù")])
    await l.save("all", [], "")
    await l.incoming({"CallSid": "S", "From": "+39333"})
    for _ in range(2):
        assert "ripetere" in (await l.gather({"CallSid": "S", "SpeechResult": ""})).body.decode()
    assert "<Hangup/>" in (await l.gather({"CallSid": "S", "SpeechResult": ""})).body.decode()  # troppo silenzio: si chiude
    await l.incoming({"CallSid": "T", "From": "+39333"})
    down = (await l.gather({"CallSid": "T", "SpeechResult": "vorrei lasciare un messaggio"})).body.decode()
    assert "<Hangup/>" in down and "riferirò" in down  # modello giù: il messaggio si prende lo stesso
    assert "scaduta" in (await l.gather({"CallSid": "ignota", "SpeechResult": "ciao"})).body.decode()
    await l.incoming({"CallSid": "U", "From": "+39333"})
    l.calls["U"]["turns"] = [{"role": "user", "content": "x"}] * (MAX_TURNS * 2 + 1)
    assert "<Hangup/>" in (await l.gather({"CallSid": "U", "SpeechResult": "ancora"})).body.decode()
    xml = (await l.incoming({"CallSid": "V", "From": "+39333"})).body.decode()
    l.llm.replies = ["Certo <script>&</script> **ok** https://evil.example"]
    out = (await l.gather({"CallSid": "V", "SpeechResult": "ciao"})).body.decode()
    assert "<script>" not in out and "evil.example" not in out and "**" not in out and "&amp;" in out  # XML e testo parlato ripuliti


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JARVIS_API_TOKEN", "tok")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("PUBLIC_URL", URL)
    monkeypatch.delenv("FREELLM_INTERNAL_URL", raising=False)
    get_settings.cache_clear()
    throttle._fails.clear()
    throttle._locked.clear()
    with TestClient(main.app) as c:
        yield c
    get_settings.cache_clear()


def test_twilio_routes_require_a_valid_signature_and_the_config_api_works(client):
    params = {"CallSid": "CA9", "From": "+39333111222", "To": "+39000"}
    assert client.post("/twilio/voice", data=params).status_code == 403
    assert client.post("/twilio/voice", data=params, headers={"X-Twilio-Signature": "sbagliata"}).status_code == 403
    sig = signature(TOKEN, URL + "/twilio/voice", params)
    r = client.post("/twilio/voice", data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml") and "non è attivo" in r.text  # firma giusta ma servizio spento
    cfg = client.get("/api/calls/config", headers=AUTH).json()
    assert cfg["enabled"] and cfg["mode"] == "off" and cfg["voice_url"] == URL + "/twilio/voice"
    assert client.post("/api/calls/config", headers=AUTH, json={"mode": "allowed", "numbers": []}).status_code == 422
    ok = client.post("/api/calls/config", headers=AUTH, json={"mode": "allowed", "numbers": [{"name": "Mamma", "number": "+39333111222"}]})
    assert ok.status_code == 200 and ok.json()["mode"] == "allowed"
    r2 = client.post("/twilio/voice", data=params, headers={"X-Twilio-Signature": sig})
    assert "<Gather" in r2.text and re.search(r"Matteo|signore", r2.text)
