#!/bin/bash
# Avvia FreeLLMAPI (solo loopback) e JARVIS (porta pubblica di Render). Se uno dei due muore
# termina l'altro ed esce con errore, così Render riavvia il container.
set -u

DATA=/app/server/data
mkdir -p "$DATA" && chown -R node:node "$DATA"
as_node() { setpriv --reuid=node --regid=node --init-groups -- "$@"; }

cd /app
PORT=3001 HOST=127.0.0.1 as_node node server/dist/index.js &
FREELLM=$!

cd /srv/jarvis
as_node /opt/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" &
JARVIS=$!

trap 'kill "$FREELLM" "$JARVIS" 2>/dev/null' TERM INT
wait -n "$FREELLM" "$JARVIS"
echo "start.sh: un processo è terminato (codice $?), arresto del container"
kill "$FREELLM" "$JARVIS" 2>/dev/null
wait
exit 1
