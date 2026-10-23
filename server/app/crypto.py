"""Cifratura dei dati a riposo: i testi salvati su Supabase sono cifrati (AES-256-GCM) con una chiave derivata da ENCRYPTION_KEY.

Il database non vede mai il testo in chiaro. Per cercare nei ricordi senza decifrarli si usano «indici ciechi»: un HMAC di ogni parola,
con una chiave diversa da quella di cifratura (il database può confrontare gli HMAC ma non risalire alle parole).
"""
import base64
import hashlib
import hmac
import os
import re
import unicodedata

PREFIX = "enc1:"
UNREADABLE = "[dato non decifrabile: la chiave di cifratura è cambiata?]"


def _hkdf(secret: bytes, info: bytes) -> bytes:
    prk = hmac.new(b"jarvis-salt-v1", secret, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


class Vault:
    def __init__(self, secret: str, previous: tuple[str, ...] | list[str] = ()):
        """`previous`: chiavi precedenti (rotazione): i dati cifrati con quelle si leggono ancora e vengono riscritti con la chiave nuova."""
        self.enabled = bool(secret)
        self._secret_len = len(secret or "")
        self._old: list[bytes] = []
        if self.enabled:
            self._data_key = _hkdf(secret.encode(), b"jarvis-data-v1")
            self._index_key = _hkdf(secret.encode(), b"jarvis-index-v1")
            self._old = [_hkdf(p.strip().encode(), b"jarvis-data-v1") for p in previous if p and p.strip() and p.strip() != secret]

    def strength(self, token: str = "") -> dict:
        """Controllo di robustezza della chiave (mai la chiave stessa): lunghezza, e se è la stessa del token di accesso (in tal caso chi ha il token può decifrare i dati)."""
        return {"enabled": self.enabled, "length": self._secret_len, "weak": self.enabled and self._secret_len < 24,
                "shared_with_token": bool(self.enabled and token and _hkdf(token.encode(), b"jarvis-data-v1") == self._data_key), "previous_keys": len(self._old)}

    def needs_reseal(self, value: str | None) -> bool:
        """Cifrato con una chiave precedente: la chiave attuale non lo apre ma una vecchia sì."""
        if not (self.enabled and self.sealed(value) and self._old):
            return False
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            raw = base64.urlsafe_b64decode(value[len(PREFIX):])
            AESGCM(self._data_key).decrypt(raw[:12], raw[12:], b"jarvis")
            return False
        except (InvalidTag, ValueError):
            pass
        return self.open(value) != UNREADABLE

    @staticmethod
    def sealed(value: str | None) -> bool:
        return bool(value) and value.startswith(PREFIX)

    def seal(self, text: str) -> str:
        """Testo -> 'enc1:<nonce+cifrato in base64>'. Senza chiave resta in chiaro (e il server lo segnala all'avvio)."""
        if not self.enabled or self.sealed(text):
            return text
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        return PREFIX + base64.urlsafe_b64encode(nonce + AESGCM(self._data_key).encrypt(nonce, text.encode(), b"jarvis")).decode()

    def open(self, value: str | None) -> str:
        """Decifra; i valori non cifrati (dati precedenti alla cifratura) passano invariati."""
        if value is None or not self.sealed(value):
            return value or ""
        if not self.enabled:
            return UNREADABLE
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            raw = base64.urlsafe_b64decode(value[len(PREFIX):])
        except ValueError:
            return UNREADABLE
        for key in (self._data_key, *self._old):  # prima la chiave attuale, poi quelle precedenti (rotazione)
            try:
                return AESGCM(key).decrypt(raw[:12], raw[12:], b"jarvis").decode()
            except (InvalidTag, ValueError):
                continue
        return UNREADABLE

    def blind(self, text: str) -> str:
        """HMAC stabile di un testo (chiavi di deduplicazione, URI, nomi di entità): il database non può risalire al contenuto."""
        norm = unicodedata.normalize("NFKD", text.strip().lower())
        norm = "".join(c for c in norm if not unicodedata.combining(c))
        if not self.enabled:
            return hashlib.sha256(norm.encode()).hexdigest()
        return hmac.new(self._index_key, norm.encode(), hashlib.sha256).hexdigest()

    def terms(self, text: str, limit: int = 64) -> list[str]:
        """Indice cieco: HMAC delle parole (senza accenti, minuscole, troncate a 6 lettere come stemmer grezzo)."""
        plain = unicodedata.normalize("NFKD", text.lower())
        words = re.findall(r"[a-z0-9]{3,}", "".join(c for c in plain if not unicodedata.combining(c)))
        out: list[str] = []
        for w in words:
            h = (hmac.new(self._index_key, w[:6].encode(), hashlib.sha256) if self.enabled else hashlib.sha256(w[:6].encode())).hexdigest()[:12]
            if h not in out:
                out.append(h)
        return out[:limit]
