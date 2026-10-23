"""Sessioni di coding: JARVIS lavora su un repository GitHub PRIVATO creato da lui, in una sandbox virtuale (cartella di lavoro isolata del server).

Come funziona e perché è sicuro:
- Nella sandbox i file si leggono, scrivono e modificano, ma **nessun codice viene eseguito sul server** (che contiene le chiavi dell'utente):
  i test girano nella CI di GitHub (GitHub Actions), i cui risultati e log JARVIS legge per correggersi da solo.
- Tocca solo i repository che ha creato lui (registro nel database + argomento `jarvis-managed`); i repository sono sempre privati; non esiste modo di cambiare
  visibilità o forzare push; un repository si elimina solo se è nel registro, privato, dopo conferma esplicita dell'utente, con limite giornaliero e registro di controllo;
  i file con chiavi/segreti o con nomi tipo `.env` vengono rifiutati prima del commit.
- Commit su un ramo di lavoro (o diretto sul ramo principale se richiesto), Pull Request, controllo della CI, merge (squash) solo a CI verde o assente.
- Tutto passa dall'API REST di GitHub con il token dell'utente (`GITHUB_TOKEN`, mai nei log né nelle risposte)."""
import asyncio
import base64
import difflib
import fnmatch
import hashlib
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .codegraph import CodeGraph
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
TOPIC = "jarvis-managed"  # argomento messo sui repository creati da JARVIS: permette di ritrovarli se l'elenco nel database va perso
CI_TEMPLATES = {
    "python": "name: CI\non: [push, pull_request, workflow_dispatch]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: {python-version: '3.12'}\n"
              "      - run: pip install -r requirements.txt pytest || pip install pytest\n      - run: python -m pytest -q\n",
    "node": "name: CI\non: [push, pull_request, workflow_dispatch]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with: {node-version: 22}\n"
            "      - run: npm ci || npm install\n      - run: npm test --if-present\n      - run: npm run build --if-present\n",
}


SCAFFOLDS = {
    "python-cli": {
        "{pkg}/__init__.py": "",
        "{pkg}/cli.py": "import argparse\n\n\ndef main(argv=None) -> int:\n    p = argparse.ArgumentParser(prog=\"{name}\")\n    p.add_argument(\"--name\", default=\"mondo\")\n    a = p.parse_args(argv)\n    print(f\"Ciao, {a.name}!\")\n    return 0\n\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n",
        "tests/test_cli.py": "from {pkg}.cli import main\n\n\ndef test_main(capsys):\n    assert main([\"--name\", \"JARVIS\"]) == 0\n    assert \"JARVIS\" in capsys.readouterr().out\n",
        "requirements.txt": "pytest\n",
        ".github/workflows/ci.yml": CI_TEMPLATES["python"],
    },
    "fastapi-api": {
        "app/__init__.py": "",
        "app/main.py": "from fastapi import FastAPI\n\napp = FastAPI(title=\"{name}\")\n\n\n@app.get(\"/health\")\ndef health():\n    return {\"ok\": True}\n",
        "tests/test_api.py": "from fastapi.testclient import TestClient\n\nfrom app.main import app\n\n\ndef test_health():\n    assert TestClient(app).get(\"/health\").json() == {\"ok\": True}\n",
        "requirements.txt": "fastapi\nhttpx\nuvicorn\npytest\n",
        ".github/workflows/ci.yml": CI_TEMPLATES["python"],
    },
    "node-express-api": {
        "package.json": "{\n  \"name\": \"{pkg}\",\n  \"version\": \"0.1.0\",\n  \"type\": \"module\",\n  \"scripts\": {\"start\": \"node src/server.js\", \"test\": \"node --test\"}\n}\n",
        "src/app.js": "import http from \"node:http\";\n\nexport function createServer() {\n  return http.createServer((req, res) => {\n    res.setHeader(\"content-type\", \"application/json\");\n    res.end(JSON.stringify({ ok: req.url === \"/health\" }));\n  });\n}\n",
        "src/server.js": "import { createServer } from \"./app.js\";\n\ncreateServer().listen(process.env.PORT || 3000);\n",
        "test/app.test.js": "import test from \"node:test\";\nimport assert from \"node:assert\";\nimport { createServer } from \"../src/app.js\";\n\ntest(\"health\", async () => {\n  const s = createServer().listen(0);\n  const { port } = s.address();\n  const r = await fetch(`http://127.0.0.1:${port}/health`);\n  assert.deepEqual(await r.json(), { ok: true });\n  s.close();\n});\n",
        ".github/workflows/ci.yml": CI_TEMPLATES["node"],
    },
    "static-site": {
        "index.html": "<!doctype html>\n<html lang=\"it\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>{name}</title>\n<link rel=\"stylesheet\" href=\"style.css\">\n</head>\n<body>\n<main><h1>{name}</h1><p>Sito pronto.</p></main>\n<script src=\"main.js\"></script>\n</body>\n</html>\n",
        "style.css": "body{font-family:system-ui,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh}\n",
        "main.js": "console.log(\"{name} pronto\");\n",
    },
    "telegram-bot": {
        "bot/__init__.py": "",
        "bot/handlers.py": "def reply(text: str) -> str:\n    return f\"Hai scritto: {text}\" if text else \"Dimmi qualcosa.\"\n",
        "bot/main.py": "import os\n\nimport httpx\n\nfrom .handlers import reply\n\n\ndef run() -> None:\n    token, offset = os.environ[\"TELEGRAM_TOKEN\"], 0\n    api = f\"https://api.telegram.org/bot{token}\"\n    while True:\n        for u in httpx.get(f\"{api}/getUpdates\", params={\"offset\": offset, \"timeout\": 30}, timeout=40).json().get(\"result\", []):\n            offset = u[\"update_id\"] + 1\n            m = u.get(\"message\") or {}\n            if m.get(\"chat\"):\n                httpx.post(f\"{api}/sendMessage\", json={\"chat_id\": m[\"chat\"][\"id\"], \"text\": reply(m.get(\"text\", \"\"))})\n\n\nif __name__ == \"__main__\":\n    run()\n",
        "tests/test_handlers.py": "from bot.handlers import reply\n\n\ndef test_reply():\n    assert reply(\"ciao\") == \"Hai scritto: ciao\"\n    assert reply(\"\")\n",
        "requirements.txt": "httpx\npytest\n",
        ".github/workflows/ci.yml": CI_TEMPLATES["python"],
    },
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
    base_text: dict[str, bytes] = field(default_factory=dict)  # contenuto dell'ultimo commit (per diff e ripristino)
    ignored: int = 0
    root: Path = Path()


class CodingService:
    def __init__(self, settings: Settings, store, client: httpx.AsyncClient | None = None, root: Path | None = None):
        self.s, self.store = settings, store
        self.gh = GitHub(settings, client)
        self.root = root or Path("/tmp/jarvis-sandbox")
        self.session: Session | None = None
        self._lock = asyncio.Lock()
        self._graph: tuple[str, CodeGraph] | None = None

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
                "correggi dai log, poi unisci (code_merge). Il codice NON si esegue sul server: i test girano nella CI di GitHub (code_add_ci se manca; code_wait_checks per attendere). Non inventare file che non hai letto. "
                "Per orientarti usa la mappa a grafo (code_graph, code_symbol, code_deps, code_path) invece di leggere interi file: costa molti meno token. Prima di modificare guarda code_tree/code_diff; per scheletri pronti code_scaffold. Eliminare un repository (code_repo_delete) richiede la conferma esplicita dell'utente: spiega quale e perché, poi attendi.")

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

    def search(self, pattern: str, glob: str = "*", context: int = 0, limit: int = 40) -> str:
        try:
            rx = re.compile(pattern, re.I)
        except re.error:
            raise CodingError("Espressione regolare non valida.") from None
        ctx, limit = max(0, min(context, 3)), max(1, min(limit, 200))
        out = []
        for k, v in self._files().items():
            if glob not in ("", "*") and not (fnmatch.fnmatch(k, glob) or fnmatch.fnmatch(k.rsplit("/", 1)[-1], glob)):
                continue
            lines = v.decode("utf-8", errors="ignore").splitlines()
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    if ctx:
                        out.append("\n".join(f"{k}:{j}{':' if j == i else '-'} {lines[j - 1].strip()[:160]}" for j in range(max(1, i - ctx), min(len(lines), i + ctx) + 1)) + "\n--")
                    else:
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
        s.base, s.base_text, s.ignored, s.head = {}, {}, 0, commit["sha"]
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
            s.base_text[t["path"]] = raw
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
        try:
            await self.gh.call("PUT", f"/repos/{full}/topics", {"names": [TOPIC]})
        except CodingError:
            pass  # solo comodità per ritrovarlo: non blocca la creazione
        await self._audit("creato", full)
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
            snap = self._files()
            s.base, s.base_text = {k: hashlib.sha256(v).hexdigest() for k, v in snap.items()}, dict(snap)
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

    # ------------------------------------------------------------------ elenco, modifica ed eliminazione dei repository creati da JARVIS
    async def _resolve(self, name: str) -> str:
        known = await self.repos()
        n = (name or "").strip().lower()
        full = next((r for r in known if r.lower() == n or r.split("/")[-1].lower() == n), "")
        if not full:
            raise CodingError("Quel repository non è tra quelli creati da JARVIS: " + (", ".join(known) or "nessuno ancora") + ".")
        return full

    async def _unregister(self, full: str) -> None:
        await self.store.set_setting("coding_repos", json.dumps([r for r in await self.repos() if r != full]))

    async def _audit(self, event: str, repo: str) -> None:
        try:
            rows = json.loads(await self.store.get_setting("coding_audit") or "[]")
        except ValueError:
            rows = []
        rows.append({"t": time.strftime("%Y-%m-%d %H:%M"), "e": event, "r": repo})
        await self.store.set_setting("coding_audit", json.dumps(rows[-60:]))

    async def audit(self, n: int = 15) -> str:
        try:
            rows = json.loads(await self.store.get_setting("coding_audit") or "[]")
        except ValueError:
            rows = []
        return "\n".join(f"{r['t']}  {r['e']}  {r['r']}" for r in rows[-n:][::-1]) or "Nessuna operazione registrata."

    async def list_repos(self) -> str:
        """Elenco completo dei repository creati da JARVIS, con i dettagli letti da GitHub; quelli eliminati altrove escono dall'elenco."""
        known = await self.repos()
        if not known:
            return "JARVIS non ha ancora creato repository (o l'elenco è vuoto: prova code_adopt per ritrovare quelli con l'argomento jarvis-managed)."
        gate = asyncio.Semaphore(6)

        async def one(full: str):
            async with gate:
                try:
                    return full, await self.gh.call("GET", f"/repos/{full}")
                except CodingError as e:
                    return full, None if "404" in str(e) else {"error": str(e)}

        out, gone = [], []
        for full, r in await asyncio.gather(*(one(f) for f in known)):
            if r is None:
                gone.append(full)
                continue
            if "error" in r:
                out.append(f"• {full} — errore nel leggerlo ({r['error'][:60]})")
                continue
            mark = " ◀ sessione attiva" if self.session and self.session.repo == full else ""
            out.append(f"• {'🔒' if r.get('private') else '⚠️ PUBBLICO'} {full}{mark} — {(r.get('description') or 'senza descrizione')[:80]} · aggiornato {str(r.get('pushed_at') or '')[:10]} · ramo {r.get('default_branch')} · "
                       f"{r.get('open_issues_count', 0)} issue/PR aperte · {r.get('size', 0)} KB{' · archiviato' if r.get('archived') else ''}")
        for full in gone:
            await self._unregister(full)
        tail = f"\nNon più su GitHub (tolti dall'elenco): {', '.join(gone)}." if gone else ""
        return f"{len(out)} repository creati da JARVIS:\n" + "\n".join(out) + tail

    async def adopt(self) -> str:
        """Ritrova i repository privati con l'argomento «jarvis-managed» (utile se l'elenco nel database è andato perso)."""
        found, known = [], set(await self.repos())
        for page in (1, 2, 3):
            rows = await self.gh.call("GET", "/user/repos", params={"per_page": 100, "page": page, "affiliation": "owner", "sort": "pushed"})
            for r in rows:
                if r.get("private") and TOPIC in (r.get("topics") or []) and r["full_name"] not in known:
                    found.append(r["full_name"])
            if len(rows) < 100:
                break
        for f in found:
            await self._register(f)
            await self._audit("adottato", f)
        return ("Ritrovati e aggiunti all'elenco: " + ", ".join(found)) if found else "Nessun repository nuovo con l'argomento jarvis-managed."

    async def repo_edit(self, name: str, description: str | None = None, new_name: str | None = None, topics: str | None = None, archived: bool | None = None) -> str:
        """Descrizione, nome, argomenti, archiviazione. La visibilità non si tocca mai: i repository restano privati."""
        full = await self._resolve(name)
        body: dict = {}
        if description is not None:
            body["description"] = description[:350]
        if new_name:
            if not NAME_RE.fullmatch(new_name) or new_name.endswith(".git"):
                raise CodingError("Nuovo nome non valido.")
            body["name"] = new_name
        if archived is not None:
            body["archived"] = bool(archived)
        res = ""
        if body:
            repo = await self.gh.call("PATCH", f"/repos/{full}", body)
            if repo.get("full_name") and repo["full_name"] != full:
                await self._unregister(full)
                await self._register(repo["full_name"])
                if self.session and self.session.repo == full:
                    self.session.repo = repo["full_name"]
                await self._audit(f"rinominato in {repo['full_name']}", full)
                full = repo["full_name"]
            res += "Aggiornato: " + ", ".join(body) + ". "
        if topics is not None:
            names = [t for t in dict.fromkeys(re.sub(r"[^a-z0-9-]", "", t.strip().lower().replace(" ", "-")) for t in topics.split(",")) if t][:9]
            await self.gh.call("PUT", f"/repos/{full}/topics", {"names": [TOPIC, *[n for n in names if n != TOPIC]]})
            res += "Argomenti: " + ", ".join([TOPIC, *names]) + ". "
        if not res:
            raise CodingError("Niente da modificare: indica descrizione, nuovo nome, argomenti o archiviazione.")
        await self._audit("modificato", full)
        return res.strip() + f" ({full})"

    async def delete_summary(self, name: str) -> tuple[str, str]:
        """(nome completo, descrizione per la richiesta di conferma) di un repository eliminabile."""
        full = await self._resolve(name)
        r = await self.gh.call("GET", f"/repos/{full}")
        if not r.get("private"):
            raise CodingError("Il repository non è privato: per sicurezza non lo elimino io.")
        return full, f"{full} — {(r.get('description') or 'senza descrizione')[:80]} · ultimo aggiornamento {str(r.get('pushed_at') or '')[:10]} · {r.get('size', 0)} KB · {r.get('open_issues_count', 0)} issue/PR aperte"

    async def delete_repo(self, name: str) -> str:
        """Eliminazione DEFINITIVA, ammessa solo per i repository creati da JARVIS e privati, e solo dopo la conferma dell'utente (la chiede lo strumento)."""
        full = await self._resolve(name)
        today = time.strftime("%Y-%m-%d")
        used = (await self.store.get_setting("coding_deleted_today") or "").split(":")
        count = int(used[1]) if len(used) == 2 and used[0] == today and used[1].isdigit() else 0
        if count >= self.s.coding_deletes_per_day:
            raise CodingError(f"Limite giornaliero di {self.s.coding_deletes_per_day} repository eliminati raggiunto.")
        r = await self.gh.call("GET", f"/repos/{full}")
        if not r.get("private"):
            raise CodingError("Il repository non è privato: per sicurezza non lo elimino io.")
        await self.gh.call("DELETE", f"/repos/{full}")
        await self.store.set_setting("coding_deleted_today", f"{today}:{count + 1}")
        await self._unregister(full)
        await self._audit("ELIMINATO", full)
        if self.session and self.session.repo == full:
            shutil.rmtree(self.session.root, ignore_errors=True)
            self.session = None
        return f"Repository {full} eliminato definitivamente da GitHub e dall'elenco."

    # ------------------------------------------------------------------ sandbox: strumenti in più
    def tree(self, path: str = "", depth: int = 3) -> str:
        s = self._need()
        files = {k: len(v) for k, v in self._files().items() if not path or k.startswith(path.strip("/"))}
        if not files:
            return "La sandbox è vuota." if not path else "Nessun file in quel percorso."
        root: dict = {}
        for k, size in sorted(files.items()):
            node = root
            parts = k.split("/")
            for p in parts[:-1]:
                node = node.setdefault(p + "/", {})
            node[parts[-1]] = size
        lines: list[str] = []

        def walk(node: dict, prefix: str, d: int) -> None:
            items = sorted(node.items(), key=lambda x: (not x[0].endswith("/"), x[0]))
            for i, (name, val) in enumerate(items):
                last = i == len(items) - 1
                lines.append(f"{prefix}{'└── ' if last else '├── '}{name}" + ("" if isinstance(val, dict) else f"  ({val} B)"))
                if isinstance(val, dict):
                    if d + 1 < depth:
                        walk(val, prefix + ("    " if last else "│   "), d + 1)
                    else:
                        lines.append(f"{prefix}{'    ' if last else '│   '}└── …")

        walk(root, "", 0)
        return f"{s.repo}\n" + "\n".join(lines[:300])

    def find(self, pattern: str) -> str:
        self._need()
        pat = pattern.strip() or "*"
        rows = [k for k in self._files() if fnmatch.fnmatch(k, pat) or fnmatch.fnmatch(k.rsplit("/", 1)[-1], pat)]
        return "\n".join(rows[:200]) + (f"\n[…{len(rows) - 200} altri]" if len(rows) > 200 else "") if rows else "Nessun file corrisponde."

    def move(self, src: str, dst: str) -> str:
        a, b = self._path(src), self._path(dst)
        if not a.is_file():
            raise CodingError("File di partenza non trovato.")
        if b.exists():
            raise CodingError("La destinazione esiste già.")
        b.parent.mkdir(parents=True, exist_ok=True)
        a.rename(b)
        return f"Spostato {src} → {dst} (al commit comparirà come eliminato + creato)."

    def append(self, path: str, content: str) -> str:
        p = self._path(path)
        old = p.read_text(encoding="utf-8") if p.is_file() else ""
        return self.write(path, old + ("" if not old or old.endswith("\n") else "\n") + content)

    def diff(self, path: str = "") -> str:
        s = self._need()
        files = self._files()
        out = []
        names = sorted({*files, *s.base_text} if not path else {path.strip("/")})
        for k in names:
            old, new = s.base_text.get(k), files.get(k)
            if old == new:
                continue
            a = (old or b"").decode("utf-8", errors="replace").splitlines()
            b = (new or b"").decode("utf-8", errors="replace").splitlines()
            tag = "nuovo" if old is None else "eliminato" if new is None else "modificato"
            body = "\n".join(difflib.unified_diff(a, b, f"a/{k}", f"b/{k}", lineterm="", n=2))
            out.append(f"### {k} ({tag})\n{body}")
        text = "\n\n".join(out)
        return (text[:7000] + "\n[…diff troncato]") if len(text) > 7000 else (text or "Nessuna modifica rispetto all'ultimo commit.")

    def discard(self, path: str = "all") -> str:
        s = self._need()
        if path in ("all", "", "*"):
            shutil.rmtree(s.root, ignore_errors=True)
            s.root.mkdir(parents=True, exist_ok=True)
            for k, v in s.base_text.items():
                p = s.root / k
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(v)
            return f"Tutte le modifiche non committate sono state annullate ({len(s.base_text)} file ripristinati)."
        key = path.strip("/")
        p = self._path(key)
        if key in s.base_text:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(s.base_text[key])
            return f"Ripristinato {key} all'ultimo commit."
        if p.is_file():
            p.unlink()
            return f"Eliminato {key} (non esisteva nell'ultimo commit)."
        raise CodingError("File non trovato.")

    def replace_all(self, pattern: str, replacement: str, glob: str = "*", dry_run: bool = True) -> str:
        """Sostituzione con espressione regolare in più file. Di default solo anteprima (dry_run): conta le corrispondenze senza scrivere."""
        self._need()
        if len(pattern) > 200:
            raise CodingError("Espressione troppo lunga.")
        try:
            rx = re.compile(pattern)
        except re.error:
            raise CodingError("Espressione regolare non valida.") from None
        hits, total = [], 0
        for k, v in self._files().items():
            if not (fnmatch.fnmatch(k, glob) or fnmatch.fnmatch(k.rsplit("/", 1)[-1], glob)):
                continue
            text = v.decode("utf-8", errors="ignore")
            new, n = rx.subn(replacement, text)
            if n:
                hits.append(f"{k}: {n}")
                total += n
                if not dry_run:
                    self._path(k).write_text(new, encoding="utf-8")
        if not hits:
            return "Nessuna corrispondenza."
        return ("Anteprima (nulla scritto): " if dry_run else "Sostituite ") + f"{total} occorrenze in {len(hits)} file:\n" + "\n".join(hits[:60]) + ("" if not dry_run else "\nRichiama con dry_run=false per applicare.")

    def stats(self) -> str:
        self._need()
        files = self._files()
        by_ext: dict[str, list[int]] = {}
        todo = 0
        for k, v in files.items():
            ext = k.rsplit(".", 1)[-1].lower() if "." in k.rsplit("/", 1)[-1] else "(senza)"
            text = v.decode("utf-8", errors="ignore")
            row = by_ext.setdefault(ext, [0, 0])
            row[0] += 1
            row[1] += text.count("\n") + 1
            todo += len(re.findall(r"\b(TODO|FIXME|XXX)\b", text))
        rows = sorted(by_ext.items(), key=lambda x: -x[1][1])[:12]
        return f"{len(files)} file, {sum(r[1] for r in by_ext.values())} righe, {todo} TODO/FIXME\n" + "\n".join(f"• .{e}: {n} file, {ln} righe" for e, (n, ln) in rows)

    def scaffold(self, kind: str, name: str = "app", overwrite: bool = False) -> str:
        """Scheletro di progetto pronto da committare: codice minimo, test e CI. I file già presenti non si toccano (salvo overwrite)."""
        k = kind.lower().strip()
        if k not in SCAFFOLDS:
            raise CodingError("Tipi disponibili: " + ", ".join(SCAFFOLDS) + ".")
        pkg = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_") or "app"
        made, skipped = [], []
        for rel, content in SCAFFOLDS[k].items():
            target = rel.replace("{pkg}", pkg)
            if self._path(target).exists() and not overwrite:
                skipped.append(target)
                continue
            self.write(target, content.replace("{pkg}", pkg).replace("{name}", name))
            made.append(target)
        return f"Scheletro «{k}» creato ({len(made)} file: {', '.join(made)})" + (f"; già presenti e lasciati: {', '.join(skipped)}" if skipped else "") + ". Committa e apri la PR: la CI lo prova."

    # ------------------------------------------------------------------ mappa del codice (a grafo): orientarsi senza rileggere i file
    def graph(self) -> CodeGraph:
        """Grafo di simboli e collegamenti della sandbox, ricostruito solo quando i file cambiano."""
        self._need()
        files = self._files()
        digest = hashlib.sha1("".join(f"{k}:{len(v)}:{hashlib.md5(v).hexdigest()}" for k, v in sorted(files.items())).encode()).hexdigest()
        if not self._graph or self._graph[0] != digest:
            self._graph = (digest, CodeGraph.build(files))
        return self._graph[1]

    def code_map(self, query: str = "") -> str:
        g = self.graph()
        return g.symbol(query) if query.strip() else g.overview()

    def code_symbol(self, name: str) -> str:
        return self.graph().symbol(name)

    def code_deps(self, path: str) -> str:
        return self.graph().deps(path)

    def code_path(self, a: str, b: str) -> str:
        return self.graph().path(a, b)

    # ------------------------------------------------------------------ rami, cronologia, PR, issue, rilasci, CI
    async def branches(self) -> str:
        s = self._need()
        rows = await self.gh.call("GET", f"/repos/{s.repo}/branches", params={"per_page": 50})
        return "\n".join(f"• {b['name']}" + (" (principale)" if b["name"] == s.default_branch else "") + (" ◀ lavoro" if b["name"] == s.branch else "") for b in rows) or "Nessun ramo."

    async def branch_delete(self, name: str) -> str:
        s = self._need()
        if name == s.default_branch or not BRANCH_RE.fullmatch(name):
            raise CodingError("Il ramo principale non si elimina.")
        await self.gh.call("DELETE", f"/repos/{s.repo}/git/refs/heads/{name}")
        if s.branch == name:
            s.branch, s.pr = "", 0
        return f"Ramo «{name}» eliminato."

    async def checkout(self, branch: str) -> str:
        s = self._need()
        mod, gone = self._changes()
        if mod or gone:
            raise CodingError("Ci sono modifiche non committate: committa o annulla (code_discard) prima di cambiare ramo.")
        if not BRANCH_RE.fullmatch(branch):
            raise CodingError("Nome del ramo non valido.")
        await self.gh.call("GET", f"/repos/{s.repo}/git/ref/heads/{branch}")  # deve esistere
        await self._sync(branch)
        s.branch, s.pr = ("" if branch == s.default_branch else branch), 0
        if s.branch:
            owner = s.repo.split("/")[0]
            rows = await self.gh.call("GET", f"/repos/{s.repo}/pulls", params={"head": f"{owner}:{branch}", "state": "open"})
            s.pr = rows[0]["number"] if rows else 0
        return f"Ora lavori sul ramo «{branch}» ({len(s.base)} file, commit {s.head[:7]})."

    async def log(self, n: int = 10) -> str:
        s = self._need()
        rows = await self.gh.call("GET", f"/repos/{s.repo}/commits", params={"sha": s.branch or s.default_branch, "per_page": max(1, min(n, 30))})
        return "\n".join(f"{c['sha'][:7]}  {str(c['commit']['author'].get('date', ''))[:10]}  {c['commit']['message'].splitlines()[0][:90]}" for c in rows) or "Nessun commit."

    async def prs(self, state: str = "open") -> str:
        s = self._need()
        rows = await self.gh.call("GET", f"/repos/{s.repo}/pulls", params={"state": state if state in ("open", "closed", "all") else "open", "per_page": 20})
        return "\n".join(f"• #{p['number']} [{p['state']}] {p['title'][:80]} ({p['head']['ref']} → {p['base']['ref']})" for p in rows) or "Nessuna PR."

    async def pr_comment(self, number: int, body: str) -> str:
        s = self._need()
        await self.gh.call("POST", f"/repos/{s.repo}/issues/{int(number)}/comments", {"body": body[:4000]})
        return f"Commento aggiunto a #{number}."

    async def pr_close(self, number: int) -> str:
        s = self._need()
        await self.gh.call("PATCH", f"/repos/{s.repo}/pulls/{int(number)}", {"state": "closed"})
        if s.pr == number:
            s.pr = 0
        return f"PR #{number} chiusa (senza unirla)."

    async def issues(self, state: str = "open") -> str:
        s = self._need()
        rows = await self.gh.call("GET", f"/repos/{s.repo}/issues", params={"state": state if state in ("open", "closed", "all") else "open", "per_page": 30})
        rows = [i for i in rows if "pull_request" not in i]
        return "\n".join(f"• #{i['number']} [{i['state']}] {i['title'][:80]}" + (f" ({', '.join(l['name'] for l in i.get('labels', []))})" if i.get("labels") else "") for i in rows) or "Nessuna issue."

    async def issue_create(self, title: str, body: str = "", labels: str = "") -> str:
        s = self._need()
        payload = {"title": title[:200], "body": body[:6000]}
        if labels.strip():
            payload["labels"] = [x.strip() for x in labels.split(",") if x.strip()][:6]
        i = await self.gh.call("POST", f"/repos/{s.repo}/issues", payload)
        return f"Issue #{i['number']} creata: {i['html_url']}"

    async def issue_comment(self, number: int, body: str) -> str:
        return await self.pr_comment(number, body)

    async def issue_close(self, number: int) -> str:
        s = self._need()
        await self.gh.call("PATCH", f"/repos/{s.repo}/issues/{int(number)}", {"state": "closed", "state_reason": "completed"})
        return f"Issue #{number} chiusa."

    async def release(self, tag: str, title: str = "", notes: str = "") -> str:
        s = self._need()
        if not re.fullmatch(r"v?\d+\.\d+\.\d+([-.][\w.]+)?", tag):
            raise CodingError("Il tag deve essere una versione, es. v1.0.0.")
        mod, gone = self._changes()
        if mod or gone:
            raise CodingError("Ci sono modifiche non committate: committa e unisci prima di rilasciare.")
        r = await self.gh.call("POST", f"/repos/{s.repo}/releases", {"tag_name": tag, "target_commitish": s.default_branch, "name": title[:100] or tag, "body": notes[:6000], "draft": False, "prerelease": False})
        return f"Rilascio {tag} pubblicato: {r['html_url']}"

    async def ci_run(self, workflow: str = "ci.yml", ref: str = "") -> str:
        s = self._need()
        if not re.fullmatch(r"[\w.-]{1,60}\.ya?ml", workflow):
            raise CodingError("Nome del workflow non valido (es. ci.yml).")
        await self.gh.call("POST", f"/repos/{s.repo}/actions/workflows/{workflow}/dispatches", {"ref": ref or s.branch or s.default_branch})
        return f"Workflow {workflow} avviato su «{ref or s.branch or s.default_branch}» (serve `workflow_dispatch` nel file). Controlla con code_ci_runs o code_wait_checks."

    async def ci_runs(self, n: int = 5) -> str:
        s = self._need()
        rows = (await self.gh.call("GET", f"/repos/{s.repo}/actions/runs", params={"per_page": max(1, min(n, 15))})).get("workflow_runs", [])
        return "\n".join(f"• {r['name']} · {r['head_branch']} · {r['status']}{('/' + r['conclusion']) if r.get('conclusion') else ''} · {str(r['created_at'])[:16]} · {r['html_url']}" for r in rows) or "Nessuna esecuzione di CI."

    async def wait_checks(self, timeout: int = 90) -> str:
        """Aspetta (al massimo `timeout` secondi) che la CI sul commit attuale finisca, poi dice com'è andata."""
        deadline = time.monotonic() + max(5, min(int(timeout), 110))
        while True:
            c = await self.checks()
            if c["state"] != "pending" or time.monotonic() >= deadline:
                break
            await asyncio.sleep(6)
        return f"CI: {c['state']}" + "".join(f"\n- {r['name']}: {r['status']} {r['conclusion']}".rstrip() for r in c["runs"]) + ("\n(ancora in corso: richiama code_wait_checks)" if c["state"] == "pending" else "")

    def status(self) -> str:
        if not self.session:
            return "Nessuna sessione di coding attiva." + ("" if self.enabled else " GITHUB_TOKEN non è configurato su Render.")
        s = self.session
        mod, gone = self._changes()
        return (f"Repository privato {s.repo} · ramo principale {s.default_branch} · ramo di lavoro {s.branch or '—'} · PR {('#%d' % s.pr) if s.pr else '—'} · "
                f"{len(s.base)} file nella sandbox, {len(mod)} modificati e {len(gone)} eliminati non ancora committati.")
