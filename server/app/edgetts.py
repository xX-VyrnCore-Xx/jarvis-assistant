"""Voce neurale di riserva, sempre disponibile (anche a PC spento): sintesi di Microsoft Edge (pacchetto edge-tts, voci italiane naturali).
È un servizio non ufficiale e gratuito: se smette di rispondere, JARVIS ripiega sulla voce del dispositivo senza errori."""
import asyncio
import hashlib
import logging
import re
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
CACHE_TTL_S, CACHE_BYTES = 900, 6_000_000  # l'audio di frasi private resta in memoria al massimo 15 minuti e 6 MB

# Il testo da leggere esce dal server verso un servizio esterno: i dati personali si sostituiscono con parole generiche (la voce non li pronuncia e non lasciano il server)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+|00)?\d[\d ().-]{7,}\d(?!\w)")
_URL = re.compile(r"https?://\S+")
_SECRET = re.compile(r"\b(?:sk|ghp|gho|ghs|xox[bp]|AKIA)[-_A-Za-z0-9]{12,}\b")


def speech_safe(text: str) -> str:
    """Il testo che va al servizio vocale, senza dati personali: email, IBAN, carte, telefoni, link e chiavi diventano parole generiche."""
    t = _SECRET.sub("una chiave segreta", text or "")
    t = _EMAIL.sub("un indirizzo email", t)
    t = _IBAN.sub("un IBAN", t)
    t = _CARD.sub("un numero di carta", t)
    t = _URL.sub("un link", t)
    return _PHONE.sub(lambda m: "un numero di telefono" if sum(c.isdigit() for c in m.group(0)) >= 9 and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m.group(0).strip()) else m.group(0), t)


class EdgeTTS:
    def __init__(self, enabled: bool = True, rate: str = "+4%", pitch: str = "+0Hz", timeout: float = 25.0):
        self.on, self.rate, self.pitch, self.timeout = enabled, rate, pitch, timeout
        self.voice = DEFAULT
        self.down_until = 0.0
        self.last_error = ""
        self._cache: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

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

    def clear(self) -> int:
        n = len(self._cache)
        self._cache.clear()
        return n

    def _trim(self) -> None:
        now = time.monotonic()
        for k in [k for k, (until, _) in self._cache.items() if until <= now]:
            del self._cache[k]
        while self._cache and (len(self._cache) > 60 or sum(len(v[1]) for v in self._cache.values()) > CACHE_BYTES):
            self._cache.popitem(last=False)

    async def speak(self, text: str) -> bytes:
        """MP3 della frase (senza dati personali: vedi speech_safe). Solleva RuntimeError se il servizio non risponde."""
        text = speech_safe(text)
        voice = VOICES[self.voice][0]
        key = hashlib.sha256(f"{voice}|{self.rate}|{text}".encode()).hexdigest()
        hit = self._cache.get(key)
        if hit and hit[0] > time.monotonic():
            self._cache.move_to_end(key)
            return hit[1]
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
        self._cache[key] = (time.monotonic() + CACHE_TTL_S, audio)
        self._trim()
        return audio
