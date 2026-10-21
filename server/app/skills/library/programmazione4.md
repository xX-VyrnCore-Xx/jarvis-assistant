name: data-science-con-pandas
title: Data science con pandas e Jupyter
domain: programmazione
description: Analizza dati tabellari con pandas/NumPy: pulizia, trasformazioni, aggregazioni, grafici e notebook riproducibili, evitando i trabocchetti più comuni.
triggers: pandas, numpy, dataframe, jupyter, notebook, pulizia dei dati, csv in python, groupby, merge di tabelle, analisi esplorativa, matplotlib, seaborn, valori mancanti, pivot table, polars

**Metodo**: 1) carica con tipi espliciti (`dtype`, `parse_dates`) e guarda `info()`, `describe()`, `head()`; 2) **pulizia**: duplicati, mancanti (scelta consapevole: eliminare, imputare, flag), outlier, categorie incoerenti, spazi e maiuscole; 3) trasformazioni **vettoriali** (niente `iterrows`), `groupby`/`agg`, `merge` con controllo `validate=` e righe perse, `pivot`, finestre mobili; 4) grafici chiari (titolo, assi, unità); 5) riproducibilità: seed, dati grezzi mai modificati, funzioni piccole, notebook che girano da cima a fondo; 6) grandi dati: Polars/DuckDB, `parquet`, tipi `category`.
**Trappole**: `SettingWithCopyWarning`, join che moltiplicano le righe, date senza fuso, float per denaro (usa Decimal/interi). **Output**: codice breve e commentato, controlli sui risultati, domanda di business risposta in una frase.
@@@
name: deep-learning-e-pytorch
title: Deep learning e PyTorch
domain: programmazione
description: Costruisce e addestra reti neurali con PyTorch: dati, modello, ciclo di training, valutazione, overfitting e uso efficiente della GPU.
triggers: pytorch, deep learning, rete neurale, training, gpu, cuda, overfitting, tensori, transformer, loss, ottimizzatore, backpropagation, dataloader, transfer learning, hugging face transformers

**Metodo**: 1) problema e metrica (classificazione, regressione, generazione) e una **baseline** semplice; 2) dati: split train/val/test senza fughe di informazione, normalizzazione, augmentation; 3) modello: parti da un preallenato (**transfer learning**) invece che da zero; 4) ciclo: `model.train()`, loss, `optimizer.zero_grad()`, `backward()`, `step()`, scheduler; `eval()` + `no_grad()` per validare; 5) stabilità: learning rate ragionevole, gradient clipping, mixed precision (`autocast`), seed; 6) diagnosi: loss che non scende (lr, dati, bug), overfitting (regolarizzazione, early stopping, più dati); 7) salva checkpoint e configurazione.
**Output**: scheletro di training completo e minimo, cosa monitorare (curve loss/val), prossimo esperimento. Su GPU gratuite (Colab T4) usa batch piccoli, 4/8 bit e accumulo del gradiente.
@@@
name: fine-tuning-lora-e-deploy-modelli
title: Fine-tuning LoRA e deploy di modelli
domain: programmazione
description: Adatta un modello aperto con LoRA/QLoRA, prepara il dataset, valuta, quantizza e serve il modello con costi e limiti realistici.
triggers: lora, qlora, fine tuning, fine-tuning, addestrare un modello, adattatore, peft, quantizzazione, gguf, vllm, ollama, servire un modello, dataset di addestramento, instruction tuning, distillazione

**Metodo**: 1) **serve davvero?** prima prompt migliori, RAG, esempi in contesto: il fine-tuning insegna stile e formato più che fatti nuovi; 2) **dataset**: qualità > quantità (centinaia/migliaia di esempi puliti), formato chat coerente, nessun dato sensibile (maschera, cifra), dedup, split di validazione; 3) modello base aperto piccolo (3-8B) e **QLoRA** 4 bit: rango 8-16, alpha 2×rango, moduli di attenzione e MLP, 1-3 epoche, lr ~1e-4; 4) valuta su domande tenute da parte e confronta col modello base (a mano + metrica); 5) unisci o carica l'adattatore, **quantizza** (GGUF/AWQ) per servire con llama.cpp/Ollama/vLLM; 6) costi: addestrare su Colab T4 gratis; servire richiede GPU o CPU con quantizzazione.
**Output**: piano con dataset, iperparametri, valutazione e dove servirlo. Rischi: memorizzazione di dati privati, regressioni; versiona dataset e adattatori.
@@@
name: rag-e-agenti-llm
title: RAG, agenti e tool calling
domain: programmazione
description: Progetta applicazioni con LLM: recupero (RAG), embedding, chunking, agenti con strumenti, MCP, valutazione e sicurezza dalle iniezioni di prompt.
triggers: rag, agente ai, agenti llm, tool calling, function calling, mcp, embedding, vector database, chunking, retrieval, prompt injection, langchain, llamaindex, workflow con llm, memoria dell'agente

**Metodo**: 1) parti dal flusso più semplice (una chiamata + contesto) e aggiungi complessità solo se serve; 2) **RAG**: chunk di 200-500 parole con sovrapposizione, metadati, ricerca ibrida (parole + vettori), **reranking**, citazioni; 3) agenti: pochi strumenti con descrizioni precise e parametri validati, limite di passi, timeout, conferma umana per azioni irreversibili; 4) **MCP** per esporre strumenti in modo standard; 5) valutazione: set di domande con risposte attese, metriche di recupero (recall@k) e di risposta, log delle traiettorie; 6) **sicurezza**: il testo recuperato è dato non istruzioni (prompt injection), privilegi minimi, niente segreti nel prompt, maschera dati sensibili.
**Output**: diagramma del flusso, schema degli strumenti, piano di valutazione e costi (token, latenza). Cache e modelli piccoli per i passi semplici.
@@@
name: docker-e-container
title: Docker e container
domain: programmazione
description: Costruisce immagini leggere e sicure, usa compose, volumi e reti, e risolve i problemi tipici di build, avvio e rete dei container.
triggers: docker, dockerfile, container, docker compose, immagine docker, volume, build multi stage, registry, containerizzare, podman, non parte il container, layer cache, healthcheck

**Metodo**: 1) immagine base piccola e ufficiale (slim/alpine/distroless), versione fissata (digest se serve); 2) **multi-stage build**: compila in uno stadio, copia solo l'artefatto; 3) ordina i layer per la cache: dipendenze prima, codice dopo; `.dockerignore`; 4) esegui come **utente non root**, filesystem in sola lettura dove possibile, niente segreti nell'immagine (variabili d'ambiente o secret a runtime); 5) un processo per container, log su stdout, `HEALTHCHECK`; 6) compose: servizi, reti, volumi, `depends_on` con condizioni; dati persistenti in volumi; 7) debug: `docker logs`, `exec`, `inspect`, controllare porte e variabili.
**Output**: Dockerfile commentato, compose minimo, comandi di verifica. Scansione vulnerabilità (Trivy) e aggiornamenti regolari.
@@@
name: ci-cd-github-actions
title: CI/CD con GitHub Actions
domain: programmazione
description: Automatizza test, build e rilascio con pipeline affidabili, veloci e sicure: cache, matrici, segreti, ambienti e rilasci con versioni.
triggers: github actions, ci/cd, pipeline, workflow yaml, integrazione continua, deploy automatico, rilascio automatico, ci rossa, matrix build, cache delle dipendenze, release automatica, gitlab ci, jenkins

**Metodo**: 1) pipeline minima: checkout → installa (con **cache**) → lint → test → build; 2) job paralleli e `needs` per l'ordine; **matrice** per versioni/sistemi; 3) trigger precisi (`pull_request`, `push` su main, `workflow_dispatch`, tag); 4) **sicurezza**: permessi minimi (`permissions:`), azioni fissate a una versione/SHA, segreti solo dove servono, mai stampati; attenzione a `pull_request_target` e a input non fidati; 5) ambienti con approvazione per la produzione; 6) rilasci: versione semantica, changelog, artefatti con checksum; 7) CI lenta o instabile: cache, test più veloci, isolamento, **mai disattivare un test** per far passare la CI.
**Output**: workflow YAML commentato, come leggere i log degli errori, come riprodurre in locale.
@@@
name: infrastructure-as-code-terraform
title: Infrastructure as Code e Terraform
domain: programmazione
description: Descrive l'infrastruttura in codice: Terraform, stato, moduli, ambienti, piani rivisti e rollback, con attenzione a costi e sicurezza.
triggers: terraform, infrastructure as code, iac, opentofu, ansible, pulumi, cloudformation, stato terraform, modulo terraform, provisioning, infrastruttura come codice, tfstate

**Metodo**: 1) tutto in codice versionato; 2) **stato remoto** con blocco (mai in git, contiene segreti); 3) moduli piccoli e riusabili, variabili tipizzate, output chiari; 4) ambienti separati (dev/prod) con account/progetti distinti; 5) `plan` rivisto prima di ogni `apply`, in CI; 6) segreti dal gestore (non nel codice); 7) tag per costi e proprietà, budget e allarmi; 8) drift: rilevalo e correggi nel codice; `import` per risorse esistenti; 9) distruzione: protezioni (`prevent_destroy`) sulle risorse critiche.
**Ansible**: configurazione idempotente dei server. **Output**: struttura di cartelle, esempio di modulo, flusso plan/apply e come tornare indietro.
@@@
name: osservabilita-log-metriche-tracce
title: Osservabilità: log, metriche e tracce
domain: programmazione
description: Rende un sistema comprensibile in produzione: log strutturati, metriche, tracce, allarmi utili e diagnosi guidata dai dati.
triggers: osservabilità, logging, log strutturati, metriche, prometheus, grafana, opentelemetry, tracing, allarmi, monitoraggio, sentry, dashboard di monitoraggio, slo, sli, correlation id

**Metodo**: 1) **tre pilastri**: log (eventi), metriche (numeri nel tempo), tracce (percorso di una richiesta); 2) log **JSON strutturati** con livello, timestamp, id di correlazione, mai dati sensibili; 3) metriche RED (rate, errors, duration) per i servizi e USE (utilizzo, saturazione, errori) per le risorse; 4) **SLO** (es. 99,5% richieste sotto 500 ms) e allarmi sul rischio di violarli, non su ogni picco; 5) alert azionabili con runbook, niente rumore; 6) OpenTelemetry per strumentare in modo neutrale; 7) diagnosi: dal sintomo (dashboard) alla traccia lenta al log preciso.
**Output**: cosa loggare e misurare, 3-5 allarmi con soglia, dashboard essenziale. Una riga di battito periodico nei log (stato, memoria, cicli) aiuta a vedere subito i blocchi.
@@@
name: code-di-messaggi-e-microservizi
title: Code di messaggi e microservizi
domain: programmazione
description: Progetta comunicazione asincrona e servizi separati: code, eventi, retry, idempotenza e quando NON usare i microservizi.
triggers: microservizi, kafka, rabbitmq, coda di messaggi, redis queue, celery, event bus, idempotenza, saga, outbox pattern, broker, consumer, producer, pub sub, dead letter queue

**Metodo**: 1) **monolite modulare prima**: i microservizi aggiungono costi (rete, deploy, dati distribuiti) giustificati da team e scala; 2) code per lavoro in background, picchi e disaccoppiamento; 3) consegna **almeno una volta** → consumatori **idempotenti** (chiave di deduplicazione); 4) retry con backoff esponenziale e jitter, **dead letter queue** per i messaggi velenosi; 5) ordine: partizioni per chiave solo dove serve; 6) consistenza tra servizi: **outbox pattern**, saga con compensazioni, niente transazioni distribuite; 7) contratti degli eventi versionati; 8) osserva lunghezza coda, età del messaggio più vecchio, errori.
**Output**: diagramma produttore→broker→consumatori, schema del messaggio, politica di retry/errore, scelta dello strumento (Redis/RQ semplice, RabbitMQ, Kafka per stream).
@@@
name: framework-frontend-vue-svelte-next
title: Vue, Svelte, Angular e Next.js
domain: programmazione
description: Sceglie e usa framework frontend moderni: componenti, stato, routing, rendering lato server, form e prestazioni, con confronti onesti.
triggers: vue, svelte, angular, nextjs, next.js, nuxt, sveltekit, astro, ssr, rendering lato server, framework frontend, componenti, stato globale, pinia, redux, solidjs, hydration

**Metodo**: 1) scegli per il **progetto e il team**, non per moda: React (ecosistema), Vue (curva dolce), Svelte (leggero), Angular (strutturato/enterprise), Astro (siti di contenuto); 2) rendering: **SSG** (statico), **SSR** (per richiesta), SPA, islands; SEO e prima visualizzazione chiedono SSR/SSG; 3) stato: locale per default, globale solo se serve (Pinia/Zustand), dati remoti con cache (TanStack Query); 4) struttura per funzionalità, componenti piccoli e tipizzati (TypeScript); 5) form e validazione (zod), accessibilità, gestione errori e caricamenti; 6) prestazioni: code splitting, immagini ottimizzate, evita idratazione inutile.
**Output**: confronto breve per il caso d'uso, struttura del progetto, esempio di componente e routing, errori tipici da evitare.
@@@
name: webassembly-e-codice-nativo-nel-browser
title: WebAssembly e prestazioni nel browser
domain: programmazione
description: Usa WebAssembly e Web Worker per calcoli pesanti nel browser: quando conviene, Rust/C++ verso wasm, interoperabilità e limiti.
triggers: webassembly, wasm, web worker, wasm-bindgen, emscripten, calcolo nel browser, rust wasm, thread nel browser, sharedarraybuffer, offscreen canvas, prestazioni javascript, webgpu

**Metodo**: 1) **misura prima**: profila; spesso il collo di bottiglia è DOM, rete o algoritmo, non JS; 2) **Web Worker** per spostare lavoro pesante fuori dal thread della UI (comunicazione per messaggi, oggetti trasferibili); 3) **WASM** per calcolo intenso (codec, crittografia, parsing, giochi, ML): Rust con `wasm-bindgen`/`wasm-pack` o C/C++ con Emscripten; 4) costo del passaggio JS↔WASM: pochi scambi grandi, non tanti piccoli; 5) dimensioni del binario (`wasm-opt`, `lto`), caricamento in streaming; 6) **WebGPU** per calcolo parallelo; 7) limiti: niente accesso diretto al DOM, memoria lineare, sicurezza (SharedArrayBuffer richiede header COOP/COEP).
**Output**: scelta motivata, scheletro del modulo e della chiamata, come misurare il guadagno.
@@@
name: resilienza-errori-retry-timeout
title: Resilienza: errori, retry, timeout e circuit breaker
domain: programmazione
description: Rende il codice robusto contro guasti esterni: timeout, retry con backoff, circuit breaker, fallback e degradazione controllata.
triggers: resilienza, retry, backoff esponenziale, timeout, circuit breaker, fallback, rate limit, gestione degli errori, errori di rete, degradazione, bulkhead, idempotente, chiamata esterna che fallisce, 429

**Metodo**: 1) **ogni chiamata esterna ha un timeout** (connessione e lettura): il default «infinito» è un bug; 2) retry solo su errori **transitori** (timeout, 429, 5xx) e su operazioni **idempotenti**; backoff esponenziale con jitter, tetto ai tentativi e al tempo totale; rispetta `Retry-After`; 3) **circuit breaker**: dopo N fallimenti smetti di chiamare per un po' e prova a riaprire; 4) **fallback**: cache, valore predefinito, provider alternativo (come il router di modelli che ripiega sul più veloce); 5) limiti di concorrenza (bulkhead, semafori) per non travolgere i provider gratuiti; 6) errori chiari: classifica, logga con contesto, non nascondere con `except: pass`; 7) test dei guasti (latenza, errori) prima di produzione.
**Output**: politica per ogni dipendenza (timeout, retry, fallback) e snippet pronto all'uso.
@@@
name: imparare-a-programmare
title: Imparare a programmare: percorso e metodo
domain: programmazione
description: Guida chi inizia o cambia linguaggio: scelta del primo linguaggio, progetti, pratica deliberata, strumenti e come non bloccarsi.
triggers: imparare a programmare, da dove comincio, primo linguaggio, principiante, corso di programmazione, diventare sviluppatore, quale linguaggio imparare, esercizi di programmazione, portfolio, tutorial hell, imparare python, imparare javascript

**Metodo**: 1) scopo: web, dati/IA, app, giochi, automazione → scelta del linguaggio (**Python** per iniziare e dati/automazione, **JavaScript/TypeScript** per il web); 2) fondamenti: variabili, condizioni, cicli, funzioni, strutture dati, errori, lettura della documentazione; 3) **progetti piccoli e veri** subito (script utile, bot, sito semplice) invece di soli tutorial; 4) pratica quotidiana breve (30-60 min) meglio di maratone; 5) strumenti: editor, terminale, Git/GitHub, debugger; 6) leggi codice altrui, scrivi test, chiedi revisione; 7) quando ti blocchi: riduci il problema, stampa/debug, cerca il messaggio d'errore, chiedi con un esempio minimo.
**Output**: piano a 8-12 settimane con tappe e progetti, risorse gratuite affidabili, 3 esercizi per iniziare. Incoraggiante ma onesto sui tempi.
@@@
name: fondamenti-di-informatica
title: Fondamenti di informatica
domain: programmazione
description: Spiega le basi che reggono tutto: complessità, memoria, sistemi operativi, reti, database, compilatori e come ragionano i computer.
triggers: fondamenti di informatica, complessità computazionale, big o, come funziona un computer, sistema operativo, memoria e processi, thread e processi, stack e heap, compilatore, protocollo tcp, cache della cpu, come funziona internet

**Metodo**: 1) parti dall'intuizione con un'analogia, poi la precisione; 2) **complessità**: O(1), O(log n), O(n), O(n log n), O(n²) e cosa significano su 1 milione di elementi; 3) memoria: stack/heap, cache e località, puntatori e riferimenti; 4) sistema operativo: processi, thread, scheduling, memoria virtuale, file system, system call; 5) rete: livelli (fisico → applicazione), IP, TCP vs UDP, DNS, HTTP, TLS; 6) basi di dati: indici, transazioni (ACID), teorema CAP; 7) dal codice all'esecuzione: compilazione, interpretazione, JIT.
**Output**: spiegazione a livelli (semplice → tecnica), un esempio concreto, un esercizio o domanda per verificare di aver capito, e dove approfondire.
