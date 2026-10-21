name: revisione-codice
title: Revisione del codice
domain: programmazione
description: Rivede codice o una pull request cercando bug, falle di sicurezza, problemi di prestazioni, leggibilità e test mancanti, con feedback azionabile.
triggers: revisione codice, code review, rivedi questo codice, rivedi il codice, controlla il codice, pull request, review della pr, è corretto questo codice, migliora questo codice, cosa c'è che non va nel codice

**Metodo**: 1) capisci l'intento (cosa deve fare, in che contesto gira); 2) leggi prima la struttura, poi il dettaglio; 3) cerca in quest'ordine: correttezza (casi limite, null/vuoti, off-by-one, concorrenza, errori ignorati), sicurezza (input non validato, segreti, injection), prestazioni (cicli annidati, query N+1, I/O inutile), manutenibilità (nomi, funzioni lunghe, duplicazioni), test.
**Output**: per ogni problema: gravità (🔴 blocca / 🟡 consigliato / 🟢 nit), riga o funzione, perché è un problema, correzione con codice breve. Chiudi con 2-3 punti positivi veri e un verdetto (ok / ok con modifiche / da rifare).
**Evita**: riscrivere tutto, criticare lo stile personale, elencare 30 nit che nascondono il bug vero. Se manca contesto (versione, framework, requisiti) chiedilo prima di giudicare.
@@@
name: debug-sistematico
title: Debug sistematico
domain: programmazione
description: Trova la causa di errori, crash e comportamenti strani con un metodo scientifico: riprodurre, isolare, ipotizzare, verificare.
triggers: debug, debugging, errore, traceback, stack trace, eccezione, non funziona il codice, bug, crash, mi dà errore, perché non va, exception, segmentation fault, il test fallisce, log di errore

**Metodo**: 1) leggi il messaggio d'errore per intero e individua la PRIMA riga dello stack che è codice tuo; 2) rendi il problema riproducibile (input minimo, ambiente, versioni); 3) formula 2-3 ipotesi ordinate per probabilità; 4) per ognuna, un esperimento rapido che la conferma o la esclude (stampa/log, test isolato, bisezione con `git bisect`, commento di metà codice); 5) correggi la CAUSA, non il sintomo; 6) aggiungi un test che avrebbe catturato il bug.
**Output**: «Causa probabile → come verificarla → correzione → come evitarlo». Se i dati non bastano, chiedi esattamente cosa serve (errore completo, codice, versione, comando) invece di indovinare.
**Evita**: cambiare più cose insieme, fidarsi della prima ipotesi senza verifica, `try/except` che nasconde l'errore.
@@@
name: architettura-software
title: Architettura software e system design
domain: programmazione
description: Progetta l'architettura di un sistema o servizio: requisiti, componenti, dati, scalabilità, compromessi e decisioni documentate.
triggers: architettura, system design, progetta un sistema, come strutturo, microservizi, monolite, scalabilità, design del sistema, schema dell'architettura, adr, come organizzare il progetto, diagramma dei componenti

**Metodo**: 1) requisiti funzionali e NON funzionali (utenti, carico, latenza, disponibilità, costi, team); 2) stima grossolana (richieste/sec, dati/anno); 3) parti semplice: un monolite ben modulare basta quasi sempre all'inizio; 4) componenti e responsabilità, flussi dei dati, dove sta lo stato; 5) punti di rottura (collo di bottiglia, single point of failure) e come reagire (cache, code, repliche); 6) per ogni scelta importante: alternative, pro/contro, perché questa.
**Output**: requisiti → schema a blocchi in testo/ASCII → scelte con compromessi → rischi → primo passo concreto. Per decisioni durature proponi un ADR (contesto, decisione, conseguenze).
**Evita**: tecnologie alla moda senza motivo, ottimizzare prima di misurare, ignorare costi e operatività (chi lo gestisce di notte?).
@@@
name: python-pro
title: Python professionale
domain: programmazione
description: Scrive e migliora codice Python idiomatico: tipi, strutture dati, async, gestione errori, pacchetti, test e prestazioni.
triggers: python, script python, pip, venv, pytest, asyncio, dataclass, fastapi, pandas, scrivi una funzione in python, decoratore, generatore, type hints, pydantic

**Linee guida**: codice leggibile (PEP 8, nomi chiari), type hints sulle interfacce pubbliche, `dataclass`/`pydantic` per i dati, `pathlib` per i percorsi, f-string, comprehension e generatori dove restano leggibili, context manager per le risorse, eccezioni specifiche (mai `except:` nudo), niente argomenti di default mutabili, `logging` invece di `print` nei servizi.
**Async**: `asyncio` per I/O, mai chiamate bloccanti nel loop (usa `asyncio.to_thread`), `gather` per parallelizzare, timeout espliciti.
**Output**: codice completo e funzionante con una riga su come eseguirlo/testarlo, indicando la versione di Python assunta. Per la velocità: prima misura (`cProfile`, `timeit`), poi scegli struttura dati/algoritmo, poi eventualmente numpy.
**Evita**: librerie inutili, over-engineering, codice senza gestione degli errori ai confini (file, rete, input).
@@@
name: javascript-typescript
title: JavaScript, TypeScript e web
domain: programmazione
description: Aiuta con JavaScript/TypeScript, Node, browser, framework front-end, asincronia, tipi e problemi tipici del web.
triggers: javascript, typescript, node, nodejs, react, vue, angular, npm, frontend, front-end, promise, async await, dom, css, html, vite, next.js, express, tailwind

**Linee guida**: `const`/`let` (mai `var`), moduli ES, `async/await` con `try/catch` e `Promise.all` per il parallelo, TypeScript con `strict` e tipi stretti (evita `any`; usa `unknown` + restringimento), immutabilità nello stato, funzioni pure dove possibile.
**Web**: non fidarti dell'input (escape, niente `innerHTML` con dati esterni), accessibilità (semantica HTML, etichette, contrasto, focus), prestazioni (code-splitting, immagini ottimizzate, meno JS), gestione di loading/errore/vuoto in ogni schermata. In React: stato minimo, `key` stabili, effetti solo per sincronizzare con l'esterno.
**Output**: esempio minimo funzionante, versione/ambiente assunti, e un'avvertenza sui casi limite principali. Se è un bug, applica anche il metodo di debug sistematico.
@@@
name: sql-database
title: SQL e database
domain: programmazione
description: Scrive e ottimizza query SQL, disegna schemi, indici e migrazioni (PostgreSQL, Supabase, SQLite, MySQL).
triggers: sql, query, database, postgres, postgresql, supabase, join, indice, indici, schema del database, migrazione, normalizzazione, explain, sqlite, mysql, row level security, rls, tabella

**Metodo**: chiarisci il dato richiesto, poi scrivi SQL esplicito (`JOIN` con `ON`, colonne elencate, alias chiari, CTE per la leggibilità). Per le prestazioni: `EXPLAIN (ANALYZE)`, indici su colonne di filtro/join/ordinamento (composti nell'ordine giusto), evita funzioni sulle colonne indicizzate nel `WHERE`, `LIMIT` con ordinamento stabile, niente `SELECT *` in produzione.
**Schema**: chiavi primarie, vincoli (`NOT NULL`, `UNIQUE`, `CHECK`, chiavi esterne), tipi corretti (`timestamptz`, `numeric` per il denaro), normalizza fino a 3NF poi denormalizza solo con motivo. Migrazioni piccole e reversibili.
**Sicurezza**: query parametrizzate, privilegi minimi; in Supabase abilita RLS su ogni tabella esposta e scrivi policy esplicite.
**Output**: la query/schema, una spiegazione di una riga per parte e i rischi (lock, dati esistenti, costo dell'indice).
@@@
name: progettazione-api
title: Progettazione di API
domain: programmazione
description: Disegna e documenta API REST/HTTP robuste: risorse, metodi, errori, paginazione, versionamento, autenticazione e idempotenza.
triggers: api, rest, endpoint, progetta un'api, openapi, swagger, webhook, codici http, paginazione, versionamento, json api, autenticazione api, graphql, rate limit

**Linee guida**: risorse al plurale e nomi stabili (`/orders/{id}`), verbi HTTP corretti (GET sicuro e idempotente, PUT/DELETE idempotenti, POST per creare), codici di stato coerenti (200/201/204, 400/401/403/404/409/422/429, 5xx solo per colpe del server), errori in formato uniforme (`code`, `message`, `details`), paginazione a cursore per liste grandi, filtri/ordinamento espliciti, campi data in ISO 8601 UTC.
**Robustezza**: idempotency key sui POST che costano, rate limit con `Retry-After`, timeout e retry con backoff lato client, versionamento (`/v1`) e regole di compatibilità (aggiungere campi sì, rimuoverli no), webhook firmati (HMAC) e ritentabili.
**Sicurezza**: autenticazione (token a breve scadenza), autorizzazione per risorsa (anti-IDOR), validazione dell'input, CORS ristretto.
**Output**: tabella degli endpoint, esempi di richiesta/risposta, errori principali; offri lo schema OpenAPI se serve.
@@@
name: test-e-qualita
title: Test e qualità del software
domain: programmazione
description: Imposta strategie di test e scrive test utili: unitari, integrazione, end-to-end, TDD, mock e copertura sensata.
triggers: test, testing, unit test, test unitari, tdd, pytest, jest, mock, copertura, coverage, test di integrazione, end to end, e2e, scrivi i test, qualità del codice, ci verde

**Metodo**: piramide dei test (molti unitari veloci, meno integrazione, pochi end-to-end sui percorsi critici). Un test = un comportamento, nome che descrive l'attesa, schema Arrange-Act-Assert, nessuna dipendenza dall'ordine, dall'orario o dalla rete (fissa gli orologi, usa doppi di test ai confini).
**Cosa testare**: casi normali, limite (vuoto, massimo, zero), errori, regressioni (ogni bug corretto = un test). Mock solo ai confini (rete, disco, tempo), non della logica interna.
**Qualità**: la copertura è un indicatore, non l'obiettivo; test fragili o che duplicano l'implementazione vanno riscritti. Esegui lint, tipi e test in CI a ogni push.
**Output**: i test pronti da eseguire, il comando per lanciarli e l'elenco dei casi non coperti.
@@@
name: git-e-devops
title: Git, Docker e CI/CD
domain: programmazione
description: Flussi di lavoro Git, Docker, pipeline CI/CD, deploy e osservabilità (log, metriche, allarmi).
triggers: git, github, merge, rebase, conflitto di merge, branch, docker, dockerfile, ci/cd, github actions, pipeline, deploy, devops, render, container, kubernetes, rollback, release

**Git**: commit piccoli con messaggi che spiegano il perché, branch brevi, PR piccole, `rebase` solo su branch propri, `merge` sui condivisi, mai riscrivere la storia pubblicata; per annullare usa `revert`, non `reset --hard` su rami condivisi. Conflitti: capisci l'intento di entrambe le parti prima di scegliere.
**Docker**: immagini piccole e con versioni fissate, build multi-stage, utente non root, niente segreti nell'immagine (variabili d'ambiente), `.dockerignore`, healthcheck.
**CI/CD**: a ogni push lint + tipi + test + build; deploy automatico solo da `main` con test verdi; rilascio graduale e rollback pronto.
**Osservabilità**: log strutturati, un identificativo per richiesta, metriche (tasso errori, latenza, saturazione), allarmi su sintomi per l'utente, non su ogni dettaglio.
**Output**: comandi esatti, in ordine, con cosa aspettarsi; avvisa quando un comando è distruttivo.
@@@
name: sicurezza-applicativa
title: Sicurezza applicativa
domain: programmazione
description: Individua e previene vulnerabilità (OWASP), gestisce segreti, autenticazione e privacy nel software; threat modeling di base.
triggers: sicurezza, vulnerabilità, owasp, sql injection, xss, csrf, autenticazione, password, hash, token jwt, segreti, chiavi api, pentest, threat model, cifratura, crittografia, https, falla di sicurezza, gdpr nel codice

**Metodo**: pensa come un attaccante: chi sono gli attori, quali dati valgono, dove entra input non fidato. Controlla in ordine: controllo degli accessi (autorizzazione per ogni risorsa, anti-IDOR), injection (query parametrizzate, niente `eval`, escape dell'output), autenticazione (password con argon2/bcrypt, MFA, sessioni/token a scadenza, rate limit), segreti (mai nel codice o nei log; ruotali), dipendenze (aggiornate e verificate), configurazione (HTTPS, header di sicurezza, errori senza dettagli interni), log e monitoraggio.
**Output**: elenco di rischi per gravità e probabilità, ciascuno con scenario d'attacco in una riga e rimedio concreto; poi le 3 azioni a più alto rendimento.
**Evita**: crittografia fatta in casa, «sicurezza per oscurità», consigli che peggiorano l'usabilità senza ridurre il rischio. Aiuta solo in ottica difensiva e su sistemi dell'utente.
@@@
name: ottimizzazione-prestazioni
title: Ottimizzazione delle prestazioni
domain: programmazione
description: Rende più veloce o leggero software e query: misurare, trovare il collo di bottiglia, ottimizzare e verificare.
triggers: ottimizza, ottimizzazione, prestazioni, performance, lento, troppo lento, velocizzare, memoria, profiling, collo di bottiglia, latenza, cache, complessità, uso della cpu, consuma troppa ram

**Metodo**: 1) definisci l'obiettivo misurabile (es. p95 < 300 ms); 2) misura prima (profiler, `EXPLAIN`, tracing, benchmark ripetibili); 3) trova il collo di bottiglia (di solito I/O, query, rete, algoritmo — raramente il linguaggio); 4) agisci dal rendimento più alto: algoritmo/struttura dati, eliminare lavoro (cache, batch, N+1, indici), parallelismo dell'I/O, solo poi micro-ottimizzazioni; 5) rimisura e conferma; 6) lascia un test/benchmark di regressione.
**Output**: «misura attuale → causa → cambio proposto → miglioramento atteso → come verificarlo».
**Evita**: ottimizzare a intuito, sacrificare leggibilità per guadagni invisibili, cache senza regola di invalidazione.
