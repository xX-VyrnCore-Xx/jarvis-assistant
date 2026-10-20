#!/bin/bash
# Avvia JARVIS (porta pubblica di Render) e FreeLLMAPI (solo loopback).
# - FREEAPI_CONFIG_JSON non valido o rifiutato: FreeLLMAPI riparte SENZA la configurazione e JARVIS resta online
#   (con un messaggio chiaro nei log), invece di mandare il container in crash loop.
# - Se uno dei due processi muore più tardi, il container esce e Render lo riavvia.
set -u

DATA=/app/server/data
mkdir -p "$DATA" && chown -R node:node "$DATA"
as_node() { setpriv --reuid=node --regid=node --init-groups -- "$@"; }

# Controllo di sintassi: non stampa mai il contenuto (contiene le chiavi), solo posizione e carattere.
if [ -n "${FREEAPI_CONFIG_JSON:-}" ]; then
  if ! /opt/venv/bin/python - <<'PY'
import json, os, sys
raw = os.environ["FREEAPI_CONFIG_JSON"]
try:
    json.loads(raw)
except json.JSONDecodeError as e:
    ch = raw[e.pos] if e.pos < len(raw) else "<fine>"
    print(f"[start.sh] FREEAPI_CONFIG_JSON NON valido: {e.msg} (riga {e.lineno}, colonna {e.colno}, posizione {e.pos}, carattere {ch!r})")
    print("[start.sh] Cause tipiche: virgola mancante tra due elementi, virgolette tipografiche “ ” al posto di \", virgola finale.")
    sys.exit(1)
PY
  then
    echo "[start.sh] Avvio FreeLLMAPI SENZA configurazione: correggi la variabile su Render e salva."
    unset FREEAPI_CONFIG_JSON
  fi
fi

cd /srv/jarvis
as_node /opt/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" &
JARVIS=$!

start_freellm() { (cd /app && PORT=3001 HOST=127.0.0.1 exec setpriv --reuid=node --regid=node --init-groups -- node server/dist/index.js) & FREELLM=$!; }
start_freellm

# Se FreeLLMAPI cade nei primi secondi con una configurazione (es. nome di provider sconosciuto), riprova senza.
if [ -n "${FREEAPI_CONFIG_JSON:-}" ]; then
  for _ in $(seq 1 30); do
    sleep 1
    if ! kill -0 "$FREELLM" 2>/dev/null; then
      echo "[start.sh] FreeLLMAPI non è partito con FREEAPI_CONFIG_JSON (controlla i nomi dei provider): riprovo SENZA configurazione."
      unset FREEAPI_CONFIG_JSON
      start_freellm
      break
    fi
  done
fi

trap 'kill "$FREELLM" "$JARVIS" 2>/dev/null' TERM INT
wait -n "$FREELLM" "$JARVIS"
echo "start.sh: un processo è terminato (codice $?), arresto del container"
kill "$FREELLM" "$JARVIS" 2>/dev/null
wait
exit 1
