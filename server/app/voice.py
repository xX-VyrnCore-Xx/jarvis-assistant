"""Voce di JARVIS: la sintesi (XTTS v2) gira sul PC Windows; il server la chiede all'app tramite il canale WebSocket."""
import base64
import binascii
import hashlib
from collections import OrderedDict

from .pc import PCBridge


class TTSError(Exception):
    pass


class VoiceService:
    """Voce di JARVIS: quella del PC (XTTS) se è acceso; altrimenti la voce neurale del server, così parla sempre."""

    mime = "audio/wav"

    def __init__(self, pc: PCBridge, edge=None):
        self.pc = pc
        self.edge = edge
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    @property
    def pc_enabled(self) -> bool:
        return self.pc.connected and bool(self.pc.caps.get("voice"))

    @property
    def enabled(self) -> bool:
        return self.pc_enabled or bool(self.edge and self.edge.enabled)

    async def speak_any(self, text: str) -> tuple[bytes, str]:
        """(audio, tipo MIME): PC se disponibile, altrimenti voce neurale."""
        if self.pc_enabled:
            try:
                return await self.speak(text), "audio/wav"
            except TTSError:
                if not (self.edge and self.edge.enabled):
                    raise
        if self.edge:
            try:
                return await self.edge.speak(text), "audio/mpeg"
            except RuntimeError as e:
                raise TTSError(str(e)) from e
        raise TTSError("La voce di JARVIS gira sul PC: accendilo e apri l'app")

    async def speak(self, text: str) -> bytes:
        if not self.pc_enabled:
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
