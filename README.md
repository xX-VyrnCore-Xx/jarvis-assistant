# JARVIS

Assistente personale H24: backend FastAPI su Render, AI via FreeLLMAPI, memoria su Supabase.

## Stato
- [x] Fase 1: backend, agente con tool calling, memoria, auth
- [x] Fase 2: Telegram (webhook, whitelist) + promemoria proattivi
- [x] Fase 3: Gmail / Calendar / Drive
- [ ] Fase 4: app Windows (Tauri) + controllo PC
- [ ] Fase 5: voce (wake word, STT, TTS)

## Avvio locale
```
cd server && pip install -r requirements-dev.txt
cp ../.env.example .env   # compila i valori
uvicorn app.main:app --reload
pytest
```
`POST /chat` con `Authorization: Bearer $JARVIS_API_TOKEN` e body `{"message": "ciao"}`.

## Deploy
1. Supabase: esegui `supabase/migrations/0001_init.sql` nello SQL editor.
2. Render: New → Blueprint dal repo (`render.yaml`), poi imposta le variabili segrete.
3. Anti-sleep (piano Free): modifica l'URL in `supabase/keepalive.sql` ed eseguilo.

## Telegram
1. Crea il bot con @BotFather e copia il token; il tuo ID numerico si legge con @userinfobot.
2. Imposta su Render `TELEGRAM_BOT_TOKEN` e `TELEGRAM_OWNER_ID` (il secret del webhook è generato in automatico).
3. All'avvio il server registra il webhook usando `RENDER_EXTERNAL_URL` (in locale: `PUBLIC_URL`, es. un tunnel).
4. Scrivi al bot: risponde solo al tuo ID. Prova "ricordami domani alle 9 di chiamare Luca".

## Google (Gmail, Calendar, Drive)
1. Abilita le API Gmail, Calendar e Drive nel tuo progetto Google Cloud; consenso OAuth con te come utente di test.
2. Sul tuo PC: `GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python server/scripts/google_auth.py` e autorizza nel browser.
   Con un client di tipo "Web" aggiungi `http://localhost:8765/` agli URI di reindirizzamento.
3. Su Render imposta `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e il `GOOGLE_REFRESH_TOKEN` stampato.

Le email vengono solo salvate come bozza; l'invio richiede la tua conferma esplicita.
Permessi richiesti: Gmail lettura + bozze/invio, Calendar, Drive in sola lettura.
