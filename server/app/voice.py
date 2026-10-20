"""Voce di JARVIS: la sintesi (XTTS v2) gira sul PC Windows; il server la chiede all'app tramite il canale WebSocket."""
import base64
import binascii
import hashlib
from collections import OrderedDict

from .pc import PCBridge


class TTSError(Exception):
    pass


class VoiceService:
    def __init__(self, pc: PCBridge):
        self.pc = pc
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self.pc.connected and bool(self.pc.caps.get("voice"))

    async def speak(self, text: str) -> bytes:
        if not self.enabled:
            raise TTSError("La voce di JARVIS gira sul PC: accendilo e apri l'app")
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        out = await self.pc.call("tts", {"text": text}, timeout=120)
        try:
            audio = base64.b64decode(out, validate=True)
        except (binascii.Error, ValueError) as e:
            raise TTSError(out[:150] or "Voce non disponibile") from e
        if audio[:4] != b"RIFF":
            raise TTSError("Risposta vocale non valida")
        self._cache[key] = audio
        while len(self._cache) > 40:
            self._cache.popitem(last=False)
        return audio
