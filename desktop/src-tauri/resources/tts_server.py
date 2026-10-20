"""Server locale XTTS v2 con la voce clonata di JARVIS. Ascolta solo su 127.0.0.1 e richiede un token casuale."""
import argparse
import hashlib
import io
import os
import secrets
import threading
import wave
from collections import OrderedDict

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, required=True)
ap.add_argument("--voice", required=True)
ap.add_argument("--token-env", default="JARVIS_TTS_TOKEN")
args = ap.parse_args()
TOKEN = os.environ.get(args.token_env, "")
RATE = 24000
LANGS = {"it", "en", "es", "fr", "de", "pt"}

from TTS.tts.configs.xtts_config import XttsConfig  # noqa: E402
from TTS.tts.models.xtts import Xtts  # noqa: E402
from TTS.utils.manage import ModelManager  # noqa: E402

torch.set_num_threads(max(1, os.cpu_count() or 2))
path, *_ = ModelManager().download_model("tts_models/multilingual/multi-dataset/xtts_v2")
cfg = XttsConfig()
cfg.load_json(os.path.join(path, "config.json"))
model = Xtts.init_from_config(cfg)
model.load_checkpoint(cfg, checkpoint_dir=path, use_deepspeed=False)
model.eval()
LATENT, EMBEDDING = model.get_conditioning_latents(audio_path=[args.voice])

lock = threading.Lock()
cache: OrderedDict[str, bytes] = OrderedDict()
app = FastAPI(title="JARVIS Voice (locale)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://tauri.localhost", "https://tauri.localhost", "tauri://localhost", "http://localhost:1420"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


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
    return {"status": "ok"}


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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
