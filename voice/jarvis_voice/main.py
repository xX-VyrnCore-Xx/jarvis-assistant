"""JARVIS vocale: "Hey Jarvis" → registra → Whisper → /chat → voce."""
import logging

import httpx
import numpy as np

from .audio import beep, mic_frames
from .config import Config
from .endpoint import Endpointer

log = logging.getLogger("jarvis.voice")


def ask(cfg: Config, text: str) -> str:
    r = httpx.post(
        f"{cfg.url}/chat",
        json={"message": text, "session_id": cfg.session_id, "voice": True},
        headers={"Authorization": f"Bearer {cfg.token}"},
        timeout=120,  # include il risveglio di Render Free
    )
    r.raise_for_status()
    return r.json()["reply"]


def record_utterance(frames) -> np.ndarray:
    ep, chunks = Endpointer(), []
    for frame in frames:
        chunks.append(frame)
        if ep.feed(frame):
            break
    return np.concatenate(chunks) if ep.heard else np.empty(0, dtype=np.int16)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = Config.load()

    import openwakeword
    from openwakeword.model import Model

    from .stt import Transcriber
    from .tts import speak

    openwakeword.utils.download_models([cfg.wake_model])
    wake = Model(wakeword_models=[cfg.wake_model], inference_framework="onnx")
    transcribe = Transcriber(cfg.whisper_model)
    log.info("In ascolto: di' 'Hey Jarvis'")

    frames = mic_frames()
    for frame in frames:
        if wake.predict(frame).get(cfg.wake_model, 0.0) < cfg.wake_threshold:
            continue
        wake.reset()
        beep()
        pcm = record_utterance(frames)
        if not len(pcm):
            continue
        text = transcribe(pcm)
        log.info("Hai detto: %s", text)
        if not text:
            continue
        try:
            speak(ask(cfg, text), cfg.voice)
        except Exception:
            log.exception("errore durante la risposta")
            speak("Ho avuto un problema a contattare il server, signore.", cfg.voice)


if __name__ == "__main__":
    main()
