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

## Notifiche in tempo reale
Promemoria, avvisi (token in esaurimento, backup fallito) e richieste di conferma arrivano come notifica:
- **App aperte** (Windows e Android): flusso SSE `GET /api/stream`, con notifica nativa di Windows; l'archivio è in `GET /api/notifications`.
- **Android con app chiusa**: push Firebase (FCM HTTP v1). Servono due cose, entrambe dal progetto Firebase:
  1. `google-services.json` dell'app Android `it.vyrncore.jarvis` → segreto GitHub `ANDROID_GOOGLE_SERVICES_JSON_B64` (base64 del file); poi si rigenera la Release.
  2. chiave dell'account di servizio (Impostazioni progetto → Account di servizio → Genera chiave) → variabile Render `FIREBASE_SERVICE_ACCOUNT_JSON` (il JSON intero).
  Senza queste restano le notifiche in-app e Telegram. L'APK registra il proprio token con `POST /api/devices`.
- **Telegram**: promemoria e avvisi arrivano anche lì.

## Dati e backup
- Supabase: tabelle `messages`, `memories`, `reminders`, `notifications`, `devices` (RLS attiva, accesso solo dal server). Il server elimina ogni notte i dati vecchi (messaggi 180 giorni, notifiche 90, promemoria completati 60, dispositivi inattivi 90).
- Hugging Face (dataset privato di `FREEAPI_DB_BACKUP_URL`): oltre al DB di FreeLLMAPI, ogni notte un export **cifrato AES-256-GCM** di Supabase in `jarvis/AAAA-MM-GG.json.enc` (ultimi 14), con scheda `README.md` e compattazione settimanale della cronologia. La chiave deriva da `ENCRYPTION_KEY`.

## Sicurezza
- **Token personale** (`JARVIS_API_TOKEN`): confronto a tempo costante; dopo 8 tentativi sbagliati lo stesso IP viene bloccato 15 minuti
  (anche con il token giusto). `/chat` è limitato a 20 richieste al minuto.
- **Azioni sensibili**: l'invio di email non lo decide il modello. `gmail_send_draft` crea una richiesta che puoi approvare
  solo dall'app o dai pulsanti di Telegram; scade dopo 10 minuti. Spostamenti di file e spegnimento del PC chiedono conferma sul PC.
- **Contenuti esterni** (email, file, pagine web) sono marcati come non fidati: il modello li tratta come dati, non come ordini.
- Dashboard di FreeLLMAPI mai raggiungibile da fuori; intestazioni `nosniff`, `no-store`, HSTS; richieste oltre 1 MB rifiutate; CORS limitato alle app.

## API per le app
Tutte con `Authorization: Bearer <JARVIS_API_TOKEN>`: `GET /api/status`, `GET /api/tokens` (token disponibili da FreeLLMAPI),
`GET /api/history`, `GET|POST|DELETE /api/reminders`, `GET /api/pending`, `POST /api/pending/{id}/approve|reject`.
