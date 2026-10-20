"""Voce di JARVIS: inoltra il testo al server XTTS v2 (Hugging Face Space) e restituisce l'audio WAV."""
import asyncio
import hashlib
from collections import OrderedDict

import httpx

from .config import Settings


class TTSError(Exception):
    pass


class VoiceService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.url = settings.tts_url.rstrip("/")
        self.token = settings.tts_token
        self._client = client or httpx.AsyncClient(timeout=150)
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._gate = asyncio.Semaphore(1)  # lo Space ha poca CPU: una sintesi alla volta

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.token)

    async def speak(self, text: str, lang: str = "it") -> bytes:
        key = hashlib.sha256(f"{lang}|{text}".encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        async with self._gate:
            try:
                r = await self._client.post(f"{self.url}/tts", json={"text": text, "lang": lang},
                                            headers={"Authorization": f"Bearer {self.token}"})
            except httpx.HTTPError as e:
                raise TTSError("Voce non raggiungibile: lo Space si sta svegliando") from e
        if r.status_code != 200:
            raise TTSError(f"Voce non disponibile ({r.status_code})")
        self._cache[key] = r.content
        while len(self._cache) > 40:
            self._cache.popitem(last=False)
        return r.content
