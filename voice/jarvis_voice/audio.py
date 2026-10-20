import numpy as np
import sounddevice as sd

from .endpoint import FRAME, SAMPLE_RATE


def mic_frames():
    """Generatore infinito di frame int16 mono a 16 kHz (80 ms ciascuno)."""
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME) as stream:
        while True:
            data, _ = stream.read(FRAME)
            yield data[:, 0].copy()


def beep(freq: float = 880.0, ms: int = 120, rate: int = 24000) -> None:
    t = np.linspace(0, ms / 1000, int(rate * ms / 1000), endpoint=False)
    sd.play((0.25 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16), rate)
    sd.wait()


def play_pcm(pcm: np.ndarray, rate: int) -> None:
    sd.play(pcm, rate)
    sd.wait()
