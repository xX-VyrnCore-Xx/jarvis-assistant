"""Coding «alla Claude Code»: annulla, punti di ripristino, modifiche atomiche, sintassi, memoria di progetto e lavori in background con notifica."""
import asyncio

import pytest

from app.codecmds import COMMANDS, listing
from app.codejobs import CodeJobs
from app.coding import CodingError
from app.config import Settings
from app.memory import MemoryStore

from tests.test_coding import env  # noqa: F401  (GitHub finto + servizio di coding)
from tests.test_features import AUTH, client  # noqa: F401


@pytest.mark.asyncio
async def test_undo_checkpoint_rollback(env):
    gh, svc = env
    await svc.create_repo("pro", "Prova", True, "mit")
    svc.write("a.py", "x = 1\n")
    svc.edit("a.py", "1", "2")
    svc.write("b.py", "y = 1\n")
    assert "b.py" in svc.undo(1) and not (svc.session.root / "b.py").exists()
    assert "a.py" in svc.undo(1) and (svc.session.root / "a.py").read_text() == "x = 1\n"
    svc.undo(5)
    assert not (svc.session.root / "a.py").exists() and svc.undo() == "Niente da annullare."
    svc.write("c.py", "z = 1\n")
    assert "salvato" in svc.checkpoint("buono")
    svc.write("c.py", "z = 999\n")
    svc.delete("README.md")
    assert "riportata" in svc.rollback("buono")
    assert (svc.session.root / "c.py").read_text() == "z = 1\n" and (svc.session.root / "README.md").exists()
    assert "prima-del-ripristino" in svc.session.checkpoints
    with pytest.raises(CodingError):
        svc.rollback("inesistente")
    for i in range(8):
        svc.checkpoint(f"p{i}")
    assert len(svc.session.checkpoints) == 5


@pytest.mark.asyncio
async def test_multi_edit_is_atomic(env):
    gh, svc = env
    await svc.create_repo("pro2", "Prova", True, "mit")
    svc.write("a.py", "a = 1\nb = 2\n")
    svc.write("b.py", "c = 3\n")
    out = svc.multi_edit([{"path": "a.py", "old": "a = 1", "new": "a = 10"}, {"path": "b.py", "old": "c = 3", "new": "c = 30"}])
    assert "2 modifiche" in out and "a = 10" in svc.read("a.py") and "c = 30" in svc.read("b.py")
    with pytest.raises(CodingError, match="Nessuna modifica applicata"):
        svc.multi_edit([{"path": "a.py", "old": "b = 2", "new": "b = 20"}, {"path": "b.py", "old": "NON C'E'", "new": "x"}])
    assert "b = 2\n" in (svc.session.root / "a.py").read_text()  # la prima modifica è stata annullata
    with pytest.raises(CodingError):
        svc.multi_edit([])


@pytest.mark.asyncio
async def test_lint_syntax_and_commit_warning(env):
    gh, svc = env
    await svc.create_repo("pro3", "Prova", True, "mit")
    svc.write("ok.py", "def f():\n    return 1\n")
    svc.write("rotto.py", "def f(:\n    return 1\n")
    svc.write("d.json", '{"a": 1,}')
    svc.write("ok.js", "function f() { return [1, 2, '}' ]; } // {\n")
    svc.write("rotto.js", "function f() { return [1, 2; }\n")
    svc.write("x.toml", "a = = 1\n")
    r = svc.lint()
    assert "rotto.py" in r and "riga 1" in r and "d.json" in r and "rotto.js" in r and "x.toml" in r and "ok.py" not in r and "ok.js" not in r
    assert svc.lint("ok.py").startswith("Sintassi OK")
    out = await svc.commit("Prova con errori")
    assert "⚠ Sintassi:" in out and "rotto.py" in out  # avverte ma non blocca


@pytest.mark.asyncio
async def test_todos_and_project_memory_in_prompt(env):
    gh, svc = env
    await svc.create_repo("pro4", "Prova", True, "mit")
    svc.write("m.py", "x = 1  # TODO: sistemare\n# FIXME bug qui\n")
    t = svc.todos()
    assert "m.py:1  TODO sistemare" in t and "m.py:2  FIXME" in t
    assert "Istruzioni del progetto" not in svc.prompt_block()
    svc.write("JARVIS.md", "Usa sempre type hint. Test con pytest.\n")
    assert "Istruzioni del progetto (JARVIS.md)" in svc.prompt_block() and "type hint" in svc.prompt_block() and "code_checkpoint" in svc.prompt_block()


def test_commands_catalog():
    names = {c["name"] for c in listing()}
    assert {"review", "test", "fix", "plan", "init", "ship", "pr", "bg", "jobs", "new", "help", "security"} <= names
    for name, (desc, prompt, args) in COMMANDS.items():
        assert desc and len(prompt) > 20 and (("{args}" in prompt) == args or name in ("ci", "todo", "deps", "tests-run", "init", "commit")), name


class FakeNotifier:
    def __init__(self):
        self.pushed, self.syncs = [], 0

    def sync(self, scope, origin=""):
        self.syncs += 1

    async def push(self, kind, title, body="", telegram=None, meta=None):
        self.pushed.append((kind, title, body, telegram, meta))
        return {}


class FakeAgent:
    def __init__(self, fail=False, slow=False):
        self.fail, self.slow, self.prompts = fail, slow, []

    async def reply_stream(self, text, session_id, **kw):
        self.prompts.append((text, session_id, kw))
        yield ("status", "Scrivo il codice nella sandbox…")
        if self.slow:
            await asyncio.sleep(30)
        if self.fail:
            raise RuntimeError("modello non raggiungibile")
        yield ("status", "Apro la Pull Request…")
        yield ("done", "Fatto: aggiunti i test, PR aperta, CI verde.")


async def _wait(jobs, jid, status, tries=100):
    for _ in range(tries):
        if jobs.jobs[jid]["status"] in status:
            return jobs.jobs[jid]
        await asyncio.sleep(0.02)
    raise AssertionError(jobs.jobs[jid]["status"])


@pytest.mark.asyncio
async def test_background_job_runs_and_notifies(env):
    gh, svc = env
    await svc.create_repo("bg1", "Prova", True, "mit")
    store, n, agent = MemoryStore(), FakeNotifier(), FakeAgent()
    jobs = CodeJobs(Settings(jarvis_api_token="t"), store, agent, svc, n)
    j = await jobs.start("Aggiungi i test per il parser")
    assert j["status"] in ("queued", "running")
    done = await _wait(jobs, j["id"], ("done", "failed"))
    assert done["status"] == "done" and "CI verde" in done["result"] and done["repo"] == "mario/bg1"
    text, sess, kw = agent.prompts[0]
    assert sess == "code" and kw["mode"] == "code" and text.startswith("LAVORO IN BACKGROUND") and "Aggiungi i test per il parser" in text
    kind, title, body, tg, meta = n.pushed[-1]
    assert kind == "code" and "finito" in title and "CI verde" in body and tg is True and meta["job_id"] == j["id"]
    # lo stato è salvato: dopo un riavvio si rilegge
    again = CodeJobs(Settings(jarvis_api_token="t"), store, agent, svc, FakeNotifier())
    await again.load()
    assert again.get(j["id"])["status"] == "done" and again.get(j["id"])["steps"][-1] == "Apro la Pull Request…"


@pytest.mark.asyncio
async def test_background_job_failure_cancel_and_restart(env):
    gh, svc = env
    await svc.create_repo("bg2", "Prova", True, "mit")
    store, n = MemoryStore(), FakeNotifier()
    bad = CodeJobs(Settings(jarvis_api_token="t"), store, FakeAgent(fail=True), svc, n)
    j = await bad.start("Cosa che fallisce")
    f = await _wait(bad, j["id"], ("failed",))
    assert "modello non raggiungibile" in f["result"] and "non riuscito" in n.pushed[-1][1]

    slow = CodeJobs(Settings(jarvis_api_token="t"), store, FakeAgent(slow=True), svc, n)
    j2 = await slow.start("Lavoro lungo")
    await _wait(slow, j2["id"], ("running",))
    assert slow.active == 1 and await slow.cancel(j2["id"])
    c = await _wait(slow, j2["id"], ("cancelled",))
    assert c["status"] == "cancelled" and slow.active == 0 and not await slow.cancel(j2["id"])
    assert len([p for p in n.pushed if "annullat" in p[1].lower()]) == 0  # l'annullamento è voluto: nessuna notifica

    # il server si riavvia a metà lavoro: il lavoro risulta interrotto e l'utente viene avvisato
    store2, n2 = MemoryStore(), FakeNotifier()
    await store2.set_setting("code_jobs", '[{"id":"ab12","title":"Lungo","prompt":"x","status":"running","created":1,"steps":[],"result":""}]')
    r = CodeJobs(Settings(jarvis_api_token="t"), store2, FakeAgent(), svc, n2)
    await r.load()
    assert r.get("ab12")["status"] == "interrupted" and "riavviato" in n2.pushed[0][2] and r.active == 0


@pytest.mark.asyncio
async def test_background_job_limits_and_requirements(env):
    gh, svc = env
    jobs = CodeJobs(Settings(jarvis_api_token="t"), MemoryStore(), FakeAgent(slow=True), svc, FakeNotifier())
    with pytest.raises(CodingError, match="Descrivi"):
        await jobs.start("  ")
    j = await jobs.start("Senza progetto aperto")  # coding attivo ma nessuna sessione: fallisce con un messaggio chiaro
    f = await _wait(jobs, j["id"], ("failed",))
    assert "Nessun progetto aperto" in f["result"]
    await svc.create_repo("bg3", "Prova", True, "mit")
    for i in range(4):
        await jobs.start(f"Lavoro {i} abbastanza lungo")
    with pytest.raises(CodingError, match="già 4 lavori"):
        await jobs.start("Uno di troppo")
    for jid in [k for k, v in jobs.jobs.items() if v["status"] in ("queued", "running")]:
        await jobs.cancel(jid)
    await asyncio.sleep(0.1)


def test_jobs_and_commands_endpoints(client):
    cmds = client.get("/api/code/commands", headers=AUTH).json()
    assert any(c["name"] == "review" and c["prompt"] for c in cmds)
    assert client.get("/api/code/jobs", headers=AUTH).json() == {"jobs": [], "active": 0}
    assert client.get("/api/code/jobs/nope", headers=AUTH).status_code == 404
    assert client.post("/api/code/jobs/nope/cancel", headers=AUTH).status_code == 409
    assert client.post("/api/code/jobs", headers=AUTH, json={"task": "x"}).status_code == 422
    r = client.post("/api/code/jobs", headers=AUTH, json={"task": "Scrivi i test del parser"})
    assert r.status_code in (201, 409)  # senza GITHUB_TOKEN 409 con spiegazione


@pytest.mark.asyncio
async def test_exec_runs_on_github_temp_branch_and_cleans_up(env):
    gh, svc = env
    svc.POLL_S = 0
    await svc.create_repo("ex1", "Prova", True, "mit")
    svc.write("src/a.py", "x = 1\n")
    out = await svc.exec("python -m pytest -q")
    assert out.startswith("✓ riuscito") and "3 passed" in out and "##[" not in out
    repo = gh.repos["mario/ex1"]
    assert not [b for b in repo["refs"] if b.startswith("jarvis-exec/")]  # ramo temporaneo eliminato
    assert svc.session.branch == "" and "src/a.py" in svc.snapshot()["changes"]["new"]  # la sandbox non è stata committata sul ramo di lavoro
    exec_commit = [c for c in repo["commits"].values() if c["message"].startswith("JARVIS exec")][0]
    assert {"src/a.py", ".jarvis-exec.sh", ".github/workflows/jarvis-exec.yml"} <= set(exec_commit["files"])
    import base64

    wf = [v for v in repo["blobs"].values() if "JARVIS exec" in base64.b64decode(v).decode(errors="ignore")][0]
    text = base64.b64decode(wf).decode()
    assert "persist-credentials: false" in text and "contents: read" in text and "secrets" not in text

    gh.exec_state = "fail"
    assert (await svc.exec("pytest")).startswith("✗ fallito")


@pytest.mark.asyncio
async def test_exec_pending_blocks_secrets_and_limit(env):
    gh, svc = env
    svc.POLL_S = 0
    await svc.create_repo("ex2", "Prova", True, "mit")
    with pytest.raises(CodingError, match="Comando mancante"):
        await svc.exec("  ")
    svc.write("config.py", "KEY = 'ghp_" + "a" * 36 + "'\n")
    with pytest.raises(CodingError, match="Commit bloccato"):
        await svc.exec("pytest")  # i segreti non escono nemmeno verso un ramo temporaneo
    svc.delete("config.py")
    gh.exec_state = "pending"
    out = await svc.exec("sleep 999", timeout=5)
    assert "ancora in corso" in out and svc._exec_pending
    gh.exec_state = "ok"
    assert (await svc.exec_result(55)).startswith("✓") and not svc._exec_pending
    with pytest.raises(CodingError, match="Nessuna esecuzione"):
        await svc.exec_result(0)
    svc.session.execs = 15
    with pytest.raises(CodingError, match="limite"):
        await svc.exec("pytest")


@pytest.mark.asyncio
async def test_read_many(env):
    gh, svc = env
    await svc.create_repo("ex3", "Prova", True, "mit")
    svc.write("a.py", "a = 1\nb = 2\n")
    svc.write("b.py", "c = 3\n")
    out = svc.read_many("a.py, b.py, nope.py")
    assert "=== a.py ===" in out and "1\ta = 1" in out and "c = 3" in out and "Errore" in out
    with pytest.raises(CodingError):
        svc.read_many("  ")


@pytest.mark.asyncio
async def test_telegram_code_and_lavori_commands(env):
    from tests.test_tools_bot import make_bot

    gh, svc = env
    await svc.create_repo("tg1", "Prova", True, "mit")
    bot, st = make_bot()
    st.codejobs = CodeJobs(Settings(jarvis_api_token="t"), MemoryStore(), FakeAgent(slow=True), svc, FakeNotifier())
    msg = lambda text, i: {"update_id": i, "message": {"from": {"id": 42}, "chat": {"id": 42}, "text": text}}  # noqa: E731
    await bot.handle_update(msg("/code", 1))
    assert "Mi dica cosa" in st.tg.out[-1][0]
    await bot.handle_update(msg("/code aggiungi i test al parser e apri la PR", 2))
    assert "Lavoro avviato" in st.tg.out[-1][0]
    jid = next(iter(st.codejobs.jobs))
    await asyncio.sleep(0.1)
    await bot.handle_update(msg("/lavori", 3))
    assert jid in st.tg.out[-1][0] and "stop" in st.tg.out[-1][0]
    await bot.handle_update(msg(f"/lavori stop {jid}", 4))
    assert "annullato" in st.tg.out[-1][0]
    await _wait(st.codejobs, jid, ("cancelled",))
    await bot.handle_update(msg("/lavori stop zzzz", 5))
    assert "Nessun lavoro" in st.tg.out[-1][0]
