"""Comandi rapidi della sezione Codice (come gli «slash command» di Claude Code): `/review`, `/test`, `/fix`… Ognuno è un prompt già scritto bene.
L'app li mostra scrivendo «/» e li espande prima dell'invio; con `/bg` (o `/<comando> bg`) il lavoro parte in background."""

# nome -> (descrizione breve, prompt con {args}, accetta argomenti)
COMMANDS: dict[str, tuple[str, str, bool]] = {
    "plan": ("Piano dettagliato, senza modificare nulla",
             "Analizza il progetto con la mappa del codice e prepara un PIANO per: {args}. Elenca i file coinvolti, i passi in ordine, i rischi e come verificare. NON modificare nulla: imposta solo il piano con code_plan.", True),
    "init": ("Crea JARVIS.md: le istruzioni del progetto",
             "Studia il progetto (code_graph, code_tree, README, configurazioni) e crea nella radice il file JARVIS.md con: scopo, struttura, comandi per test/build, convenzioni di stile, regole da rispettare e punti delicati. Breve e concreto (max 60 righe). Poi committa.", False),
    "review": ("Revisione critica delle modifiche",
               "Fai una revisione critica delle modifiche non committate (code_diff, code_review, code_lint): bug, casi limite, sicurezza, test mancanti, leggibilità. Correggi ciò che è chiaramente sbagliato e riassumi il resto per gravità. {args}", True),
    "pr-review": ("Rivedi una Pull Request",
                  "Rivedi la Pull Request {args} con code_pr_diff: correttezza, sicurezza, test, stile. Lascia un commento riassuntivo con code_pr_comment (punti bloccanti prima, poi suggerimenti).", True),
    "test": ("Scrivi i test mancanti",
             "Individua le parti importanti senza test{args} e scrivi i test più utili (casi normali, limite ed errore), nello stile dei test esistenti. Controlla la sintassi e poi la CI.", True),
    "fix": ("Correggi un bug o la CI",
            "Correggi questo problema: {args}. Trova prima la causa vera (leggi il codice e, se c'entra, i log della CI con code_ci_logs), correggi in modo minimo, aggiungi un test che lo dimostra e controlla la CI.", True),
    "ci": ("Porta la CI a verde",
           "Controlla la CI (code_checks). Se è rossa leggi i log (code_ci_logs), trova la causa vera senza aggirare i test, correggi, committa e attendi di nuovo (code_wait_checks) fino a verde, massimo 3 tentativi.", False),
    "explain": ("Spiega il codice",
                "Spiega com'è fatto {args}: usa la mappa del codice, descrivi componenti, flussi principali e punti delicati, con riferimenti a file e righe. Niente modifiche.", True),
    "refactor": ("Refactor a piccoli passi",
                 "Fai un refactor a piccoli passi di {args}: stesso comportamento, più chiaro. Prima un code_checkpoint, poi cambiamenti piccoli, test che li dimostrano, code_lint e revisione finale.", True),
    "security": ("Audit di sicurezza",
                 "Fai un audit di sicurezza del progetto{args}: input non fidati, iniezioni, segreti, autenticazione/autorizzazione, dipendenze, gestione errori. Correggi ciò che è sicuro correggere, il resto elencalo per gravità.", True),
    "optimize": ("Prestazioni",
                 "Cerca i colli di bottiglia{args}: complessità, I/O ripetuto, query inutili, lavoro sincrono evitabile. Proponi e applica le ottimizzazioni misurabili e sicure, spiegando il guadagno atteso.", True),
    "docs": ("Documentazione",
             "Migliora la documentazione{args}: README (installazione, uso, esempi), docstring dei punti pubblici, e un JARVIS.md se manca. Solo ciò che è vero dal codice.", True),
    "todo": ("Risolvi i TODO",
             "Elenca i TODO/FIXME (code_todos), scegli quelli chiari e a basso rischio e risolvili con test; per gli altri riassumi cosa serve.", False),
    "commit": ("Controlla e committa",
               "Esegui code_lint e code_review, correggi i problemi, poi committa con un messaggio chiaro (cosa e perché) su un ramo di lavoro. {args}", True),
    "pr": ("Commit, PR e CI verde",
           "Committa le modifiche (dopo code_lint e code_review) su un ramo di lavoro, apri la Pull Request con un buon titolo e una descrizione (cosa, perché, come verificare), attendi la CI e correggila se è rossa. {args}", True),
    "ship": ("Dall'idea alla PR verde",
             "Realizza questo, dall'inizio alla fine: {args}. Piano, implementazione a passi con test, controllo di sintassi, revisione, commit su un ramo, PR, CI verde (correggendo la causa vera). Non unire la PR.", True),
    "undo": ("Annulla l'ultima modifica", "Annulla le ultime modifiche con code_undo ({args} passi, 1 se non indicato) e dimmi cosa è tornato com'era.", True),
    "checkpoint": ("Salva un punto di ripristino", "Salva un punto di ripristino della sandbox con code_checkpoint (nome: {args}).", True),
    "rollback": ("Torna a un punto di ripristino", "Riporta la sandbox al punto di ripristino {args} con code_rollback e conferma cosa è cambiato.", True),
    "deps": ("Dipendenze", "Analizza le dipendenze del progetto: non usate, obsolete, rischiose o duplicate. Proponi e applica solo modifiche sicure.", False),
    "tests-run": ("Lancia la CI e riporta", "Avvia la CI (code_ci_run), attendi l'esito (code_wait_checks) e riassumi i risultati; se ci sono errori spiega la causa probabile.", False),
}

# comandi che non passano dal modello (li gestisce l'app)
LOCAL = {"bg": "Esegui in background: «/bg <cosa fare>»", "jobs": "Lavori in background", "new": "Azzera la chat di coding", "help": "Elenco dei comandi"}


def listing() -> list[dict]:
    rows = [{"name": k, "desc": d, "args": a, "prompt": p} for k, (d, p, a) in COMMANDS.items()]
    rows += [{"name": k, "desc": d, "args": k == "bg", "prompt": "", "local": True} for k, d in LOCAL.items()]
    return rows
