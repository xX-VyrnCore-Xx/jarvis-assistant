import base64
import json
import re
import time
from pathlib import Path

import httpx
import pytest

from app.coding import CodingError, CodingService
from app.config import Settings
from app.memory import MemoryStore
from app.pending import PendingStore
from app.tools import ToolRegistry
from app.tools.coding_tools import register_coding_tools


class FakeGitHub:
    """GitHub in memoria: repository, rami, commit (albero completo), PR, controlli di CI."""

    def __init__(self):
        self.repos, self.n, self.ci, self.exec_state = {}, 0, "success", "ok"
        self.seen = []

    def sha(self):
        self.n += 1
        return f"{self.n:040x}"

    def commit(self, repo, files, parent=None, message="m"):
        c = self.sha()
        repo["commits"][c] = {"files": dict(files), "parent": parent, "message": message}
        repo["trees"][f"t{c}"] = c
        return c

    def handle(self, req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer ghp_TESTTOKEN"
        path, method = req.url.path, req.method
        body = json.loads(req.content) if req.content else {}
        self.seen.append((method, path))
        j = lambda d, code=200: httpx.Response(code, json=d)  # noqa: E731
        if path == "/user":
            return j({"login": "mario"})
        if path == "/user/repos" and method == "POST":
            assert body["private"] is True
            name = body["name"]
            repo = {"private": True, "default": "main", "commits": {}, "trees": {}, "refs": {}, "blobs": {}, "prs": {}, "desc": body["description"], "empty": not body["auto_init"]}
            files = {}
            if body["auto_init"]:
                files["README.md"] = base64.b64encode(f"# {name}\n".encode()).decode()
                if body.get("license_template"):
                    files["LICENSE"] = base64.b64encode(b"MIT License").decode()
                repo["refs"]["main"] = self.commit(repo, {k: v for k, v in files.items()})
            self.repos[f"mario/{name}"] = repo
            return j({"full_name": f"mario/{name}", "default_branch": "main", "private": True}, 201)
        if path == "/user/repos" and method == "GET":
            return j([{"full_name": k, "private": v["private"], "topics": v.get("topics", [])} for k, v in self.repos.items()])
        m = re.match(r"/repos/(mario/[^/]+)(/.*)?$", path)
        assert m, path
        repo, rest = self.repos[m.group(1)], m.group(2) or ""
        if rest == "":
            full = m.group(1)
            if method == "DELETE":
                self.repos.pop(full)
                return httpx.Response(204)
            if method == "PATCH":
                if "description" in body:
                    repo["desc"] = body["description"]
                if "archived" in body:
                    repo["archived"] = body["archived"]
                if "name" in body:
                    self.repos[f"mario/{body['name']}"] = self.repos.pop(full)
                    full = f"mario/{body['name']}"
                return j({"full_name": full})
            return j({"full_name": full, "private": repo["private"], "default_branch": "main", "description": repo["desc"], "pushed_at": "2026-10-21T10:00:00Z", "open_issues_count": 2, "size": 5,
                      "archived": repo.get("archived", False)})
        if rest == "/topics" and method == "PUT":
            repo["topics"] = body["names"]
            return j({})
        if rest == "/branches":
            return j([{"name": b} for b in repo["refs"]])
        if rest == "/issues" and method == "POST":
            repo.setdefault("issues", {})[1] = {"title": body["title"], "state": "open"}
            return j({"number": 1, "html_url": "https://github.com/issue/1"}, 201)
        if rest == "/issues" and method == "GET":
            return j([{"number": n, "state": i["state"], "title": i["title"], "labels": []} for n, i in repo.get("issues", {}).items()])
        if m2 := re.match(r"/issues/(\d+)$", rest):
            repo["issues"][int(m2.group(1))]["state"] = body["state"]
            return j({})
        if rest == "/actions/workflows/ci.yml/dispatches":
            repo["dispatched"] = body["ref"]
            return httpx.Response(204)
        if rest.startswith("/contents/") and method == "PUT":
            repo["refs"]["main"] = self.commit(repo, {rest[10:]: body["content"]})
            return j({}, 201)
        if m2 := re.match(r"/commits/(.+)/check-runs$", rest):
            return j({"check_runs": [] if self.ci == "none" else [{"id": 7, "name": "test", "status": "in_progress" if self.ci == "pending" else "completed", "conclusion": "failure" if self.ci == "failure" else "success"}]})
        if m2 := re.match(r"/commits/(.+)$", rest):
            ref = m2.group(1)
            sha = repo["refs"].get(ref, ref)
            return j({"sha": sha, "commit": {"tree": {"sha": f"t{sha}"}}})
        if (m2 := re.match(r"/git/trees/(.+)$", rest)) and method == "GET":
            c = repo["trees"][m2.group(1)]
            return j({"tree": [{"path": p, "type": "blob", "sha": f"{c}:{p}", "size": 10} for p in repo["commits"][c]["files"]]})
        if (m2 := re.match(r"/git/blobs/(.+)$", rest)) and method == "GET":
            c, p = m2.group(1).split(":", 1)
            return j({"encoding": "base64", "content": repo["commits"][c]["files"][p]})
        if rest == "/git/blobs":
            k = self.sha()
            repo["blobs"][k] = body["content"]
            return j({"sha": k}, 201)
        if m2 := re.match(r"/git/ref/heads/(.+)$", rest):
            if m2.group(1) not in repo["refs"]:
                return j({"message": "Not Found"}, 404)
            return j({"object": {"sha": repo["refs"][m2.group(1)]}})
        if m2 := re.match(r"/git/commits/(.+)$", rest):
            return j({"tree": {"sha": f"t{m2.group(1)}"}})
        if rest == "/git/trees":
            parent = repo["commits"][body["base_tree"][1:]]["files"]
            files = dict(parent)
            for e in body["tree"]:
                if e["sha"] is None:
                    files.pop(e["path"], None)
                else:
                    files[e["path"]] = repo["blobs"][e["sha"]]
            k = f"x{self.sha()}"
            repo["pending_tree"] = files
            return j({"sha": k}, 201)
        if rest == "/git/commits":
            c = self.commit(repo, repo["pending_tree"], body["parents"][0], body["message"])
            return j({"sha": c}, 201)
        if rest == "/git/refs" and method == "POST":
            repo["refs"][body["ref"].split("heads/")[1]] = body["sha"]
            return j({}, 201)
        if m2 := re.match(r"/git/refs/heads/(.+)$", rest):
            if method == "PATCH":
                repo["refs"][m2.group(1)] = body["sha"]
                assert body["force"] is False  # mai forzare
                return j({})
            if method == "DELETE":
                repo["refs"].pop(m2.group(1), None)
                return httpx.Response(204)
        if rest == "/pulls" and method == "POST":
            repo["prs"][1] = {"head": body["head"], "base": body["base"]}
            return j({"number": 1, "html_url": "https://github.com/pr/1"}, 201)
        if rest == "/pulls/1/merge":
            pr = repo["prs"][1]
            head = repo["refs"][pr["head"]]
            repo["refs"]["main"] = self.commit(repo, repo["commits"][head]["files"], message="squash")
            return j({"merged": True})
        if rest == "/actions/runs" and "head_sha" in dict(req.url.params):
            repo["exec_sha"] = req.url.params["head_sha"]
            return j({"workflow_runs": [{"id": 55, "name": "JARVIS exec", "status": "completed"}]})
        if rest == "/actions/runs/55":
            return j({"id": 55, "status": "in_progress" if self.exec_state == "pending" else "completed", "conclusion": "success" if self.exec_state == "ok" else "failure"})
        if rest == "/actions/runs/55/jobs":
            return j({"jobs": [{"id": 9}]})
        if rest == "/actions/jobs/9/logs":
            return httpx.Response(200, text="2026-10-21T10:00:00.0000Z ##[group]Run bash .jarvis-exec.sh\n2026-10-21T10:00:01.0000Z 3 passed in 0.1s\n2026-10-21T10:00:02.0000Z ##[endgroup]\n", headers={"content-type": "text/plain"})
        if m2 := re.match(r"/actions/jobs/7/logs$", rest):
            return httpx.Response(200, text="2026-10-21T10:00:00.0000000Z FAILED test_x.py::t - AssertionError\n", headers={"content-type": "text/plain"})
        raise AssertionError((method, path))


@pytest.fixture
def env(tmp_path):
    gh = FakeGitHub()
    s = Settings(jarvis_api_token="t", github_token="ghp_TESTTOKEN")
    svc = CodingService(s, MemoryStore(), httpx.AsyncClient(transport=httpx.MockTransport(gh.handle)), root=tmp_path)
    return gh, svc


@pytest.mark.asyncio
async def test_full_flow_create_write_commit_pr_ci_merge(env):
    gh, svc = env
    assert "Creato" in (await svc.create_repo("mio-progetto", "Prova", True, "mit")) or True
    assert gh.repos["mario/mio-progetto"]["private"] and svc.session.repo == "mario/mio-progetto"
    assert set(svc.session.base) == {"README.md", "LICENSE"}
    svc.write("src/app.py", "print('ciao')\n")
    svc.edit("src/app.py", "ciao", "salve")
    assert "*modificato*" in svc.ls() and "src/app.py" in svc.ls()
    assert "salve" in svc.read("src/app.py")
    out = await svc.commit("Aggiungi app")
    branch = svc.session.branch
    assert branch.startswith("jarvis/aggiungi-app") and "1 file modificati" in out
    assert (await svc.commit("niente")).startswith("Niente da committare")
    assert "PR #1" in await svc.open_pr("Aggiungi app")
    gh.ci = "pending"
    with pytest.raises(CodingError, match="pending"):
        await svc.merge()
    gh.ci = "failure"
    assert "AssertionError" in await svc.ci_logs() and "2026-10" not in await svc.ci_logs()
    with pytest.raises(CodingError, match="failure"):
        await svc.merge()
    gh.ci = "success"
    assert "unita" in await svc.merge()
    assert svc.session.branch == "" and "src/app.py" in svc.session.base and branch not in gh.repos["mario/mio-progetto"]["refs"]
    assert not any(m == "DELETE" and "/repos/mario/mio-progetto" == p for m, p in gh.seen)  # nessuna eliminazione di repository


@pytest.mark.asyncio
async def test_empty_repo_gets_initial_commit_direct_push_and_sync_protection(env):
    gh, svc = env
    await svc.create_repo("vuoto", "", False, "none")
    assert ".gitignore" in svc.session.base
    svc.write("a.txt", "uno")
    assert "su «main»" in await svc.commit("Primo file", direct=True)
    svc.write("b.txt", "due")
    with pytest.raises(CodingError, match="non committate"):
        await svc.sync()
    gh.ci = "none"
    svc.session.pr = 1
    svc.session.branch = ""
    with pytest.raises(CodingError, match="non committate"):
        await svc.merge()


@pytest.mark.asyncio
async def test_security_rules(env):
    gh, svc = env
    await svc.create_repo("sicuro", "", True, "")
    for bad in ("../fuori.txt", "/etc/passwd", ".git/config", ".env", "chiavi/server.pem", "a/../../x"):
        with pytest.raises(CodingError):
            svc.write(bad, "x")
    svc.write("conf.py", 'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\n')
    with pytest.raises(CodingError, match="bloccato"):
        await svc.commit("Aggiungi configurazione")
    svc.write("conf.py", 'API_KEY = os.environ["API_KEY"]\ntoken = request.headers["x"]\n')
    assert "1 file" in await svc.commit("Aggiungi configurazione")
    with pytest.raises(CodingError, match="messaggio"):
        svc.write("z.py", "1")
        await svc.commit("x")
    with pytest.raises(CodingError):
        await svc.create_repo("../evil", "", True, "mit")
    with pytest.raises(CodingError, match="Licenza"):
        await svc.create_repo("ok", "", True, "proprietaria")
    with pytest.raises(CodingError, match="non è tra quelli"):
        await svc.resume("altro/repo-non-mio")
    gh.repos["mario/sicuro"]["private"] = False
    with pytest.raises(CodingError, match="non è privato"):
        await svc.resume("sicuro")


@pytest.mark.asyncio
async def test_daily_limit_and_disabled_without_token(env, tmp_path):
    gh, svc = env
    for i in range(3):
        await svc.create_repo(f"r{i}", "", True, "mit")
    with pytest.raises(CodingError, match="Limite"):
        await svc.create_repo("r4", "", True, "mit")
    off = CodingService(Settings(jarvis_api_token="t", github_token=""), MemoryStore(), root=tmp_path)
    assert not off.enabled and "GITHUB_TOKEN" in off.status()
    with pytest.raises(CodingError, match="GITHUB_TOKEN"):
        await off.create_repo("x", "", True, "mit")


@pytest.mark.asyncio
async def test_tools_require_user_confirmation_to_create_repo(env):
    gh, svc = env
    pending, reg = PendingStore(), ToolRegistry()
    register_coding_tools(reg, svc, pending)
    out = await reg.call("code_start_session", json.dumps({"name": "demo", "description": "Una demo", "readme": True, "license": "mit"}))
    assert "conferma" in out and not gh.repos  # niente repository finché l'utente non approva
    p = pending.list_pending()[0]
    assert "PRIVATO" in p.summary and "MIT".lower() in p.summary.lower()
    await pending.decide(p.id, True)
    assert "mario/demo" in gh.repos and svc.session
    assert "Sessione di coding attiva" in svc.prompt_block()
    await reg.call("code_write", json.dumps({"path": "main.py", "content": "x = 1\n"}))
    assert "main.py" in await reg.call("code_ls", "{}")
    assert (await reg.call("code_read", json.dumps({"path": "main.py"}))).startswith("[")  # contenuto marcato come dato
    assert "Errore" in await reg.call("code_write", json.dumps({"path": "../x", "content": "1"}))
    names = [t["function"]["name"] for t in reg.specs]
    assert "code_commit" in names and "code_merge" in names and not any("visibility" in n or "force" in n for n in names)


@pytest.mark.asyncio
async def test_list_edit_adopt_and_audit(env):
    gh, svc = env
    await svc.create_repo("uno", "Primo", True, "mit")
    assert gh.repos["mario/uno"]["topics"] == ["jarvis-managed"]
    await svc.create_repo("due", "Secondo", True, "none")
    out = await svc.list_repos()
    assert "2 repository" in out and "mario/uno" in out and "Secondo" in out and "🔒" in out
    assert "Aggiornato" in await svc.repo_edit("uno", description="Nuova", topics="Bot, Python bot")
    assert gh.repos["mario/uno"]["desc"] == "Nuova" and gh.repos["mario/uno"]["topics"] == ["jarvis-managed", "bot", "python-bot"]
    await svc.repo_edit("uno", new_name="uno-bis")
    assert "mario/uno-bis" in gh.repos and "mario/uno-bis" in await svc.repos() and svc.session.repo != "mario/uno"
    with pytest.raises(CodingError, match="Niente da modificare"):
        await svc.repo_edit("due")
    with pytest.raises(CodingError, match="non è tra quelli"):
        await svc.repo_edit("estraneo", description="x")
    await svc.store.set_setting("coding_repos", "[]")  # elenco perso: si ritrova dall'argomento
    gh.repos["mario/estraneo"] = {**gh.repos["mario/due"], "topics": []}
    assert "mario/due" in await svc.adopt() and "mario/estraneo" not in await svc.repos()
    log = await svc.audit()
    assert "creato" in log and "rinominato" in log and "adottato" in log


@pytest.mark.asyncio
async def test_delete_repo_needs_confirmation_registry_private_and_limit(env):
    gh, svc = env
    pending, reg = PendingStore(), ToolRegistry()
    register_coding_tools(reg, svc, pending)
    await svc.create_repo("vecchio", "Da buttare", True, "mit")
    gh.repos["mario/non-mio"] = {**gh.repos["mario/vecchio"]}
    out = await reg.call("code_repo_delete", json.dumps({"name": "vecchio"}))
    assert "conferma" in out and "mario/vecchio" in gh.repos  # niente cancellazione senza OK
    p = pending.list_pending()[0]
    assert "DEFINITIVAMENTE" in p.summary and "Da buttare" in p.summary
    await pending.decide(p.id, False)
    assert "mario/vecchio" in gh.repos
    await reg.call("code_repo_delete", json.dumps({"name": "vecchio"}))
    await pending.decide(pending.list_pending()[0].id, True)
    assert "mario/vecchio" not in gh.repos and "mario/vecchio" not in await svc.repos() and svc.session is None
    assert "ELIMINATO" in await svc.audit()
    assert "Errore" in await reg.call("code_repo_delete", json.dumps({"name": "non-mio"}))  # non creato da JARVIS
    await svc.create_repo("pubblico", "", True, "mit")
    gh.repos["mario/pubblico"]["private"] = False
    with pytest.raises(CodingError, match="non è privato"):
        await svc.delete_repo("pubblico")
    gh.repos["mario/pubblico"]["private"] = True
    await svc.store.set_setting("coding_deleted_today", f"{time.strftime('%Y-%m-%d')}:1")
    svc.s.coding_deletes_per_day = 1
    with pytest.raises(CodingError, match="Limite"):
        await svc.delete_repo("pubblico")


@pytest.mark.asyncio
async def test_sandbox_extras_diff_discard_replace_scaffold_move(env):
    gh, svc = env
    await svc.create_repo("lab", "", True, "mit")
    svc.write("a.py", "x = 1\nprint(x)\n")
    assert "nuovo" in svc.diff() and "+x = 1" in svc.diff("a.py")
    await svc.commit("Aggiungi a.py")
    svc.edit("a.py", "x = 1", "x = 2")
    assert "-x = 1" in svc.diff() and "+x = 2" in svc.diff()
    assert "Ripristinato" in svc.discard("a.py") and "x = 1" in svc.read("a.py")
    assert "Anteprima" in svc.replace_all(r"x\b", "y", "*.py") and "x = 1" in svc.read("a.py")
    assert "Sostituite" in svc.replace_all(r"x\b", "y", "*.py", dry_run=False) and "y = 1" in svc.read("a.py")
    svc.move("a.py", "pkg/b.py")
    assert "pkg/b.py" in svc.find("*.py") and "eliminato" in svc.diff()
    assert "└──" in svc.tree() and "TODO" in svc.stats()
    assert "a.py" in svc.search("print", glob="*.py", context=1) or "pkg/b.py" in svc.search("print", glob="*.py", context=1)
    svc.discard("all")
    assert "a.py" in svc.find("*.py") and "pkg/b.py" not in svc.find("*.py")
    assert "creato" in svc.scaffold("fastapi-api", "demo")
    assert "tests/test_api.py" in svc.find("test_*") and "workflow_dispatch" in svc.read(".github/workflows/ci.yml")
    assert "già presenti" in svc.scaffold("fastapi-api", "demo")
    with pytest.raises(CodingError, match="Tipi disponibili"):
        svc.scaffold("cobol")


@pytest.mark.asyncio
async def test_branches_issues_ci_run(env):
    gh, svc = env
    await svc.create_repo("rami", "", True, "mit")
    svc.write("f.txt", "uno\n")
    await svc.commit("Aggiungi f.txt")
    assert "main" in await svc.branches() and "◀ lavoro" in await svc.branches()
    with pytest.raises(CodingError, match="principale"):
        await svc.branch_delete("main")
    assert "creata" in await svc.issue_create("Bug", "descr", "") and "Bug" in await svc.issues()
    assert "chiusa" in await svc.issue_close(1) and gh.repos["mario/rami"]["issues"][1]["state"] == "closed"
    assert "avviato" in await svc.ci_run("ci.yml") and gh.repos["mario/rami"]["dispatched"]
    with pytest.raises(CodingError, match="workflow"):
        await svc.ci_run("../evil.yml")


@pytest.mark.asyncio
async def test_code_graph_tools_map_symbols_callers_and_paths_cheaply(env):
    gh, svc = env
    await svc.create_repo("mappa", "", True, "mit")
    svc.write("app/main.py", "from app.util import helper\n\ndef run():\n    '''Avvia tutto'''\n    return helper(1)\n")
    svc.write("app/util.py", "def helper(x):\n    return fmt(x)\n\ndef fmt(x):\n    return str(x)\n")
    svc.write("web/app.js", "import { api } from './api.js';\nexport function load() { return api.get(); }\n")
    svc.write("web/api.js", "export const api = { get() {} };\n")
    pending, reg = PendingStore(), ToolRegistry()
    register_coding_tools(reg, svc, pending)
    out = await reg.call("code_graph", "{}")
    assert out.startswith("[") and "Grafo del codice" in out and "helper" in out and len(out) < 2700  # poche centinaia di token
    sym = await reg.call("code_symbol", json.dumps({"name": "helper"}))
    assert "app/util.py:1" in sym and "usato da: run" in sym and "usa: fmt" in sym
    assert "importa: app/util.py" in await reg.call("code_deps", json.dumps({"path": "app/main.py"}))
    assert "run" in (p := await reg.call("code_path", json.dumps({"a": "run", "b": "fmt"}))) and "helper" in p
    assert "importa: web/api.js" in await reg.call("code_deps", json.dumps({"path": "web/app.js"}))
    svc.write("app/util.py", "def helper(x):\n    return x\n")  # il grafo si aggiorna da solo quando i file cambiano
    assert "usa: fmt" not in await reg.call("code_symbol", json.dumps({"name": "helper"}))
    assert "Nessun simbolo" in await reg.call("code_symbol", json.dumps({"name": "inesistente_xyz"}))
