# JARVIS + FreeLLMAPI in un solo container: entra nelle 750 ore gratuite di Render.
# FreeLLMAPI ascolta solo su 127.0.0.1:3001; JARVIS è l'unico servizio pubblico e ne inoltra solo /v1/*
# (così qualunque app può usarlo con la chiave unificata) lasciando privata la dashboard.
# Immagine upstream fissata per digest: nessun aggiornamento a sorpresa.
FROM ghcr.io/tashfeenahmed/freellmapi:v0.16.6@sha256:9b11990847dc2cba7b7041a7fe9bd2246cfae49993f00e86371333082e9a2b49

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/jarvis
COPY server/requirements.txt .
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY server/app ./app
COPY --chmod=755 deploy/start.sh /usr/local/bin/start.sh

ENV FREEAPI_DB_PATH=/app/server/data/freellmapi.db \
    FREELLM_DB_PATH=/app/server/data/freellmapi.db \
    FREELLM_BASE_URL=http://127.0.0.1:3001/v1 \
    FREELLM_INTERNAL_URL=http://127.0.0.1:3001 \
    PROXY_RATE_LIMIT_RPM=600 \
    FREELLM_MODEL=auto

ENTRYPOINT []
CMD ["/usr/local/bin/start.sh"]
