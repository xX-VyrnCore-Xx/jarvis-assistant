import asyncio

import edge_tts
import miniaudio
import numpy as np

from .audio import play_pcm
from .speech import clean_for_speech


async def _synth(text: str, voice: str) -> bytes:
    chunks = []
    async for ch in edge_tts.Communicate(text, voice).stream():
        if ch["type"] == "audio":
            chunks.append(ch["data"])
    return b"".join(chunks)


def speak(text: str, voice: str) -> None:
    text = clean_for_speech(text)
    if not text:
        return
    mp3 = asyncio.run(_synth(text, voice))
    dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=24000)
    play_pcm(np.frombuffer(dec.samples, dtype=np.int16), 24000)
