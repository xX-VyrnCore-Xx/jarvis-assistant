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

## Tool e funzioni dell'assistente
Tool validati (tipi, parametri obbligatori, valori ammessi), con timeout, risultati limitati e più tool eseguiti insieme nello stesso turno:
memoria (`remember`, `recall`, `list_memories`, `forget`), promemoria (`add_/list_/delete_reminder`, `remind_in`), `web_search`, `web_news`, `wikipedia`, `read_webpage` (solo indirizzi pubblici),
`get_weather`, `calculate`, `date_info`, `convert_currency`, `unit_convert`, `world_time`, `crypto_price`, liste (`task_*`), `reminder_snooze`, `pc_system_info`, `pc_media`, `send_notification`, `get_token_budget`, controllo del PC e Google:
Gmail (cerca, leggi, bozze, risposte in thread, invio con conferma), Calendar (elenca/cerca, crea con luogo e giornata intera, **modifica**, **elimina con conferma**, fasce libere), Drive (cerca, leggi, recenti).

## Telegram
1. Crea il bot con @BotFather e copia il token; il tuo ID numerico si legge con @userinfobot.
2. Imposta su Render `TELEGRAM_BOT_TOKEN` e `TELEGRAM_OWNER_ID` (il secret del webhook è generato in automatico).
3. All'avvio il server registra il webhook usando `RENDER_EXTERNAL_URL` (in locale: `PUBLIC_URL`, es. un tunnel).
4. Scrivi al bot: risponde solo al tuo ID. Prova "ricordami domani alle 9 di chiamare Luca".

Bot: risposte formattate (grassetto, codice, link), indicatore «sta scrivendo», comandi `/aiuto /stato /token /promemoria /ricordi /nuova` con pulsanti per eliminare,
duplicati ignorati, un messaggio alla volta per chat. All'avvio e ogni 10 minuti JARVIS riprende il controllo del bot se un vecchio servizio con lo stesso token ha reimpostato il suo webhook
(scartando i messaggi arretrati). Per liberarlo del tutto, elimina o sospendi il vecchio servizio su Render.

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

## Voce di JARVIS (XTTS v2)
La voce clonata da `desktop/src-tauri/resources/jarvis.wav` gira **sul tuo PC**, gratis (nessun Space né Docker a pagamento).
- **Windows**: al primo avvio l'app propone di installarla (anche da Impostazioni): scarica Python portatile, le librerie e il modello XTTS v2
  (circa 3 GB, una volta sola) in `%LOCALAPPDATA%\JARVIS\voice`. Il processo parte con l'app e si chiude con lei.
- **Android**: il telefono chiede la sintesi al server, che la inoltra al PC collegato (`POST /api/tts`). Se il PC è spento ripiega sulla voce del telefono.
- **Voce locale "Hey Jarvis"**: usa la stessa strada, con Edge-TTS come ripiego.
- **Chiusura completa**: icona nella barra → *Esci* ferma anche il processo della voce (la X della finestra invece lascia JARVIS attivo nella tray).
Licenza del modello: Coqui CPML, solo uso non commerciale. Sulla CPU la sintesi è circa in tempo reale.

## Notifiche in tempo reale
Promemoria, avvisi (token in esaurimento, backup fallito) e richieste di conferma arrivano come notifica:
- **App aperte** (Windows e Android): flusso SSE `GET /api/stream`, con notifica nativa di Windows; l'archivio è in `GET /api/notifications`.
- **Android con app chiusa**: push Firebase (FCM HTTP v1). Servono due cose, entrambe dal progetto Firebase:
  1. `google-services.json` dell'app Android `it.vyrncore.jarvis` → segreto GitHub `ANDROID_GOOGLE_SERVICES_JSON_B64` (base64 del file); poi si rigenera la Release.
  2. chiave dell'account di servizio (Impostazioni progetto → Account di servizio → Genera chiave) → variabile Render `FIREBASE_SERVICE_ACCOUNT_JSON` (il JSON intero).
  Senza queste restano le notifiche in-app e Telegram. L'APK registra il proprio token con `POST /api/devices`.
- **Telegram**: promemoria e avvisi arrivano anche lì.

## Aggiornamenti dall'app e consumi

- **Aggiornamenti**: il server controlla le Release di GitHub ogni 30 minuti e avvisa tutte le app (in tempo reale, push e Telegram) quando ne esce una nuova. Per l'avviso istantaneo aggiungi su GitHub un webhook «Releases» verso `https://<server>/github/webhook` con segreto uguale a `GITHUB_WEBHOOK_SECRET`. Su Android l'app mostra un banner «Aggiorna»: scarica l'APK e Android propone l'installazione sopra l'app attuale (serve la stessa chiave di firma: configura i 4 segreti `ANDROID_KEYSTORE_*`, altrimenti l'APK di debug cambia a ogni build e va prima disinstallata la vecchia). Su Windows il pulsante apre il download dell'installer.
- **Token**: la sezione mostra previsione di esaurimento, consumo giornaliero di JARVIS e latenza (`/api/tokens`, `/api/usage`). Il modello si sceglie da Altro → Intelligenza (`/api/models`).
- **Notifiche**: da Altro → Canali e ore silenziose scegli per ogni tipo se arriva nell'app, come push o su Telegram. Sui promemoria ci sono +10 min / +1 ora / Fatto.
- **Salute**: `/api/health` e il comando Telegram `/salute` mostrano memoria, cifratura, integrazioni e ultimo backup.

## Intelligenza e proattività

- **Impara da solo**: dopo ogni conversazione JARVIS estrae fatti, preferenze, persone e impegni duraturi e li salva nel secondo cervello (tag `appreso`); le attività le aggiunge alla lista. Ha un filtro a costo zero e un tetto giornaliero (`LEARN_MAX_PER_DAY`, spegnibile con `LEARN_ENABLED=false`). Non salva ciò che sa già.
- **Profilo**: ogni settimana ricompila un profilo di te dai ricordi (`/profilo` su Telegram, `GET /api/brain/profile`) e lo usa in ogni risposta, insieme alla situazione del momento (attività aperte, prossimi promemoria).
- **Ricerca più furba**: `brain_deep_search` riformula la domanda in più modi, `brain_about` raccoglie tutto su una persona o un progetto, e le ricerche accettano un periodo (`since`/`until`).
- **Proattivo** (`PROACTIVE_ENABLED`, `PROACTIVE_MAX_PER_DAY`, `EVENING_HOUR`): avviso 10-45 minuti prima di ogni evento (anche su Telegram), email nuove nella posta principale, punto della sera con l'agenda di domani, riepilogo della domenica e allarme se i token finiscono prima del reset. Zero token spesi: i testi si compongono dai dati; rispetta le ore silenziose e non ripete mai lo stesso avviso.

## Log, Telegram e conoscenza di base

- **Log ogni minuto**: nei log di Render compare una riga `heartbeat` al minuto (uptime, memoria, richieste ai modelli, secondo cervello, app collegate, stato dei cicli di fondo); se un ciclo si ferma scatta un avviso. Ogni chiamata a un modello lascia una riga con durata e token. `PYTHONUNBUFFERED` è attivo: le righe arrivano subito.
- **Bot Telegram**: tastiera rapida (Agenda, Email, Attività, Cervello, Consumo, Impostazioni), `/oggi`, `/agenda`, `/email` (istantanei, senza modello), `/impara argomento`, `/proattivo` (stato e pausa degli avvisi), pulsanti «Approfondisci» e «Più breve» sotto ogni risposta, suggerimento se sbaglia un comando, notifiche con icone e grassetto, attesa automatica se Telegram limita i messaggi.
- **Cultura generale nel secondo cervello**: ~200 voci essenziali di Wikipedia (Italia, geografia, paesi, scienza, storia, economia, tecnologia, cultura, salute) si caricano da sole, 3 ogni 5 minuti (`KNOWLEDGE_SEED_PER_CYCLE`, 0 = spento), senza spendere token del modello. Nel prompt entra al massimo una voce, solo se pertinente; il tool `brain_learn` e `/impara` aggiungono qualsiasi altro argomento.

## Secondo cervello (RAG)
Memoria a lungo termine per note, ricordi, pagine web, file, email e Drive, con recupero **ibrido** e tutto **cifrato a riposo**:
- **Acquisizione**: `brain_add_note`, `brain_save_url`, `drive_save_to_brain`, `gmail_save_to_brain`; su Telegram `/nota testo`, e file `.txt/.md/.pdf` inviati al bot; nelle app la scheda **Cervello**. Frammenti coerenti (~1200 caratteri, per titolo e paragrafo, con sovrapposizione), deduplicazione per contenuto e per URI (stesso URI = aggiornamento).
- **Recupero**: embedding multilingue via FreeLLMAPI (`/v1/embeddings`, famiglia `RAG_EMBED_MODEL`, default `bge-m3`, serve la chiave Cloudflare o Hugging Face) **fusi con BM25** sulle parole (RRF), potenziamento per importanza/fissati/uso, decadimento per il diario, **MMR** contro i duplicati e **espansione tramite il grafo** di persone, luoghi e progetti. Se gli embedding non sono disponibili funziona comunque per parole e i vettori si aggiungono dopo.
- **Contesto automatico**: a ogni messaggio il contesto pertinente (con id `[#n]`) entra nel prompt, mascherato dai filtri di privacy; le fonti esterne sono marcate come dati, non istruzioni.
- **Arricchimento**: il modello propone titolo, riassunto, tag, entità e importanza; **diario** notturno che riassume la giornata; **ripasso** di ciò che è importante ma poco rivisto; **buongiorno** alle `BRIEFING_HOUR` (agenda, promemoria, attività, un ricordo da ripassare).
- **Privacy**: testi ed embedding sono cifrati nel database (l'indice vive in RAM sul server: nessuna ricerca vettoriale sul database); la ricerca per parole usa HMAC. I testi che escono verso i provider (embedding, arricchimento, diario) passano dal mascheramento dei dati sensibili.
- Tool per il modello: `brain_add_note`, `brain_search`, `brain_read`, `brain_related`, `brain_pin`, `brain_forget`, `brain_save_url`, `brain_resurface`, `brain_stats`. API: `/api/brain/*`.

## Privacy e cifratura
- **Cifratura a riposo**: messaggi, ricordi, promemoria, notifiche e liste sono salvati su Supabase **cifrati** (AES-256-GCM, chiave derivata da `ENCRYPTION_KEY`): il database non vede mai il testo. La ricerca nei ricordi usa un **indice cieco** (HMAC delle parole, con una chiave diversa). I dati scritti prima vengono cifrati in automatico a lotti dopo l'avvio.
  **Conserva `ENCRYPTION_KEY`**: se cambia, i dati cifrati non si leggono più. Il refresh token Google e i backup su Hugging Face sono già cifrati.
- **Privacy verso i modelli** (`PRIVACY_MODE`, default `standard`): prima di uscire verso i provider, IBAN, carte (con controllo Luhn), chiavi/token, password e codice fiscale diventano segnaposto (`[IBAN_1]`…) e vengono rimessi al loro posto nelle risposte e negli argomenti dei tool: il modello non li vede mai ma tutto funziona. `strict` maschera anche email e telefoni; `off` disattiva. I messaggi d'errore non riportano mai il corpo delle risposte dei provider.
  Nota: FreeLLMAPI instrada su provider gratuiti con condizioni diverse; per dati davvero sensibili controlla le condizioni d'uso sull'addestramento dei piani gratuiti dei provider che hai attivato.
- Per leggere un backup: `ENCRYPTION_KEY=... python server/scripts/decrypt_backup.py file.json.enc`.

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
