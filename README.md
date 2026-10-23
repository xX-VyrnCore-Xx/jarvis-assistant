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
   Le piattaforme valide sono quelle del catalogo FreeLLMAPI. **Senza chiave** si attivano da sole all'avvio OVH AI Endpoints (`ovh`), Kilo Gateway (`kilo`) e la ricerca web **Parallel** (`AUTO_KEYLESS_PROVIDERS=0` le disattiva); **SiliconFlow** si attiva impostando `SILICONFLOW_API_KEY` su Render. `web_search` e `web_news` interrogano prima i motori di FreeLLMAPI (Parallel) e ripiegano su DuckDuckGo. JARVIS legge da solo la chiave unificata dal DB.

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
- **Installer** (NSIS, in italiano, per l'utente corrente, senza permessi di amministratore): immagini dedicate, cartella JARVIS nel menu Start; prima di installare, aggiornare o disinstallare chiude da solo JARVIS (voce compresa) così i file in uso si sostituiscono senza errori.
- **Primo avvio**: procedura guidata in quattro passi (benvenuto → collegamento con prova del token → preferenze: avvio con Windows e voce parlata → voce locale opzionale).
- **Uscita**: la X nasconde la finestra; «Esci definitivamente» (icona nella barra o Impostazioni) chiude voce, installazione in corso e tutti i processi figli (`taskkill /T`), toglie l'icona e termina il processo (con terminazione forzata dopo 3 secondi se qualcosa resta appeso). Una sola copia dell'app alla volta: riaprirla porta davanti quella già attiva.
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

## Competenze (skills)

JARVIS ha **171 competenze integrate** in nove ambiti (nuovo: **Scienza e attualità**: notizie in tempo reale, fact-checking, statistica, matematica, fisica, astronomia, economia, storia e geopolitica, ricerca accademica; più data science, deep learning, fine-tuning LoRA, RAG e agenti, Docker, CI/CD, Terraform, osservabilità, code di messaggi, framework frontend, WebAssembly, resilienza, cybersecurity, crittografia, reti e VPN, blockchain, open data, GDPR, Excel, partita IVA, e-commerce, salute, lingue): **Programmazione** (80: revisione del codice, debug, architettura, Python, JS/TS avanzato, React, Node, Rust, Go, Java/Kotlin, C/C++, shell Linux, SQL, NoSQL e cache, API, test, algoritmi, clean code, refactoring del legacy, concorrenza e sistemi distribuiti, cloud e IaC, DevOps, sicurezza, prestazioni, mobile, AI engineering e RAG, machine learning, automazione e scraping, documentazione; e ancora FastAPI, Django/Flask, PHP/Laravel, C#/.NET, Swift/iOS, Flutter, Android Compose, GraphQL/gRPC, WebSocket, autenticazione, PostgreSQL avanzato, ORM, regex, compilatori, giochi, firmware, DDD, build tool, supply chain, open source, data engineering, PowerShell, Tauri/Electron, bot, test di carico, date e fusi orari, numeri e denaro, Unicode/i18n, Git avanzato, incidenti e SRE, Kubernetes, HTTP/CORS, Core Web Vitals, PWA, estensioni browser, IDE e debugger), **Grafica e design** (17: UI/UX, design system, tipografia, colore, layout, accessibilità, logo, SVG, CSS e animazioni, fotografia, video, 3D e Blender, Figma, stampa, visualizzazione dei dati, immagini con AI, icone e icona dell'app), **Tecnologia** (14: hardware, reti, privacy e sicurezza personale, smartphone, smart home, Windows/macOS, self-hosting, Arduino/Raspberry, AI per tutti, prompt engineering, acquisti, backup, stampa 3D, valutare l'hype), più Comunicazione (8), Finanza (7), Marketing (9), Business (7) e Vita (7).

- **Si attivano da sole**: la richiesta viene confrontata con le competenze (frasi di attivazione e parole chiave, zero chiamate in più) e il metodo di quelle pertinenti, al massimo due, entra nel prompt (~2400 caratteri). Le chiacchiere e le richieste semplici non ne attivano nessuna. Spegni tutto con `SKILLS_ENABLED=false`.
- **A richiesta**: `/skills` e `/skill nome richiesta` su Telegram, «Competenze» in Altro nell'app Android (la competenza scelta vale per la prossima domanda), i tool `list_skills` e `use_skill`, e il campo `skill` di `/chat` e `/chat/stream`.
- **Le tue**: «crea una competenza per scrivere il mio report del venerdì…» (`skill_save`): si salva cifrata nel secondo cervello e si attiva da sola. `skill_delete` la elimina; quelle integrate sono in `server/app/skills/library/*.md` (formato: intestazione `name/title/domain/description/triggers`, riga vuota, testo; blocchi separati da `@@@`).
- Le competenze su fisco, salute e diritto danno orientamento generale e rimandano ai professionisti; i dati aggiornati si cercano sul web.

## Promemoria e Calendario, velocità

- **Promemoria ↔ Calendario Google**: ogni promemoria creato in app, su Telegram o a voce diventa anche un evento del Calendario (⏰, con avviso di Google). **Il Calendario comanda**: se sposti o elimini l'evento, il promemoria dell'app si aggiorna o sparisce (sincronizzazione ogni 5 minuti, o subito con `POST /api/reminders/sync`); un evento scritto a mano come «Promemoria: …» diventa un promemoria dell'app. Rimandare o eliminare un promemoria nell'app muove o cancella l'evento. Senza Google collegato funziona solo nell'app; se il Calendario è momentaneamente giù il promemoria resta e riceve l'evento alla sincronizzazione successiva. `REMINDER_CALENDAR_POPUP=false` toglie l'avviso doppio di Google.
- **Risposte più veloci**: a ogni richiesta si inviano al modello solo gli strumenti pertinenti (prima tutti: 4-5.000 token a messaggio, quota gratuita e limiti dei provider superati); se serve altro il modello li attiva da solo (`need_tools`). Cronologia, secondo cervello, profilo e situazione si leggono insieme. Se il router non risponde entro 35 secondi (`LLM_ATTEMPT_TIMEOUT_S`) si ripiega sul modello che di recente risponde più in fretta, invece di aspettare i 60 secondi del provider.
- **Anti-sleep**: `GET /health` riceve un ping ogni 5 minuti da UptimeRobot e uno ogni 10 da Supabase (`pg_cron`, `supabase/keepalive.sql`): il servizio non va mai in sospensione.

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

## Privacy, cifratura e fine-tuning LoRA
- **Cifrato a riposo** (AES-256-GCM): messaggi, ricordi, promemoria, notifiche, liste, secondo cervello (testi, titoli, tag, vettori, nomi) e ora anche **impostazioni, token dei dispositivi ed etichette** (migrazione `0003`; i dati vecchi si cifrano da soli). Le ricerche usano indici ciechi (HMAC): il database non vede mai le parole.
- **Intestazioni di sicurezza** più severe (CSP restrittiva, anti-iframe, HSTS con sottodomini, Permissions-Policy) e schema/documentazione delle API non più pubblici.
- **LoRA**: `POST /api/finetune/export` prepara le conversazioni (mascheratura *strict* di IBAN, carte, chiavi, password, email, telefoni) e le salva **cifrate** nel dataset privato Hugging Face; il notebook `finetune/jarvis_lora.ipynb` (Colab gratuito) le decifra solo in memoria con la tua `ENCRYPTION_KEY`, addestra l'adattatore e lo salva in un repo modello privato. Vedi `finetune/README.md`: per usarlo dal vivo serve una GPU, non Render Free.
- Limite onesto: l'indice per parole (HMAC troncato) permette a chi ha accesso al database di vedere *quali* parole ricorrono, non il testo; e i testi escono verso i provider dei modelli (mascherati) per poter rispondere.

## Notizie e informazioni in tempo reale
- Strumento `news_headlines`: titoli **dal vivo** (cache di 5 minuti) da ANSA, Repubblica, Corriere, Il Sole 24 Ore, Il Post, BBC, Al Jazeera, Guardian, NPR, DW, Wired, Hacker News, The Verge, Ars Technica, TechCrunch, GitHub, Hugging Face, arXiv, NASA, ScienceDaily, BCE, Gazzetta, BBC Sport e terremoti USGS; filtri per categoria (`italia`, `mondo`, `tecnologia`, `ai`, `scienza`, `economia`, `sport`, `terremoti`) e argomento. `feed_add`/`feed_remove`/`feed_list` per i tuoi feed RSS/Atom (fino a 30, solo indirizzi pubblici). Il modello è istruito a non dare mai per «attuale» ciò che ricorda: controlla dal vivo e cita fonte e ora.
- Ogni `LIVE_INGEST_MINUTES` (20) le notizie nuove delle ultime 24 ore entrano nel secondo cervello (fonte «notizia», niente token del modello, scadenza 10 giorni, mai nel contesto delle risposte); il buongiorno mattutino include le notizie principali.
- **Auto-aggiornamento**: ogni giorno 5 voci della conoscenza di base (357 in totale) vengono riscaricate a rotazione da Wikipedia; il server si aggiorna da solo a ogni nuova versione del codice (Render) e le app avvisano delle Release; `jarvis_status` mostra versione, ultima Release, ultimo aggiornamento di notizie e conoscenza e feed non raggiungibili. JARVIS **non riscrive il proprio codice**: sarebbe un rischio di sicurezza, le modifiche passano da Pull Request e CI.

## Routing dei modelli e sessioni di coding
- **Routing**: con il modello «auto» JARVIS sceglie per ogni richiesta il profilo di FreeLLMAPI più adatto (`auto:fast` per richieste brevi e lavori di fondo, `auto:reliable` per le chiamate di strumenti, `auto:smart` per codice e ragionamenti, `auto:balanced` per il resto) e indica il tipo di lavoro (`X-FreeLLM-Task-Type`). Impara dall'esito: un profilo che fallisce 3 volte in 10 minuti viene saltato per 5 minuti; ai tentativi successivi si ripiega su `auto:reliable`, poi `auto:balanced`, o sul modello più veloce di recente. Un modello scelto a mano non viene mai cambiato. `LLM_ROUTING=false` lo disattiva.
- **Coding in sandbox**: a «crea un progetto / programma…» JARVIS chiede nome, descrizione, README e licenza, poi (dopo la **tua conferma** nell'app o su Telegram) crea un repository GitHub **sempre privato** e una sandbox (cartella di lavoro del server). Scrive e modifica i file, committa su un ramo di lavoro (o direttamente sul principale), apre la Pull Request, legge la CI e i suoi log per correggersi, e unisce (squash) quando la CI è verde.
  **Gestione dei repository**: `code_sessions`/`code_repos` elencano tutti i repository creati da JARVIS con dettagli (descrizione, ultimo aggiornamento, issue/PR aperte, dimensione); `code_repo_edit` cambia descrizione, nome, argomenti, archiviazione; `code_repo_delete` elimina (con conferma); `code_adopt` ritrova quelli con l'argomento `jarvis-managed` se l'elenco va perso.
  **Sandbox e strumenti**: `code_tree`, `code_find`, `code_search` (glob e contesto), `code_diff`, `code_discard`, `code_move`, `code_append`, `code_replace` (regex multi-file, prima anteprima), `code_stats`, `code_scaffold` (python-cli, fastapi-api, node-express-api, static-site, telegram-bot, con test e CI); rami (`code_branches`, `code_checkout`, `code_branch_delete`), cronologia (`code_log`), PR (`code_prs`, `code_pr_comment`, `code_pr_close`), issue, release (`code_release`) e CI (`code_ci_run`, `code_ci_runs`, `code_wait_checks`).
  Richiede `GITHUB_TOKEN` su Render: token **classico** con scope `repo` (e `workflow` se vuoi la CI), creato da GitHub → Settings → Developer settings; incollalo solo nella dashboard di Render. Per **eliminare, rinominare o modificare** un repository serve anche lo scope `delete_repo` (token classico) oppure il permesso **Administration: write** (token fine-grained); senza, queste azioni falliscono con «Permessi insufficienti» e il resto funziona.
  **Sicurezza**: nessun codice viene eseguito sul server (contiene le tue chiavi): i test girano nella CI di GitHub, che JARVIS legge. Tocca solo i repository che ha creato lui (registro nel database), mai quelli esistenti, nemmeno questo; non può cambiare visibilità né forzare push; **elimina un repository solo se è nel suo registro, è privato e dopo la tua conferma esplicita** (app o Telegram), con limite di 3 al giorno e registro delle operazioni (`code_audit`); rifiuta file con chiavi o nomi tipo `.env`/`.pem`; massimo 3 repository nuovi al giorno. La sandbox sta nel disco effimero di Render: committa spesso (JARVIS lo fa), il lavoro non committato si perde a un riavvio. Un repository vuoto riceve un `.gitignore` come primo commit (l'API di GitHub lo richiede).

## Novità: salvataggi, cervello allineato, ricorrenze
- **Backup su Hugging Face**: l'export cifrato ora è compresso (formato `JV2`, i vecchi `JV1` si leggono ancora), esclude ciò che si riscarica (notizie e Wikipedia) e i vettori dei frammenti (si ricalcolano), e include le impostazioni. Gli errori dicono il passo e il motivo (es. «HTTP 403: il token non può scrivere su questo dataset»), i guasti passeggeri si ritentano, e dopo un fallimento si riprova dopo un'ora (massimo 3 volte al giorno) con un avviso. `POST /api/backup/run` (e il pulsante «Esegui ora» in Altro) lo esegue subito.
- **Il cervello segue JARVIS**: promemoria attivi, ricordi brevi e attività aperte sono rispecchiati nel secondo cervello e ne escono quando vengono eliminati, scattano o vengono tolti dal Calendario, compresi i fatti «appresi» dalla stessa richiesta. Un controllo ogni 5 minuti ripara qualsiasi divergenza; l'apprendimento automatico non salva più i promemoria come fatti.
- **Promemoria ricorrenti**: `repeat` = `daily`, `weekdays`, `weekly`, `monthly`, `yearly` (migrazione `supabase/migrations/0004_reminder_repeat.sql`). Quando scatta, JARVIS crea il successivo (con il suo evento nel Calendario) mantenendo l'ora anche col cambio dell'ora legale.
- **Riepilogo serale** alle 21 (`EVENING_HOUR`, 0 = spento): cosa resta da fare e il programma di domani.
- **App Android**: pallino dello stato del collegamento, riconnessione automatica con conto alla rovescia (e subito al ritorno della rete), battito che scopre le connessioni morte, avvisi dei promemoria con «+10 min / +1 ora / Fatto», scelta della ripetizione, scheda «Salvataggi».

## Telefono e WhatsApp (Android)
- **Chiamare**: da Altro → Telefono → «Chiama» (nome in rubrica o numero; Telefono, WhatsApp voce o video), oppure chiedendolo a JARVIS («chiama Luca su WhatsApp»). Dalla chat la chiamata parte **solo dopo la tua conferma** (app o Telegram): il server manda l'ordine al telefono, che cerca il contatto nella tua rubrica (il server non la vede mai). Con l'app chiusa l'ordine compare come avviso e parte con un tocco (Android non permette di chiamare dallo sfondo). WhatsApp non ha un'API pubblica per le chiamate: si usa il collegamento di WhatsApp ai contatti del telefono; se il contatto non ha WhatsApp si apre la chat.
- **Risposta automatica**: spenta di default. Si attiva da Altro dopo aver autorizzato almeno un numero e concesso i permessi, con una conferma esplicita; JARVIS **accetta** (con il viva voce, se vuoi) le chiamate telefoniche solo da quei numeri, dopo 0-6 secondi di squillo. Non può parlare al posto tuo (Android non permette alle app di inserire audio nelle chiamate) e non può accettare le chiamate WhatsApp. Ogni risposta o rifiuto resta nel registro del telefono.
- Permessi richiesti: Telefono (chiamare, stato, registro chiamate per leggere il numero che squilla, rispondere) e Contatti. Il codice nativo è in `mobile/native/phone/` e viene aggiunto all'APK da `scripts/build-android.sh`.

## Sincronizzazione tra dispositivi e Calendario
- **Una sola conversazione**: app Android e app Windows condividono la stessa chat (le sessioni `mobile`, `desktop` e `main` sono la stessa; Telegram resta separato). Quando un dispositivo scrive o cambia promemoria, note del secondo cervello o conversazione, il server avvisa subito gli altri (evento `sync` sul flusso `/api/stream`, con l'id del dispositivo per non ricaricare chi ha fatto la modifica); alla riconnessione e al ritorno in primo piano l'app si rimette in pari.
- **Errori del Calendario spiegati**: l'esito dell'ultima sincronizzazione e la causa (autorizzazione scaduta, API Calendar non abilitata, permessi mancanti, limite di richieste, rete) compaiono nell'app (Promemoria → banner con «Riprova», pulsante «Sincronizza») e in `GET /api/status` (`calendar_sync`); `POST /api/reminders/sync` non risponde mai con un errore del server. Nei log un solo avviso per causa.

## Bot Telegram
- **Messaggi**: formattazione ricca (titoli, elenchi annidati, citazioni, tabelle a colonne allineate, codice con evidenziazione per linguaggio, barrato, spoiler, linee), blocchi di codice mai spezzati a metà, reazione 👀 al tuo messaggio finché risponde, notifiche con corpo in citazione, schede `/stato` (semafori 🟢🟡🔴 per ogni sistema) e `/promemoria` raggruppati per giorno.
- **Sempre collegato**: all'avvio il bot si configura con tentativi e pause crescenti (anche se Telegram o la rete hanno un singhiozzo); ogni 3 minuti si controlla che il webhook sia il nostro e che Telegram riesca a consegnare, altrimenti lo si ripristina/riarma; ogni chiamata a Telegram ritenta su errori di rete, 5xx e limiti (429). Senza indirizzo pubblico passa da solo alla lettura diretta (`TELEGRAM_MODE=auto|webhook|polling`). Dopo un'interruzione di oltre 20 minuti (aggiornamento, riavvio) il bot ti avvisa in silenzio «Sono di nuovo online». Profilo del bot e menu dei comandi si impostano da soli. Lo stato del collegamento sta in `/stato`, `/salute` e nel battito dei log.

## App Android: sicurezza, notifiche, aggiornamenti
- **Sicurezza**: il token personale è cifrato sul telefono (AES-256-GCM, chiave WebCrypto non esportabile in IndexedDB; quello in chiaro delle versioni precedenti viene cifrato e cancellato al primo avvio); **blocco con PIN** a sei cifre (PBKDF2-SHA256 150.000 iterazioni con sale, confronto a tempo costante, attese 30 s → 15 min dopo 5 errori) con blocco subito, dopo 30 s o 5 min in background; contenuto nascosto nelle app recenti; Content-Security-Policy restrittiva; solo HTTPS con soli certificati di sistema (`network_security_config`), nessun backup né trasferimento dei dati, debug della WebView spento. Limite: il PIN protegge l'uso dell'app, non il telefono sbloccato e già compromesso; manca il blocco biometrico (richiederebbe un plugin nativo da verificare).
- **Notifiche**: centro notifiche per giorni con filtri e colori per tipo, avviso in cima allo schermo con l'app aperta (tocco per aprire, gesto per scacciare), campanella che squilla; push con priorità alta solo per promemoria/avvisi/conferme, durata di consegna per tipo, contenuto nascosto a schermo bloccato, un solo avviso di aggiornamento alla volta.
- **Aggiornamenti**: controllo all'avvio e ogni 6 ore, banner con dimensione e «nascondi per un giorno», scheda con versione, note di rilascio leggibili, SHA-256 copiabile, controllo dell'indirizzo di download (solo `github.com/…/releases/download/`), «più tardi» e «salta questa versione», novità mostrate una volta dopo l'aggiornamento. Scorri a sinistra/destra per cambiare sezione.
