"""Strumenti delle sessioni di coding (sandbox + repository GitHub privato creato da JARVIS). Vedi `coding.py` per le regole di sicurezza."""
from ..coding import CodingError, CodingService
from . import UNTRUSTED, ToolRegistry


def register_coding_tools(reg: ToolRegistry, coding: CodingService, pending) -> None:
    on = lambda: coding.enabled  # noqa: E731
    s = {"type": "string"}
    b = {"type": "boolean"}
    i = {"type": "integer"}
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731

    def guarded(fn):
        async def run(**kw) -> str:
            try:
                r = fn(**kw)
                return await r if hasattr(r, "__await__") else r
            except CodingError as e:
                return f"Errore: {e}"
        return run

    async def start(name: str, description: str = "", readme: bool = True, license: str = "mit") -> str:
        async def create() -> str:
            try:
                return await coding.create_repo(name.strip(), description.strip(), readme, license.strip())
            except CodingError as e:
                return f"Errore: {e}"

        lic = license.strip().lower() or "nessuna"
        p = pending.create("code_repo", f"Creare il repository PRIVATO «{name.strip()}» su GitHub (descrizione: {description.strip()[:80] or '—'}; README: {'sì' if readme else 'no'}; licenza: {lic})", create)
        return ("In attesa della conferma dell'utente (app o Telegram) per creare il repository privato. "
                f"Id richiesta: {p.id}. Dopo l'approvazione la sandbox sarà pronta: poi usa code_status e inizia a lavorare.")

    async def read(path: str, start: int = 1, lines: int = 400) -> str:
        return UNTRUSTED + coding.read(path, start, lines)

    async def ci_logs() -> str:
        return UNTRUSTED + await coding.ci_logs()

    async def checks() -> str:
        c = await coding.checks()
        return f"CI: {c['state']}" + "".join(f"\n- {r['name']}: {r['status']} {r['conclusion']}".rstrip() for r in c["runs"])

    async def sessions() -> str:
        return await coding.list_repos()

    async def delete_repo(name: str) -> str:
        try:
            full, summary = await coding.delete_summary(name)
        except CodingError as e:
            return f"Errore: {e}"

        async def run() -> str:
            try:
                return await coding.delete_repo(full)
            except CodingError as e:
                return f"Errore: {e}"

        p = pending.create("code_repo_delete", f"ELIMINARE DEFINITIVAMENTE il repository privato {summary}. L'operazione non è reversibile.", run)
        return ("In attesa della conferma esplicita dell'utente (app o Telegram) per eliminare il repository: senza il suo OK non succede nulla. "
                f"Id richiesta: {p.id}. Non insistere e non chiedere di nuovo: avvisalo che deve confermare.")

    async def search(pattern: str, glob: str = "*", context: int = 0, limit: int = 40) -> str:
        return UNTRUSTED + coding.search(pattern, glob, context, limit)

    async def graph_tool(fn, *args) -> str:
        return UNTRUSTED + fn(*args)

    async def issues(state: str = "open") -> str:
        return UNTRUSTED + await coding.issues(state)

    async def status() -> str:
        return coding.status()

    reg.register("code_start_session", "Inizia una sessione di coding: crea un repository GitHub PRIVATO (sempre privato) e la sandbox. PRIMA di chiamarla CHIEDI all'utente: nome del repository, descrizione, se aggiungere il README e quale licenza (MIT, Apache-2.0, GPL-3.0, BSD-3-Clause, Unlicense, oppure nessuna). Serve poi la sua conferma.",
                 obj({"name": s, "description": s, "readme": b, "license": s}, ["name"]), start, available=on)
    reg.register("code_resume", "Riprende una sessione di coding su un repository creato in precedenza da JARVIS (nome o proprietario/nome).", obj({"name": s}, ["name"]), guarded(coding.resume), available=on)
    reg.register("code_sessions", "Elenco COMPLETO dei repository creati da JARVIS (privati) con descrizione, ultimo aggiornamento, issue/PR aperte e dimensione.", obj({}), guarded(sessions), available=on)
    reg.register("code_repos", "Alias di code_sessions: lista dei repository creati da JARVIS con i dettagli.", obj({}), guarded(sessions), available=on)
    reg.register("code_status", "Stato della sessione di coding: repository, rami, PR, file modificati non ancora committati.", obj({}), status)
    reg.register("code_ls", "Elenca i file della sandbox (con quelli modificati/eliminati). 'path' filtra per prefisso.", obj({"path": s}), guarded(coding.ls), available=on)
    reg.register("code_read", "Legge un file della sandbox con numeri di riga (max 800 righe per volta; usa start per continuare).", obj({"path": s, "start": {"type": "integer"}, "lines": {"type": "integer"}}, ["path"]), guarded(read), available=on)
    reg.register("code_write", "Crea o sovrascrive un file nella sandbox (max 200 KB). Niente segreti nel codice: usa variabili d'ambiente.", obj({"path": s, "content": s}, ["path", "content"]), guarded(coding.write), available=on)
    reg.register("code_edit", "Sostituisce un testo esatto in un file (deve comparire una sola volta, salvo replace_all). Per modifiche piccole preferiscilo a riscrivere il file.",
                 obj({"path": s, "old": s, "new": s, "replace_all": b}, ["path", "old", "new"]), guarded(coding.edit), available=on)
    reg.register("code_delete", "Elimina un file dalla sandbox.", obj({"path": s}, ["path"]), guarded(coding.delete), available=on)
    reg.register("code_search", "Cerca un'espressione regolare nei file della sandbox. glob filtra i file (es. *.py), context (0-3) aggiunge righe attorno.", obj({"pattern": s, "glob": s, "context": i, "limit": i}, ["pattern"]), guarded(search), available=on)
    reg.register("code_commit", "Committa tutte le modifiche della sandbox su GitHub. Di norma su un ramo di lavoro (creato da solo); direct=true scrive sul ramo principale. Messaggio chiaro e breve. Rifiuta file con chiavi/segreti.",
                 obj({"message": s, "direct": b, "branch": s}, ["message"]), guarded(coding.commit), available=on)
    reg.register("code_sync", "Riscarica la sandbox dall'ultimo commit su GitHub (richiede che non ci siano modifiche non committate).", obj({}), guarded(coding.sync), available=on)
    reg.register("code_open_pr", "Apre una Pull Request dal ramo di lavoro verso il principale.", obj({"title": s, "body": s}, ["title"]), guarded(coding.open_pr), available=on)
    reg.register("code_checks", "Stato della CI (GitHub Actions) sul commit attuale: none, pending, success, failure.", obj({}), guarded(checks), available=on)
    reg.register("code_ci_logs", "Log dei controlli di CI falliti (ultime righe), per capire cosa correggere.", obj({}), guarded(ci_logs), available=on)
    reg.register("code_add_ci", "Scrive nella sandbox un workflow di CI minimo (python o node) in .github/workflows/ci.yml: i test girano su GitHub, mai sul server.", obj({"language": s}, ["language"]), guarded(coding.add_ci), available=on)
    reg.register("code_merge", "Unisce la PR nel ramo principale (squash) e aggiorna la sandbox. Solo se non ci sono modifiche non committate e la CI è verde o assente.", obj({}), guarded(coding.merge), available=on)

    # ---- repository: modifica, ritrovamento, eliminazione (con conferma), registro
    reg.register("code_adopt", "Ritrova i repository privati con l'argomento «jarvis-managed» e li rimette nell'elenco (se l'elenco è andato perso).", obj({}), guarded(coding.adopt), available=on)
    reg.register("code_repo_edit", "Modifica un repository creato da JARVIS: descrizione, nuovo nome, argomenti (separati da virgola), archiviazione. La visibilità non cambia mai (resta privato). Richiede permesso Administration sul token.",
                 obj({"name": s, "description": s, "new_name": s, "topics": s, "archived": b}, ["name"]), guarded(coding.repo_edit), available=on)
    reg.register("code_repo_delete", "ELIMINA DEFINITIVAMENTE un repository creato da JARVIS (solo se privato). Prima di chiamarla spiega all'utente quale repository elimini e perché: serve la sua conferma esplicita, senza OK non succede nulla.",
                 obj({"name": s}, ["name"]), delete_repo, available=on)
    reg.register("code_audit", "Registro delle operazioni sui repository (creati, modificati, eliminati, adottati).", obj({"n": i}), guarded(coding.audit), available=on)
    # ---- sandbox
    reg.register("code_tree", "Albero dei file della sandbox (profondità regolabile).", obj({"path": s, "depth": i}), guarded(coding.tree), available=on)
    reg.register("code_find", "Trova file per nome con un glob (es. *.py, test_*).", obj({"pattern": s}, ["pattern"]), guarded(coding.find), available=on)
    reg.register("code_move", "Sposta o rinomina un file nella sandbox.", obj({"src": s, "dst": s}, ["src", "dst"]), guarded(coding.move), available=on)
    reg.register("code_append", "Aggiunge testo in fondo a un file (lo crea se manca).", obj({"path": s, "content": s}, ["path", "content"]), guarded(coding.append), available=on)
    reg.register("code_diff", "Differenze non ancora committate (diff unificato), di tutta la sandbox o di un file.", obj({"path": s}), guarded(coding.diff), available=on)
    reg.register("code_discard", "Annulla le modifiche non committate: un file oppure tutto (path=all).", obj({"path": s}), guarded(coding.discard), available=on)
    reg.register("code_replace", "Sostituzione con regex in più file. Di default solo anteprima (dry_run=true): rilancia con dry_run=false per applicare.",
                 obj({"pattern": s, "replacement": s, "glob": s, "dry_run": b}, ["pattern", "replacement"]), guarded(coding.replace_all), available=on)
    reg.register("code_stats", "Statistiche della sandbox: file, righe per estensione, TODO/FIXME.", obj({}), guarded(coding.stats), available=on)
    reg.register("code_scaffold", "Crea nella sandbox uno scheletro di progetto con test e CI: python-cli, fastapi-api, node-express-api, static-site, telegram-bot. Non sovrascrive file esistenti.",
                 obj({"kind": s, "name": s, "overwrite": b}, ["kind"]), guarded(coding.scaffold), available=on)
    # ---- rami, cronologia, PR, issue, rilasci, CI
    reg.register("code_branches", "Elenca i rami del repository.", obj({}), guarded(coding.branches), available=on)
    reg.register("code_branch_delete", "Elimina un ramo (mai il principale).", obj({"name": s}, ["name"]), guarded(coding.branch_delete), available=on)
    reg.register("code_checkout", "Passa a un altro ramo esistente e riscarica la sandbox (richiede nessuna modifica non committata).", obj({"branch": s}, ["branch"]), guarded(coding.checkout), available=on)
    reg.register("code_log", "Ultimi commit del ramo attuale.", obj({"n": i}), guarded(coding.log), available=on)
    reg.register("code_prs", "Elenca le Pull Request (state: open, closed, all).", obj({"state": s}), guarded(coding.prs), available=on)
    reg.register("code_pr_comment", "Commenta una Pull Request.", obj({"number": i, "body": s}, ["number", "body"]), guarded(coding.pr_comment), available=on)
    reg.register("code_pr_close", "Chiude una Pull Request senza unirla.", obj({"number": i}, ["number"]), guarded(coding.pr_close), available=on)
    reg.register("code_issues", "Elenca le issue (state: open, closed, all).", obj({"state": s}), guarded(issues), available=on)
    reg.register("code_issue_create", "Apre una issue (labels separate da virgola).", obj({"title": s, "body": s, "labels": s}, ["title"]), guarded(coding.issue_create), available=on)
    reg.register("code_issue_comment", "Commenta una issue.", obj({"number": i, "body": s}, ["number", "body"]), guarded(coding.issue_comment), available=on)
    reg.register("code_issue_close", "Chiude una issue.", obj({"number": i}, ["number"]), guarded(coding.issue_close), available=on)
    reg.register("code_release", "Pubblica una release (tag, titolo, note) sul ramo principale.", obj({"tag": s, "title": s, "notes": s}, ["tag"]), guarded(coding.release), available=on)
    reg.register("code_ci_run", "Avvia a mano un workflow di CI (workflow_dispatch).", obj({"workflow": s, "ref": s}), guarded(coding.ci_run), available=on)
    reg.register("code_ci_runs", "Ultime esecuzioni della CI.", obj({"n": i}), guarded(coding.ci_runs), available=on)
    reg.register("code_wait_checks", "Attende (fino a timeout secondi, max 110) che la CI finisca e riporta l'esito.", obj({"timeout": i}), guarded(coding.wait_checks), available=on, timeout=125)
    # ---- mappa a grafo del codice (stile Graphify): orientarsi con poche centinaia di token
    reg.register("code_graph", "Mappa a grafo del codice della sandbox: file, simboli (classi/funzioni con riga e firma), chiamate e importazioni, i simboli più collegati e i punti d'ingresso. "
                 "Usala PRIMA di leggere i file: poi code_read solo sulle righe indicate. Con 'query' cerca un simbolo.",
                 obj({"query": s}), guarded(lambda query="": graph_tool(coding.code_map, query)), available=on)
    reg.register("code_symbol", "Dove è definito un simbolo (classe/funzione/metodo), la sua firma, chi lo usa e cosa usa.", obj({"name": s}, ["name"]),
                 guarded(lambda name: graph_tool(coding.code_symbol, name)), available=on)
    reg.register("code_deps", "Dipendenze di un file: cosa importa, da chi è importato, cosa definisce.", obj({"path": s}, ["path"]),
                 guarded(lambda path: graph_tool(coding.code_deps, path)), available=on)
    reg.register("code_path", "Il percorso di chiamate/importazioni che collega due simboli o file del codice.", obj({"a": s, "b": s}, ["a", "b"]),
                 guarded(lambda a, b: graph_tool(coding.code_path, a, b)), available=on)
