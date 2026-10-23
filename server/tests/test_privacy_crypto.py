import asyncio
import json

import httpx
import pytest

from app.agent import Agent
from app.config import Settings
from app.crypto import UNREADABLE, Vault
from app.llm import LLMClient, LLMError
from app.memory import MemoryStore, SupabaseStore
from app.privacy import Redactor
from app.tools import ToolRegistry
from app.tools.basic import register_basic_tools
from tests.test_agent import FakeLLM
from tests.test_features import client  # noqa: F401

IBAN = "IT60X0542811101000000123456"
CARD = "4539 1488 0343 6467"  # numero di prova valido per Luhn


def test_vault_roundtrip_wrong_key_and_blind_index():
    v = Vault("chiave-segreta")
    sealed = v.seal("Ho un appuntamento dal dentista")
    assert sealed.startswith("enc1:") and "dentista" not in sealed
    assert v.seal(sealed) == sealed and v.open(sealed) == "Ho un appuntamento dal dentista"
    assert v.seal("x") != v.seal("x")  # nonce casuale: lo stesso testo non produce lo stesso cifrato
    assert Vault("altra-chiave").open(sealed) == UNREADABLE
    assert v.open("testo vecchio in chiaro") == "testo vecchio in chiaro"  # dati precedenti alla cifratura
    assert Vault("").seal("ciao") == "ciao"
    # indice cieco: stesse parole -> stessi HMAC (anche con accenti/maiuscole), chiavi diverse -> HMAC diversi
    assert set(v.terms("Il caffè")) & set(v.terms("CAFFE")) and not set(v.terms("caffè")) & set(Vault("altra").terms("caffè"))
    assert all("caff" not in t for t in v.terms("caffè"))


def test_redactor_masks_validates_and_restores():
    r = Redactor("standard")
    text = f"Il mio IBAN è {IBAN}, carta {CARD}, password: Tr0ub4dor&3 e il numero 1234567890123 non è una carta"
    out = r.mask(text)
    assert IBAN not in out and CARD not in out and "Tr0ub4dor" not in out
    assert "[IBAN_1]" in out and "[CARTA_1]" in out and "1234567890123" in out  # il falso positivo resta com'è (Luhn)
    assert r.mask(IBAN) == "[IBAN_1]"  # stesso valore, stesso segnaposto
    assert r.unmask(out) == text
    assert json.loads(f'{{"to": "{r.unmask_json("[IBAN_1]")}"}}')["to"] == IBAN
    assert Redactor("standard").mask("mario@x.it +39 333 1234567") == "mario@x.it +39 333 1234567"
    assert "[EMAIL_1]" in Redactor("strict").mask("scrivi a mario@x.it") and Redactor("off").mask(IBAN) == IBAN


@pytest.mark.asyncio
async def test_model_never_sees_sensitive_data_but_tools_and_user_do():
    seen = {}
    call = {"id": "1", "type": "function", "function": {"name": "remember", "arguments": json.dumps({"content": "IBAN [IBAN_1]"})}}
    s = Settings(jarvis_api_token="t")
    store, reg = MemoryStore(), ToolRegistry()
    register_basic_tools(reg, s, store)
    llm = FakeLLM([{"content": None, "tool_calls": [call]}, {"content": "Salvato l'IBAN [IBAN_1]."}])
    agent = Agent(s, llm, store, reg)
    answer = await agent.reply(f"Ricorda il mio IBAN {IBAN}", "s")
    sent = json.dumps(llm.calls)
    assert IBAN not in sent and "[IBAN_1]" in sent  # al modello arriva solo il segnaposto
    assert store.memories == [f"IBAN {IBAN}"]  # il tool ha ricevuto il valore vero
    assert answer == f"Salvato l'IBAN {IBAN}."
    assert store.messages[0]["content"].endswith(IBAN)  # cronologia (cifrata a riposo nel database) col testo vero


def _supabase(vault, rows=None):
    sent = []
    rows = rows if rows is not None else {}

    def handler(req: httpx.Request) -> httpx.Response:
        table = req.url.path.rsplit("/", 1)[-1]
        if req.method == "POST":
            body = json.loads(req.content)
            sent.append((table, body))
            return httpx.Response(201, json=[{**body, "id": 1}])
        if req.method == "PATCH":
            sent.append((table + ":patch", json.loads(req.content)))
            return httpx.Response(204)
        sent.append((table + ":get", dict(req.url.params)))
        return httpx.Response(200, json=rows.get(table, []))

    s = Settings(supabase_url="https://x.supabase.co", supabase_service_key="k")
    return SupabaseStore(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)), vault=vault), sent, rows


@pytest.mark.asyncio
async def test_supabase_store_encrypts_writes_decrypts_reads_and_searches_blind():
    v = Vault("k1")
    store, sent, rows = _supabase(v)
    await store.add_message("s", "user", "segreto del messaggio")
    await store.add_memory("Ama il caffè amaro")
    assert all("segreto" not in json.dumps(b) and "caff" not in json.dumps(b) for _, b in sent)  # il database vede solo cifrato + HMAC
    mem = next(b for t, b in sent if t == "memories")
    assert mem["terms"] and mem["content"].startswith("enc1:")

    rows["memories"] = [{"id": 1, "content": mem["content"]}]
    assert await store.search_memories("caffè", 5) == ["Ama il caffè amaro"]
    assert "ov.{" in sent[-1][1]["terms"] and "caff" not in sent[-1][1]["terms"]  # ricerca sull'indice cieco, non sul testo
    rows["messages"] = [{"role": "user", "content": next(b for t, b in sent if t == "messages")["content"]}]
    assert await store.recent_messages("s", 5) == [{"role": "user", "content": "segreto del messaggio"}]


@pytest.mark.asyncio
async def test_existing_plaintext_rows_get_encrypted_in_place():
    store, sent, rows = _supabase(Vault("k1"), {"memories": [{"id": 7, "content": "vecchio ricordo in chiaro"}]})
    assert await store.encrypt_existing() == 1
    table, patch = next((t, b) for t, b in sent if t == "memories:patch")
    assert patch["content"].startswith("enc1:") and patch["terms"] and "vecchio" not in json.dumps(patch)


@pytest.mark.asyncio
async def test_tool_cache_dedupes_expires_and_invalidates():
    reg, calls = ToolRegistry(), []

    async def slow(x: str) -> str:
        calls.append(x)
        await asyncio.sleep(0.05)
        return f"r-{x}" if x != "bad" else "Errore: no"

    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    reg.register("lookup", "", schema, slow, cache_ttl=60)
    a, b = await asyncio.gather(reg.call("lookup", '{"x":"1"}'), reg.call("lookup", '{"x":"1"}'))
    assert a == b == "r-1" and calls == ["1"]  # due richieste uguali insieme: una sola chiamata a monte
    assert await reg.call("lookup", '{"x":"1"}') == "r-1" and calls == ["1"]  # dalla cache
    await reg.call("lookup", '{"x":"bad"}'); await reg.call("lookup", '{"x":"bad"}')
    assert calls.count("bad") == 2  # gli errori non si memorizzano
    reg.invalidate("lookup")
    await reg.call("lookup", '{"x":"1"}')
    assert calls.count("1") == 2


@pytest.mark.asyncio
async def test_llm_retries_with_backoff_and_does_not_leak_bodies(monkeypatch):
    sleeps = []

    async def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr("app.llm.asyncio.sleep", fake_sleep)
    n = {"c": 0}

    def handler(req):
        n["c"] += 1
        if n["c"] < 3:
            return httpx.Response(429, headers={"retry-after": "2"}, text="prompt echo: IBAN " + IBAN)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    s = Settings(freellm_base_url="http://x/v1", freellm_api_key="k")
    llm = LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert (await llm.chat([{"role": "user", "content": "x"}]))["content"] == "ok" and sleeps[:2] == [2.0, 2.0]  # rispetta Retry-After

    bad = LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="IBAN " + IBAN))))
    with pytest.raises(LLMError) as e:
        await bad.chat([{"role": "user", "content": "x"}])
    assert IBAN not in str(e.value)  # i messaggi d'errore non riportano il corpo (che può citare il prompt)
    rejected = LLMClient(s, httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="no"))))
    with pytest.raises(LLMError, match="rifiutato"):
        await rejected.chat([{"role": "user", "content": "x"}])


@pytest.mark.asyncio
async def test_tasks_snooze_units_and_crypto_tools():
    from app.tools.web import convert_units, register_web_tools

    s = Settings()
    store, reg = MemoryStore(), ToolRegistry()
    register_basic_tools(reg, s, store)
    assert "id 1" in await reg.call("task_add", json.dumps({"text": "latte", "list_name": "Spesa"}))
    await reg.call("task_add", json.dumps({"text": "chiamare Luca"}))
    out = await reg.call("task_list", "{}")
    assert "spesa:" in out and "attività:" in out and "latte" in out
    await reg.call("task_done", json.dumps({"task_id": 1}))
    assert "latte" not in await reg.call("task_list", "{}") and "✔ latte" in await reg.call("task_list", json.dumps({"include_done": True}))
    await reg.call("task_delete", json.dumps({"task_id": 2}))
    assert "chiamare" not in await reg.call("task_list", "{}")

    from datetime import datetime, timedelta, timezone
    await store.add_reminder("pasta", datetime.now(timezone.utc) + timedelta(minutes=1))
    assert "rimandato" in await reg.call("reminder_snooze", json.dumps({"reminder_id": 1, "minutes": 30}))
    assert "non trovato" in await reg.call("reminder_snooze", json.dumps({"reminder_id": 99}))

    assert convert_units(100, "km", "mi").startswith("100 km = 62.1371 mi") and "21.11" in convert_units(70, "°F", "°C")

    def handler(req):
        return httpx.Response(200, json={"bitcoin": {"eur": 90000.5, "usd": 98000, "eur_24h_change": 1.234}})

    web = ToolRegistry()
    register_web_tools(web, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert "bitcoin: 90,000.50 €" in await web.call("crypto_price", json.dumps({"coin": "BTC"}))


def test_key_rotation_reads_old_data_flags_it_for_resealing_and_checks_strength():
    old, new = Vault("chiave-vecchia-molto-lunga-abcdef123456"), Vault("chiave-nuova-molto-lunga-abcdef1234567", ["chiave-vecchia-molto-lunga-abcdef123456"])
    sealed = old.seal("dato importante")
    assert Vault("chiave-nuova-molto-lunga-abcdef1234567").open(sealed) == UNREADABLE  # senza la chiave precedente non si legge
    assert new.open(sealed) == "dato importante" and new.needs_reseal(sealed)
    fresh = new.seal(new.open(sealed))
    assert not new.needs_reseal(fresh) and new.open(fresh) == "dato importante" and not new.needs_reseal("testo in chiaro")
    assert Vault("corta").strength()["weak"] and not new.strength()["weak"]
    assert Vault("token-di-accesso").strength("token-di-accesso")["shared_with_token"] and not new.strength("altro-token")["shared_with_token"]


def test_neural_voice_text_never_carries_personal_data_and_caches_are_bounded():
    from app.edgetts import speech_safe
    from app.tools import CACHE_TOTAL_MAX, ToolRegistry

    t = speech_safe("Scrivi a mario.rossi@example.com o chiama +39 333 1234567, IBAN IT60X0542811101000000123456, vedi https://x.it/a?t=1, chiave sk-abcdefghij1234567890, il 2026-10-23 alle 10:30")
    assert "@" not in t and "333" not in t and "IT60" not in t and "https" not in t and "sk-abc" not in t
    assert "un indirizzo email" in t and "un numero di telefono" in t and "un IBAN" in t and "un link" in t and "2026-10-23" in t and "10:30" in t  # date e orari restano

    import asyncio

    reg = ToolRegistry()

    async def big(q: str) -> str:
        return "x" * 50_000

    async def mail(q: str) -> str:
        return "contenuto di una email privata"

    reg.register("web_big", "d", {"type": "object", "properties": {"q": {"type": "string"}}}, big, cache_ttl=900)
    reg.register("gmail_read", "d", {"type": "object", "properties": {"q": {"type": "string"}}}, mail, cache_ttl=900)

    async def go():
        for i in range(60):
            await reg.call("web_big", f'{{"q": "{i}"}}')
        await reg.call("gmail_read", '{"q": "1"}')

    asyncio.run(go())
    assert sum(len(v[1]) for v in reg._cache.values()) <= CACHE_TOTAL_MAX  # la cache non cresce oltre il tetto
    mail_entry = next(v for k, v in reg._cache.items() if k.startswith("gmail_read"))
    import time

    assert mail_entry[0] - time.monotonic() <= 46  # i contenuti privati scadono in 45 secondi
    assert reg.clear_cache() > 0 and not reg._cache


def test_privacy_endpoints(client):  # noqa: F811
    from tests.test_features import AUTH

    r = client.get("/api/privacy", headers=AUTH).json()
    assert {f["id"] for f in r["flows"]} >= {"llm", "tts", "stt", "supabase", "github"} and r["redaction"] in ("standard", "strict", "off") and "encryption" in r
    assert client.post("/api/privacy/neural-voice", headers=AUTH, json={"neural_voice": False}).json()["neural_voice"] is False
    assert client.get("/api/voice", headers=AUTH).json()["neural"] is False
    assert client.post("/api/privacy/wipe", headers=AUTH).json()["ok"] is True
    assert "security" in client.get("/api/status", headers=AUTH).json()
