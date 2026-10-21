import json
from types import SimpleNamespace

import pytest

from app.agent import Agent
from app.config import Settings
from app.memory import MemoryStore
from app.skills.registry import DOMAINS, Skill, SkillRegistry, parse_block
from app.skills.tools import register_skill_tools
from app.tools import ToolRegistry
from tests.test_brain import make
from tests.test_tools_bot import make_bot

REG = SkillRegistry()


def top(text, k=2):
    return [s.name for s in REG.match(text, k=k)]


def test_library_is_complete_and_well_formed():
    assert len(REG) >= 130
    for d in ("comunicazione", "finanza", "marketing", "business", "vita", "tecnologia"):
        assert len(REG.by_domain(d)) >= 6, d
    assert len(REG.by_domain("programmazione")) >= 60 and len(REG.by_domain("grafica")) >= 15
    for s in REG.skills.values():
        assert s.domain in DOMAINS and s.builtin
        assert 40 <= len(s.description) <= 300, s.name
        assert 3 <= len(s.triggers) <= 25, s.name
        assert 500 <= len(s.body) <= 2400, (s.name, len(s.body))  # abbastanza ricco ma entro il budget del prompt
        assert "**Output**" in s.body or "**Metodo**" in s.body, s.name


def test_every_skill_is_reachable_from_its_own_trigger_phrases():
    missed = []
    for s in REG.skills.values():
        hits = [REG.match(t, k=3, min_score=2.0) for t in s.triggers]
        if not any(s in h[:2] for h in hits):  # almeno una sua frase la porta tra le prime due
            missed.append(s.name)
    assert not missed, missed


@pytest.mark.parametrize("text,expected", [
    ("Puoi rivedere questo codice? ho aperto una pull request", "revisione-codice"),
    ("mi dà questo traceback e non capisco perché", "debug-sistematico"),
    ("come strutturo l'architettura di un'app con microservizi?", "architettura-software"),
    ("scrivimi una query sql con join e un indice su postgres", "sql-database"),
    ("la mia pagina è troppo lenta, come la ottimizzo?", "ottimizzazione-prestazioni"),
    ("scrivi una email di sollecito per una fattura non pagata", "email-professionale"),
    ("devo chiedere un aumento di stipendio, come negozio?", "negoziazione"),
    ("preparami la presentazione per il pitch agli investitori", "presentazioni-e-pitch"),
    ("come faccio a dire a un collega che sbaglia? conversazione difficile", "feedback-e-conversazioni-difficili"),
    ("quanto devo mettere da parte ogni mese? voglio un fondo di emergenza", "finanza-personale"),
    ("conviene investire in etf con un piano di accumulo?", "investimenti-base"),
    ("come funziona il regime forfettario con la partita iva?", "tasse-italia"),
    ("calcola il punto di pareggio, il break even della mia attività", "finanza-aziendale"),
    ("mi spieghi la differenza tra tan e taeg del mutuo?", "mutui-e-prestiti"),
    ("prepara un piano di marketing per il lancio del mio prodotto", "strategia-marketing"),
    ("scrivi la headline e il copy della landing page", "copywriting"),
    ("come migliorare la seo e le parole chiave del sito?", "seo"),
    ("serve un piano editoriale per instagram e linkedin", "social-media"),
    ("come calcolo il cac e il ltv, e faccio un test a/b?", "analytics-e-kpi"),
    ("devo pianificare un progetto con milestone e rischi", "project-management"),
    ("ho un'idea di startup, come la valido con un mvp?", "startup-e-business-plan"),
    ("aiutami con il cv e il colloquio di lavoro", "carriera-e-lavoro"),
    ("devo preparare un esame, come studio e memorizzo?", "apprendimento-e-studio"),
    ("ho un dilemma, devo scegliere: pro e contro", "decisioni-e-pensiero-critico"),
    ("organizza il viaggio: itinerario e valigia per Lisbona", "viaggi-e-logistica"),
    ("posso recedere da un acquisto online? ho diritto al rimborso?", "diritti-e-burocrazia-italia"),
    ("il mio useeffect parte in loop, come evito i re-render in react?", "react-e-frontend-moderno"),
    ("come faccio il graceful shutdown di un server express con node?", "nodejs-backend"),
    ("errore del borrow checker in rust: value borrowed here after move", "rust"),
    ("come uso le goroutine e i canali in go senza leak?", "go"),
    ("come scrivo uno script bash sicuro con set -euo pipefail?", "shell-e-linux"),
    ("mi spieghi la programmazione dinamica e la complessità big o?", "algoritmi-e-strutture-dati"),
    ("come costruisco un rag con embedding per un chatbot e valuto le allucinazioni?", "ai-engineering-llm"),
    ("devo aggiornare un progetto legacy senza test, riscrivo da zero?", "refactoring-e-codice-legacy"),
    ("voglio una redis cache con ttl e invalidazione", "nosql-e-cache"),
    ("devo progettare un design system con token e dark mode", "design-system-e-ui-kit"),
    ("che font abbino per titoli e testo? serve una scala tipografica", "tipografia"),
    ("scegli una palette di colori con il giusto contrasto wcag", "colore-e-palette"),
    ("rendi il mio sito accessibile con screen reader e navigazione da tastiera", "accessibilita-web"),
    ("disegna un'icona svg 24x24 con il path e ottimizzala", "grafica-vettoriale-e-svg"),
    ("prepara l'icona adattiva android e l'ico per windows", "icone-e-app-icon"),
    ("che grafico uso per mostrare l'andamento delle vendite nel tempo?", "data-visualization"),
    ("come preparo il pdf per la stampa con abbondanza e cmyk?", "grafica-per-stampa"),
    ("come faccio un'animazione css fluida con keyframes e transform?", "css-e-animazioni"),
    ("il wifi è lento e il router va a scatti, come diagnostico la rete?", "reti-e-wifi"),
    ("come proteggo gli account con password manager e 2fa dal phishing?", "privacy-e-sicurezza-personale"),
    ("voglio montare un home server con docker compose e nextcloud", "linux-e-self-hosting"),
    ("progetto con esp32 e sensore, resistenza per il led", "elettronica-arduino-raspberry"),
    ("come imposto un backup 3-2-1 con restic?", "backup-e-cloud-storage"),
    ("scrivi un prompt migliore con esempi few shot per il mio system prompt", "prompt-engineering"),
    ("come strutturo un servizio fastapi con pydantic e dependency injection?", "fastapi-e-backend-python"),
    ("devo prevenire gli n+1 in django con select_related", "django-e-flask"),
    ("uso laravel ed eloquent: come faccio l'eager loading?", "php-e-laravel"),
    ("come uso async await e linq in c# con asp.net core?", "csharp-e-dotnet"),
    ("la mia app swiftui non aggiorna la vista, come uso state e binding?", "swift-e-ios"),
    ("flutter: setstate o riverpod per gestire lo stato?", "flutter-e-dart"),
    ("viewmodel e hilt in jetpack compose, come li organizzo?", "android-nativo-compose"),
    ("conviene graphql o grpc al posto di rest? serve dataloader", "graphql-e-grpc"),
    ("come implemento i websocket con riconnessione e heartbeat?", "websocket-e-realtime"),
    ("come faccio il login con oauth2 e pkce, jwt o sessioni?", "autenticazione-e-autorizzazione"),
    ("query lenta su postgres: window function, indice gin e explain analyze", "postgresql-avanzato"),
    ("sqlalchemy fa troppe query, come evito il problema n+1 dell'orm?", "orm-e-accesso-ai-dati"),
    ("scrivi una regex per validare e attenzione al backtracking redos", "regex-e-parsing"),
    ("voglio creare un linguaggio di programmazione con lexer e ast", "interpreti-e-compilatori"),
    ("come faccio il game loop con delta time in godot?", "sviluppo-giochi"),
    ("firmware freertos su stm32: interrupt e watchdog", "programmazione-embedded"),
    ("cos'è un aggregato in ddd e quando uso cqrs ed event sourcing?", "ddd-e-architettura-a-eventi"),
    ("la build con vite è lenta, come configuro un monorepo con turborepo?", "build-tools-e-bundler"),
    ("come tengo sicure le dipendenze npm contro il typosquatting?", "gestione-dipendenze-e-supply-chain"),
    ("che licenza scelgo per il mio progetto open source: mit o gpl?", "open-source-e-licenze"),
    ("devo costruire una pipeline etl con airflow e dbt su bigquery", "data-engineering"),
    ("script powershell per creare un'attività pianificata su windows", "powershell-e-automazione-windows"),
    ("come comunico tra frontend e backend rust in tauri con invoke?", "tauri-e-app-desktop"),
    ("sto scrivendo un bot telegram con webhook e pulsanti inline", "bot-e-chatbot-sviluppo"),
    ("voglio fare test di carico con k6 e property based testing", "test-avanzati-e-carico"),
    ("bug sull'ora legale: come gestisco fusi orari e utc nel codice?", "date-ora-e-fusi-orari"),
    ("perché 0.1 + 0.2 non fa 0.3? come gestisco i soldi nel codice?", "numeri-precisione-e-denaro"),
    ("i caratteri accentati escono strani, problema di utf-8 e mojibake", "unicode-e-localizzazione"),
    ("ho sbagliato un commit: come uso reflog e rebase interattivo?", "git-avanzato"),
    ("il servizio è giù in produzione, come gestisco l'incidente e il post-mortem?", "affidabilita-incident-e-postmortem"),
    ("il pod va in crashloopbackoff su kubernetes", "kubernetes-pratico"),
    ("errore cors nel browser: come imposto gli header e la cache http?", "http-e-web-platform"),
    ("migliora lcp e core web vitals del mio sito", "web-performance"),
    ("voglio una pwa con service worker e funzionamento offline", "pwa-e-service-worker"),
    ("devo fare un'estensione chrome con manifest v3 e content script", "estensioni-browser"),
    ("come uso i breakpoint condizionali nel debugger di vs code?", "ide-e-produttivita-sviluppatore"),
])
def test_routing_picks_the_right_skill_first_or_second(text, expected):
    assert expected in top(text), (text, top(text))


@pytest.mark.parametrize("text", ["ciao come stai", "che ore sono?", "che tempo fa domani a Roma", "grazie mille", "ricordami di chiamare Luca alle 18", "quanto fa 12 per 7", "cosa ho in agenda domani?", "metti un promemoria tra un'ora", "quanto costa un caffè a Milano", "dimmi le ultime notizie", "apri il sito di repubblica", "come si chiama la capitale della Francia?", "raccontami una barzelletta", "che giorno è oggi?", "scrivimi una poesia sull'autunno", "suggerisci un nome per il mio gatto"])
def test_small_talk_and_simple_requests_activate_nothing(text):
    assert top(text) == []


def test_context_respects_budget_and_second_skill_must_be_relevant():
    two = REG.match("rivedi questo codice python e trova il bug, mi dà errore", k=2)
    ctx = REG.context(two, 1800)
    assert len(ctx) < 2300 and ctx.startswith("Competenze specialistiche attive") and "## " in ctx
    assert REG.context([], 1000) == ""
    long = Skill("x-long", "Lunga", "vita", "d" * 50, ["lunga"], "riga\n" * 1000, False)
    assert "usa use_skill" in REG.context([long], 700)


def test_parse_block_rejects_invalid_definitions():
    assert parse_block("name: ok-name\ndescription: una descrizione\ntriggers: a, b\n\ncorpo della competenza") is not None
    assert parse_block("name: Nome Non Valido\ndescription: x\n\ncorpo") is None
    assert parse_block("name: senza-corpo\ndescription: x") is None


@pytest.mark.asyncio
async def test_agent_injects_matching_skill_and_forced_skill_only_when_enabled():
    seen = []

    class LLM:
        async def chat(self, messages, tools=None, model=None, kind="chat"):
            seen.append(messages[0]["content"])
            return {"content": "ok"}

    reg, store = ToolRegistry(), MemoryStore()
    agent = Agent(Settings(jarvis_api_token="t"), LLM(), store, reg)
    agent.skills = REG
    await agent.reply("rivedi questo codice, ho una pull request", "s1")
    assert "Revisione del codice" in seen[-1]
    await agent.reply("ciao, come va tutto quanto oggi", "s2")
    assert "Competenze specialistiche attive" not in seen[-1]
    await agent.reply("dimmi la tua", "s3", skills=["tasse-italia"])
    assert "Tasse e fisco in Italia" in seen[-1]
    off = Agent(Settings(jarvis_api_token="t", skills_enabled=False), LLM(), store, reg)
    off.skills = REG
    await off.reply("rivedi questo codice, ho una pull request", "s4")
    assert "Competenze specialistiche attive" not in seen[-1]


@pytest.mark.asyncio
async def test_skill_tools_custom_skill_lifecycle_and_persistence():
    brain, _ = make()
    reg = ToolRegistry()
    skills = SkillRegistry()
    register_skill_tools(reg, skills, brain)

    assert "revisione-codice" in await reg.call("list_skills", json.dumps({"domain": "programmazione"}))
    used = await reg.call("use_skill", json.dumps({"name": "tasse-italia"}))
    assert "forfettario" in used.lower() and "Applica questo metodo" in used
    assert "non trovata" in await reg.call("use_skill", json.dumps({"name": "inesistente"}))

    bad = await reg.call("skill_save", json.dumps({"name": "tasse-italia", "title": "x", "description": "d", "instructions": "i" * 60}))
    assert "integrata" in bad
    ok = await reg.call("skill_save", json.dumps({"name": "report-settimanale", "title": "Report settimanale", "description": "Come scrivo il mio report del venerdì al capo",
                                                  "instructions": "Struttura: 1) risultati della settimana con numeri; 2) problemi; 3) priorità della prossima. Massimo 10 righe.",
                                                  "triggers": "report del venerdì, report settimanale"}))
    assert "salvata" in ok and skills.match("scrivimi il report settimanale per il capo")[0].name == "report-settimanale"

    # sopravvive al riavvio (nuovo registro dallo stesso cervello) e non compare nelle ricerche normali
    fresh = SkillRegistry()
    assert await fresh.load_custom(brain) == 1 and fresh.get("report-settimanale").builtin is False
    assert not [r for r in await brain.search("report settimanale venerdì", k=5) if r["source"] == "skill"]

    assert "eliminata" in await reg.call("skill_delete", json.dumps({"name": "report-settimanale"}))
    assert await SkillRegistry().load_custom(brain) == 0
    assert "integrate non si eliminano" in await reg.call("skill_delete", json.dumps({"name": "seo"}))


@pytest.mark.asyncio
async def test_bot_skills_commands():
    bot, st = make_bot()
    st.skills = REG
    msg = lambda text, i: {"update_id": i, "message": {"from": {"id": 42}, "chat": {"id": 42}, "text": text}}  # noqa: E731
    await bot.handle_update(msg("/skills", 1))
    text, markup = st.tg.out[-1]
    assert "Le mie competenze" in text and any("Finanza" in b[0]["text"] for b in markup["inline_keyboard"])
    await bot.handle_update({"update_id": 2, "callback_query": {"id": "c", "from": {"id": 42}, "data": "sk:finanza", "message": {"chat": {"id": 42}, "message_id": 3}}})
    assert "tasse-italia" in st.tg.out[-1][0]
    await bot.handle_update(msg("/skill seo come posiziono il mio sito", 3))
    assert st.tg.out[-1][0].startswith("eco:come posiziono il mio sito")
    await bot.handle_update(msg("/skill nonesiste prova", 4))
    assert "Non conosco" in st.tg.out[-1][0]
