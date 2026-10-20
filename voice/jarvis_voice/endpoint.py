"""Rilevamento della fine del parlato (puro, senza dipendenze audio: facile da testare)."""
import numpy as np

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms: la dimensione che openWakeWord si aspetta


def rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(frame.astype(np.float32))))) if len(frame) else 0.0


class Endpointer:
    """Dice quando l'utente ha finito di parlare.

    Calibra il rumore di fondo sui primi frame, poi considera "voce" ciò che supera
    `max(noise * factor, floor)`. Termina dopo `silence_ms` di silenzio *dopo* aver sentito
    voce; se nessuno parla entro `no_speech_ms` termina a vuoto; limite assoluto `max_ms`.
    """

    def __init__(self, silence_ms=900, no_speech_ms=5000, max_ms=15000, factor=3.0, floor=350.0, calib_frames=3):
        self.frame_ms = FRAME * 1000 / SAMPLE_RATE
        self.silence_frames = int(silence_ms / self.frame_ms)
        self.no_speech_frames = int(no_speech_ms / self.frame_ms)
        self.max_frames = int(max_ms / self.frame_ms)
        self.factor, self.floor, self.calib_frames = factor, floor, calib_frames
        self._noise: list[float] = []
        self.n = 0
        self.heard = False
        self._quiet = 0

    @property
    def threshold(self) -> float:
        noise = sum(self._noise) / len(self._noise) if self._noise else 0.0
        return max(noise * self.factor, self.floor)

    def feed(self, frame: np.ndarray) -> bool:
        """True quando bisogna smettere di registrare."""
        self.n += 1
        level = rms(frame)
        if self.n <= self.calib_frames:
            self._noise.append(level)
            return False
        if level > self.threshold:
            self.heard, self._quiet = True, 0
        else:
            self._quiet += 1
        if self.n >= self.max_frames:
            return True
        if self.heard:
            return self._quiet >= self.silence_frames
        return self.n >= self.no_speech_frames
