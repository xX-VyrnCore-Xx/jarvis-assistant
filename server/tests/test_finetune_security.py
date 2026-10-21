import json

import pytest

from app.backup import decrypt, derive_key, encrypt
from app.config import Settings
from app.finetune import PATH, PURPOSE, build_examples, export_dataset, to_jsonl
from app.memory import MemoryStore
from app.security import SecurityHeaders


def rows():
    r = []
    for i in range(14):
        r += [{"session_id": "s1", "role": "user", "content": f"Domanda {i} con IBAN IT60X0542811101000000123456"},
              {"session_id": "s1", "role": "assistant", "content": f"Risposta lunga abbastanza numero {i}, signore."}]
    r += [{"session_id": "briefing", "role": "assistant", "content": "Buongiorno signore, ecco la giornata."},
          {"session_id": "s2", "role": "user", "content": "ciao"}, {"session_id": "s2", "role": "assistant", "content": "Errore: provider non raggiungibile"}]
    return r


def test_examples_are_masked_chunked_and_skip_errors_and_briefings():
    ex = build_examples(rows())
    assert len(ex) == 3 and all(e["messages"][0]["role"] == "system" for e in ex)
    text = to_jsonl(ex).decode()
    assert "IT60X0542811101000000123456" not in text and "[IBAN_1]" in text
    assert "Errore" not in text and "Buongiorno" not in text


def test_dataset_crypto_uses_its_own_key():
    s = Settings(jarvis_api_token="t", encryption_key="segreto")
    blob = encrypt(derive_key(s, PURPOSE), b"{}")
    assert decrypt(derive_key(s, PURPOSE), blob) == b"{}"
    with pytest.raises(Exception):
        decrypt(derive_key(s), blob)


class FakeBackup:
    enabled = True
    repo = "u/priv"
    _auth = {"Authorization": "Bearer x"}

    class _client:
        sent = None

        @classmethod
        async def post(cls, url, headers=None, content=None):
            cls.sent = (url, content)

            class R:
                def raise_for_status(self): pass
            return R()


class Store(MemoryStore):
    async def messages_between(self, start, end, limit):
        return rows()


@pytest.mark.asyncio
async def test_export_uploads_only_ciphertext():
    s = Settings(jarvis_api_token="t", encryption_key="segreto")
    out = await export_dataset(s, Store(), FakeBackup(), 30)
    assert out["uploaded"] and out["examples"] == 3
    url, content = FakeBackup._client.sent
    assert url.endswith("/api/datasets/u/priv/commit/main") and PATH in content and "Domanda" not in content and "IT60" not in content
    FakeBackup.enabled = False
    with pytest.raises(RuntimeError):
        await export_dataset(s, Store(), FakeBackup(), 30)


@pytest.mark.asyncio
async def test_security_headers_are_strict():
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(m): sent.append(m)
    await SecurityHeaders(app)({"type": "http", "path": "/api/x", "headers": []}, None, send)
    h = dict(sent[0]["headers"])
    assert h[b"x-frame-options"] == b"DENY" and b"default-src 'none'" in h[b"content-security-policy"] and b"includeSubDomains" in h[b"strict-transport-security"]


@pytest.mark.asyncio
async def test_settings_and_devices_are_encrypted_at_rest_and_legacy_rows_converted():
    from app.crypto import Vault
    from tests.test_privacy_crypto import _supabase

    v = Vault("k1")
    store, sent, rows = _supabase(v, {"app_settings": [{"key": "a", "value": "valore chiaro"}], "devices": [{"id": 3, "token": "fcm-token-segreto-123", "label": "Telefono"}]})
    await store.set_setting("k", "stato segreto")
    await store.upsert_device("android", "fcm-token-segreto-123", "Pixel di Mario")
    dumped = json.dumps(sent)
    assert "stato segreto" not in dumped and "fcm-token-segreto" not in dumped and "Pixel" not in dumped
    dev = next(b for t, b in sent if t == "devices")
    assert dev["token_hash"] == v.blind("fcm-token-segreto-123") and dev["token"].startswith("enc1:")
    sent.clear()
    await store.encrypt_existing()
    patches = {t: b for t, b in sent if t.endswith(":patch")}
    assert patches["app_settings:patch"]["value"].startswith("enc1:") and patches["devices:patch"]["token_hash"] == v.blind("fcm-token-segreto-123")
