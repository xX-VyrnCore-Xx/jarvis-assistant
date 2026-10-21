name: produttivita-e-tempo
title: Produttività e gestione del tempo
domain: vita
description: Organizza tempo, priorità e attività: matrice delle priorità, pianificazione settimanale, concentrazione e abitudini.
triggers: produttività, gestione del tempo, priorità, organizzarmi, procrastinare, procrastinazione, to do, lista delle cose da fare, pianificare la settimana, gtd, pomodoro, concentrazione, non ho tempo, troppe cose da fare, abitudini, routine

**Metodo**: 1) **raccogli** tutto in un posto (anche con le attività di JARVIS); 2) chiarisci il prossimo passo concreto di ogni cosa; 3) **priorità**: importante/urgente (fai subito, pianifica, delega, elimina); 4) massimo 3 priorità al giorno e una sola «cosa che conta»; 5) blocchi di lavoro profondo (50-90 minuti) senza notifiche, pause vere; 6) stima con buffer (le cose durano di più); 7) revisione settimanale di 20 minuti; 8) abitudini: piccole, legate a un'abitudine esistente, ripetibili.
**Procrastinazione**: riduci il primo passo a 2 minuti, scegli un orario preciso, togli l'attrito.
**Output**: piano della giornata o settimana con orari, e proponi di creare promemoria o attività con i tool (`remind_in`, `task_add`) solo se l'utente vuole.
@@@
name: apprendimento-e-studio
title: Apprendimento e studio efficace
domain: vita
description: Costruisce piani di studio e metodi per imparare davvero: ripetizione dilazionata, richiamo attivo, tecnica di Feynman, esami e nuove competenze.
triggers: studiare, studio, piano di studio, imparare, come imparo, esame, memorizzare, ripasso, flashcard, tecnica di feynman, imparare una lingua, preparare un esame, appunti, mappa concettuale, apprendimento

**Metodo**: 1) obiettivo e scadenza → lavora a ritroso; 2) scomponi in argomenti con livello di partenza e tempo per ciascuno; 3) **richiamo attivo** (rispondi senza guardare, fai domande) batte la rilettura; 4) **ripetizione dilazionata** (1 giorno, 3, 7, 14, 30) per fissare nel lungo termine; 5) **Feynman**: spiega l'argomento con parole semplici, dove inciampi studia ancora; 6) pratica varia (esercizi, casi, simulazioni d'esame con tempo); 7) sonno, pause e sessioni da 25-50 minuti.
**Lingue**: input comprensibile ogni giorno, parlare presto, vocabolario in contesto, ripetizione dilazionata.
**Output**: piano settimanale con sessioni e obiettivi, schede/domande per il ripasso, simulazione di prova. Può salvare ciò che si impara nel secondo cervello (`brain_learn`, `brain_add_note`).
@@@
name: decisioni-e-pensiero-critico
title: Decisioni e pensiero critico
domain: vita
description: Aiuta a decidere meglio: opzioni, criteri, rischi, pre-mortem, bias cognitivi e decisioni reversibili o no.
triggers: decisione, devo scegliere, cosa faccio, pro e contro, dilemma, scelta difficile, matrice decisionale, indeciso, quale scegliere, conviene o no, pensiero critico, bias, pre-mortem, dubbi

**Metodo**: 1) definisci la decisione e **quando** serve davvero; 2) è reversibile (porta a due vie: decidi in fretta) o no (più tempo e dati)? 3) criteri che contano, con pesi; 4) opzioni (anche «non fare nulla» e opzioni intermedie); 5) matrice pesata con punteggi onesti; 6) **pre-mortem**: immagina che sia andata male, perché? 7) bias da controllare: conferma, costi irrecuperabili, ancoraggio, disponibilità, eccesso di fiducia; 8) decidi, scrivi perché, fissa un momento di verifica.
**Output**: tabella con criteri/opzioni, raccomandazione motivata (e cosa la cambierebbe), rischi principali e un piccolo esperimento per ridurre l'incertezza. La decisione finale resta all'utente; per questioni mediche, legali o finanziarie importanti rimanda a un professionista.
@@@
name: viaggi-e-logistica
title: Viaggi e pianificazione
domain: vita
description: Pianifica viaggi e spostamenti: itinerario, budget, prenotazioni, documenti, clima, sicurezza e checklist.
triggers: viaggio, viaggiare, itinerario, vacanza, weekend a, cosa vedere a, prenotare, volo, hotel, budget del viaggio, valigia, checklist del viaggio, visto, assicurazione di viaggio, dove andare, trasferta

**Metodo**: 1) vincoli: date, budget, persone, interessi, ritmo; 2) destinazione e periodo (meteo con `get_weather`, stagionalità, eventi); 3) itinerario a giornate con tempi realistici di spostamento, pause e un'alternativa per la pioggia; 4) prenotazioni nell'ordine giusto (voli e alloggio, poi attrazioni a numero chiuso); 5) budget per voci con margine del 10-15% (`calculate`, `convert_currency`); 6) documenti (passaporto/carta d'identità, validità, visti o autorizzazioni), assicurazione sanitaria, copie digitali; 7) checklist valigia e di casa.
**Output**: itinerario giorno per giorno, budget stimato, checklist, e promemoria utili da creare (check-in, scadenze di prenotazione). Per regole di ingresso e sicurezza rimanda ai siti ufficiali (Viaggiare Sicuri) e verifica le info aggiornate.
@@@
name: benessere-e-abitudini
title: Benessere e abitudini sane
domain: vita
description: Informazioni generali su sonno, alimentazione, movimento e stress per costruire abitudini sostenibili. Non sostituisce il medico.
triggers: dormire meglio, sonno, alimentazione, dieta, allenamento, esercizio, stress, ansia, benessere, camminare, perdere peso, abitudini sane, energia, mal di schiena, idratazione, meditazione

**Principi generali**: sonno regolare di circa 7-9 ore per gli adulti, luce al mattino, schermi e caffeina limitati la sera; alimentazione varia con molta verdura, legumi, cereali integrali, proteine adeguate, poco ultra-processato; movimento: circa 150 minuti di attività moderata a settimana più 2 sedute di forza; gestione dello stress con pause, respirazione lenta, socialità, tempo all'aperto. Cambia **una** abitudine alla volta, piccola e misurabile (es. 10 minuti di camminata dopo pranzo).
**Output**: piano graduale di 2-4 settimane con obiettivi semplici e come monitorarli. 
**Limiti importanti**: sono informazioni generali, non una diagnosi né una terapia. Sintomi persistenti, dolore forte, ansia/depressione che pesano, gravidanza, patologie o farmaci → parla con un medico o altro professionista. In caso di emergenza chiama il 112. Niente diete estreme.
@@@
name: cucina-e-spesa
title: Cucina, menu e spesa
domain: vita
description: Pianifica menu settimanali, lista della spesa, ricette, sostituzioni e organizzazione in cucina rispettando gusti, tempo e budget.
triggers: ricetta, cosa cucino, cosa preparo per cena, menu della settimana, lista della spesa, meal prep, cucinare, sostituire un ingrediente, quantità, ricette veloci, avanzi, pranzo, cena, dolce, impasto

**Metodo**: 1) vincoli: persone, tempo, budget, attrezzatura, allergie/intolleranze, preferenze; 2) menu settimanale con ingredienti che si riusano e 1-2 preparazioni in batch; 3) lista della spesa ordinata per reparti, confrontata con ciò che c'è in casa; 4) ricette con ingredienti e dosi precise, tempi e passaggi numerati, trucchi per il risultato; 5) conservazione e avanzi (frigo/freezer), sicurezza alimentare (cottura, catena del freddo).
**Allergie**: non fare mai supposizioni; segnala gli allergeni e invita a leggere le etichette.
**Output**: menu + lista della spesa o ricetta completa; offri variante veloce, vegetariana o economica. Puoi aggiungere la spesa alle liste con i tool (`task_add` in «spesa») se l'utente vuole.
@@@
name: diritti-e-burocrazia-italia
title: Diritti quotidiani e burocrazia in Italia
domain: vita
description: Orienta su contratti, acquisti online, affitto, privacy (GDPR), reclami e pratiche; informazioni generali, non consulenza legale.
triggers: diritto, contratto, recesso, garanzia, rimborso, reclamo, affitto, locazione, privacy, gdpr, multa, burocrazia, pratica, spid, disdetta, condominio, consumatore, caparra, denuncia, diritti del consumatore

**Punti fermi (verifica sempre la norma aggiornata)**: acquisti a distanza/online: diritto di recesso di 14 giorni senza motivazione (con eccezioni); garanzia legale di conformità sui beni di 24 mesi dalla consegna; la disdetta e le clausole vanno lette e conservate per iscritto (PEC o raccomandata per le comunicazioni importanti); locazioni: contratto registrato, deposito cauzionale limitato per legge; privacy: diritto di accesso, rettifica, cancellazione e opposizione, reclami al Garante.
**Metodo**: 1) raccogli i fatti e i documenti (contratto, date, comunicazioni); 2) individua la regola applicabile; 3) passi pratici in ordine (reclamo scritto → diffida → conciliazione/organismi di settore → giudice di pace/avvocato); 4) scadenze e termini; 5) bozza di lettera/PEC su richiesta.
**Avvertenza**: orientamento generale, non parere legale: per cause, importi alti o situazioni complesse serve un avvocato; cerca le norme aggiornate sul web e cita le fonti ufficiali.
