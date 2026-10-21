name: fastapi-e-backend-python
title: FastAPI e back-end Python
domain: programmazione
description: Costruisce servizi Python moderni con FastAPI/Pydantic: struttura, dipendenze, async, validazione, database, test, sicurezza e deploy.
triggers: fastapi, pydantic, uvicorn, back-end python, api in python, starlette, dependency injection fastapi, sqlalchemy async, httpx, openapi python, router fastapi, python web service

**Metodo**: struttura a strati (`routers` sottili → `services` con la logica → `repositories`/accesso ai dati), modelli **Pydantic** distinti per input, output e database (mai restituire direttamente l'entità del DB), `Depends` per sessione, utente corrente e configurazione (facili da sostituire nei test), impostazioni da variabili d'ambiente con `pydantic-settings`.
**Async**: `async def` solo se dentro c'è I/O non bloccante; librerie sincrone dentro `def` (thread pool) o `asyncio.to_thread`; un solo client `httpx.AsyncClient` condiviso con timeout; niente lavoro CPU nell'event loop.
**Robustezza**: codici HTTP corretti e gestori di eccezioni centralizzati, validazione dei parametri con `Query/Path` e vincoli, paginazione, middleware per id di richiesta e log, `lifespan` per aprire/chiudere risorse, task in background solo per lavori brevi (per il resto una coda).
**Test**: `TestClient`/`httpx.AsyncClient` con `app.dependency_overrides`.
**Deploy**: `uvicorn` dietro proxy, `--workers` secondo CPU, health check, versioni fissate.
**Output**: scheletro del progetto o endpoint completo, con i modelli e il test.
@@@
name: django-e-flask
title: Django e Flask
domain: programmazione
description: Sviluppo web in Python con Django (ORM, admin, sicurezza, DRF) e Flask (blueprint, estensioni): quando usarli, struttura e insidie.
triggers: django, flask, django rest framework, drf, orm di django, migrazioni django, blueprint flask, jinja, template django, settings.py, django admin, gunicorn, wsgi, celery

**Scelta**: **Django** quando servono batterie incluse (ORM, migrazioni, admin, autenticazione, form, sicurezza); **Flask** per servizi piccoli o molto personalizzati (poi scegli tu ORM, validazione, auth).
**Django**: app piccole con un solo scopo; modelli con vincoli e `select_related/prefetch_related` (niente N+1: controlla con `django-debug-toolbar`), logica nei servizi/manager non nelle viste, `settings` per ambiente, `DEBUG=False`, `ALLOWED_HOSTS`, segreti da variabili d'ambiente, `python manage.py check --deploy`; **DRF** con serializer e permessi espliciti, paginazione; compiti lunghi con **Celery** + Redis; migrazioni piccole e reversibili.
**Flask**: application factory, blueprint, configurazione per ambiente, estensioni mantenute (SQLAlchemy, Flask-Migrate, Marshmallow/pydantic), gestori di errori, test con `app.test_client()`.
**Produzione**: gunicorn + proxy, file statici dal proxy/CDN, log, backup del DB.
**Output**: struttura del progetto e il codice mirato, con versioni assunte.
@@@
name: php-e-laravel
title: PHP moderno e Laravel
domain: programmazione
description: Scrive PHP 8+ pulito e usa Laravel: Eloquent, routing, code, validazione, sicurezza e deploy; gestisce anche WordPress in modo sicuro.
triggers: php, laravel, eloquent, composer, symfony, wordpress, plugin wordpress, blade, artisan, php 8, phpunit, tema wordpress, woocommerce

**PHP moderno**: `declare(strict_types=1)`, tipi su parametri e ritorni, enum, `readonly`, costruttori promossi, PSR-12, Composer con autoload PSR-4, niente `mysql_*` né concatenazione SQL.
**Laravel**: controller sottili → form request per la validazione → servizi/azioni per la logica; **Eloquent** con relazioni ed *eager loading* (`with()`) contro N+1, `fillable`/`guarded`, scope, resource per le risposte API, migrazioni, seeder e factory; code (queue) e job per lavori lenti, scheduler al posto di cron sparsi, cache, policy/gate per l'autorizzazione, test con Pest/PHPUnit e `RefreshDatabase`.
**Sicurezza**: query parametrizzate, escape nell'output (Blade `{{ }}`), CSRF, hash delle password (`Hash::make`), `APP_DEBUG=false`, `.env` fuori dal repo, aggiornamenti.
**WordPress**: hook (`add_action/add_filter`), sanitizzazione e *nonce*, `$wpdb->prepare`, non modificare il core né i temi di terze parti (usa tema figlio/plugin).
**Output**: codice completo con la struttura dei file e i comandi `artisan`/`composer` da eseguire.
@@@
name: csharp-e-dotnet
title: C# e .NET
domain: programmazione
description: Sviluppo con C# e .NET: linguaggio moderno, ASP.NET Core, Entity Framework, async/await, LINQ, test e distribuzione.
triggers: c#, csharp, .net, dotnet, asp.net, asp.net core, entity framework, linq, blazor, nuget, unity c#, visual studio, async await c#, minimal api, wpf, maui

**Linguaggio**: tipi nullable abilitati, `record` per i dati immutabili, pattern matching, `using` per le risorse, `var` quando il tipo è ovvio, LINQ leggibile (attenzione all'esecuzione differita e alle enumerazioni multiple), `async/await` fino in fondo (`Task`, mai `.Result`/`.Wait()`; `ConfigureAwait` solo nelle librerie), `CancellationToken` nei metodi lunghi.
**ASP.NET Core**: minimal API o controller, **dependency injection** integrata (durata corretta: singleton/scoped/transient — attenzione ai servizi scoped dentro singleton), opzioni tipizzate (`IOptions<T>`), middleware, validazione, `ProblemDetails` per gli errori, autenticazione JWT/Identity, health check, logging strutturato (Serilog).
**Entity Framework Core**: `AsNoTracking` per le sole letture, `Include` per evitare N+1, migrazioni, proiezioni con `Select`, niente `ToList()` troppo presto.
**Test**: xUnit + `WebApplicationFactory`.
**Desktop/mobile**: WPF/WinForms/MAUI/Blazor secondo il caso.
**Output**: codice completo con `.csproj` e pacchetti NuGet indicati, versione di .NET assunta.
@@@
name: swift-e-ios
title: Swift e sviluppo iOS
domain: programmazione
description: App per iPhone e Mac con Swift e SwiftUI: sintassi, concorrenza, architettura, persistenza, permessi e pubblicazione sull'App Store.
triggers: swift, swiftui, ios, iphone app, xcode, uikit, app store, core data, swiftdata, combine, async await swift, testflight, apple developer, macos app

**Linguaggio**: `let` di default, optional con `guard let`/`if let` (mai `!` non verificato), `struct` per i valori e `class` solo per identità/condivisione, enum con valori associati, protocolli e estensioni, gestione errori con `throws`, **concorrenza strutturata** (`async/await`, `Task`, `actor`, `@MainActor` per la UI).
**SwiftUI**: la vista è funzione dello stato; `@State` (locale), `@Binding`, `@Observable`/`@StateObject` (modello), `@Environment`; viste piccole e componibili, niente logica pesante nel `body`; navigazione con `NavigationStack`; anteprime per ogni stato.
**Architettura**: MVVM semplice, servizi iniettati, persistenza con SwiftData/Core Data, rete con `URLSession` + `Codable`.
**Piattaforma**: permessi con testo di spiegazione in `Info.plist`, background e notifiche (APNs), Keychain per i segreti, accessibilità (Dynamic Type, VoiceOver), test su dispositivo reale.
**Rilascio**: account sviluppatore, firma e profili, TestFlight, linee guida di revisione.
**Output**: codice compilabile (versione di iOS/Xcode indicata) e struttura del progetto.
@@@
name: flutter-e-dart
title: Flutter e Dart
domain: programmazione
description: App multipiattaforma con Flutter e Dart: widget, gestione dello stato, navigazione, prestazioni, plugin e rilascio.
triggers: flutter, dart, widget flutter, riverpod, bloc flutter, provider flutter, setstate, pubspec, flutter web, app flutter, hot reload, stateful widget

**Metodo**: tutto è un **widget**; preferisci `StatelessWidget` e `const` dove possibile (meno rebuild), spezza i widget grandi, `ListView.builder` per le liste lunghe, `Keys` quando l'ordine cambia. **Stato**: locale con `setState`/`ValueNotifier`; condiviso con **Riverpod** (consigliato) o Bloc; separa UI, logica e dati (repository); `FutureBuilder/StreamBuilder` o provider asincroni con gestione di caricamento/errore.
**Dart**: null safety, `async/await`, `Stream`, `extension`, `sealed class` + `switch` per gli stati; `freezed/json_serializable` per i modelli.
**Navigazione**: `go_router`. **Rete e dati**: `dio`/`http`, cache locale (Drift/Isar/Hive), offline.
**Prestazioni**: DevTools (Performance, Widget Inspector), evita lavoro nel `build`, immagini ridimensionate, `Isolate` per il lavoro pesante.
**Piattaforma**: plugin nativi con *platform channels*, permessi, icone e splash, firma e rilascio (Play Store/App Store), flavor per ambienti.
**Output**: codice funzionante con `pubspec.yaml` delle dipendenze e la struttura delle cartelle.
@@@
name: android-nativo-compose
title: Android nativo con Kotlin e Jetpack Compose
domain: programmazione
description: App Android native: Compose, ViewModel, coroutine/Flow, Room, Hilt, WorkManager, permessi, notifiche e release firmata.
triggers: jetpack compose, android nativo, viewmodel, room, hilt, workmanager, android studio, manifest android, gradle android, kotlin android, flow android, notifiche android, permessi android, apk firmato

**Architettura consigliata**: UI (Compose) → **ViewModel** → repository → sorgenti dati (Room, rete con Retrofit/Ktor); stato in `StateFlow` esposto come *UI state* immutabile, eventi una tantum separati; dependency injection con **Hilt**.
**Compose**: funzioni `@Composable` pure e piccole, *state hoisting* (stato in alto, eventi in basso), `remember`/`rememberSaveable`, `LazyColumn` con `key`, evita ricomposizioni inutili (stabilità dei tipi, `derivedStateOf`), anteprime `@Preview`, tema Material 3 con dark mode e colori dinamici.
**Piattaforma**: ciclo di vita e `collectAsStateWithLifecycle`; coroutine con scope corretti; **WorkManager** per lavori differibili; permessi a runtime nel contesto; canali di notifica (Android 8+) e permesso `POST_NOTIFICATIONS` (13+); `targetSdk` aggiornato; Doze e limiti in background.
**Release**: R8/ProGuard, `versionCode` crescente, firma con **keystore stabile** (backup!), AAB, Play App Signing.
**Output**: codice Kotlin completo (Gradle con versioni) e le insidie del ciclo di vita.
@@@
name: graphql-e-grpc
title: GraphQL, gRPC e alternative a REST
domain: programmazione
description: Sceglie e progetta API GraphQL, gRPC o tRPC: schema, risolutori, N+1, versionamento, streaming e quando preferirli a REST.
triggers: graphql, grpc, protobuf, trpc, apollo, schema graphql, resolver, dataloader, query graphql, mutation, subscription, protocol buffers, rest o graphql

**Scelta**: **REST** per API pubbliche semplici e cache HTTP; **GraphQL** quando client diversi chiedono forme di dati diverse (evita over/under-fetching); **gRPC** per comunicazione interna tra servizi (veloce, tipizzata, streaming); **tRPC** per full-stack TypeScript con un solo repository.
**GraphQL**: schema pensato per il dominio (non per le tabelle), nullabilità esplicita, paginazione a connessioni/cursore, **DataLoader** (batching) per evitare N+1 nei resolver, limiti di profondità/complessità e timeout contro query abusive, autorizzazione nei resolver (non solo allo strato esterno), errori con `extensions`, introspezione chiusa in produzione se serve, persisted queries; evolvi senza versioni (`@deprecated`).
**gRPC**: contratti `.proto` versionati (non riusare numeri di campo, aggiungi campi opzionali), deadline su ogni chiamata, retry con idempotenza, streaming server/client/bidirezionale, `grpc-web` per il browser.
**Output**: schema/proto di esempio, resolver o servizio, e i compromessi rispetto a REST.
@@@
name: websocket-e-realtime
title: WebSocket, SSE e tempo reale
domain: programmazione
description: Funzioni in tempo reale: WebSocket, Server-Sent Events, long polling, scalabilità, riconnessione, presenza e sicurezza.
triggers: websocket, socket.io, server-sent events, sse, tempo reale, realtime, real-time, chat in tempo reale, long polling, pub/sub, notifiche in tempo reale, push dal server, presenza online

**Scelta**: **SSE** per flussi dal server al client (notifiche, progresso, streaming di testo): semplice, su HTTP, riconnessione integrata; **WebSocket** per comunicazione bidirezionale a bassa latenza (chat, giochi, collaborazione); long polling come ripiego.
**Progettazione**: messaggi con tipo e versione (JSON con schema), **id di sequenza** per recuperare ciò che si è perso alla riconnessione (`Last-Event-ID`), **heartbeat/ping** per rilevare connessioni morte, **riconnessione con backoff e jitter**, backpressure (non accumulare buffer senza limite), idempotenza dei messaggi.
**Scalabilità**: connessioni lunghe consumano memoria → limiti per utente, più istanze dietro un **bus pub/sub** (Redis, NATS) per diffondere gli eventi, sticky session solo se serve; proxy/load balancer con timeout adatti (`X-Accel-Buffering: no` per SSE su nginx).
**Sicurezza**: autenticazione all'apertura (token a breve scadenza, non nell'URL se possibile), verifica dell'`Origin`, autorizzazione per canale, rate limit, validazione di ogni messaggio.
**Output**: protocollo dei messaggi, codice server e client con riconnessione, e il piano di scalabilità.
@@@
name: autenticazione-e-autorizzazione
title: Autenticazione e autorizzazione
domain: programmazione
description: Progetta login e permessi: sessioni vs JWT, OAuth2/OIDC, refresh token, password, MFA, passkey, RBAC/ABAC e errori da evitare.
triggers: autenticazione, autorizzazione, login, oauth, oauth2, openid connect, oidc, jwt, refresh token, sessione, rbac, permessi utente, single sign on, sso, passkey, accesso con google, cookie di sessione

**Scelte**: preferisci un **identity provider** (Auth0, Clerk, Keycloak, Supabase Auth, Cognito) a scrivere tutto da solo. Sessioni lato server con cookie `HttpOnly; Secure; SameSite=Lax` per le app web tradizionali; **JWT** brevi (5-15 min) con **refresh token** a rotazione per API/mobile; mai i token in `localStorage` se evitabile.
**OAuth2/OIDC**: usa il flusso **Authorization Code + PKCE** (anche per app mobile e SPA); valida `state`, `nonce`, `iss`, `aud`, firma e scadenza; scope minimi; redirect URI esatti.
**Password**: hash con argon2id/bcrypt, limiti ai tentativi, controllo delle password compromesse, **MFA** e **passkey (WebAuthn)**; recupero account sicuro (token monouso a scadenza).
**Autorizzazione**: controlla **a ogni richiesta e per ogni risorsa** (anti-IDOR), nel back-end; RBAC per ruoli, ABAC/policy per regole sugli attributi (proprietario, organizzazione); default: nega.
**Errori tipici**: JWT senza verifica o con `alg: none`, segreti nel client, fiducia nell'ID utente inviato dal client, token mai revocabili.
**Output**: diagramma del flusso (testuale), configurazione consigliata e checklist di verifica.
@@@
name: postgresql-avanzato
title: PostgreSQL avanzato
domain: programmazione
description: Usa a fondo PostgreSQL: tipi di indice, JSONB, CTE e window function, transazioni e isolamento, partizionamento, vacuum, pgvector ed EXPLAIN.
triggers: postgresql avanzato, window function, cte ricorsiva, jsonb, indice gin, pgvector, partizionamento, vacuum, isolamento delle transazioni, explain analyze, deadlock postgres, trigger postgres, extension postgres, lock

**Strumenti**: **indici**: B-tree (default), GIN (JSONB, array, full-text), GiST/SP-GiST (geometrie), BRIN (tabelle enormi ordinate), indici parziali, per espressione e **covering** (`INCLUDE`); `EXPLAIN (ANALYZE, BUFFERS)` per vedere seq scan, stime sbagliate e I/O; `pg_stat_statements` per le query più costose.
**SQL avanzato**: CTE (e ricorsive per gerarchie), **window function** (`ROW_NUMBER`, `LAG`, `SUM() OVER (PARTITION BY …)`), `LATERAL`, `UPSERT` (`ON CONFLICT`), `RETURNING`, `FILTER`, ricerca testuale (`tsvector`), `JSONB` con operatori e indici GIN.
**Transazioni**: livelli di isolamento (Read Committed di default; Repeatable Read/Serializable con retry), `SELECT … FOR UPDATE [SKIP LOCKED]` per code, transazioni brevi, ordine coerente dei lock contro i deadlock.
**Manutenzione**: autovacuum e *bloat*, `ANALYZE`, partizionamento per tempo, pool di connessioni (PgBouncer), backup/PITR.
**Estensioni**: `pgvector` (ricerca per similarità, indici HNSW/IVFFlat), `pg_trgm`, `pg_cron`.
**Output**: query o schema commentati, il piano atteso e i rischi (lock, dimensione dell'indice).
@@@
name: orm-e-accesso-ai-dati
title: ORM e accesso ai dati
domain: programmazione
description: Usa bene gli ORM (SQLAlchemy, Prisma, Hibernate, Entity Framework): mapping, N+1, transazioni, migrazioni e quando scrivere SQL a mano.
triggers: orm, sqlalchemy, prisma, hibernate, entity framework, drizzle, typeorm, n+1, lazy loading, repository pattern, migrazioni del database, unit of work, query builder, active record

**Principi**: l'ORM comoda ma non sostituisce la conoscenza di SQL: guarda **sempre le query generate** (log SQL).
**N+1**: sintomo = una query per ogni elemento di una lista; rimedio = *eager loading* (`joinedload/selectinload`, `include`, `JOIN FETCH`) o query esplicita con `IN`; misurala nei test (conta le query).
**Pratica**: transazioni brevi con un confine chiaro (una per richiesta/caso d'uso), sessioni non condivise tra thread/richieste, proiezioni (seleziona solo le colonne necessarie) per le liste, paginazione a cursore, indici su filtri e join, vincoli nel DB (non solo nel codice), migrazioni versionate e reversibili (aggiungi→migra→rimuovi, mai rotture di compatibilità in un solo passo), `bulk` per inserimenti massivi.
**Quando SQL a mano**: report complessi, aggregazioni pesanti, operazioni massive, funzioni specifiche del DB (parametrizzato!).
**Architettura**: repository solo se isola davvero la persistenza; evita di far trapelare le entità ORM fino all'API (usa DTO).
**Output**: esempio di mapping e query con la versione corretta e quella problematica, e come verificare il numero di query.
@@@
name: regex-e-parsing
title: Espressioni regolari e parsing
domain: programmazione
description: Scrive e legge regex corrette e leggibili, evita il backtracking catastrofico e sceglie quando usare un parser vero (JSON, HTML, grammatiche).
triggers: regex, espressione regolare, espressioni regolari, regexp, pattern matching, parsing, parser, tokenizer, grammatica, lookahead, gruppo di cattura, redos, estrarre con regex, validare con regex, analisi sintattica

**Metodo regex**: 1) descrivi a parole cosa deve combaciare e cosa NO, con esempi positivi e negativi; 2) costruisci a pezzi e testa ogni pezzo (regex101, test con casi limite); 3) ancora il pattern (`^…$`, `\b`), usa classi specifiche (`[0-9]` o `\d` secondo l'Unicode), quantificatori **non avidi** (`*?`) dove serve, gruppi con nome `(?<anno>\d{4})`, flag (`i`, `m`, `s`, `x` per commentare); 4) **sicurezza**: evita `(a+)+` e alternative sovrapposte (backtracking catastrofico/ReDoS), limita la lunghezza dell'input, usa motori senza backtracking (RE2) per dati non fidati.
**Quando NON usarla**: HTML/XML → parser DOM; JSON/CSV → librerie dedicate; linguaggi con annidamento → **parser** (combinatori, PEG, generatori come ANTLR/Lark); email e URL → librerie di validazione o semplici controlli + conferma reale.
**Parser**: tokenizer → analisi (ricorsiva discendente) → AST; errori con riga e colonna.
**Output**: la regex con spiegazione parte per parte, test positivi/negativi e il linguaggio/motore assunto.
@@@
name: interpreti-e-compilatori
title: Interpreti, compilatori e linguaggi
domain: programmazione
description: Costruisce interpreti e compilatori: lexer, parser, AST, valutazione, bytecode/VM, tipi e generazione di codice; capisce come funzionano i linguaggi.
triggers: compilatore, interprete, linguaggio di programmazione, creare un linguaggio, lexer, ast, albero sintattico, bytecode, virtual machine, parser ricorsivo, dsl, type checker, crafting interpreters, generazione di codice

**Pipeline**: **lexer** (testo → token) → **parser** (token → **AST**, ricorsiva discendente con precedenza degli operatori / Pratt parsing) → **analisi semantica** (scope, risoluzione dei nomi, controllo dei tipi) → esecuzione: **tree-walking interpreter** (più semplice), **bytecode + VM** (più veloce) o **compilazione** verso un IR/LLVM/assembly/JS.
**Metodo per iniziare**: 1) definisci la grammatica (EBNF) con esempi; 2) parti da un'aritmetica con variabili, poi funzioni, poi controllo di flusso; 3) errori utili (riga/colonna, cosa ci si aspettava) e recupero; 4) ambienti (scope) come catena di dizionari; chiusure; 5) test con programmi di esempio e output atteso; 6) ottimizzazioni solo dopo (costanti, inlining).
**Argomenti utili**: garbage collection (conteggio dei riferimenti, mark-and-sweep), inferenza dei tipi (Hindley–Milner), DSL interni vs esterni.
**Risorse**: «Crafting Interpreters» (gratuito), LLVM tutorial «Kaleidoscope».
**Output**: struttura dei moduli e codice minimo funzionante in un linguaggio a scelta.
@@@
name: sviluppo-giochi
title: Sviluppo di videogiochi
domain: programmazione
description: Crea giochi con Godot, Unity o Unreal e librerie 2D/web: game loop, ECS, fisica, input, asset, prestazioni e struttura del progetto.
triggers: videogioco, sviluppo giochi, game development, godot, unity, unreal engine, game loop, gamedev, sprite, collisioni, ecs, phaser, pygame, gdscript, game design

**Metodo**: 1) scegli lo strumento: **Godot** (leggero, open source, GDScript/C#), **Unity** (C#, ecosistema vasto), **Unreal** (3D di fascia alta, C++/Blueprint), **Phaser/PixiJS/Three.js** per il web, **pygame** per imparare; 2) **prototipa il «divertimento centrale»** in pochi giorni con grafica provvisoria; 3) **game loop**: input → aggiornamento (con **delta time**, mai legato ai frame) → rendering; fisica a passo fisso; 4) struttura: scene/oggetti (nodi) o **ECS** (entità-componenti-sistemi) per grandi quantità di entità; stati del gioco come macchina a stati; eventi/segnali per disaccoppiare; 5) input astratto (azioni, non tasti), più dispositivi; 6) asset: dimensioni e formati ottimizzati, atlante di sprite, pooling degli oggetti; 7) prestazioni: profiler, niente allocazioni per frame, draw call contenute; 8) salvataggi versionati.
**Design**: loop di gioco chiaro, curva di difficoltà, feedback immediato (suono, particelle).
**Output**: struttura del progetto, codice del sistema richiesto (movimento, collisioni, nemici) e piano a milestone. Licenze degli asset.
@@@
name: programmazione-embedded
title: Programmazione embedded e RTOS
domain: programmazione
description: Firmware per microcontrollori (ARM Cortex-M, ESP32, AVR): C/C++/Rust, periferiche, interrupt, RTOS, consumo, debugging e affidabilità.
triggers: firmware, embedded, microcontrollore programmazione, rtos, freertos, interrupt, stm32, esp-idf, registro, watchdog, bootloader, uart, spi, i2c driver, zephyr, platformio

**Metodo**: 1) vincoli (memoria, CPU, consumo, tempo reale); 2) astrazione dell'hardware (HAL) separata dalla logica applicativa → logica testabile sul PC; 3) **interrupt**: routine brevissime (imposta un flag/accoda un evento), variabili condivise `volatile` + accesso atomico, niente `printf`/allocazioni dentro; 4) **RTOS** (FreeRTOS/Zephyr): task con priorità e stack dimensionato, code e semafori per comunicare, mutex con attenzione all'inversione di priorità, **niente attese attive**; 5) memoria: allocazione statica, evita `malloc`, controlla stack e heap; 6) **robustezza**: watchdog, validazione degli input dei sensori, macchine a stati, gestione dei reset, aggiornamenti OTA con rollback e firma; 7) **risparmio energetico**: sleep profondo, clock ridotti, svegli da interrupt; 8) debug: seriale/log, **SWD** con debugger, analizzatore logico/oscilloscopio.
**Qualità**: MISRA-C come guida, analisi statica, test su hardware-in-the-loop.
**Output**: struttura del firmware, codice del driver/task richiesto e le verifiche di temporizzazione.
@@@
name: ddd-e-architettura-a-eventi
title: DDD, CQRS ed event-driven
domain: programmazione
description: Modella domini complessi con Domain-Driven Design, architettura esagonale, CQRS ed event sourcing, sapendo quando NON servono.
triggers: ddd, domain driven design, architettura esagonale, clean architecture, cqrs, event sourcing, bounded context, aggregato, event driven, eventi di dominio, ports and adapters, microservizi e domini, linguaggio ubiquo

**Quando serve**: logica di dominio complessa e che cambia; per un CRUD semplice basta uno strato sottile. L'architettura è un costo: giustificala.
**DDD strategico**: **linguaggio ubiquo** condiviso con chi conosce il dominio; **bounded context** (confini in cui un termine ha un solo significato) e mappa dei contesti; sottodomini core/di supporto/generici (investi sul core).
**DDD tattico**: **entità** (identità), **value object** (immutabili, confronto per valore), **aggregati** (confine di consistenza: una transazione = un aggregato, riferimenti tra aggregati per id), servizi di dominio, **repository** per aggregati, **eventi di dominio**.
**Architettura esagonale / clean**: il dominio non dipende da framework né DB; porte (interfacce) e adattatori (HTTP, DB, code) ai bordi; dipendenze verso l'interno.
**CQRS**: modelli separati per scrivere e leggere (utile con carichi diversi o viste dedicate). **Event sourcing**: lo stato è la sequenza di eventi — potente (audit, ricostruzione) ma complesso (versionamento degli eventi, proiezioni, correzioni): usalo solo con motivo forte.
**Event-driven**: eventi immutabili con schema versionato, consegna almeno una volta + idempotenza, outbox.
**Output**: mappa dei contesti, aggregati principali con invarianti, e un esempio di codice del caso d'uso.
@@@
name: build-tools-e-bundler
title: Build tool, bundler e monorepo
domain: programmazione
description: Configura Vite, Webpack, esbuild, Rollup, Turborepo/Nx e pnpm workspaces: build rapide, code splitting, alias, variabili d'ambiente e monorepo.
triggers: vite, webpack, esbuild, rollup, bundler, monorepo, turborepo, nx, pnpm workspace, code splitting, tree shaking, build lenta, alias di importazione, babel, swc, variabili d'ambiente vite

**Scelta**: **Vite** (sviluppo veloce con ESM nativo, build con Rollup) per app e librerie moderne; **esbuild/tsup** per librerie e script; **Webpack** per progetti esistenti o esigenze particolari; **Turborepo/Nx** per orchestrare i task nei monorepo.
**Pratica**: **code splitting** per rotta (`import()`), *tree shaking* (moduli ES, `sideEffects` nel `package.json`), analisi del bundle (`rollup-plugin-visualizer`) per scovare dipendenze pesanti, immagini e font ottimizzati, **hash dei file** per la cache a lungo termine, source map separate, target dei browser esplicito.
**Variabili d'ambiente**: `import.meta.env` con prefisso `VITE_` (sono **pubbliche**: niente segreti nel client).
**Monorepo**: workspace pnpm, pacchetti condivisi con versioni interne (`workspace:*`), `tsconfig` di base ed `extends`, cache dei task (build/test/lint solo su ciò che cambia), **un solo lockfile**, regole di confine tra pacchetti.
**Diagnosi**: build lenta → profila i plugin, evita Babel dove basta SWC/esbuild, TypeScript in un passo separato (`tsc --noEmit`).
**Output**: file di configurazione commentato e i comandi, con le versioni degli strumenti.
@@@
name: gestione-dipendenze-e-supply-chain
title: Dipendenze e sicurezza della supply chain
domain: programmazione
description: Gestisce librerie e pacchetti (npm, pip, poetry, cargo): versioni, lockfile, aggiornamenti, vulnerabilità, licenze e attacchi alla supply chain.
triggers: dipendenze, npm, pip, poetry, requirements.txt, package.json, lockfile, semver, dependabot, vulnerabilità delle dipendenze, supply chain, typosquatting, aggiornare le librerie, conflitto di versioni, sbom, audit delle dipendenze

**Principi**: ogni dipendenza è codice altrui che esegui: aggiungila solo se serve davvero (valuta manutenzione, popolarità, licenza, dimensione, alternative nella libreria standard).
**Versioni**: **lockfile** sempre nel repository (`package-lock.json`, `poetry.lock`, `Cargo.lock`) e installazioni riproducibili (`npm ci`, `pip install --require-hashes` o `uv`/`pip-tools`); **semver** (maggiore = rotture) e intervalli prudenti; ambienti isolati (venv, container).
**Aggiornamenti**: a piccoli passi e spesso (**Dependabot/Renovate**), una cosa alla volta, CI verde, leggi i changelog; per le *major* pianifica.
**Sicurezza**: `npm audit`, `pip-audit`, `cargo audit`, OSV; attenzione a **typosquatting** (nomi simili), pacchetti abbandonati, script di installazione (`postinstall`), account manutentore compromessi; fissa le versioni delle azioni CI (per hash), verifica le firme/provenienza, **SBOM** per sapere cosa contiene l'app.
**Conflitti di versione**: individua chi richiede cosa (`npm ls`, `pipdeptree`), allinea o isola.
**Licenze**: compatibilità (MIT/Apache vs GPL/AGPL) con l'uso previsto.
**Output**: piano di aggiornamento ordinato e comandi di verifica; segnala i rischi concreti.
@@@
name: open-source-e-licenze
title: Open source, licenze e contributi
domain: programmazione
description: Pubblica e mantiene progetti open source: scelta della licenza, README, contributi, pull request, versioni, sicurezza e community.
triggers: open source, licenza, licenza mit, gpl, apache 2, contribuire a un progetto, pubblicare su github, mantenere un progetto open source, contributing, fork, semver, issue template, codice di condotta, copyright del codice

**Licenze (orientamento, non consulenza legale)**: **MIT/BSD/Apache-2.0** = permissive (uso anche commerciale, Apache aggiunge concessione di brevetti); **GPL/AGPL** = *copyleft* (le opere derivate restano libere; AGPL vale anche per i servizi via rete); **LGPL** = copyleft debole per librerie; senza licenza = tutti i diritti riservati (nessuno può usarlo). Scegli in base a obiettivi (diffusione vs reciprocità) e compatibilità con le dipendenze.
**Pubblicare**: repository con `README` (cosa fa, installazione, esempio), `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` (come segnalare vulnerabilità), template di issue/PR, CI pubblica, **release con tag semver** e changelog.
**Contribuire**: leggi le regole, apri prima una issue per proporre, PR piccole e focalizzate con test e descrizione chiara, accetta le revisioni con calma, firma (DCO) se richiesto.
**Mantenere**: rispondi con tempi realistici, etichette (*good first issue*), automatizza (CI, Dependabot, rilasci), impara a dire di no, individua co-manutentori.
**Segreti**: mai chiavi nella storia di git (se capita: revoca e riscrivi).
**Output**: file pronti (README, CONTRIBUTING, scelta e motivazione della licenza) e checklist di pubblicazione.
@@@
name: data-engineering
title: Data engineering e pipeline di dati
domain: programmazione
description: Costruisce pipeline ETL/ELT affidabili: orchestrazione (Airflow, Dagster), dbt, data warehouse, formati (Parquet), qualità e streaming.
triggers: data engineering, etl, elt, pipeline di dati, airflow, dagster, dbt, data warehouse, bigquery, snowflake, parquet, spark, kafka dati, data lake, qualità dei dati, orchestrazione

**Metodo**: 1) fonti, volumi, freschezza richiesta (batch giornaliero o quasi tempo reale?) e consumatori; 2) **ELT** moderna: carica i dati grezzi nel warehouse (BigQuery/Snowflake/Postgres/DuckDB) e trasformali con **SQL/dbt** a livelli (*raw → staging → marts*); 3) **orchestrazione** con dipendenze esplicite, retry, backfill e allarmi (Airflow/Dagster/Prefect); 4) pipeline **idempotenti** (rilanciare non duplica: scritture per partizione, `MERGE`/upsert) e deterministiche; 5) formati colonnari (**Parquet**) partizionati per data; 6) **qualità**: test sui dati (unicità, non-null, relazioni, intervalli — dbt tests/Great Expectations), monitoraggio di volume e freschezza, contratti dei dati con i produttori; 7) schema che evolve con compatibilità; 8) **streaming** (Kafka, Flink) solo se serve; 9) costi (partizioni, clustering, query limitate), sicurezza e dati personali (GDPR: minimizzazione, mascheramento).
**Piccola scala**: DuckDB + Parquet + cron spesso bastano.
**Output**: schema dei livelli, esempio di modello/DAG e i controlli di qualità.
@@@
name: powershell-e-automazione-windows
title: PowerShell e automazione Windows
domain: programmazione
description: Scrive script PowerShell sicuri e automatizza Windows: oggetti e pipeline, file, registro, servizi, attività pianificate, remoting e installazioni.
triggers: powershell, script powershell, automazione windows, cmdlet, task scheduler, attività pianificata, registro di sistema, winget, powershell remoting, get-childitem, windows script, bat, pwsh

**Concetti**: PowerShell passa **oggetti**, non testo: `Get-Process | Where-Object CPU -gt 100 | Sort-Object CPU -Descending | Select-Object -First 5`. Verbo-Nome (`Get-`, `Set-`, `New-`), `Get-Help`, `Get-Member` per scoprire le proprietà.
**Script sicuri**: `Set-StrictMode -Version Latest`, `$ErrorActionPreference = 'Stop'`, `try/catch/finally`, parametri tipizzati con `[CmdletBinding()]` e `[Parameter(Mandatory)]`, `-WhatIf`/`-Confirm` per le operazioni distruttive (`SupportsShouldProcess`), percorsi con `Join-Path` e `-LiteralPath`, **niente password in chiaro** (`Get-Credential`, SecretManagement), politica di esecuzione consapevole (`RemoteSigned`).
**Compiti comuni**: file (`Copy-Item`, `Robocopy`), servizi (`Get-Service`, `Restart-Service`), **attività pianificate** (`Register-ScheduledTask`), registro (`Get-ItemProperty HKCU:\…`), installazioni (`winget install`), rete (`Test-NetConnection`), CSV/JSON (`Import-Csv`, `ConvertFrom-Json`), remoting (`Invoke-Command`).
**Compatibilità**: PowerShell 7 (`pwsh`, multipiattaforma) vs 5.1 di Windows (attenzione a codifiche e parametri come `-Encoding Byte`).
**Output**: script completo e commentato, con prova a secco e avviso sui comandi che modificano il sistema.
@@@
name: tauri-e-app-desktop
title: App desktop: Tauri, Electron e nativo
domain: programmazione
description: Sviluppa app desktop con Tauri, Electron o framework nativi: architettura, comunicazione front-end/back-end, sicurezza, installer, aggiornamenti e firma.
triggers: tauri, electron, app desktop, applicazione desktop, installer, auto update desktop, tray icon, comandi tauri, ipc, windows app, msi, nsis, autostart, notifica desktop

**Scelta**: **Tauri** (front-end web + back-end Rust, app leggere, WebView di sistema, sicurezza a permessi) vs **Electron** (Chromium incluso, ecosistema Node enorme, più pesante) vs nativo (Qt, .NET/WinUI, SwiftUI) per integrazione profonda.
**Tauri**: i *comandi* Rust (`#[tauri::command]`) sono l'API verso il front-end (`invoke`): validali come input non fidato; **capabilities/permessi** minimi per finestre e plugin; stato condiviso con `manage()`; eventi per il flusso inverso; plugin ufficiali (notifiche, autostart, opener, updater); `tauri icon` genera tutte le icone da un PNG.
**Sicurezza**: CSP rigorosa, nessun contenuto remoto non fidato nella WebView, niente `eval`, segreti nel gestore credenziali del sistema (Keychain/Credential Manager) e non in `localStorage`.
**Prestazioni/UX**: operazioni lente fuori dal thread UI, tray e avvio con il sistema solo su scelta dell'utente, stato della finestra ricordato.
**Distribuzione**: installer (NSIS/MSI, dmg, AppImage), **firma del codice** (senza, SmartScreen/Gatekeeper avvisano), **aggiornamenti** firmati (plugin updater) o notifica di nuova versione con download verificato (checksum), CI con build per sistema operativo.
**Output**: struttura del progetto, comando Rust + chiamata JS d'esempio, configurazione dei permessi e pipeline di rilascio.
@@@
name: bot-e-chatbot-sviluppo
title: Sviluppo di bot (Telegram, Discord, Slack)
domain: programmazione
description: Crea bot e assistenti chat: webhook vs polling, comandi, pulsanti inline, stato, limiti di frequenza, sicurezza e integrazione con LLM.
triggers: bot telegram, bot discord, bot slack, creare un bot, chatbot, webhook telegram, comandi del bot, pulsanti inline, discord.py, python-telegram-bot, api del bot, botfather, slash command

**Metodo**: 1) piattaforma e API (Telegram Bot API, Discord, Slack); 2) **webhook** (consigliato in produzione: HTTPS, secret token, risposta rapida) vs **polling** (semplice in sviluppo); 3) autenticazione: **consenti solo gli utenti previsti** (id numerico del proprietario), ignora gli altri; 4) comandi chiari e `/aiuto`, menu dei comandi registrati, tastiere inline con `callback_data` brevi e validati; 5) **idempotenza**: le piattaforme rinviano gli aggiornamenti → deduplica per `update_id`; 6) **limiti**: ~30 messaggi/s globali, ~1/s per chat (Telegram): coda e gestione dell'errore 429 (`retry_after`); messaggi lunghi divisi; 7) stato della conversazione salvato (database), non in memoria; 8) formattazione (HTML/Markdown) con escape corretto; 9) file e vocali con dimensioni/limiti; 10) gestione errori gentile e log.
**Con LLM**: risposte in streaming con modifica del messaggio, contesto limitato, strumenti con conferma per azioni sensibili, nessun dato personale non necessario ai modelli.
**Segreti**: token del bot solo in variabili d'ambiente; se trapela, rigenera con BotFather.
**Output**: codice del bot con gestione dei comandi/callback, configurazione del webhook e checklist di sicurezza.
@@@
name: test-avanzati-e-carico
title: Test avanzati: property-based, contratti e carico
domain: programmazione
description: Va oltre gli unit test: property-based testing, mutation testing, contract test, snapshot, test di carico (k6, Locust) e di resilienza.
triggers: property based testing, hypothesis, mutation testing, contract test, pact, test di carico, k6, locust, load testing, stress test, snapshot test, test flaky, chaos engineering, test di resilienza

**Property-based**: invece di esempi, descrivi **proprietà** che devono valere per tutti gli input (`decode(encode(x)) == x`, ordinare è idempotente, somma commutativa) e lascia che **Hypothesis/fast-check** generi i casi (con riduzione del controesempio).
**Mutation testing** (mutmut, Stryker): cambia il codice e verifica che i test se ne accorgano: misura la qualità dei test, non la copertura.
**Contract test** (Pact, schema OpenAPI): consumer e provider si verificano a vicenda senza ambienti integrati.
**Snapshot**: solo per output stabili e piccoli, da rivedere ad ogni modifica.
**Flaky test**: cause tipiche (tempo, ordine, rete, stato condiviso, concorrenza): isola, fissa gli orologi, rendi atomici i dati; mai «rilancia finché passa».
**Carico** (k6, Locust, Gatling): obiettivo (es. 200 utenti, p95 < 300 ms), scenari realistici, rampa progressiva (smoke → load → stress → soak), ambiente simile alla produzione, misura latenza percentile, errori, saturazione (CPU, DB, connessioni).
**Resilienza**: guasti simulati (timeout, dipendenza giù), circuit breaker e retry verificati.
**Output**: esempio di test/script pronto, soglie (SLO) e come leggere i risultati.
@@@
name: date-ora-e-fusi-orari
title: Date, orari e fusi orari nel codice
domain: programmazione
description: Gestisce il tempo senza bug: UTC, fusi orari e ora legale, ISO 8601, durate, calendari, timestamp e errori classici in date e scadenze.
triggers: fuso orario, timezone, ora legale, utc, datetime, data e ora, iso 8601, timestamp, durata, calendario, bug sulle date, mezzanotte, formato data, scadenza, date in python, zoneinfo, moment.js, temporal

**Regole d'oro**: 1) **salva in UTC** (o come istante assoluto con offset) e converti solo per mostrare, nel fuso dell'utente; 2) usa tipi **con fuso** (*aware*), mai date «naive» mischiate con aware; 3) i fusi si identificano con nomi **IANA** (`Europe/Rome`), non con offset fissi: l'offset cambia con l'**ora legale** (ci sono giorni di 23 e 25 ore e orari che non esistono o si ripetono); 4) formato di scambio **ISO 8601** (`2026-10-21T08:30:00+02:00` / `…Z`); 5) per eventi futuri in un luogo (appuntamento alle 9:00 a Roma) salva **ora locale + fuso**, non l'istante UTC (le regole possono cambiare); 6) distingui **istante**, **data civile** (compleanno: niente fuso) e **durata**; 7) aggiungere «1 giorno» ≠ aggiungere 24 ore; mesi di lunghezza diversa, anni bisestili; fine mese con attenzione.
**Strumenti**: Python `zoneinfo`/`datetime`, JS **Temporal** (o date-fns/Luxon; evita Moment.js), Java `java.time`, database `timestamptz`.
**Test**: fissa l'orologio, prova i cambi dell'ora legale, mezzanotte, 29 febbraio, fusi con mezz'ora (India).
**Output**: codice corretto con il ragionamento sul tipo di tempo in gioco.
@@@
name: numeri-precisione-e-denaro
title: Numeri, floating point e denaro
domain: programmazione
description: Evita errori numerici: floating point, arrotondamenti, decimali, valute e importi in denaro, overflow, confronti e unità di misura.
triggers: floating point, virgola mobile, 0.1 + 0.2, arrotondamento, decimal, denaro nel codice, importi, valuta nel codice, overflow, precisione numerica, bigint, centesimi, errore di arrotondamento, confronto tra float, nan

**Fatti**: i `float`/`double` binari **non rappresentano esattamente** molti decimali (`0.1 + 0.2 ≠ 0.3`); `NaN != NaN`; gli interi hanno limiti (overflow silenzioso in C/Java, `Number.MAX_SAFE_INTEGER` = 2^53−1 in JS → usa `BigInt`).
**Denaro**: **mai float**. Rappresenta gli importi come **interi in centesimi** (o `Decimal`/`NUMERIC` con scala fissa) insieme al codice valuta (ISO 4217; alcune valute hanno 0 o 3 decimali); operazioni con tipi decimali (`decimal.Decimal`, `BigDecimal`, `numeric` SQL), **regola di arrotondamento esplicita** (half-up vs *bancario*/half-even), arrotonda alla fine non a ogni passo; ripartizione di un importo (es. 100 € in 3) con il resto assegnato esplicitamente; **IVA e percentuali** calcolate con regole di legge/contratto documentate.
**Confronti**: tra float usa tolleranza (`math.isclose`, epsilon relativo), non `==`; ordina senza fidarti di somme di molti float (somma di Kahan/`fsum`).
**Unità di misura**: includile nei nomi (`timeout_ms`), conversioni centralizzate.
**Test**: casi di confine (zero, negativi, grandi numeri, arrotondamenti a metà).
**Output**: codice corretto, spiegazione dell'errore e regola di arrotondamento adottata.
@@@
name: unicode-e-localizzazione
title: Unicode, i18n e localizzazione del software
domain: programmazione
description: Gestisce testi in ogni lingua: Unicode e UTF-8, normalizzazione, ordinamento, i18n/l10n, plurali, formati locali e testo bidirezionale.
triggers: unicode, utf-8, codifica dei caratteri, encoding, i18n, l10n, internazionalizzazione, traduzioni dell'app, plurali, caratteri strani, mojibake, emoji nel codice, ordinamento alfabetico, gettext, icu

**Unicode**: usa **UTF-8** ovunque (file, database `utf8mb4` in MySQL, header HTTP `charset=utf-8`); un «carattere» visibile può essere più **code point** (accenti combinati, emoji con modificatori): lunghezza e inversione di stringhe vanno fatte per **grapheme cluster**; **normalizzazione** (NFC) prima di confrontare/indicizzare («è» può avere due forme); confronto e ordinamento con le regole del locale (`Intl.Collator`, ICU), non con `<`; maiuscole/minuscole dipendenti dalla lingua (turco `İ`).
**Mojibake** (`Ã¨` invece di `è`): qualcuno ha letto UTF-8 come Latin-1 → correggi la codifica alla fonte.
**i18n/l10n**: **mai concatenare** stringhe tradotte; usa messaggi con segnaposto e **regole dei plurali** (ICU MessageFormat/gettext: l'italiano ha 2 forme, l'arabo 6); chiavi di traduzione stabili, contesto per i traduttori; spazio per testi più lunghi (tedesco +30%); formati di **data, numero, valuta** locali (`Intl.DateTimeFormat/NumberFormat`); testo **bidirezionale** (arabo/ebraico, `dir="rtl"`); lingua di ripiego.
**Output**: codice con le librerie giuste e i casi di test (accenti, emoji, RTL).
@@@
name: git-avanzato
title: Git avanzato
domain: programmazione
description: Padroneggia Git: rebase interattivo, bisect, reflog, cherry-pick, stash, worktree, hook, risoluzione di conflitti e recupero da errori.
triggers: git avanzato, rebase interattivo, git bisect, reflog, cherry-pick, git stash, worktree, git hook, ho sbagliato un commit, recuperare un commit perso, squash dei commit, git reset, force push, sottomoduli

**Recuperare dagli errori**: `git reflog` mostra dove sei stato (anche dopo reset/rebase): ripristina con `git reset --hard <hash>` o crea un branch da quel commit; `git restore`/`git checkout -- file` per i file; `git revert` per annullare un commit **pubblicato**; `git commit --amend` solo su commit non pubblicati.
**Storia pulita**: `git rebase -i HEAD~5` (squash, fixup, reword, riordino); `git commit --fixup` + `--autosquash`; `git pull --rebase`; **`--force-with-lease`** al posto di `--force` (e mai su rami condivisi).
**Trovare bug**: `git bisect start/bad/good` (o `bisect run ./test.sh`); `git blame -L`; `git log -S"testo"`/`-G`; `git log --oneline --graph --all`.
**Lavorare in parallelo**: `git worktree add ../fix main`, `git stash -u`, `git cherry-pick <hash>` (con `-x`), branch di funzione piccoli.
**Conflitti**: `git merge`/`rebase`, capisci le due intenzioni, `git mergetool`, `git rerere` per riusare le risoluzioni.
**Automazione**: hook (`pre-commit`) per lint/test, `.gitattributes`, `.gitignore` globale; **segreti committati** → revoca subito, poi `git filter-repo`.
**Output**: i comandi esatti in ordine, cosa accadrà, e l'avviso se riscrivono la storia.
@@@
name: affidabilita-incident-e-postmortem
title: Affidabilità, incidenti e post-mortem (SRE)
domain: programmazione
description: Gestisce malfunzionamenti in produzione: triage, comunicazione, mitigazione, post-mortem senza colpe, SLO, error budget e runbook.
triggers: incidente, in produzione, il servizio è giù, post-mortem, postmortem, sre, slo, sla, error budget, runbook, outage, on-call, rollback urgente, disponibilità del servizio, allarmi

**Durante un incidente**: 1) **stabilizza prima, indaga dopo**: la mitigazione più rapida e sicura (rollback dell'ultimo rilascio, disattivare una funzione, scalare, spostare il traffico); 2) un **responsabile dell'incidente**, un canale unico, un cronista; 3) **comunica** a intervalli fissi (cosa sappiamo, cosa facciamo, prossimo aggiornamento); 4) cambia **una cosa per volta** e annotala; 5) cerca cosa è cambiato di recente (deploy, config, traffico, dipendenze, certificati scaduti, disco pieno, quote); 6) conferma la risoluzione con le metriche.
**Dopo**: **post-mortem senza colpe** entro pochi giorni: cronologia, impatto (utenti, durata), causa radice (i «5 perché», fattori contribuenti), cosa ha funzionato, **azioni correttive con responsabile e data**, cosa si impara; condividilo.
**Prevenire**: **SLI/SLO** (es. 99,9% di richieste riuscite in 30 giorni) ed **error budget** per decidere tra velocità e stabilità; allarmi sui **sintomi per l'utente** (non su ogni metrica), con un runbook per ognuno; rilasci graduali (canary), *feature flag*, backup testati, esercitazioni.
**Output**: checklist dell'incidente, bozza di post-mortem con le sezioni e le azioni proposte.
@@@
name: kubernetes-pratico
title: Kubernetes in pratica
domain: programmazione
description: Usa Kubernetes senza perdersi: pod, deployment, servizi, ingress, configurazione, risorse, probe, Helm, debug con kubectl e quando evitarlo.
triggers: kubernetes, k8s, kubectl, pod, deployment, helm, ingress, configmap, namespace, k3s, crashloopbackoff, liveness probe, cluster kubernetes, minikube, argo cd

**Quando**: serve con molti servizi, scalabilità automatica e team strutturati; per poche app, un PaaS o Docker Compose costa meno. Per iniziare: `k3s`/`minikube`/`kind` in locale.
**Concetti**: **Pod** (uno o più container) gestiti da un **Deployment** (repliche, aggiornamenti graduali), esposti da un **Service** (ClusterIP/LoadBalancer) e raggiunti da **Ingress**; **ConfigMap/Secret** per la configurazione (i Secret sono solo codificati: usa un gestore dei segreti), **namespace** per separare gli ambienti, **PersistentVolume** per i dati.
**Buone pratiche**: **richieste e limiti** di CPU/memoria sempre; **readiness/liveness/startup probe**; immagini con tag fissi (non `latest`), utente non root; `PodDisruptionBudget` e più repliche; **HPA** per l'autoscaling; manifest in Git (**GitOps**: Argo CD/Flux), **Helm/Kustomize** per i template.
**Debug**: `kubectl get pods -A`, `describe pod X` (eventi), `logs -f X [--previous]`, `exec -it`, `top`; stati: **CrashLoopBackOff** (guarda i log precedenti, config o segreti mancanti), **ImagePullBackOff** (nome/credenziali), **Pending** (risorse insufficienti), **OOMKilled** (limite di memoria).
**Output**: manifest YAML commentati e i comandi di verifica; evita complessità inutile.
@@@
name: http-e-web-platform
title: HTTP e piattaforma web
domain: programmazione
description: Capisce a fondo il web: HTTP/2/3, cookie, CORS, cache e header, CDN, TLS, same-origin, CSP e debug con DevTools e curl.
triggers: http, header http, cors, errore cors, cache http, cdn, cookie samesite, cache-control, etag, tls, https, csp, content security policy, curl, devtools, same-origin policy, preflight

**HTTP**: metodi e idempotenza, codici di stato, header chiave (`Content-Type`, `Authorization`, `Accept`, `Cache-Control`); HTTP/2 (multiplexing, header compressi) e HTTP/3 (QUIC): meno «trucchi» di bundling.
**Cache**: `Cache-Control: public, max-age=31536000, immutable` per file con hash nel nome; `no-cache` + **`ETag`/`Last-Modified`** per rivalidare; `no-store` per dati sensibili; **CDN** davanti al sito statico; `Vary` quando la risposta cambia per header.
**CORS**: è una regola del **browser** per leggere risposte cross-origin; il server deve rispondere con `Access-Control-Allow-Origin` (origine esatta, non `*` se ci sono credenziali), gestire il **preflight** `OPTIONS` (metodi/header consentiti) e `Allow-Credentials` se necessario; `curl` funziona sempre perché non applica CORS → non è un bug del server se il browser blocca: controlla gli header.
**Cookie**: `HttpOnly`, `Secure`, `SameSite=Lax/Strict`, `Path`, scadenza; terze parti sempre più bloccate.
**Sicurezza**: HTTPS ovunque + HSTS, **CSP**, `X-Content-Type-Options`, `Referrer-Policy`.
**Debug**: scheda Rete di DevTools (tempi, header), `curl -v -I`, `openssl s_client`.
**Output**: spiegazione con la sequenza richiesta/risposta e gli header corretti da impostare.
@@@
name: web-performance
title: Prestazioni web e Core Web Vitals
domain: programmazione
description: Rende veloci siti e app web: LCP, INP, CLS, immagini, font, JavaScript, caricamento, rendering, cache e misura con Lighthouse e dati reali.
triggers: core web vitals, lcp, inp, cls, lighthouse, sito lento, velocità del sito, pagespeed, ottimizzare le immagini, lazy loading, tempo di caricamento, render blocking, web performance, tti

**Misura prima**: Lighthouse/PageSpeed per diagnosi, **dati reali** (CrUX, RUM) per verità; obiettivi **Core Web Vitals**: **LCP** ≤ 2,5 s (contenuto principale), **INP** ≤ 200 ms (reattività), **CLS** ≤ 0,1 (stabilità del layout).
**Leve per LCP**: server veloce/CDN e cache, **HTML già col contenuto** (SSR/statico), immagine principale ottimizzata (AVIF/WebP, dimensioni giuste con `srcset`, `fetchpriority="high"`, niente lazy-load per quella sopra la piega), `preload` mirato, CSS critico in linea.
**INP**: meno JavaScript (code splitting, rimuovi librerie pesanti), spezza i compiti lunghi (> 50 ms) con `scheduler.yield`/`requestIdleCallback`, lavoro pesante nei **Web Worker**, evita re-render inutili.
**CLS**: `width/height` (o `aspect-ratio`) su immagini e iframe, spazio riservato per annunci e embed, font con `font-display: swap` e metriche di ripiego.
**Altro**: `defer`/`async` sugli script, `loading="lazy"` sotto la piega, compressione Brotli, HTTP/2+, cache a lungo termine con file con hash, terze parti sotto controllo.
**Output**: elenco di interventi per impatto con il guadagno atteso, snippet pronti e come verificare.
@@@
name: pwa-e-service-worker
title: PWA e service worker
domain: programmazione
description: Crea Progressive Web App: manifest, service worker, strategie di cache, offline, notifiche push, installazione e aggiornamenti senza sorprese.
triggers: pwa, progressive web app, service worker, offline, manifest, cache api, workbox, installare il sito come app, web push, background sync, app web installabile

**Requisiti**: HTTPS, **manifest** (`name`, `icons` 192/512 anche *maskable*, `start_url`, `display: standalone`, `theme_color`), **service worker** registrato; test con Lighthouse.
**Service worker**: ciclo di vita `install` → `activate` → `fetch`; **strategie di cache** (Workbox): *cache first* per asset con hash, *network first* per i dati (con ripiego), *stale-while-revalidate* per contenuti che possono essere un po' vecchi; precache dell'app shell; pagina **offline** di ripiego.
**Aggiornamenti** (la parte difficile): un nuovo service worker resta in attesa finché le schede vecchie si chiudono; offri «Nuova versione disponibile → Aggiorna» (`skipWaiting` + `clients.claim` + ricarica), versiona le cache e cancella le vecchie, mai mettere in cache `index.html` a lungo.
**Dati offline**: IndexedDB, coda di operazioni da sincronizzare (Background Sync), gestione dei conflitti.
**Notifiche push**: Push API + VAPID, permesso richiesto **dopo un'azione dell'utente**, limiti su iOS (solo app installata).
**Sicurezza**: non mettere in cache risposte con dati personali condivisibili; scope corretto.
**Output**: manifest e service worker completi con la strategia scelta e come testare gli aggiornamenti.
@@@
name: estensioni-browser
title: Estensioni per browser
domain: programmazione
description: Sviluppa estensioni per Chrome, Edge e Firefox (Manifest V3): content script, service worker, permessi, messaggistica, storage e pubblicazione.
triggers: estensione chrome, estensione del browser, extension, manifest v3, content script, chrome web store, webextension, firefox add-on, popup dell'estensione, background script, userscript

**Struttura (Manifest V3)**: `manifest.json` con `manifest_version: 3`, `permissions` **minimi** (e `host_permissions` ristretti: la revisione e la fiducia dell'utente dipendono da qui, `optional_permissions` quando possibile), `action` (popup), `background.service_worker` (a eventi, **non persistente**: niente stato in variabili globali), `content_scripts` con `matches` precisi.
**Componenti e comunicazione**: *content script* vivono nella pagina (isolati dal JS della pagina), passano messaggi con `chrome.runtime.sendMessage/onMessage` al service worker, che usa le API privilegiate (`storage`, `tabs`, `alarms`, `declarativeNetRequest`, `scripting`); stato persistente in `chrome.storage.local/sync`; attività periodiche con `alarms`.
**Sicurezza**: CSP predefinita (niente `eval`, niente codice remoto), tratta come non fidato ogni dato della pagina, `textContent` invece di `innerHTML`, valida i messaggi.
**Sviluppo**: caricamento «non pacchettizzata», ricarica automatica, Vite + CRXJS/WXT, TypeScript; compatibilità con Firefox (`browser.*`, polyfill `webextension-polyfill`).
**Pubblicazione**: icone, screenshot, descrizione chiara, **informativa privacy** per i dati raccolti, revisione dello store.
**Output**: `manifest.json` e codice di popup/content/background con il flusso dei messaggi.
@@@
name: ide-e-produttivita-sviluppatore
title: IDE, debugger e produttività dello sviluppatore
domain: programmazione
description: Lavora più velocemente: VS Code/JetBrains/Vim, scorciatoie, debugger e breakpoint, refactoring automatico, terminale, snippet, formattatori e flussi.
triggers: vs code, visual studio code, jetbrains, intellij, pycharm, vim, neovim, scorciatoie, debugger, breakpoint, ide, configurazione vscode, estensioni vscode, copilot, produttività programmando, launch.json

**Metodo**: usa l'editor a **tastiera** e impara 10 scorciatoie in più al mese: cerca ovunque (`Ctrl+Shift+F`/`Shift+Shift`), vai a definizione/riferimenti, rinomina simbolo (**refactoring automatico**, non cerca-e-sostituisci), multi-cursore, comandi (`Ctrl+Shift+P`).
**Debugger**: **breakpoint condizionali**, *logpoint* (stampa senza modificare il codice), step in/over/out, ispezione delle variabili e **watch**, stack delle chiamate, eccezioni «break on raise», debug remoto/di container; configurazione `launch.json` per ogni progetto.
**Qualità automatica**: formatter (Prettier, Black, `gofmt`, `rustfmt`) al salvataggio, linter (ESLint, Ruff), tipi (TypeScript, mypy), `pre-commit` e **EditorConfig**: niente discussioni di stile.
**Ambiente**: terminale integrato, workspace e settings **nel repository** (`.vscode/`), dev container per ambienti riproducibili, snippet per codice ripetitivo, gestione di più versioni di runtime (mise/asdf/pyenv/nvm).
**AI nel flusso**: assistenti di codice per boilerplate/test/spiegazioni, ma rivedi sempre ciò che proponi (correttezza, sicurezza, licenze).
**Output**: configurazione pronta (settings, launch, estensioni consigliate) e le scorciatoie più utili per il caso.
