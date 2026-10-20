"""Server XTTS v2: legge il testo con la voce clonata di JARVIS. Un solo lavoro alla volta (la CPU è condivisa)."""
import hashlib
import io
import os
import secrets
import threading
import wave
from collections import OrderedDict

import numpy as np
import torch
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from TTS.utils.manage import ModelManager

TOKEN = os.environ.get("TTS_TOKEN", "")
REFERENCE = os.path.join(os.path.dirname(__file__), "voice", "jarvis.wav")
RATE = 24000
LANGS = {"it", "en", "es", "fr", "de", "pt"}

torch.set_num_threads(max(1, (os.cpu_count() or 2)))
path, *_ = ModelManager().download_model("tts_models/multilingual/multi-dataset/xtts_v2")
cfg = XttsConfig()
cfg.load_json(os.path.join(path, "config.json"))
model = Xtts.init_from_config(cfg)
model.load_checkpoint(cfg, checkpoint_dir=path, use_deepspeed=False)
model.eval()
LATENT, EMBEDDING = model.get_conditioning_latents(audio_path=[REFERENCE])  # calcolati una sola volta

lock = threading.Lock()
cache: OrderedDict[str, bytes] = OrderedDict()
app = FastAPI(title="JARVIS Voice")


class In(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    lang: str = "it"
    speed: float = Field(default=1.05, ge=0.7, le=1.4)


def to_wav(samples: np.ndarray) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": "xtts_v2"}


@app.post("/tts")
def tts(body: In, authorization: str = Header(default="")) -> Response:
    if not TOKEN or not secrets.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(401, "Non autorizzato")
    if body.lang not in LANGS:
        raise HTTPException(422, "Lingua non supportata")
    key = hashlib.sha256(f"{body.lang}|{body.speed}|{body.text}".encode()).hexdigest()
    if key in cache:
        cache.move_to_end(key)
        return Response(cache[key], media_type="audio/wav")
    with lock, torch.inference_mode():
        out = model.inference(body.text, body.lang, LATENT, EMBEDDING, temperature=0.7, speed=body.speed,
                              enable_text_splitting=True)
    audio = to_wav(np.asarray(out["wav"], dtype=np.float32))
    cache[key] = audio
    while len(cache) > 64:
        cache.popitem(last=False)
    return Response(audio, media_type="audio/wav")
