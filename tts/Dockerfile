FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1 COQUI_TOS_AGREED=1 HOME=/home/user TTS_HOME=/home/user/.local/share PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 ffmpeg && rm -rf /var/lib/apt/lists/* \
 && useradd -m -u 1000 user
WORKDIR /home/user/app
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
USER user
# il modello (~1,8 GB) viene scaricato nell'immagine: l'avvio non dipende dalla rete
RUN python -c "from TTS.utils.manage import ModelManager; ModelManager().download_model('tts_models/multilingual/multi-dataset/xtts_v2')"
COPY --chown=user app.py .
COPY --chown=user voice voice
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
