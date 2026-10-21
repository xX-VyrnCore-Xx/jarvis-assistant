name: notizie-e-informazione-in-tempo-reale
title: Notizie e informazione in tempo reale
domain: scienza
description: Risponde a «cosa succede adesso» con fonti dal vivo, data e ora, confrontando più testate e distinguendo fatti, stime e voci.
triggers: rassegna stampa, aggiornamenti in tempo reale, cosa dicono i giornali, situazione attuale, analisi delle notizie, approfondisci la notizia, confronta le fonti, ultim'ora in corso, come sta evolvendo, cosa sta succedendo in

**Metodo**: 1) per ogni domanda sul presente NON usare la memoria: chiama `news_headlines` (con topic e/o categoria) e, se serve, `web_search`/`read_webpage` per il testo completo; 2) confronta almeno due fonti indipendenti (agenzie come ANSA/BBC/Reuters pesano più dei titoli virali); 3) separa **fatti verificati**, **dati ufficiali**, **dichiarazioni** e **voci/ipotesi**; 4) indica sempre fonte e quanto è recente («ANSA, 40 min fa»); 5) se le fonti discordano, dillo e mostra le due versioni; 6) se non trovi nulla di recente, dì «non risulta ancora» invece di inventare.
**Output**: 3-5 punti con fonte e ora, poi una riga su cosa è ancora incerto o in evoluzione. Per eventi in corso offri di seguirli (promemoria, controllo periodico). Per le notizie salvate nel secondo cervello vale `brain_search` con source «news», ma solo come cronologia: il presente si controlla dal vivo.
@@@
name: fact-checking-e-disinformazione
title: Fact-checking e disinformazione
domain: scienza
description: Verifica notizie, immagini e affermazioni virali: fonte originale, prove, contesto, bias, errori statistici e trappole di titoli e social.
triggers: fact checking, è vero che, bufala, fake news, disinformazione, verifica questa notizia, notizia falsa, immagine falsa, catena di sant'antonio, affidabile questa fonte, complotto, verificare una notizia, clickbait

**Metodo**: 1) **trova la fonte primaria** (comunicato, studio, sentenza, dataset) e non il «ha detto che»; 2) chi lo dice e perché (competenza, interessi, storico); 3) cerca conferme indipendenti e smentite (`web_search`, `news_headlines`); 4) controlla data e contesto (foto vecchie riciclate: ricerca inversa dell'immagine); 5) numeri: assoluto o percentuale? rispetto a cosa? campione e periodo? correlazione non è causalità; 6) studi: pre-print o peer-reviewed, dimensione del campione, conflitti di interesse; 7) segnali d'allarme: urgenza, rabbia, «condividi prima che cancellino», nessuna fonte.
**Output**: verdetto chiaro (vero, falso, fuorviante, non verificabile) con 2-3 prove e link, cosa resta incerto e come verificare da soli. Non dare mai per certo ciò che non puoi controllare; correggi con tatto.
@@@
name: statistica-e-probabilita-pratica
title: Statistica e probabilità pratica
domain: scienza
description: Legge e usa i numeri senza farsi ingannare: media e mediana, campioni, intervalli, test, correlazione, rischio e probabilità condizionata.
triggers: statistica, probabilità, media e mediana, deviazione standard, campione, intervallo di confidenza, p-value, correlazione, test statistico, rischio relativo, distribuzione normale, a/b test, sondaggio

**Metodo**: 1) chiarisci la domanda e il tipo di dati (categorici, continui, tempo); 2) descrivi prima di inferire: media, mediana, dispersione, outlier, grafico; 3) campione: casuale? abbastanza grande? distorsioni di selezione? 4) incertezza: intervallo di confidenza, non un solo numero; 5) test: ipotesi nulla, p-value come «quanto sarebbe strano se non ci fosse effetto», mai come probabilità che l'ipotesi sia vera; dimensione dell'effetto conta più della significatività; 6) probabilità condizionata e Bayes (falsi positivi: un test al 99% con malattia rara sbaglia spesso); 7) rischio relativo vs assoluto.
**Errori comuni**: correlazione=causa, confronti multipli senza correzione, regressione verso la media, paradosso di Simpson. **Output**: risposta in parole semplici, calcolo mostrato (usa `calculate`), limiti dell'analisi.
@@@
name: matematica-per-tutti
title: Matematica e problem solving
domain: scienza
description: Risolve e spiega problemi di matematica passo per passo: capire il testo, scegliere il metodo, calcolare con precisione e verificare il risultato.
triggers: matematica, equazione, problema di matematica, derivata, integrale, algebra, geometria, percentuali, proporzioni, fai il calcolo, risolvi, dimostrazione, limiti, probabilità dei dadi, sistema di equazioni

**Metodo**: 1) riscrivi il problema con le tue parole e individua incognite e dati; 2) fai un disegno o una tabella se aiuta; 3) scegli il metodo (sostituzione, proporzione, derivata, scomposizione) e spiegane il perché; 4) calcola in modo ordinato, **usando `calculate` per i numeri** (mai a memoria con cifre lunghe); 5) **verifica**: sostituisci il risultato, controlla unità, ordine di grandezza e casi limite; 6) dai la risposta in una frase con l'unità.
**Insegnare**: se chi chiede sta studiando, proponi un indizio prima della soluzione, poi un esercizio simile; segnala l'errore tipico (segni, frazioni, unità). Per dimostrazioni: ipotesi, tesi, passaggi giustificati. Se il testo è ambiguo, dichiara l'interpretazione scelta.
@@@
name: fisica-e-ingegneria-di-base
title: Fisica e ingegneria di base
domain: scienza
description: Spiega e calcola fenomeni fisici e problemi tecnici: moto, energia, elettricità, calore, onde, unità di misura e stime di ordine di grandezza.
triggers: fisica, forza, energia, potenza, corrente elettrica, tensione e resistenza, legge di ohm, velocità e accelerazione, calore, onde, ingegneria, quanta energia, ordine di grandezza, circuito, pressione

**Metodo**: 1) modello semplice: cosa è rilevante, cosa trascurare; 2) unità del Sistema Internazionale e **analisi dimensionale** per controllare le formule; 3) leggi giuste (Newton, conservazione di energia e quantità di moto, Ohm e Joule, termodinamica); 4) calcolo con `calculate`, cifre significative sensate; 5) stima di Fermi per capire se il risultato è plausibile (ordine di grandezza); 6) spiega il «perché» con un esempio quotidiano.
**Pratica**: potenza = tensione × corrente; energia (kWh) = potenza × ore (utile per bollette); efficienza e perdite; sicurezza elettrica: niente consigli rischiosi su alta tensione, rimanda a un professionista. **Output**: formula, numeri con unità, risultato, plausibilità.
@@@
name: astronomia-e-spazio
title: Astronomia e spazio
domain: scienza
description: Racconta e calcola l'universo: sistema solare, stelle, missioni, eventi celesti, scale di distanza e come osservare il cielo.
triggers: astronomia, spazio, pianeti, sistema solare, stelle, galassia, buco nero, eclissi, missione spaziale, nasa, telescopio, cielo stellato, stazione spaziale, luna piena, meteore

**Metodo**: 1) per eventi e missioni **recenti** usa `news_headlines` (categoria scienza) o `web_search`: gli eventi celesti e le date cambiano; 2) per i fondamenti usa `wikipedia`; 3) dai le **scale** con confronti (distanza Terra-Luna ≈ 384.000 km, Sole ≈ 150 milioni di km, luce: 8 minuti dal Sole); 4) distingui ciò che è misurato da ciò che è teoria o ipotesi; 5) per osservare: luogo buio, app di mappa del cielo, binocolo prima del telescopio, **mai guardare il Sole senza filtri certificati**; 6) per calcoli (periodi, distanze, velocità) usa `calculate`.
**Output**: spiegazione chiara, un dato sorprendente verificato, e se utile cosa osservare nei prossimi giorni (chiedi la località).
@@@
name: economia-e-macroeconomia
title: Economia e macroeconomia
domain: scienza
description: Spiega inflazione, tassi, PIL, bilancia commerciale, mercati e politiche economiche, collegandoli alle notizie e alla vita quotidiana.
triggers: macroeconomia, inflazione, tassi di interesse, pil, bce, recessione, debito pubblico, spread, politica monetaria, disoccupazione, bilancia commerciale, crisi economica, economia italiana

**Metodo**: 1) definisci il concetto in una frase e il suo indicatore; 2) **dati aggiornati dal vivo** (`news_headlines` categoria economia, BCE, `web_search`): mai citare tassi o inflazione a memoria; 3) catena causale: tassi ↑ → credito più caro → domanda ↓ → inflazione ↓; 4) effetti su mutui, risparmi, stipendi, prezzi; 5) due scuole di pensiero quando la questione è controversa, senza schierarsi; 6) distingui breve e lungo periodo.
**Output**: spiegazione semplice, dato recente con fonte e data, cosa cambia per chi chiede, cosa seguire (prossima riunione BCE, dati ISTAT). Non è consulenza finanziaria personalizzata.
@@@
name: storia-e-geopolitica
title: Storia e geopolitica
domain: scienza
description: Analizza eventi storici e crisi attuali: cause, attori, interessi, cronologia, fonti e prospettive diverse, con onestà sui limiti.
triggers: storia, geopolitica, guerra, conflitto, relazioni internazionali, trattato, impero, rivoluzione, nato, onu, sanzioni, crisi internazionale, cause della guerra, cronologia, confini, diplomazia

**Metodo**: 1) **cronologia** dei fatti chiave con date; 2) **attori** e loro interessi (sicurezza, economia, identità, risorse); 3) cause di lungo periodo vs scintilla; 4) più prospettive (non solo quella occidentale); 5) fonti primarie e storici, distinguendo fatti, interpretazioni e propaganda; 6) per il presente usa `news_headlines` (mondo) e `web_search`, con data e fonte, e dichiara quando la situazione cambia in fretta.
**Output**: sintesi in pochi punti, cronologia, scenari possibili etichettati come ipotesi. Tono sobrio, niente giudizi morali improvvisati, nessuna previsione certa; evita semplificazioni.
@@@
name: ricerca-accademica-e-tesi
title: Ricerca accademica, tesi e studio
domain: scienza
description: Aiuta a cercare fonti scientifiche, leggere articoli, strutturare tesi e relazioni, citare correttamente ed evitare plagio.
triggers: tesi, ricerca scientifica, articolo scientifico, paper, bibliografia, citazioni, stato dell'arte, revisione della letteratura, abstract, metodologia, relazione universitaria, pubblicazione, peer review, plagio

**Metodo**: 1) domanda di ricerca precisa e ipotesi; 2) **ricerca fonti**: Google Scholar, arXiv, PubMed, Semantic Scholar; prima review e survey, poi studi primari; 3) leggi in ordine abstract → conclusioni → metodi → risultati; 4) schedatura: obiettivo, metodo, campione, risultati, limiti; 5) struttura: introduzione, stato dell'arte, metodo, risultati, discussione, conclusioni; 6) stile di citazione coerente (APA, IEEE), mai testo copiato senza virgolette e fonte; 7) metodo e limiti dichiarati con onestà.
**Output**: scaletta, query di ricerca da provare, griglia di lettura, bozza di abstract. Non inventare mai riferimenti: se non trovi una fonte, dillo; verifica che ogni citazione esista (`web_search`).
