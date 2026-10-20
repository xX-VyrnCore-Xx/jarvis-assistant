import numpy as np

from jarvis_voice.endpoint import FRAME, Endpointer
from jarvis_voice.speech import clean_for_speech


def frame(amp):
    return (np.random.default_rng(0).standard_normal(FRAME) * amp).astype(np.int16)


def run(ep, loud_frames, quiet_before, quiet_after):
    seq = [frame(20)] * quiet_before + [frame(3000)] * loud_frames + [frame(20)] * quiet_after
    for i, f in enumerate(seq, 1):
        if ep.feed(f):
            return i
    return None


def test_stops_after_silence_following_speech():
    ep = Endpointer(silence_ms=800)
    stop = run(ep, loud_frames=15, quiet_before=5, quiet_after=40)
    assert ep.heard
    assert stop is not None and stop >= 5 + 15 + ep.silence_frames - 1


def test_gives_up_when_nobody_speaks():
    ep = Endpointer(no_speech_ms=2000)
    stop = run(ep, 0, 0, 100)
    assert not ep.heard and stop is not None and stop <= 30


def test_hard_limit():
    ep = Endpointer(max_ms=1600)
    assert run(ep, loud_frames=100, quiet_before=0, quiet_after=0) == ep.max_frames


def test_clean_for_speech():
    out = clean_for_speech("**Ciao!** Vedi https://x.it/a\n- punto uno\n```code```\n😀 fine")
    assert "http" not in out and "*" not in out and "code" not in out and "😀" not in out
    assert out.startswith("Ciao!") and "punto uno" in out and out.endswith("fine")
