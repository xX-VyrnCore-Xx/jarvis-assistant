"""Voce neurale di riserva, sempre disponibile (anche a PC spento): sintesi di Microsoft Edge (pacchetto edge-tts, voci italiane naturali).
È un servizio non ufficiale e gratuito: se smette di rispondere, JARVIS ripiega sulla voce del dispositivo senza errori."""
import asyncio
import hashlib
import logging
import time
from collections import OrderedDict

log = logging.getLogger("jarvis.tts")

VOICES = {  # nome breve → voce neurale italiana
    "isabella": ("it-IT-IsabellaNeural", "Isabella · calda e naturale"),
    "elsa": ("it-IT-ElsaNeural", "Elsa · chiara e pacata"),
    "diego": ("it-IT-DiegoNeural", "Diego · voce maschile"),
}
DEFAULT = "isabella"
BACKOFF_S = 300  # dopo un errore si smette di provare per qualche minuto


class EdgeTTS:
    def __init__(self, enabled: bool = True, rate: str = "+4%", pitch: str = "+0Hz", timeout: float = 25.0):
        self.on, self.rate, self.pitch, self.timeout = enabled, rate, pitch, timeout
        self.voice = DEFAULT
        self.down_until = 0.0
        self.last_error = ""
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self.on and time.monotonic() >= self.down_until

    def set_voice(self, name: str) -> bool:
        if name not in VOICES:
            return False
        self.voice = name
        return True

    async def _stream(self, text: str, voice: str) -> bytes:
        import edge_tts

        out = bytearray()
        async for ch in edge_tts.Communicate(text, voice, rate=self.rate, pitch=self.pitch).stream():
            if ch["type"] == "audio":
                out += ch["data"]
        return bytes(out)

    async def speak(self, text: str) -> bytes:
        """MP3 della frase. Solleva RuntimeError se il servizio non risponde."""
        voice = VOICES[self.voice][0]
        key = hashlib.sha256(f"{voice}|{self.rate}|{text}".encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if not self.enabled:
            raise RuntimeError("voce neurale non disponibile")
        try:
            audio = await asyncio.wait_for(self._stream(text, voice), self.timeout)
            if len(audio) < 500:
                raise RuntimeError("audio vuoto")
        except Exception as e:
            self.down_until = time.monotonic() + BACKOFF_S
            self.last_error = type(e).__name__
            log.warning("voce neurale non riuscita (%s): ripiego sulla voce del dispositivo", type(e).__name__)
            raise RuntimeError("voce neurale non disponibile") from e
        self.last_error = ""
        self._cache[key] = audio
        while len(self._cache) > 60:
            self._cache.popitem(last=False)
        return audio
