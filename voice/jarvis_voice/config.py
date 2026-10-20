import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    url: str
    token: str
    wake_model: str = "hey_jarvis"
    wake_threshold: float = 0.5
    whisper_model: str = "small"
    voice: str = "it-IT-DiegoNeural"
    session_id: str = "voice"

    @classmethod
    def load(cls) -> "Config":
        load_dotenv()
        url, token = os.environ.get("JARVIS_URL", ""), os.environ.get("JARVIS_API_TOKEN", "")
        if not url or not token:
            raise SystemExit("Imposta JARVIS_URL e JARVIS_API_TOKEN (file .env o variabili d'ambiente).")
        return cls(
            url=url.rstrip("/"),
            token=token,
            wake_model=os.environ.get("WAKE_MODEL", cls.wake_model),
            wake_threshold=float(os.environ.get("WAKE_THRESHOLD", cls.wake_threshold)),
            whisper_model=os.environ.get("WHISPER_MODEL", cls.whisper_model),
            voice=os.environ.get("TTS_VOICE", cls.voice),
        )
