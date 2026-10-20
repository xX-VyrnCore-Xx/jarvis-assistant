# JARVIS

Assistente personale H24: backend FastAPI su Render, AI via FreeLLMAPI, memoria su Supabase.

## Stato
- [x] Fase 1: backend, agente con tool calling, memoria, auth
- [ ] Fase 2: Telegram + promemoria proattivi
- [ ] Fase 3: Gmail / Calendar / Drive
- [ ] Fase 4: app Windows (Tauri) + controllo PC
- [ ] Fase 5: voce (wake word, STT, TTS)

## Avvio locale
```
cd server && pip install -r requirements.txt
cp ../.env.example .env   # compila i valori
uvicorn app.main:app --reload
pytest
```
`POST /chat` con `Authorization: Bearer $JARVIS_API_TOKEN` e body `{"message": "ciao"}`.

## Deploy
1. Supabase: esegui `supabase/migrations/0001_init.sql` nello SQL editor.
2. Render: New → Blueprint dal repo (`render.yaml`), poi imposta le variabili segrete.
3. Anti-sleep (piano Free): modifica l'URL in `supabase/keepalive.sql` ed eseguilo.
