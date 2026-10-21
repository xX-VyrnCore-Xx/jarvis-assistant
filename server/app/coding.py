"""Sessioni di coding: JARVIS lavora su un repository GitHub PRIVATO creato da lui, in una sandbox virtuale (cartella di lavoro isolata del server).

Come funziona e perché è sicuro:
- Nella sandbox i file si leggono, scrivono e modificano, ma **nessun codice viene eseguito sul server** (che contiene le chiavi dell'utente):
  i test girano nella CI di GitHub (GitHub Actions), i cui risultati e log JARVIS legge per correggersi da solo.
- Tocca solo i repository che ha creato lui (registro nel database); i repository sono sempre privati; non esistono strumenti per eliminare repository,
  cambiare visibilità o forzare push; i file con chiavi/segreti o con nomi tipo `.env` vengono rifiutati prima del commit.
- Commit su un ramo di lavoro (o diretto sul ramo principale se richiesto), Pull Request, controllo della CI, merge (squash) solo a CI verde o assente.
- Tutto passa dall'API REST di GitHub con il token dell'utente (`GITHUB_TOKEN`, mai nei log né nelle risposte)."""
import asyncio
import base64
import hashlib
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .config import Settings
from .privacy import STANDARD, Redactor

log = logging.getLogger("jarvis.coding")
API = "https://api.github.com"
LICENSES = {"mit": "mit", "apache-2.0": "apache-2.0", "apache": "apache-2.0", "gpl-3.0": "gpl-3.0", "gpl": "gpl-3.0", "bsd-3-clause": "bsd-3-clause", "bsd": "bsd-3-clause",
            "unlicense": "unlicense", "mpl-2.0": "mpl-2.0", "none": None, "nessuna": None, "": None}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,60}$")
MAX_FILE, MAX_FILES, MAX_TOTAL = 200_000, 400, 8_000_000
LITERAL_SECRET = re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token|private[_-]?key)\w*\s*[:=]\s*[\"'][A-Za-z0-9/+_=.-]{16,}[\"']")
BLOCKED_NAMES = re.compile(r"(^|/)(\.env(\..*)?|id_rsa|id_ed25519|.*\.(pem|key|p12|pfx|keystore|jks)|credentials\.json|secrets?\.(json|ya?ml))$", re.I)
CI_TEMPLATES = {
    "python": "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: {python-version: '3.12'}\n"
              "      - run: pip install -r requirements.txt pytest || pip install pytest\n      - run: python -m pytest -q\n",
    "node": "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with: {node-version: 22}\n"
            "      - run: npm ci || npm install\n      - run: npm test --if-present\n      - run: npm run build --if-present\n",
}


class CodingError(RuntimeError):
    """Messaggio sicuro da mostrare all'utente (mai contiene il token)."""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "lavoro"


class GitHub:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._token = settings.github_token
        self._client = client or httpx.AsyncClient(timeout=30, follow_redirects=True)
        self._me = ""

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    async def call(self, method: str, path: str, body=None, params=None, ok: tuple[int, ...] = (200, 201, 204)):
        if not self._token:
            raise CodingError("GITHUB_TOKEN non configurato su Render.")
        try:
            r = await self._client.request(method, API + path, json=body, params=params, headers={
                "Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "jarvis-assistant"})
        except httpx.HTTPError as e:
            raise CodingError(f"GitHub non raggiungibile ({type(e).__name__}).") from e
        if r.status_code in ok:
            return r.json() if r.content and "json" in r.headers.get("content-type", "") else r.text
        msg = ""
        try:
            msg = str(r.json().get("message", ""))[:200]
        except ValueError:
            pass
        hint = {401: " Token non valido o scaduto.", 403: " Permessi insufficienti o limite di richieste raggiunto.", 404: " Non trovato (o il token non vi accede).", 409: " Conflitto.", 422: " Richiesta non valida."}.get(r.status_code, "")
        raise CodingError(f"GitHub: HTTP {r.status_code}{hint} {msg}".strip())

    async def me(self) -> str:
        if not self._me:
            self._me = (await self.call("GET", "/user"))["login"]
        return self._me


@dataclass
class Session:
    repo: str  # proprietario/nome
    default_branch: str = "main"
    branch: str = ""  # ramo di lavoro (vuoto: ancora da creare)
    head: str = ""  # commit del ramo (o del principale) da cui parte la sandbox
    pr: int = 0
    base: dict[str, str] = field(default_factory=dict)  # percorso -> sha256 del contenuto sincronizzato
    ignored: int = 0
    root: Path = Path()


class CodingService:
    def __init__(self, settings: Settings, store, client: httpx.AsyncClient | None = None, root: Path | None = None):
        self.s, self.store = settings, store
        self.gh = GitHub(settings, client)
        self.root = root or Path("/tmp/jarvis-sandbox")
        self.session: Session | None = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.gh.enabled

    # ------------------------------------------------------------------ registro dei repository creati da JARVIS (gli unici che può toccare)
    async def repos(self) -> list[str]:
        try:
            return [r for r in json.loads(await self.store.get_setting("coding_repos") or "[]") if isinstance(r, str)]
        except ValueError:
            return []

    async def _register(self, full: str) -> None:
        rows = await self.repos()
        if full not in rows:
            await self.store.set_setting("coding_repos", json.dumps(rows + [full]))

    def prompt_block(self) -> str:
        """Testo per il prompt di sistema quando c'è una sessione attiva (serve anche al router dei modelli)."""
        s = self.session
        if not s:
            return ""
        return (f"Sessione di coding attiva: repository privato {s.repo} (ramo principale {s.default_branch}, ramo di lavoro {s.branch or 'non ancora creato'}"
                f"{', PR #%d aperta' % s.pr if s.pr else ''}). Lavori nella sandbox con code_*: scrivi i file, committa spesso con messaggi chiari, apri la PR, controlla la CI (code_checks), "
                "correggi dai log, poi unisci (code_merge). Il codice NON si esegue sul server: i test girano nella CI di GitHub (code_add_ci se manca). Non inventare file che non hai letto.")

    # ------------------------------------------------------------------ sandbox: file
    def _path(self, rel: str) -> Path:
        s = self._need()
        rel = (rel or "").strip()
        if rel.startswith(("/", "\\")):
            raise CodingError("Usa percorsi relativi alla radice del repository.")
        if not rel or ".." in Path(rel).parts or rel.startswith(".git/") or rel == ".git" or "\x00" in rel or len(rel) > 200:
            raise CodingError("Percorso non valido.")
        if BLOCKED_NAMES.search(rel):
            raise CodingError("File con credenziali (es. .env, chiavi, .pem): non si creano nel repository.")
        p = (s.root / rel).resolve()
        if s.root.resolve() not in p.parents and p != s.root.resolve():
            raise CodingError("Percorso fuori dalla sandbox.")
        return p

    def _need(self) -> Session:
        if not self.session:
            raise CodingError("Nessuna sessione di coding attiva: usa code_start_session (nuovo repository) o code_resume.")
        return self.session

    def _files(self) -> dict[str, bytes]:
        s = self._need()
        out = {}
        for p in sorted(s.root.rglob("*")):
            if p.is_file() and not p.is_symlink():
                out[p.relative_to(s.root).as_posix()] = p.read_bytes()
        return out

    def ls(self, path: str = "") -> str:
        s = self._need()
        files = self._files()
        rows = [f"{k}  ({len(v)} B){'  *modificato*' if hashlib.sha256(v).hexdigest() != s.base.get(k) else ''}" for k, v in files.items() if not path or k.startswith(path.strip('/'))]
        gone = [f"{k}  *eliminato*" for k in s.base if k not in files]
        return "\n".join(rows + gone) or "La sandbox è vuota."

    def read(self, path: str, start: int = 1, lines: int = 400) -> str:
        p = self._path(path)
        if not p.is_file():
            raise CodingError("File non trovato nella sandbox.")
        text = p.read_text(encoding="utf-8", errors="replace").splitlines()
        part = text[max(0, start - 1):max(0, start - 1) + max(1, min(lines, 800))]
        return "\n".join(f"{i}\t{l}" for i, l in enumerate(part, start)) + (f"\n[…{len(text) - start - len(part) + 1} righe ancora]" if start - 1 + len(part) < len(text) else "")

    def write(self, path: str, content: str) -> str:
        p = self._path(path)
        data = content.encode()
        if len(data) > MAX_FILE:
            raise CodingError(f"File troppo grande (massimo {MAX_FILE // 1000} KB): dividilo.")
        files = self._files()
        if path.strip("/") not in files and len(files) >= MAX_FILES:
            raise CodingError(f"Troppi file (massimo {MAX_FILES}).")
        if sum(len(v) for k, v in files.items() if k != path.strip("/")) + len(data) > MAX_TOTAL:
            raise CodingError("La sandbox ha raggiunto il limite di spazio.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Scritto {path} ({len(data)} B, {content.count(chr(10)) + 1} righe)."

    def edit(self, path: str, old: str, new: str, replace_all: bool = False) -> str:
        p = self._path(path)
        if not p.is_file():
            raise CodingError("File non trovato nella sandbox.")
        text = p.read_text(encoding="utf-8")
        n = text.count(old)
        if not old or n == 0:
            raise CodingError("Il testo da sostituire non c'è nel file (controlla con code_read: deve combaciare esattamente).")
        if n > 1 and not replace_all:
            raise CodingError(f"Il testo compare {n} volte: aggiungi contesto per renderlo unico, oppure usa replace_all.")
        p.write_text(text.replace(old, new) if replace_all else text.replace(old, new, 1), encoding="utf-8")
        return f"Modificato {path} ({n if replace_all else 1} sostituzione/i)."

    def delete(self, path: str) -> str:
        p = self._path(path)
        if not p.is_file():
            raise CodingError("File non trovato nella sandbox.")
        p.unlink()
        return f"Eliminato {path} (sparirà dal repository al prossimo commit)."

    def search(self, pattern: str, limit: int = 40) -> str:
        try:
            rx = re.compile(pattern, re.I)
        except re.error:
            raise CodingError("Espressione regolare non valida.") from None
        out = []
        for k, v in self._files().items():
            for i, line in enumerate(v.decode("utf-8", errors="ignore").splitlines(), 1):
                if rx.search(line):
                    out.append(f"{k}:{i}: {line.strip()[:160]}")
                    if len(out) >= limit:
                        return "\n".join(out) + "\n[…altri risultati omessi]"
        return "\n".join(out) or "Nessuna corrispondenza."

    # ------------------------------------------------------------------ sincronizzazione con GitHub
    async def _sync(self, ref: str) -> None:
        s = self._need()
        owner_repo = s.repo
        commit = await self.gh.call("GET", f"/repos/{owner_repo}/commits/{ref}")
        tree = await self.gh.call("GET", f"/repos/{owner_repo}/git/trees/{commit['commit']['tree']['sha']}", params={"recursive": "1"})
        shutil.rmtree(s.root, ignore_errors=True)
        s.root.mkdir(parents=True, exist_ok=True)
        s.base, s.ignored, s.head = {}, 0, commit["sha"]
        todo = [t for t in tree.get("tree", []) if t["type"] == "blob"]
        gate = asyncio.Semaphore(8)
        total = 0

        async def fetch(t: dict) -> None:
            nonlocal total
            if t.get("size", 0) > MAX_FILE or BLOCKED_NAMES.search(t["path"]) or len(s.base) >= MAX_FILES or total > MAX_TOTAL:
                s.ignored += 1
                return
            async with gate:
                blob = await self.gh.call("GET", f"/repos/{owner_repo}/git/blobs/{t['sha']}")
            raw = base64.b64decode(blob["content"]) if blob.get("encoding") == "base64" else str(blob["content"]).encode()
            if b"\x00" in raw:  # binari: restano nel repository, non nella sandbox
                s.ignored += 1
                return
            p = (s.root / t["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            s.base[t["path"]] = hashlib.sha256(raw).hexdigest()
            total += len(raw)

        await asyncio.gather(*(fetch(t) for t in todo))

    async def _open(self, repo: str, default_branch: str, ref: str) -> str:
        self.session = Session(repo, default_branch, root=self.root / repo.replace("/", "__"))
        await self._sync(ref)
        return f"{len(self.session.base)} file sincronizzati" + (f", {self.session.ignored} ignorati (binari/grandi/segreti)" if self.session.ignored else "")

    # ------------------------------------------------------------------ ciclo di vita
    async def create_repo(self, name: str, description: str, readme: bool, license_key: str) -> str:
        if not NAME_RE.fullmatch(name) or name.endswith(".git"):
            raise CodingError("Nome non valido: lettere, numeri, punto, trattino e underscore (max 60).")
        if license_key.lower() not in LICENSES:
            raise CodingError("Licenza non riconosciuta: " + ", ".join(k for k in LICENSES if k and k not in ("apache", "gpl", "bsd", "nessuna")) + " o nessuna.")
        today = time.strftime("%Y-%m-%d")
        used = (await self.store.get_setting("coding_created_today") or "").split(":")
        count = int(used[1]) if len(used) == 2 and used[0] == today and used[1].isdigit() else 0
        if count >= self.s.coding_repos_per_day:
            raise CodingError(f"Limite giornaliero di {self.s.coding_repos_per_day} repository creati da JARVIS raggiunto.")
        lic = LICENSES[license_key.lower()]
        body = {"name": name, "description": (description or "")[:300], "private": True, "auto_init": bool(readme or lic)}
        if lic:
            body["license_template"] = lic
        repo = await self.gh.call("POST", "/user/repos", body)
        full = repo["full_name"]
        await self.store.set_setting("coding_created_today", f"{today}:{count + 1}")
        await self._register(full)
        default = repo.get("default_branch") or "main"
        if not body["auto_init"]:  # repository vuoto: l'API dei commit non funziona finché non c'è un primo commit
            await self.gh.call("PUT", f"/repos/{full}/contents/.gitignore", {"message": "Commit iniziale", "content": base64.b64encode(b"__pycache__/\nnode_modules/\n.env\n*.log\n").decode(), "branch": default})
        info = await self._open(full, default, default)
        return f"Repository privato creato: https://github.com/{full} ({info}). Sandbox pronta."

    async def resume(self, name: str) -> str:
        known = await self.repos()
        full = next((r for r in known if r.lower() == name.lower() or r.split("/")[-1].lower() == name.lower()), "")
        if not full:
            raise CodingError("Quel repository non è tra quelli creati da JARVIS: " + (", ".join(known) or "nessuno ancora") + ".")
        repo = await self.gh.call("GET", f"/repos/{full}")
        if not repo.get("private"):
            raise CodingError("Il repository non è privato: per sicurezza non ci lavoro.")
        info = await self._open(full, repo.get("default_branch") or "main", repo.get("default_branch") or "main")
        return f"Sessione ripresa su {full}: {info}."

    async def sync(self) -> str:
        s = self._need()
        changed = self._changes()
        if changed[0] or changed[1]:
            raise CodingError("Ci sono modifiche non committate: committa prima (o sarebbero perse).")
        await self._sync(s.branch or s.default_branch)
        return f"Sandbox aggiornata: {len(s.base)} file all'ultimo commit {s.head[:7]}."

    def _changes(self) -> tuple[dict[str, bytes], list[str]]:
        s = self._need()
        files = self._files()
        mod = {k: v for k, v in files.items() if hashlib.sha256(v).hexdigest() != s.base.get(k)}
        gone = [k for k in s.base if k not in files]
        return mod, gone

    def _scan(self, mod: dict[str, bytes]) -> None:
        """Rifiuta file che contengono chiavi, token o IBAN (non carte/codici fiscali: nel codice darebbero troppi falsi positivi)."""
        bad = []
        for k, v in mod.items():
            text = v.decode("utf-8", errors="ignore")
            if LITERAL_SECRET.search(text) or any(rx.search(text) and (chk is None or any(chk(m.group(0)) for m in rx.finditer(text))) for kind, rx, chk in STANDARD if kind in ("IBAN", "CHIAVE")):
                bad.append(k)
        if bad:
            raise CodingError("Commit bloccato: sembrano contenere chiavi, token o dati bancari in " + ", ".join(bad[:5]) + ". Usa variabili d'ambiente.")

    async def commit(self, message: str, direct: bool = False, branch: str = "") -> str:
        async with self._lock:
            s = self._need()
            mod, gone = self._changes()
            if not mod and not gone:
                return "Niente da committare: nessuna modifica."
            self._scan(mod)
            msg = (message or "").strip()[:200]
            if len(msg) < 4:
                raise CodingError("Serve un messaggio di commit chiaro.")
            target = s.default_branch if direct else (branch or s.branch or f"jarvis/{slug(msg)}-{time.strftime('%m%d%H%M')}")
            if not BRANCH_RE.fullmatch(target) or target.endswith((".lock", "/")) or ".." in target:
                raise CodingError("Nome del ramo non valido.")
            repo = s.repo
            exists = True
            try:
                parent = (await self.gh.call("GET", f"/repos/{repo}/git/ref/heads/{target}"))["object"]["sha"]
            except CodingError:
                exists = False
                parent = (await self.gh.call("GET", f"/repos/{repo}/git/ref/heads/{s.default_branch}"))["object"]["sha"]
            if exists and target == s.branch and parent != s.head:
                raise CodingError("Il ramo su GitHub è cambiato dopo l'ultima sincronizzazione: usa code_sync prima di continuare.")
            base_tree = (await self.gh.call("GET", f"/repos/{repo}/git/commits/{parent}"))["tree"]["sha"]
            entries = []
            for path, raw in mod.items():
                blob = await self.gh.call("POST", f"/repos/{repo}/git/blobs", {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
                entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            entries += [{"path": g, "mode": "100644", "type": "blob", "sha": None} for g in gone]
            tree = await self.gh.call("POST", f"/repos/{repo}/git/trees", {"base_tree": base_tree, "tree": entries})
            commit = await self.gh.call("POST", f"/repos/{repo}/git/commits", {"message": msg, "tree": tree["sha"], "parents": [parent]})
            if exists:
                await self.gh.call("PATCH", f"/repos/{repo}/git/refs/heads/{target}", {"sha": commit["sha"], "force": False})
            else:
                await self.gh.call("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{target}", "sha": commit["sha"]})
            s.base = {k: hashlib.sha256(v).hexdigest() for k, v in self._files().items()}
            s.head = commit["sha"]
            if not direct:
                s.branch = target
            return f"Commit {commit['sha'][:7]} su «{target}»: {len(mod)} file modificati, {len(gone)} eliminati."

    async def open_pr(self, title: str, body: str = "") -> str:
        s = self._need()
        if not s.branch:
            raise CodingError("Nessun ramo di lavoro: fai prima un commit (non diretto).")
        if s.pr:
            return f"La PR #{s.pr} è già aperta: https://github.com/{s.repo}/pull/{s.pr}"
        try:
            pr = await self.gh.call("POST", f"/repos/{s.repo}/pulls", {"title": title[:200] or s.branch, "head": s.branch, "base": s.default_branch, "body": body[:4000]})
        except CodingError:
            owner = s.repo.split("/")[0]
            rows = await self.gh.call("GET", f"/repos/{s.repo}/pulls", params={"head": f"{owner}:{s.branch}", "state": "open"})
            if not rows:
                raise
            pr = rows[0]
        s.pr = pr["number"]
        return f"PR #{s.pr} aperta: {pr['html_url']}"

    async def checks(self) -> dict:
        s = self._need()
        runs = (await self.gh.call("GET", f"/repos/{s.repo}/commits/{s.head}/check-runs")).get("check_runs", [])
        if not runs:
            return {"state": "none", "runs": []}
        rows = [{"id": r["id"], "name": r["name"], "status": r["status"], "conclusion": r.get("conclusion") or ""} for r in runs]
        if any(r["status"] != "completed" for r in rows):
            state = "pending"
        elif any(r["conclusion"] not in ("success", "neutral", "skipped") for r in rows):
            state = "failure"
        else:
            state = "success"
        return {"state": state, "runs": rows}

    async def ci_logs(self, max_chars: int = 5000) -> str:
        c = await self.checks()
        bad = [r for r in c["runs"] if r["status"] == "completed" and r["conclusion"] not in ("success", "neutral", "skipped")]
        if not bad:
            return f"Nessun controllo fallito (stato: {c['state']})."
        s = self._need()
        out = []
        for r in bad[:2]:
            try:
                text = await self.gh.call("GET", f"/repos/{s.repo}/actions/jobs/{r['id']}/logs")
            except CodingError as e:
                text = f"(log non disponibili: {e})"
            text = re.sub(r"\x1b\[[0-9;]*m|^\d{4}-\d\d-\d\dT[\d:.]+Z ", "", str(text), flags=re.M)
            out.append(f"== {r['name']} ({r['conclusion']}) ==\n{Redactor('standard').mask(text)[-max_chars:]}")
        return "\n\n".join(out)

    async def add_ci(self, language: str) -> str:
        lang = language.lower().strip()
        if lang not in CI_TEMPLATES:
            raise CodingError("Linguaggi disponibili: " + ", ".join(CI_TEMPLATES) + ".")
        self.write(".github/workflows/ci.yml", CI_TEMPLATES[lang])
        return "Workflow di CI scritto in .github/workflows/ci.yml: committa e apri la PR per farlo girare (il token deve avere il permesso «workflow»)."

    async def merge(self) -> str:
        s = self._need()
        if not s.pr:
            raise CodingError("Nessuna PR aperta: usa code_open_pr.")
        mod, gone = self._changes()
        if mod or gone:
            raise CodingError("Ci sono modifiche non committate: committa prima.")
        c = await self.checks()
        if c["state"] in ("pending", "failure"):
            raise CodingError(f"CI {c['state']}: " + ("attendi che finisca (code_checks)." if c["state"] == "pending" else "leggi i log con code_ci_logs, correggi e committa."))
        await self.gh.call("PUT", f"/repos/{s.repo}/pulls/{s.pr}/merge", {"merge_method": "squash"})
        branch, pr = s.branch, s.pr
        try:
            await self.gh.call("DELETE", f"/repos/{s.repo}/git/refs/heads/{branch}")
        except CodingError:
            pass
        s.branch, s.pr = "", 0
        await self._sync(s.default_branch)
        return f"PR #{pr} unita nel ramo {s.default_branch} (squash); ramo «{branch}» eliminato. Sandbox aggiornata."

    def status(self) -> str:
        if not self.session:
            return "Nessuna sessione di coding attiva." + ("" if self.enabled else " GITHUB_TOKEN non è configurato su Render.")
        s = self.session
        mod, gone = self._changes()
        return (f"Repository privato {s.repo} · ramo principale {s.default_branch} · ramo di lavoro {s.branch or '—'} · PR {('#%d' % s.pr) if s.pr else '—'} · "
                f"{len(s.base)} file nella sandbox, {len(mod)} modificati e {len(gone)} eliminati non ancora committati.")
