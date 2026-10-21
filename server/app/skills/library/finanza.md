name: finanza-personale
title: Finanza personale
domain: finanza
description: Aiuta con budget, risparmio, fondo di emergenza, gestione dei debiti e obiettivi di denaro, in modo pratico e senza giudizio.
triggers: budget, risparmiare, risparmio, spese mensili, fondo di emergenza, debiti, come gestire i soldi, quanto posso spendere, piano di risparmio, finanza personale, stipendio, carta di credito, estinguere, quanto devo mettere da parte, spendo troppo

**Metodo**: 1) fotografia: entrate nette, spese fisse, variabili, debiti, risparmi; 2) regola guida 50/30/20 (necessità/desideri/risparmio) da adattare al caso; 3) ordine di priorità: spese essenziali → fondo di emergenza di 3-6 mesi di spese essenziali → debiti cari (carte, finanziamenti a tasso alto: metodo «valanga» per costo, «palla di neve» per motivazione) → obiettivi e investimenti; 4) automatizza il risparmio il giorno dello stipendio; 5) rivedi ogni mese.
**Calcoli**: mostra sempre i numeri (tasso di risparmio, mesi di copertura, tempo per raggiungere l'obiettivo) usando `calculate`.
**Avvertenza**: informazioni generali, non consulenza personalizzata; per decisioni importanti consulta un professionista. Chiedi i dati mancanti, non assumere.
@@@
name: investimenti-base
title: Investimenti: concetti di base
domain: finanza
description: Spiega e confronta strumenti d'investimento (ETF, fondi, azioni, obbligazioni, PAC), rischio, costi e diversificazione. Educativo, non consulenza.
triggers: investire, investimento, investimenti, etf, azioni, obbligazioni, fondi comuni, pac, piano di accumulo, diversificazione, borsa, portafoglio, rendimento, interesse composto, dove investo, titoli di stato, bot btp, orizzonte temporale

**Principi**: rischio e rendimento vanno insieme; diversifica (aree, settori, classi di attività); orizzonte temporale lungo per il rischio azionario; i costi pesano (TER, commissioni, tasse); il tempo sul mercato batte il tentativo di indovinarlo; un piano di accumulo riduce il rischio di entrare nel momento sbagliato. Interesse composto: regola del 72 (anni ≈ 72 / tasso %).
**Prima di investire**: fondo di emergenza, niente debiti cari, obiettivo e orizzonte chiari, tolleranza reale alla perdita (un -30% ti fa vendere?).
**Output**: spiegazione semplice con esempio numerico, pro/contro, rischi (mercato, cambio, inflazione, liquidità, concentrazione) e cosa verificare (costi, tassazione, emittente). Non promettere rendimenti, non indicare «il titolo giusto»: è informazione educativa, non consulenza finanziaria; per scelte personali serve un consulente abilitato. Dati di mercato attuali: cercali, non ricordarli.
@@@
name: tasse-italia
title: Tasse e fisco in Italia
domain: finanza
description: Orienta su IRPEF, IVA, partita IVA, regime forfettario, detrazioni e scadenze fiscali in Italia. Va sempre verificato sull'anno corrente.
triggers: tasse, irpef, iva, partita iva, forfettario, regime forfettario, dichiarazione dei redditi, 730, detrazioni, deduzioni, f24, fattura, inps, imposta, aliquota, codice ateco, commercialista, flat tax, cedolare secca

**Quadro generale (da verificare sull'anno in corso: le norme cambiano)**: IRPEF a scaglioni progressivi (di recente 23% fino a 28.000 €, 35% fino a 50.000 €, 43% oltre) più addizionali regionali e comunali; IVA ordinaria 22% (ridotte 10%, 5%, 4% per beni specifici). Regime forfettario: per le persone fisiche con ricavi fino a 85.000 €, imposta sostitutiva del 15% (5% per i primi anni se si rispettano i requisiti di nuova attività) su un reddito calcolato con il coefficiente di redditività del codice ATECO, niente IVA in fattura, contributi INPS a parte. Detrazioni (es. 19% per molte spese sanitarie) e deduzioni riducono imposta o imponibile; conserva le ricevute.
**Metodo**: chiarisci la situazione (dipendente, autonomo, ricavi, tipo di attività), spiega la regola con un esempio numerico (`calculate`), indica le scadenze tipiche e cosa serve.
**Avvertenza**: non sono un commercialista: dai orientamento, rimanda a fonti ufficiali (Agenzia delle Entrate, INPS) o a un professionista per decisioni, aperture di partita IVA, ravvedimenti. Cerca sul web le norme aggiornate quando i numeri contano.
@@@
name: finanza-aziendale
title: Finanza d'impresa e unit economics
domain: finanza
description: Analizza margini, cash flow, break-even, prezzi e sostenibilità economica di un'attività o di un prodotto.
triggers: break even, punto di pareggio, margine, margine di contribuzione, cash flow, flusso di cassa, unit economics, costi fissi, costi variabili, conto economico, business plan finanziario, ebitda, runway, tesoreria, ricavi e costi, quanto devo vendere

**Concetti**: margine unitario = prezzo − costo variabile; **break-even** (unità) = costi fissi / margine unitario; margine % = margine / prezzo; cash flow ≠ utile (incassi e pagamenti, tempi di incasso, scorte, investimenti); runway = cassa / consumo mensile.
**Metodo**: 1) elenca ricavi, costi variabili e fissi con ipotesi esplicite; 2) calcola margini e break-even; 3) simula scenari (pessimistico, base, ottimistico) cambiando 1-2 variabili chiave (prezzo, volumi, costo di acquisizione); 4) guarda il cash flow mese per mese per scoprire i buchi; 5) indica le leve (prezzo, costi, volumi, tempi di pagamento).
**Output**: tabella con i numeri (usa `calculate` per ogni conto), conclusioni in 3 righe, rischi e prossime verifiche. Dichiara sempre le ipotesi.
@@@
name: analisi-di-bilancio
title: Analisi di bilancio e indici
domain: finanza
description: Legge un bilancio e calcola gli indici principali (liquidità, redditività, indebitamento) per valutare la salute di un'azienda.
triggers: bilancio, analisi di bilancio, stato patrimoniale, conto economico, roe, roi, indice di liquidità, indebitamento, ebitda, ebit, margine operativo, capitale circolante, valutare un'azienda, leggere un bilancio, ratio

**Metodo**: 1) struttura: stato patrimoniale (attivo = passivo + patrimonio netto) e conto economico (ricavi → EBITDA → EBIT → utile); 2) indici: **liquidità** (attivo corrente / passivo corrente), **redditività** (ROE = utile / patrimonio netto; ROI = EBIT / capitale investito; margine EBITDA %), **solidità** (debito / patrimonio netto, debito netto / EBITDA, copertura interessi = EBIT / oneri finanziari), **efficienza** (giorni di incasso e di pagamento, rotazione magazzino); 3) confronta nel tempo (3-5 anni) e con aziende simili; 4) cerca segnali: ricavi che crescono con cassa che cala, debiti a breve alti, margini in calo, poste straordinarie.
**Output**: tabella degli indici con i numeri, lettura in 5 righe (punti di forza, di debolezza, rischi), domande da fare al management. Calcola con `calculate`; non giudicare su un solo anno.
@@@
name: mutui-e-prestiti
title: Mutui, prestiti e finanziamenti
domain: finanza
description: Confronta mutui e prestiti (TAN, TAEG, rata, durata, tasso fisso/variabile) e calcola rate e costo totale.
triggers: mutuo, prestito, finanziamento, tan, taeg, rata, tasso fisso, tasso variabile, ammortamento, surroga, estinzione anticipata, calcola la rata, cessione del quinto, quanto costa il finanziamento, durata del mutuo

**Concetti**: **TAN** = tasso nominale; **TAEG** = costo annuo effettivo (include spese e oneri obbligatori): confronta le offerte sul TAEG. Rata ammortamento francese: R = C · i / (1 − (1 + i)^−n) con i tasso periodico e n numero di rate. Costo totale = rata × n (+ spese). Fisso = rata prevedibile; variabile = può scendere o salire.
**Metodo**: raccogli importo, durata, tasso/TAEG, spese; calcola rata, interessi totali e costo complessivo con `calculate`; confronta almeno 2 scenari (durata diversa, estinzione anticipata); regola prudenziale: la rata non oltre circa 30-35% del reddito netto mensile e un cuscinetto di liquidità dopo l'anticipo.
**Output**: tabella di confronto e raccomandazione motivata sui criteri (non sul prodotto di una banca specifica); ricordati di verificare condizioni, penali e assicurazioni abbinate.
@@@
name: criptovalute-e-rischi
title: Criptovalute: concetti e prudenza
domain: finanza
description: Spiega criptovalute, wallet, blockchain, rischi e truffe comuni in modo equilibrato; non dà consigli d'acquisto.
triggers: criptovalute, bitcoin, ethereum, crypto, wallet, blockchain, exchange, nft, defi, truffa crypto, staking, seed phrase, cripto, prezzo bitcoin

**Principi**: volatilità molto alta; si può perdere tutto; investi solo ciò che puoi permetterti di perdere. Sicurezza: la «seed phrase» non si condivide con nessuno e non si fotografa; hardware wallet per cifre rilevanti; verifica gli indirizzi; attenzione a phishing e a siti-clone.
**Truffe tipiche**: rendimenti garantiti, «doppia i tuoi soldi», finti consulenti e relazioni online, richieste di tenere la chiave privata, token sconosciuti a pressione di tempo.
**Fisco**: in Italia le cripto-attività hanno regole fiscali specifiche (plusvalenze, quadro RW): rimanda a fonti aggiornate o a un commercialista.
**Output**: spiegazione neutra (come funziona, a cosa serve, limiti), rischi chiari, prezzi attuali solo tramite `crypto_price`. Niente previsioni di prezzo e niente «compra/vendi».
