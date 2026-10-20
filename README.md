# JARVIS

Assistente personale H24: backend FastAPI su Render, AI via FreeLLMAPI, memoria su Supabase.

## Stato
- [x] Fase 1: backend, agente con tool calling, memoria, auth
- [x] Fase 2: Telegram (webhook, whitelist) + promemoria proattivi
- [x] Fase 3: Gmail / Calendar / Drive
- [x] Fase 4: app Windows (Tauri) + controllo PC (`desktop/`)
- [x] Fase 5: voce, "Hey Jarvis" + Whisper + Edge-TTS (`voice/`)

## Avvio locale
```
cd server && pip install -r requirements-dev.txt
cp ../.env.example .env   # compila i valori
uvicorn app.main:app --reload
pytest
```
`POST /chat` con `Authorization: Bearer $JARVIS_API_TOKEN` e body `{"message": "ciao"}`.

## Deploy (tutto gratuito su Render)
Un solo servizio Docker (`Dockerfile`, `render.yaml`) contiene **JARVIS** e **FreeLLMAPI**. FreeLLMAPI ascolta solo in
loopback; JARVIS ne inoltra pubblicamente solo `/v1/*` (la dashboard resta privata). Un unico servizio basta per restare nelle 750 ore gratuite/mese di Render (due servizi H24 non ci stanno).

1. **Supabase**: migrazioni in `supabase/migrations/`, anti-sleep in `supabase/keepalive.sql` (con l'URL del servizio).
2. **Render**: New → Blueprint dal repo. Variabili: `SUPABASE_*`, `TELEGRAM_*`, `GOOGLE_*` (opzionali) e quelle sotto.
   `JARVIS_API_TOKEN`, `ENCRYPTION_KEY` e il secret Telegram si generano da soli: leggili dalla dashboard.
3. **Persistenza di FreeLLMAPI** (il disco Free si azzera ai riavvii): crea un dataset **privato** su Hugging Face e un token
   con scrittura solo su quel repo, poi imposta
   `FREEAPI_DB_BACKUP_URL=https://huggingface.co/datasets/<utente>/<repo>/resolve/main/freellmapi.db.backup`
   e `FREEAPI_DB_BACKUP_TOKEN`. Il DB, cifrato con `ENCRYPTION_KEY`, viene salvato ogni 5 minuti e ripristinato all'avvio.
   **Conserva `ENCRYPTION_KEY`**: senza di essa il backup non si decifra.
4. **Chiavi dei provider** in `FREEAPI_CONFIG_JSON` (applicato a ogni avvio), per esempio:
   `{"keys":[{"platform":"groq","key":"gsk_..."},{"platform":"google","key":"AIza..."}],"routing":{"strategy":"balanced"}}`
   Le piattaforme valide sono quelle del catalogo FreeLLMAPI. JARVIS legge da solo la chiave unificata dal DB.

### Usare FreeLLMAPI da altre app
Qualunque app compatibile OpenAI/Anthropic può usare `https://<servizio>.onrender.com/v1` con la chiave unificata.
Per ottenerle: `curl -H "Authorization: Bearer $JARVIS_API_TOKEN" https://<servizio>.onrender.com/admin/freellm`
→ `{"base_url": ..., "api_key": ...}`. Il ping di Supabase (`keepalive.sql`) lo tiene sveglio.

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

## App Windows
`desktop/` (Tauri). L'installer `.exe` è prodotto dalla CI (artifact `JARVIS-windows-installer`).
Al primo avvio apri ⚙ e inserisci URL del server e `JARVIS_API_TOKEN`. `Alt+Spazio` mostra/nasconde la finestra.
Sviluppo: `cd desktop && npm install && npm run tauri dev` (richiede Rust).

## Voce
Vedi `voice/README.md`.
