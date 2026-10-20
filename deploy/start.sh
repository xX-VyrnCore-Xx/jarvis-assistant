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

# `kill -0` può fallire con EPERM su un processo vivo se il container non ha CAP_KILL (succede su Render):
# lo stato si legge da /proc, che non dipende dai permessi.
alive() {
  local st
  st=$(sed -E 's/^[^)]*\) (.).*/\1/' "/proc/${1:-0}/stat" 2>/dev/null) || return 1
  [ -n "$st" ] && [ "$st" != "Z" ]
}
port_open() {
  /opt/venv/bin/python -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1',3001))==0 else 1)"
}

start_freellm

# Se FreeLLMAPI cade all'avvio con una configurazione (es. nome di provider sconosciuto), riprova senza.
# Si riavvia SOLO se il processo è morto E la porta è libera: mai due istanze sullo stesso database.
# Su un piano Free l'avvio di Node può richiedere 30-40 s, quindi si aspetta finché non ascolta.
if [ -n "${FREEAPI_CONFIG_JSON:-}" ]; then
  for _ in $(seq 1 60); do
    sleep 1
    port_open && break
    if ! alive "$FREELLM" && ! port_open; then
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
