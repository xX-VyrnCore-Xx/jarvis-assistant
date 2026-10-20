import asyncio
import io
import logging
import wave

import edge_tts
import httpx
import miniaudio
import numpy as np

from .audio import play_pcm
from .speech import clean_for_speech, split_sentences

log = logging.getLogger("jarvis.tts")


async def _edge(text: str, voice: str) -> bytes:
    chunks = []
    async for ch in edge_tts.Communicate(text, voice).stream():
        if ch["type"] == "audio":
            chunks.append(ch["data"])
    return b"".join(chunks)


def _play_edge(text: str, voice: str) -> None:
    mp3 = asyncio.run(_edge(text, voice))
    dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=24000)
    play_pcm(np.frombuffer(dec.samples, dtype=np.int16), 24000)


def _jarvis_voice(cfg, text: str) -> tuple[np.ndarray, int]:
    r = httpx.post(f"{cfg.url}/api/tts", json={"text": text}, headers={"Authorization": f"Bearer {cfg.token}"}, timeout=150)
    r.raise_for_status()
    with wave.open(io.BytesIO(r.content)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


def speak(text: str, cfg) -> None:
    """Voce clonata di JARVIS (XTTS v2 sul server); se non risponde, ripiega su Edge-TTS."""
    text = clean_for_speech(text)
    if not text:
        return
    parts = split_sentences(text[:700])
    for i, part in enumerate(parts):
        try:
            pcm, rate = _jarvis_voice(cfg, part)
        except Exception as e:
            log.warning("voce di JARVIS non disponibile (%s): uso Edge-TTS", type(e).__name__)
            _play_edge(" ".join(parts[i:]), cfg.voice)
            return
        play_pcm(pcm, rate)
