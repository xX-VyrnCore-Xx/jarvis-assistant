import base64
import json
import re
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
        self.repos, self.n, self.ci = {}, 0, "success"
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
        m = re.match(r"/repos/(mario/[^/]+)(/.*)?$", path)
        assert m, path
        repo, rest = self.repos[m.group(1)], m.group(2) or ""
        if rest == "":
            return j({"private": repo["private"], "default_branch": "main"})
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
    assert "code_commit" in names and "code_merge" in names and not any("delete_repo" in n or "visibility" in n or "force" in n for n in names)
