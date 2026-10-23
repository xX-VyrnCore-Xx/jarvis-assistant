import pytest

from app.agent import CODE_PROMPT, Agent
from app.config import Settings
from app.memory import MemoryStore
from app.routing import Router
from app.skills.registry import SkillRegistry
from app.tools import ToolRegistry

from tests.test_coding import env  # noqa: F401  (GitHub finto + servizio di coding)
from tests.test_features import AUTH, client  # noqa: F401


@pytest.mark.asyncio
async def test_plan_review_and_snapshot(env):
    gh, svc = env
    await svc.create_repo("studio", "Prova", True, "mit")
    assert "1. Leggere" in svc.plan_set("- Leggere il codice\n- Scrivere i test\n2) Implementare")
    assert "Restano 2" in svc.plan_done(1) and "inesistente" in str(pytest.raises(Exception, svc.plan_done, 9).value)
    svc.write("src/app.py", "def f():\n    print('debug')\n    # TODO sistemare\n    try:\n        pass\n    except:\n        pass\n")
    r = svc.review()
    assert "senza toccare i test" in r and "TODO/FIXME" in r and "print/breakpoint" in r and "nascondono" in r
    svc.write("tests/test_app.py", "def test_f():\n    assert True\n")
    assert "senza toccare i test" not in svc.review()
    svc.write("config.py", "KEY = 'ghp_" + "a" * 36 + "'\n")
    assert "Commit bloccato" in svc.review()  # i segreti si vedono già in revisione
    snap = svc.snapshot()
    assert snap["active"] and snap["repo"] == "mario/studio" and "src/app.py" in snap["changes"]["new"] and snap["plan"][0]["done"] is True
    assert "src/app.py" in svc.file_list()


@pytest.mark.asyncio
async def test_code_mode_uses_its_own_session_prompt_and_only_programming_skills(env):
    gh, svc = env
    await svc.create_repo("studio2", "Prova", True, "mit")
    reg, store = ToolRegistry(), MemoryStore()
    a = Agent(Settings(jarvis_api_token="t"), None, store, reg)
    a.skills, a.coding = SkillRegistry(), svc
    await store.add_message("code", "user", "scrivi un test per la funzione parse")
    await store.add_message("main", "user", "ricordami di comprare il latte")
    msgs, _, active = await a._prepare("Sto facendo il debug di questo errore Python: Traceback ... come lo risolvo?", "code", False, None, "code")
    system = msgs[0]["content"]
    assert system.startswith("MODALITÀ CODING") and "Sessione di coding attiva" in system and {"coding", "web", "competenze"} <= active
    assert [m["content"] for m in msgs[1:-1]] == ["scrivi un test per la funzione parse"]  # niente chat personale
    assert "Chi è l'utente" not in system and "Situazione adesso" not in system
    assert "Competenze specialistiche attive" in system
    assert Router().classify(msgs, True, "chat")[1] == "code"  # la modalità coding sceglie il profilo per il codice
    assert a._rounds("code") > a._rounds("") and CODE_PROMPT.count("code_review") == 1


def test_coding_skills_are_a_large_programming_set():
    sk = SkillRegistry()
    names = {s.name for s in sk.coding_skills()}
    assert len(names) >= 60 and {"revisione-codice", "debug-sistematico", "python-pro", "ci-cd-github-actions"} <= names
    assert not names & {s.name for s in sk.by_domain("finanza")}
    only = sk.match("come ottimizzo una query SQL lenta su postgres", k=3, domains=sk.CODE_DOMAINS)
    assert only and all(s.domain in sk.CODE_DOMAINS for s in only)


def test_code_endpoints_without_an_open_project(client):
    h = AUTH
    r = client.get("/api/code/overview", headers=h)
    assert r.status_code == 200 and isinstance(r.json()["enabled"], bool) and r.json()["session"] == {"active": False} and len(r.json()["skills"]) >= 60
    assert client.get("/api/code/files", headers=h).status_code in (404, 409)  # senza GitHub 404, con GitHub ma senza progetto aperto 409
    assert client.post("/api/code/new", headers=h).json() == {"ok": True}
    assert client.get("/api/code/history", headers=h).json() == []


@pytest.mark.asyncio
async def test_create_endpoint_logic_creates_private_repo_with_scaffold_and_commits(env):
    gh, svc = env
    await svc.create_repo("nuovo-api", "Una API", True, "mit")
    svc.scaffold("fastapi-api", "nuovo-api")
    out = await svc.commit("Scheletro iniziale", direct=True)
    assert gh.repos["mario/nuovo-api"]["private"] and "app/main.py" in svc.snapshot()["changes"]["new"] + sorted(svc.session.base) and "file" in out
    assert svc.snapshot()["changes"] == {"modified": [], "new": [], "deleted": []}  # tutto committato sul ramo principale


def test_create_endpoint_validates_input(client):
    r = client.post("/api/code/create", headers=AUTH, json={"name": "x y", "scaffold": "boh"})
    assert r.status_code in (404, 409, 422)  # senza GitHub 404; con GitHub nome/modello non validi 409/422
    assert client.post("/api/code/create", headers=AUTH, json={"name": "a"}).status_code == 422  # troppo corto
