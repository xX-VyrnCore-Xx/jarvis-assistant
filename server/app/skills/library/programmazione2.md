name: react-e-frontend-moderno
title: React e front-end moderno
domain: programmazione
description: Sviluppa interfacce React: componenti, hook, stato, data fetching, prestazioni, form, test e architettura di un front-end moderno.
triggers: react, hook, useeffect, usestate, usememo, componente react, jsx, tsx, next.js, redux, zustand, tanstack query, re-render, react router, server components, form in react, context api

**Metodo**: componenti piccoli e puri; stato **minimo** (ciò che si può derivare non va nello stato), tenuto il più vicino possibile a chi lo usa; stato del server con una libreria dedicata (TanStack Query/SWR: cache, retry, invalidazione) e stato globale solo se serve davvero (Zustand/Context). `useEffect` solo per sincronizzare con sistemi esterni — non per derivare dati né per reagire a eventi (usa gli handler); dipendenze complete, funzione di pulizia. `key` stabili (mai l'indice se la lista cambia).
**Prestazioni**: misura con React DevTools Profiler; evita lavoro nel render, `memo`/`useMemo`/`useCallback` solo dove il profilo lo giustifica, virtualizza le liste lunghe, code-splitting con `lazy`.
**Form e UX**: validazione (zod + react-hook-form), stati di caricamento/errore/vuoto in ogni vista, aggiornamenti ottimistici con rollback.
**Test**: Testing Library sul comportamento visibile, non sui dettagli interni.
**Output**: codice TypeScript funzionante con struttura di cartelle e il perché delle scelte; segnala la versione di React assunta.
@@@
name: nodejs-backend
title: Node.js e back-end JavaScript
domain: programmazione
description: Costruisce servizi Node.js (Express, Fastify, NestJS): struttura, async, validazione, errori, sicurezza, log e deploy.
triggers: node.js, nodejs, express, fastify, nestjs, backend node, server node, middleware, api node, npm run, event loop, stream node, pm2, back-end javascript, zod, prisma

**Metodo**: separa strati (route → servizio → accesso ai dati), configurazione da variabili d'ambiente validate all'avvio, validazione di ogni input (zod/JSON Schema) e DTO tipizzati, errori centralizzati con codici HTTP coerenti, `async/await` ovunque (nessuna promise senza `await` o `catch`), niente lavoro CPU nell'event loop (worker thread o coda), timeout su ogni chiamata esterna, logger strutturato (pino) con id di richiesta, chiusura ordinata su SIGTERM (smetti di accettare, finisci le richieste, chiudi connessioni).
**Sicurezza**: helmet, CORS ristretto, rate limit, query parametrizzate/ORM, segreti fuori dal repo, `npm audit` e lockfile.
**Test**: Supertest sulle route, database di prova o doppi ai confini.
**Output**: scheletro del servizio o l'esempio mirato, comandi per avviare e testare, e i punti da monitorare in produzione (memoria, event loop lag, errori).
@@@
name: typescript-avanzato
title: TypeScript avanzato
domain: programmazione
description: Tipi avanzati in TypeScript: generics, utility types, narrowing, tipi condizionali, inferenza e configurazione stretta.
triggers: typescript, generics, utility types, tipi condizionali, narrowing, type guard, tsconfig, as const, satisfies, infer, keyof, mapped types, errore di tipo ts, unknown vs any, discriminated union

**Principi**: abilita `strict` (e `noUncheckedIndexedAccess`); preferisci `unknown` ad `any` e restringi con type guard; modella gli stati con **unioni discriminate** (`{status:"ok",data}|{status:"err",error}`) e controlla l'esaustività con `never`; lascia inferire dove è chiaro, annota i confini pubblici; `as const` + `satisfies` per configurazioni; generics con vincoli (`<T extends {id:string}>`); utility type (`Pick`, `Omit`, `Partial`, `Required`, `Record`, `ReturnType`, `Awaited`); tipi di dominio «brand» per evitare di scambiare id.
**Errori frequenti**: cast con `as` per far tacere il compilatore, `!` non verificato, tipi duplicati a mano invece di derivarli (`typeof`, `keyof`, `z.infer`).
**Output**: il tipo/codice corretto con una riga sul perché funziona e, se un errore è criptico, la traduzione in parole semplici e la correzione.
@@@
name: rust
title: Rust
domain: programmazione
description: Aiuta con Rust: ownership e borrowing, lifetime, errori con Result, trait, cargo, concorrenza, async e errori del borrow checker.
triggers: rust, cargo, borrow checker, ownership, lifetime, trait, result e option, tokio, clippy, crate, unsafe rust, impl, rustc, mutabilità in rust, tauri

**Metodo**: ogni valore ha un solo proprietario; i prestiti sono `&T` (molti) oppure `&mut T` (uno solo) mai insieme; per gli errori del borrow checker: 1) leggi il messaggio (indica spesso la correzione), 2) chiediti chi deve possedere il dato, 3) soluzioni in ordine: restituire/spostare il valore, ridurre l'ambito del prestito, clonare (`clone`) se costa poco, `Rc/Arc` per proprietà condivisa, `RefCell/Mutex` per mutabilità interiore, strutturare il codice diversamente.
**Idiomi**: `Result<T, E>` con `?`, `thiserror`/`anyhow`, `Option` combinatori, iteratori al posto dei cicli a indice, `enum` per modellare stati, `derive` dove possibile, `#[cfg(test)]`. Async con `tokio`: niente blocchi nel runtime (`spawn_blocking`).
**Qualità**: `cargo fmt`, `cargo clippy -- -D warnings`, `cargo test`. Evita `unwrap()` fuori dai test; `unsafe` solo isolato e commentato.
**Output**: codice che compila (indica edizione e crate), spiegazione del perché il compilatore protesta.
@@@
name: go
title: Go (Golang)
domain: programmazione
description: Scrive Go idiomatico: package, interfacce piccole, errori, goroutine e canali, context, test e strumenti.
triggers: golang, go lang, linguaggio go, goroutine, canali go, go mod, context.context, defer, go test, interfaccia go, gin, go routine, programma in go, errore in go

**Linee guida**: semplicità; package piccoli con nomi brevi; interfacce **piccole**, definite da chi le usa («accept interfaces, return structs»); errori come valori: controllali subito, aggiungi contesto (`fmt.Errorf("leggo %s: %w", p, err)`), `errors.Is/As`; niente `panic` per errori attesi.
**Concorrenza**: avvia una goroutine solo sapendo **quando e come finisce**; `context.Context` come primo parametro per cancellazione e timeout; `sync.WaitGroup`/`errgroup`; canali per passare proprietà dei dati, `Mutex` per proteggere stato; chiudi i canali dal produttore; evita perdite di goroutine. Prova con `go test -race`.
**Strumenti**: `gofmt`, `go vet`, `staticcheck`, test a tabella (`t.Run`), `go mod tidy`, benchmark con `testing.B`.
**Output**: codice completo con `main` e test, e la nota su dove sono i punti di concorrenza e come si fermano.
@@@
name: java-e-kotlin
title: Java, Kotlin e ecosistema JVM
domain: programmazione
description: Sviluppo con Java e Kotlin: Spring Boot, Android, coroutine, stream, null safety, Gradle/Maven e basi della JVM.
triggers: java, kotlin, spring boot, spring, jvm, gradle, maven, coroutine, android studio, kotlin multiplatform, hibernate, jpa, nullpointerexception, lambda java, stream java

**Linee guida**: Kotlin: tipi non nullable per default, `data class`, `sealed class` per gli stati, funzioni di estensione, **coroutine** strutturate (scope, `Dispatchers.IO` per I/O, mai bloccare il main thread), `Flow` per flussi. Java: `record`, `Optional` solo come ritorno, stream senza effetti collaterali, `try-with-resources`, immutabilità.
**Spring Boot**: strati controller/servizio/repository, DTO separati dalle entità, validazione (`@Valid`), configurazione per profili, transazioni nel servizio, attenzione a N+1 e al caricamento lazy di JPA.
**Strumenti e JVM**: Gradle/Maven con versioni fissate, test con JUnit 5 + Mockito/MockK, log con SLF4J; per le prestazioni profila prima (JFR); capisci heap, garbage collector e leak tipici (cache senza limite).
**Output**: codice completo con dipendenze e versioni, e le insidie del caso (nullità, thread, transazioni).
@@@
name: c-e-cpp
title: C e C++
domain: programmazione
description: Programmazione in C/C++: memoria, puntatori, RAII, smart pointer, comportamento indefinito, CMake, sanitizer e C++ moderno.
triggers: c++, cpp, linguaggio c, puntatori, segmentation fault, memory leak, smart pointer, raii, cmake, valgrind, undefined behavior, template c++, stl, malloc, makefile, c++17

**Metodo**: in C++ moderno niente `new/delete` a mano: **RAII** + `std::unique_ptr` (proprietà unica), `shared_ptr` solo se serve davvero, contenitori STL (`vector`, `string_view`, `span`), `const` ovunque possibile, `std::optional`/`variant`, algoritmi e range invece di cicli grezzi, regola dello zero.
**Bug tipici**: uso dopo la liberazione, doppio `free`, buffer overflow, indice fuori limite, iteratori invalidati, dato non inizializzato, data race. Sono **comportamento indefinito**: individuali con `-fsanitize=address,undefined`, `valgrind`, `-Wall -Wextra -Werror`, `clang-tidy`.
**Build**: CMake con target moderni, standard esplicito (`-std=c++20`), test con GoogleTest/Catch2.
**C**: controlla sempre i valori di ritorno, passa le dimensioni dei buffer, `snprintf` al posto di `sprintf`.
**Output**: codice compilabile (compilatore e standard indicati) con la spiegazione di proprietà e durata di ogni risorsa.
@@@
name: shell-e-linux
title: Shell scripting e riga di comando Linux
domain: programmazione
description: Scrive script bash sicuri e usa bene la riga di comando: pipe, grep/sed/awk, find, permessi, cron, systemd, ssh.
triggers: bash, shell script, script bash, riga di comando, terminale, grep, sed, awk, find, chmod, cron, systemd, ssh, pipe, linux comando, zsh, one-liner, rsync

**Script sicuri**: `#!/usr/bin/env bash` + `set -euo pipefail`; **virgolette su tutte le variabili** (`"$var"`), `[[ ]]` per i test, `trap` per la pulizia, funzioni piccole, `local`, controllo degli argomenti, `mktemp` per i file temporanei, mai `rm -rf $dir/` con variabile non verificata. Sopra le ~100 righe o con strutture dati complesse passa a Python.
**Strumenti**: `grep -rn`/`rg`, `find -name … -print0 | xargs -0`, `sed -E 's/…/…/'`, `awk -F, '{s+=$3} END{print s}'`, `sort | uniq -c | sort -nr`, `jq` per JSON, `curl -fsS`, `tee`, `xargs -P` per il parallelo.
**Sistema**: permessi (`chmod 640`, `chown`), cron (`m h dom mon dow`, percorsi assoluti, log), unità `systemd` (`Restart=on-failure`), chiavi SSH (`ssh-keygen -t ed25519`), `rsync -avz --dry-run` prima.
**Output**: comando/script pronto, spiegato pezzo per pezzo, con avviso sui comandi distruttivi (e un `--dry-run` quando esiste).
@@@
name: algoritmi-e-strutture-dati
title: Algoritmi e strutture dati
domain: programmazione
description: Risolve problemi algoritmici: complessità, scelta della struttura dati, schemi ricorrenti (two pointers, BFS/DFS, DP, heap) e preparazione ai colloqui.
triggers: algoritmo, algoritmi, strutture dati, complessità, big o, ricorsione, programmazione dinamica, grafo, albero binario, ordinamento, ricerca binaria, hash map, coding interview, leetcode, heap, backtracking, two pointers

**Metodo**: 1) capisci il problema (esempi, casi limite, vincoli sui dati → complessità accettabile); 2) soluzione ovvia (forza bruta) e sua complessità; 3) riconosci lo schema: **hash map** (conteggi/ricerche O(1)), **two pointers / sliding window** (sequenze ordinate o sottostringhe), **ricerca binaria** (anche sulla risposta), **BFS** (distanze minime), **DFS/backtracking** (esplorazione, permutazioni), **heap** (top-k), **DP** (sottoproblemi sovrapposti: definisci stato, transizione, caso base), **union-find**, ordinamento + scansione; 4) ottimizza; 5) verifica a mano su un esempio e sui casi limite (vuoto, uno, duplicati, negativi).
**Output**: idea in 3 righe → complessità tempo/spazio → codice pulito → test dei casi limite. Per l'apprendimento, guida con domande e indizi prima di dare la soluzione completa.
@@@
name: clean-code-e-design-pattern
title: Clean code e design pattern
domain: programmazione
description: Migliora la struttura del codice: nomi, funzioni, SOLID, composizione, pattern utili e cattive abitudini (code smell) con refactoring mirato.
triggers: clean code, codice pulito, solid, design pattern, pattern, code smell, principio di responsabilità, dependency injection, composizione o ereditarietà, nomi delle variabili, funzione troppo lunga, factory, observer, strategy, dry, yagni

**Metodo**: 1) nomi che rivelano l'intenzione; 2) funzioni brevi che fanno **una cosa** e restano a un solo livello di astrazione; 3) pochi parametri (oggetti per i gruppi); 4) niente effetti collaterali nascosti, separa calcolo e I/O; 5) commenti per il **perché**, non per il cosa; 6) gestione errori coerente.
**SOLID in pratica**: una ragione per cambiare; estendi senza modificare; sostituibilità; interfacce piccole; dipendi da astrazioni (iniezione delle dipendenze → test facili). Preferisci **composizione** all'ereditarietà.
**Pattern**: usali per un problema reale, non per decorazione — Strategy (comportamenti intercambiabili), Factory (creazione), Observer/eventi (disaccoppiare), Adapter (integrare), Decorator, Repository. Segnali di troppa ingegneria: interfacce con una sola implementazione «per il futuro», livelli che inoltrano soltanto.
**Output**: prima/dopo del codice con il motivo di ogni cambio; se il codice funziona e non cambierà, dillo.
@@@
name: sviluppo-mobile
title: Sviluppo di app mobile
domain: programmazione
description: App per Android e iOS: scelta della tecnologia (nativo, Flutter, React Native, Capacitor), ciclo di vita, permessi, offline, notifiche push e pubblicazione.
triggers: app mobile, android, ios, react native, capacitor, apk, aab, play store, app store, notifiche push, firebase, permessi android, sviluppare un'app

**Scelta**: nativo (Kotlin/Compose, Swift/SwiftUI) per massime prestazioni e API di sistema; **Flutter** o **React Native** per un'unica base di codice con UI quasi nativa; **Capacitor/PWA** per portare un'app web con accesso ai sensori. Scegli in base a team, prestazioni, funzioni di sistema, tempi.
**Pratica**: rispetta il **ciclo di vita** (l'app viene sospesa e terminata: salva lo stato), thread principale libero, **offline-first** (cache locale, sincronizzazione, risoluzione dei conflitti), richiedi i permessi nel contesto e spiega il motivo, notifiche push (FCM/APNs) con canali e gestione del token, deep link, accessibilità e dark mode, batteria e dati.
**Rilascio**: firma con chiave **stabile** (conservala: senza di lei gli aggiornamenti non si installano), versionCode crescente, AAB per il Play Store, test su dispositivi reali e su schermi diversi, crash reporting.
**Output**: scelta motivata, struttura dell'app, codice dell'esempio e checklist di rilascio.
@@@
name: nosql-e-cache
title: NoSQL, Redis e strategie di cache
domain: programmazione
description: Sceglie e usa database non relazionali (Redis, MongoDB) e progetta cache con invalidazione corretta.
triggers: redis, mongodb, nosql, cache, caching, ttl, invalidazione della cache, key value, documento json, memcached, cache stampede, dynamodb, elasticsearch, code con redis

**Quando**: relazionale (SQL) di default; documenti (MongoDB) per dati con forma variabile e letti insieme; chiave-valore (Redis) per cache, sessioni, contatori, code leggere, rate limit, classifiche; ricerca testuale (Elasticsearch/OpenSearch) per ricerca avanzata.
**Cache**: pattern **cache-aside** (leggi cache → se manca leggi il DB e riempi), TTL sempre impostato, chiavi con versione/namespace, invalidazione alla scrittura (o TTL breve se tollerabile), protezione da **stampede** (lock/richiesta unica per chiave, TTL con jitter), misura il tasso di hit. «Le due cose difficili: nomi e invalidazione della cache».
**MongoDB**: modella in base alle query (incorpora ciò che si legge insieme, referenzia il resto), indici, niente documenti illimitati.
**Redis**: limite di memoria e politica di eviction (`allkeys-lru`), persistenza consapevole (RDB/AOF), non usarlo come unica fonte di verità senza strategia.
**Output**: schema chiavi/documenti, politica TTL e invalidazione, esempio di codice e rischi.
@@@
name: ai-engineering-llm
title: Costruire applicazioni con LLM
domain: programmazione
description: Progetta app con modelli linguistici: prompt, output strutturato, tool calling, RAG (chunking, embedding, ricerca ibrida), valutazione, costi e sicurezza.
triggers: llm, rag, embedding, embeddings, chatbot, prompt injection, tool calling, function calling, fine tuning, agente ai, vector database, langchain, openai api, anthropic api, valutazione llm, allucinazioni, contesto del modello

**Metodo**: 1) parti dal compito e da **come lo valuti** (un piccolo set di casi con risposta attesa: serve prima di toccare i prompt); 2) prompt chiaro (ruolo, contesto, compito, formato, esempi), output **strutturato** (JSON con schema e validazione) e tentativi di riparazione; 3) **tool calling**: pochi strumenti, descrizioni nette, argomenti validati, esecuzione sul lato server con permessi minimi; 4) **RAG**: chunk di 200-500 parole con sovrapposizione e titolo, embedding multilingue, **ricerca ibrida** (vettori + parole chiave, fusione RRF), filtri sui metadati, eventuale reranking, cita le fonti, contesto breve e pertinente; 5) costi/latenza: modelli piccoli dove bastano, cache, streaming, limiti di token; 6) sicurezza: i contenuti recuperati sono **dati, non istruzioni** (prompt injection), niente segreti nel prompt, filtra i dati personali, conferma umana per azioni irreversibili.
**Output**: architettura, prompt di esempio, schema dei dati, piano di valutazione con metriche e i rischi da coprire.
@@@
name: automazione-e-scraping
title: Automazione, API e scraping responsabile
domain: programmazione
description: Automatizza attività ripetitive con script, API, cron e browser headless; scraping nel rispetto di regole e limiti.
triggers: automazione, automatizzare, scraping, web scraping, playwright, selenium, beautifulsoup, cron job, bot, script che scarica, integrazione api, zapier, n8n, webhook, richieste http, requests python

**Metodo**: 1) controlla se esiste un'**API ufficiale** o un export: è sempre meglio dello scraping; 2) se serve scraping: leggi ToS e `robots.txt`, identificati con uno User-Agent, **rate limit** e pause, cache, niente dati personali di terzi senza base giuridica; 3) strumenti: `requests/httpx` + parser (BeautifulSoup/lxml) per pagine statiche, Playwright per siti dinamici (cerca prima la chiamata JSON dietro la pagina); 4) robustezza: timeout, retry con backoff, **idempotenza** (rilanciare non duplica), log, gestione dei cambi di layout; 5) pianificazione con cron/GitHub Actions/systemd timer, segreti in variabili d'ambiente; 6) avvisi (email/Telegram) in caso di errore.
**Strumenti no-code**: n8n/Zapier/Make per flussi semplici tra servizi.
**Output**: script completo con gestione errori e istruzioni di pianificazione; avverti dei limiti legali ed etici quando rilevanti. Niente aggiramento di protezioni o paywall.
@@@
name: documentazione-tecnica
title: Documentazione tecnica
domain: programmazione
description: Scrive README, documentazione di API e progetti, docstring, ADR, changelog e guide che le persone leggono davvero.
triggers: documentazione, readme, scrivi la documentazione, docstring, changelog, guida tecnica, documentare il codice, adr, manuale, commenti nel codice, documentazione api, tutorial tecnico, wiki del progetto

**Metodo**: scrivi per un lettore preciso (chi è, cosa sa, cosa vuole fare). Struttura **Diátaxis**: tutorial (imparare facendo), guide pratiche (come fare X), riferimento (completo e asciutto), spiegazioni (perché).
**README**: cos'è e a cosa serve in 2 righe → installazione e avvio in 3 comandi che funzionano → esempio minimo → configurazione → come contribuire/testare → licenza. Prova i comandi su una macchina pulita.
**Codice**: commenti e docstring per intenzioni, vincoli e invarianti (non per ripetere il codice); esempi eseguibili; changelog per versione (Aggiunto/Modificato/Corretto, formato «Keep a Changelog»); **ADR** per le decisioni importanti.
**Stile**: frasi brevi, imperativo per i passi, titoli descrittivi, blocchi di codice con il linguaggio, niente «semplicemente».
**Output**: il documento pronto, con elenco di ciò che va verificato dall'autore (comandi, versioni, link).
@@@
name: refactoring-e-codice-legacy
title: Refactoring e codice legacy
domain: programmazione
description: Mette le mani su codice vecchio o confuso in sicurezza: test di caratterizzazione, passi piccoli, sostituzione graduale e aggiornamenti di dipendenze.
triggers: codice legacy, refactoring, riscrivere da zero, ereditato un progetto, aggiornare le dipendenze, migrazione, upgrade di versione, debito tecnico, spaghetti code, ristrutturare il codice, monolite da spezzare, strangler

**Metodo**: 1) **non riscrivere da zero** (quasi mai conviene); 2) capisci cosa fa: esegui, leggi i punti di ingresso, traccia un flusso reale; 3) metti una **rete di sicurezza**: test di caratterizzazione (fissano il comportamento attuale, anche i difetti), test end-to-end sui percorsi critici; 4) refactoring a **passi minuscoli** con test verdi a ogni passo e commit frequenti (rinomina, estrai funzione, sposta, elimina codice morto); 5) rompi le dipendenze con «giunture» (interfacce, adapter) per rendere testabile ciò che è intrecciato; 6) sostituzione graduale (**strangler fig**): il nuovo codice affianca il vecchio dietro lo stesso confine, si sposta il traffico a pezzi; 7) aggiornamenti: una dipendenza alla volta, leggi le note di rilascio, CI verde, rollback pronto.
**Output**: piano a tappe con rischio e valore di ciascuna, primi 3 passi concreti, e cosa NON toccare ora. Mai mischiare refactoring e nuove funzioni nello stesso commit.
@@@
name: concorrenza-e-sistemi-distribuiti
title: Concorrenza e sistemi distribuiti
domain: programmazione
description: Affronta race condition, lock, code, idempotenza, consistenza e guasti parziali nei sistemi concorrenti e distribuiti.
triggers: concorrenza, race condition, deadlock, lock, mutex, thread, sistemi distribuiti, consistenza, idempotenza, coda di messaggi, kafka, rabbitmq, retry, transazioni distribuite, cap theorem, eventual consistency, timeout e retry

**Principi**: la rete fallisce, i messaggi si perdono, si duplicano e arrivano fuori ordine; i nodi si fermano a metà. Progetta per questo.
**Concorrenza locale**: individua lo stato condiviso e proteggilo o eliminalo (immutabilità, passaggio di messaggi); lock con ordine fisso (evita deadlock) e sezioni critiche brevi; operazioni atomiche; verifica con strumenti (`-race`, ThreadSanitizer).
**Distribuiti**: timeout su ogni chiamata, **retry con backoff e jitter**, **idempotenza** (chiave per richiesta: ripetere non duplica), code per assorbire i picchi e disaccoppiare, «almeno una volta» + deduplicazione, **outbox** per pubblicare eventi insieme alla transazione, **saga** invece di transazioni distribuite, circuit breaker; consistenza: scegli per ogni dato tra forte ed eventuale (CAP/PACELC).
**Osservabilità**: id di correlazione, tracing, metriche.
**Output**: scenario di guasto → rischio → rimedio, con diagramma testuale del flusso e dei punti di ripetizione.
@@@
name: cloud-e-infrastruttura
title: Cloud, serverless e infrastruttura come codice
domain: programmazione
description: Sceglie e configura servizi cloud (AWS, GCP, Azure, Render, Vercel): serverless, container, Terraform, costi, sicurezza e piani gratuiti.
triggers: cloud, aws, gcp, azure, serverless, lambda, terraform, infrastruttura come codice, vercel, render, cloudflare, kubernetes, costi del cloud, iam, bucket s3, piano gratuito, hosting, deploy su cloud

**Metodo**: 1) requisiti (carico, latenza, dati, conformità, budget); 2) parti dal servizio **più gestito** che basta (PaaS tipo Render/Vercel/Fly → container gestiti → serverless → VM → Kubernetes solo se serve); 3) dati e backup prima del resto; 4) **IaC** (Terraform/Pulumi) per ambienti ripetibili e rivisti in PR; 5) sicurezza: **privilegi minimi** (IAM), segreti in un gestore, rete privata dove possibile, cifratura, MFA su ogni account, log di audit; 6) **costi**: etichette per progetto, budget e allarmi, spegni ciò che non usi, attenzione a traffico in uscita e a servizi «sempre accesi»; 7) affidabilità: più zone, health check, deploy graduali, rollback.
**Piani gratuiti**: leggi i limiti (sospensione, memoria, ore, banda) e il piano B.
**Output**: architettura proposta con alternative, stima costi indicativa (verifica i listini attuali), checklist di sicurezza e primi passi.
@@@
name: machine-learning-pratico
title: Machine learning e data science pratici
domain: programmazione
description: Costruisce modelli di machine learning in modo corretto: dati, baseline, valutazione, overfitting, scikit-learn, reti neurali e messa in produzione.
triggers: machine learning, apprendimento automatico, scikit-learn, sklearn, rete neurale, deep learning, pytorch, tensorflow, overfitting, dataset di addestramento, classificazione, regressione, feature, train test split, modello predittivo, kaggle

**Metodo**: 1) problema e metrica di successo legata al business (non solo accuracy: precision/recall, F1, AUC, MAE…); 2) dati: qualità, bilanciamento, **perdita di informazioni dal futuro (data leakage)**, divisione train/validation/test (a tempo se i dati sono temporali); 3) **baseline semplice** (media, regressione logistica) da battere; 4) feature engineering, poi modelli ad alberi (gradient boosting) per dati tabellari, deep learning per immagini/testo/audio; 5) valutazione con cross-validation, analisi degli errori per segmento; 6) controlla overfitting (curve, regolarizzazione, early stopping); 7) riproducibilità (seed, versioni, pipeline) e **monitoraggio** in produzione (drift).
**Etica**: bias nei dati, privacy, spiegabilità.
**Output**: pipeline in Python (`pandas` + `scikit-learn` o PyTorch), metriche con interpretazione, limiti del modello e prossimi esperimenti.
