import numpy as np
from faster_whisper import WhisperModel


class Transcriber:
    def __init__(self, model: str):
        # int8 su CPU: gira bene anche su portatili senza GPU
        self.model = WhisperModel(model, device="cpu", compute_type="int8")

    def __call__(self, pcm16: np.ndarray) -> str:
        audio = pcm16.astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(audio, language="it", vad_filter=True, beam_size=1)
        return " ".join(s.text.strip() for s in segments).strip()
