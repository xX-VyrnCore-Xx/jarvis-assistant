import pytest

from app.grammar import Corrector, _safe, quick
from tests.test_features import AUTH, client  # noqa: F401


def test_quick_rules_fix_typical_dictation_and_typing_errors_without_touching_meaning():
    assert quick("perche' non vieni ? e' tardi,ma sono qui.Ciao") == "Perché non vieni? È tardi, ma sono qui. Ciao"
    assert quick("qual'è il problema un'amico un'auto un'altra volta") == "Qual è il problema un amico un'auto un'altra volta"
    assert quick("un po di pazienza, gia fatto piu tardi pero va bene un pò") == "Un po' di pazienza, già fatto più tardi però va bene un po'"
    assert quick("Sara e Andrea: sara tardi, eta  piu  grande") == "Sara e Andrea: sarà tardi, età più grande"  # i nomi propri restano
    assert quick("alle 10:30 costa 3,50 su www.example.com") == "Alle 10:30 costa 3,50 su www.example.com"  # orari, decimali e indirizzi intatti
    assert quick("   ") == "" and quick("già corretto.") == "Già corretto."


def test_model_output_is_accepted_only_if_it_keeps_the_meaning():
    assert _safe("ho comprato 3 mele a 2,50", "Ho comprato 3 mele a 2,50.")
    assert not _safe("ho comprato 3 mele a 2,50", "Ho comprato 4 mele a 2,50.")  # numeri cambiati
    assert not _safe("scrivimi a mario@x.it", "Scrivimi a luigi@x.it")  # indirizzo cambiato
    assert not _safe("ciao come stai oggi pomeriggio", "Certamente! Ecco una poesia lunga lunga lunga sul mare e sul cielo e sul vento che passa")  # risposta invece di correzione


@pytest.mark.asyncio
async def test_corrector_full_uses_the_model_but_falls_back_to_the_rules():
    class Llm:
        def __init__(self, out=None):
            self.out, self.n = out, 0

        async def chat(self, messages, tools=None, **kw):
            self.n += 1
            if self.out is None:
                raise RuntimeError("giù")
            assert kw["kind"] == "fix" and "NON cambiare il significato" in messages[0]["content"]
            return {"content": self.out}

    c = Corrector(Llm("Ieri io e Marco siamo andati al mare."))
    assert await c.fix("ieri io e marco siamo andato al mare", "full") == "Ieri io e Marco siamo andati al mare."
    assert await Corrector(Llm("Ecco una poesia completamente diversa e molto più lunga del testo originale che dovevo solo correggere")).fix("ciao a tutti voi qui", "full") == "Ciao a tutti voi qui"
    bad = Corrector(Llm(None))
    assert await bad.fix("perche' no", "full") == "Perché no"  # il modello non risponde: restano le regole
    llm = Llm("x")
    assert await Corrector(llm).fix("perche' no", "quick") == "Perché no" and llm.n == 0  # quick non chiama mai il modello


def test_stt_and_correct_endpoints(client, monkeypatch):  # noqa: F811
    llm = client.app.state.agent.llm

    async def fake(audio, filename="v.ogg", mime="audio/ogg"):
        assert filename == "voce.webm" and mime == "audio/webm" and len(audio) > 800
        return "ciao,come stai oggi"

    monkeypatch.setattr(llm, "transcribe", fake)
    r = client.post("/api/stt?fix=quick", headers={**AUTH, "Content-Type": "audio/webm;codecs=opus"}, content=b"x" * 2000)
    assert r.status_code == 200 and r.json() == {"text": "Ciao, come stai oggi", "raw": "ciao,come stai oggi"}
    assert client.post("/api/stt?fix=none", headers={**AUTH, "Content-Type": "audio/webm"}, content=b"x" * 2000).json()["text"] == "ciao,come stai oggi"
    assert client.post("/api/stt", headers={**AUTH, "Content-Type": "audio/webm"}, content=b"x" * 100).status_code == 422
    assert client.post("/api/stt", headers={**AUTH, "Content-Type": "video/mp4"}, content=b"x" * 2000).status_code == 415

    async def ghost(audio, filename="v.ogg", mime="audio/ogg"):
        return "Sottotitoli creati dalla comunità Amara.org"

    monkeypatch.setattr(llm, "transcribe", ghost)
    assert client.post("/api/stt", headers={**AUTH, "Content-Type": "audio/webm"}, content=b"x" * 2000).json()["text"] == ""  # allucinazione su silenzio: scartata
    r = client.post("/api/correct", headers=AUTH, json={"text": "perche' non vieni", "level": "quick"})
    assert r.json() == {"text": "Perché non vieni", "changed": True}
