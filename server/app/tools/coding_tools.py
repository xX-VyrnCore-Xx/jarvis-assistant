"""Strumenti delle sessioni di coding (sandbox + repository GitHub privato creato da JARVIS). Vedi `coding.py` per le regole di sicurezza."""
from ..coding import CodingError, CodingService
from . import UNTRUSTED, ToolRegistry


def register_coding_tools(reg: ToolRegistry, coding: CodingService, pending) -> None:
    on = lambda: coding.enabled  # noqa: E731
    s = {"type": "string"}
    b = {"type": "boolean"}
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
        rows = await coding.repos()
        return ("Repository creati da JARVIS: " + ", ".join(rows)) if rows else "Nessun repository creato da JARVIS finora."

    async def status() -> str:
        return coding.status()

    reg.register("code_start_session", "Inizia una sessione di coding: crea un repository GitHub PRIVATO (sempre privato) e la sandbox. PRIMA di chiamarla CHIEDI all'utente: nome del repository, descrizione, se aggiungere il README e quale licenza (MIT, Apache-2.0, GPL-3.0, BSD-3-Clause, Unlicense, oppure nessuna). Serve poi la sua conferma.",
                 obj({"name": s, "description": s, "readme": b, "license": s}, ["name"]), start, available=on)
    reg.register("code_resume", "Riprende una sessione di coding su un repository creato in precedenza da JARVIS (nome o proprietario/nome).", obj({"name": s}, ["name"]), guarded(coding.resume), available=on)
    reg.register("code_sessions", "Elenca i repository creati da JARVIS su cui può lavorare.", obj({}), sessions, available=on)
    reg.register("code_status", "Stato della sessione di coding: repository, rami, PR, file modificati non ancora committati.", obj({}), status)
    reg.register("code_ls", "Elenca i file della sandbox (con quelli modificati/eliminati). 'path' filtra per prefisso.", obj({"path": s}), guarded(coding.ls), available=on)
    reg.register("code_read", "Legge un file della sandbox con numeri di riga (max 800 righe per volta; usa start per continuare).", obj({"path": s, "start": {"type": "integer"}, "lines": {"type": "integer"}}, ["path"]), guarded(read), available=on)
    reg.register("code_write", "Crea o sovrascrive un file nella sandbox (max 200 KB). Niente segreti nel codice: usa variabili d'ambiente.", obj({"path": s, "content": s}, ["path", "content"]), guarded(coding.write), available=on)
    reg.register("code_edit", "Sostituisce un testo esatto in un file (deve comparire una sola volta, salvo replace_all). Per modifiche piccole preferiscilo a riscrivere il file.",
                 obj({"path": s, "old": s, "new": s, "replace_all": b}, ["path", "old", "new"]), guarded(coding.edit), available=on)
    reg.register("code_delete", "Elimina un file dalla sandbox.", obj({"path": s}, ["path"]), guarded(coding.delete), available=on)
    reg.register("code_search", "Cerca un'espressione regolare in tutti i file della sandbox.", obj({"pattern": s}, ["pattern"]), guarded(coding.search), available=on)
    reg.register("code_commit", "Committa tutte le modifiche della sandbox su GitHub. Di norma su un ramo di lavoro (creato da solo); direct=true scrive sul ramo principale. Messaggio chiaro e breve. Rifiuta file con chiavi/segreti.",
                 obj({"message": s, "direct": b, "branch": s}, ["message"]), guarded(coding.commit), available=on)
    reg.register("code_sync", "Riscarica la sandbox dall'ultimo commit su GitHub (richiede che non ci siano modifiche non committate).", obj({}), guarded(coding.sync), available=on)
    reg.register("code_open_pr", "Apre una Pull Request dal ramo di lavoro verso il principale.", obj({"title": s, "body": s}, ["title"]), guarded(coding.open_pr), available=on)
    reg.register("code_checks", "Stato della CI (GitHub Actions) sul commit attuale: none, pending, success, failure.", obj({}), guarded(checks), available=on)
    reg.register("code_ci_logs", "Log dei controlli di CI falliti (ultime righe), per capire cosa correggere.", obj({}), guarded(ci_logs), available=on)
    reg.register("code_add_ci", "Scrive nella sandbox un workflow di CI minimo (python o node) in .github/workflows/ci.yml: i test girano su GitHub, mai sul server.", obj({"language": s}, ["language"]), guarded(coding.add_ci), available=on)
    reg.register("code_merge", "Unisce la PR nel ramo principale (squash) e aggiorna la sandbox. Solo se non ci sono modifiche non committate e la CI è verde o assente.", obj({}), guarded(coding.merge), available=on)
