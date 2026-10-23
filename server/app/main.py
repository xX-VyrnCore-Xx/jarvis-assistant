import asyncio
import hashlib
import hmac
import html
import json
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field

from .agent import Agent
from .api import VERSION, router as api_router
from .auth import require_token, throttle
from .backup import HFBackup
from .brain.embed import Embedder
from .brain.service import Brain
from .brain.store import MemoryBrainStore, SupabaseBrainStore
from .brain.tools import register_brain_tools
from .crypto import Vault
from .bot import COMMANDS, TelegramBot
from .voice import VoiceService
from .budget_service import BudgetService
from .freellm_admin import FreeLLMAdmin
from .pending import PendingStore
from .security import RateLimiter, SecurityHeaders, client_ip
from .config import Settings, get_settings
from .llm import LLMClient, LLMError
from .gateway import make_client
from .gateway import router as gateway_router
from .memory import build_store
from .pc import PCBridge
from .notify import Notifier
from .brain.knowledge import Knowledge
from .skills.registry import SkillRegistry
from .skills.tools import register_skill_tools
from .proactive import Proactive
from .brain.mirror import BrainMirror
from .reminders import ReminderService
from .coding import CodingService
from .tools.coding_tools import register_coding_tools
from .voiceline import VoiceLine, router as voiceline_router
from .phonebridge import PhoneBridge
from .tools.phone_tools import register_phone_tools
from . import tgwatch
from .live import LiveFeeds, register_live_tools
from .scheduler import background_loop, brain_loop, heartbeat_loop, live_loop, maintenance_loop, proactive_loop
from .updates import UpdateService
from .usage import UsageTracker
from .telegram import Telegram
from .tools import ToolRegistry
from .google import GoogleClient
from .tools.basic import register_basic_tools
from .tools.google_tools import register_google_tools
from .tools.pc_tools import register_pc_tools
from .tools.web import register_web_tools


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    voice: bool = False  # risposta destinata alla sintesi vocale
    model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:/-]{1,80}$")  # modello scelto nell'app; vuoto = automatico
    skill: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")  # competenza da usare di sicuro (altrimenti si sceglie da sola)


class ChatOut(BaseModel):
    reply: str


async def _telegram_run(app: FastAPI, settings: Settings) -> None:
    """Collega il bot (webhook o lettura diretta), poi lo tiene collegato; all'avvio avvisa se il servizio è stato fermo a lungo."""
    tg: Telegram = app.state.tg
    mode = await tgwatch.setup(tg, settings, COMMANDS)
    await tgwatch.announce_return(tg, app.state.store, VERSION)
    if mode == "webhook":
        await tgwatch.guard_loop(tg, settings)
    else:
        await tgwatch.poll_loop(tg, app.state.bot, app.state.bot.accepts)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = app.state.store = build_store(settings)
    tools = ToolRegistry()
    admin = app.state.admin = FreeLLMAdmin(settings)
    budget = app.state.budget = BudgetService(admin)
    vault = Vault(settings.encryption_key or settings.jarvis_api_token)
    if settings.supabase_url and settings.supabase_service_key:
        bstore = SupabaseBrainStore(settings, vault)
    else:
        bstore = MemoryBrainStore()
        bstore.vault = vault
    usage = app.state.usage = UsageTracker()
    llm = app.state.llm = LLMClient(settings, usage=usage)
    brain = app.state.brain = Brain(settings, bstore, Embedder(settings, usage=usage), vault, llm)
    brain.knowledge = Knowledge(settings, brain, store)
    reminders = app.state.reminders = ReminderService(settings, store)  # promemoria ↔ Calendario (google si collega dopo)
    register_basic_tools(tools, settings, store, budget=budget.text if budget.enabled else None, brain=brain, reminders=reminders, search=llm.search if settings.web_search_engines else None)
    register_brain_tools(tools, brain)
    app.state.gateway_client = make_client()
    pc = app.state.pc = PCBridge()
    register_pc_tools(tools, pc)
    register_web_tools(tools, search=llm.search if settings.web_search_engines else None)
    pending = app.state.pending = PendingStore(settings.pending_ttl_s)
    app.state.chat_limiter = RateLimiter(settings.chat_per_minute)
    google = app.state.google = GoogleClient(settings, store=store)
    await google.load()
    reminders.google = google
    if google.has_client:
        register_google_tools(tools, settings, google, pending, brain)
    app.state.agent = Agent(settings, llm, store, tools, brain)
    skills = app.state.skills = SkillRegistry()
    register_skill_tools(tools, skills, brain)
    app.state.agent.skills = skills
    coding = app.state.coding = CodingService(settings, store)
    register_coding_tools(tools, coding, pending)
    bridge = app.state.phone = PhoneBridge(lambda: app.state.notifier)
    register_phone_tools(tools, pending, lambda: app.state.notifier, bridge)
    app.state.agent.coding = coding
    try:
        custom = await skills.load_custom(brain)
    except Exception as e:  # il database può non essere pronto: le competenze personali tornano al prossimo avvio
        custom = 0
        log.info("competenze personali non caricate: %s", type(e).__name__)
    log.info("competenze: %d integrate, %d personali", len(skills) - custom, custom)
    tg = app.state.tg = Telegram(settings)
    app.state.settings = settings
    app.state.bot = TelegramBot(app)
    if tg.enabled:
        def notify_pending(p) -> None:
            asyncio.get_running_loop().create_task(
                tg.send_buttons(settings.telegram_owner_id, f"Conferma richiesta: {p.summary}",
                                [("Approva", f"ok:{p.id}"), ("Rifiuta", f"no:{p.id}")])
            )

        pending.on_create = notify_pending
    async def send_notification(title: str, body: str = "") -> str:
        await app.state.notifier.push("info", title[:120], body[:500])
        return "Notifica inviata."

    tools.register("send_notification", "Invia una notifica a tutte le app dell'utente (PC e telefono).",
                   {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title"]},
                   send_notification)
    app.state.backup = HFBackup(settings)
    app.state.voice = VoiceService(pc)
    notifier = app.state.notifier = Notifier(settings, store, tg)
    reminders.on_change = lambda: notifier.sync("reminders")
    app.state.voiceline = VoiceLine(settings, store, llm, notifier)  # segreteria telefonica con voce (Twilio), spenta finché non si imposta TWILIO_AUTH_TOKEN
    mirror = app.state.mirror = BrainMirror(brain, store)  # il cervello segue promemoria, ricordi e attività
    reminders.mirror = mirror
    prev = pending.on_create

    def on_pending(p) -> None:
        if prev:
            prev(p)
        try:
            asyncio.get_running_loop().create_task(notifier.push("pending", "Conferma richiesta", p.summary))
        except RuntimeError:  # creata fuori dal loop (test): nessuna notifica
            pass

    pending.on_create = on_pending
    guard = None
    task = asyncio.create_task(background_loop(settings, store, notifier, budget, app.state.backup, mirror, reminders))
    updates = app.state.updates = UpdateService(settings, store, notifier)
    live = app.state.live = LiveFeeds(settings, store)
    await live.load_custom()
    register_live_tools(tools, live, updates, brain, getattr(brain, "knowledge", None), VERSION)
    live_task = asyncio.create_task(live_loop(settings, store, live, brain, getattr(brain, "knowledge", None))) if settings.live_news else None
    brain_task = asyncio.create_task(brain_loop(settings, store, brain, app.state.agent, notifier, mirror))
    maint_task = asyncio.create_task(maintenance_loop(settings, store, usage, updates, notifier, reminders))
    proactive = app.state.proactive = Proactive(settings, store, notifier, google, brain, budget)
    proactive_task = asyncio.create_task(proactive_loop(settings, proactive))
    heartbeat_task = asyncio.create_task(heartbeat_loop(app))
    if tg.enabled:
        guard = asyncio.create_task(_telegram_run(app, settings))
    vault = getattr(store, "vault", None)
    log.info("sicurezza: cifratura_dati=%s privacy_modelli=%s", "attiva" if vault and vault.enabled else "NO (manca ENCRYPTION_KEY)", settings.privacy_mode)
    log.info("secondo_cervello: attivo=%s embedding=%s modello=%s", brain.enabled, brain.embedder.enabled, brain.embedder.model)
    log.info("integrazioni: telegram=%s google=%s(client=%s) firebase=%s backup_hf=%s freellm=%s supabase=%s",
             tg.enabled, google.enabled, google.has_client, notifier.fcm.enabled, app.state.backup.enabled, budget.enabled,
             "sì" if settings.supabase_url and settings.supabase_service_key else "no")
    yield
    task.cancel()
    brain_task.cancel()
    if live_task:
        live_task.cancel()
    maint_task.cancel()
    proactive_task.cancel()
    heartbeat_task.cancel()
    await usage.flush(store)  # non perde i consumi dell'ultima ora allo spegnimento
    if guard:
        guard.cancel()
    await app.state.gateway_client.aclose()


logging.getLogger("jarvis").setLevel(logging.INFO)
logging.getLogger("jarvis").propagate = False
if not logging.getLogger("jarvis").handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    logging.getLogger("jarvis").addHandler(_h)
log = logging.getLogger("jarvis")


class _RedactQuery(logging.Filter):
    """I log di accesso non devono mostrare i parametri dell'indirizzo (es. codici di autorizzazione Google): si tiene solo il percorso."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str) and "?" in record.args[2]:
            record.args = (*record.args[:2], record.args[2].split("?")[0] + "?[…]", *record.args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactQuery())
app = FastAPI(title="JARVIS", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)  # niente schema pubblico delle API
app.include_router(gateway_router)
app.include_router(api_router)
app.include_router(voiceline_router)

# La finestra web delle app (Tauri/Capacitor) è un'origine diversa dal server: senza CORS il browser blocca /chat.
# L'autenticazione è un Bearer token (niente cookie), quindi nessuna credenziale cross-site.
APP_ORIGINS = [
    "http://tauri.localhost", "https://tauri.localhost", "tauri://localhost",  # Windows (Tauri 2)
    "https://localhost", "http://localhost", "capacitor://localhost",  # Android (Capacitor) e sviluppo
    "http://localhost:1420",
]


def _cors_origins() -> list[str]:
    extra = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
    return APP_ORIGINS + extra


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Device-Id"],
    max_age=600,
)
app.add_middleware(SecurityHeaders)


def _base_url() -> str:
    s = app.state.settings
    return (s.public_url or s.render_external_url).rstrip("/")


@app.get("/google/callback", response_class=HTMLResponse)
async def google_callback(code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    """Ritorno dalla pagina di consenso Google. Vale solo con uno `state` generato dal comando /google del proprietario."""
    page = lambda title, text: HTMLResponse(  # noqa: E731
        f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<body style='font-family:system-ui;background:#07121c;color:#e8f6ff;display:grid;place-items:center;height:100vh;margin:0'>"
        f"<div style='max-width:420px;padding:24px;text-align:center'><h2>{title}</h2><p>{text}</p></div>")
    if error or not code:
        return page("Collegamento annullato", "Google non ha concesso l'accesso. Puoi riprovare da Telegram con /google.")
    try:
        await app.state.google.complete(code, state, f"{_base_url()}/google/callback")
    except ValueError as e:
        return page("Collegamento non riuscito", html.escape(str(e)))
    except Exception:
        log.exception("collegamento Google fallito")
        return page("Collegamento non riuscito", "Errore imprevisto: riprova tra poco.")
    await app.state.notifier.push("info", "Google collegato", "Gmail, Calendar e Drive sono ora attivi.", telegram=True)
    return page("Google collegato", "Gmail, Calendar e Drive sono attivi. Puoi chiudere questa scheda.")


@app.api_route("/", methods=["GET", "HEAD"])
async def root() -> dict:
    return {"name": "JARVIS", "status": "ok"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat/stream", dependencies=[Depends(require_token)])
async def chat_stream(body: ChatIn, x_device_id: str = Header(default="", max_length=64)) -> StreamingResponse:
    """Come /chat ma a eventi SSE: `status` (uso di un tool), `delta` (testo man mano), `done` (risposta intera), `error`."""
    limiter: RateLimiter = app.state.chat_limiter
    if wait := limiter.retry_after():
        raise HTTPException(429, "Troppe richieste: rallenta un momento", headers={"Retry-After": str(wait)})
    limiter.hit()

    async def gen():
        try:
            async for kind, data in app.state.agent.reply_stream(body.message, body.session_id, voice=body.voice, model=body.model, skills=[body.skill] if body.skill else None):
                yield f"event: {kind}\ndata: {json.dumps({'text': data}, ensure_ascii=False)}\n\n"
                if kind == "done":
                    app.state.notifier.sync("chat", x_device_id)  # gli altri dispositivi mostrano subito lo scambio
        except LLMError as e:
            yield f"event: error\ndata: {json.dumps({'text': str(e)}, ensure_ascii=False)}\n\n"
        except Exception:
            log.exception("errore nella risposta in streaming")
            yield f"event: error\ndata: {json.dumps({'text': 'Si è verificato un problema, riprova.'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/github/webhook")
async def github_webhook(request: Request) -> dict:
    """Facoltativo: GitHub avvisa alla pubblicazione di una Release e le app lo sanno subito (altrimenti basta il controllo ogni 30 minuti)."""
    secret = app.state.settings.github_webhook_secret
    if not secret:
        raise HTTPException(404, "Not found")
    raw = await request.body()
    sig = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not secrets.compare_digest(sig, expected):
        raise HTTPException(403, "Forbidden")
    if request.headers.get("x-github-event") == "release":
        payload = json.loads(raw or b"{}")
        if payload.get("action") in ("published", "released"):
            return {"ok": True, "result": await app.state.updates.poll_and_notify(force=True)}
    return {"ok": True}


@app.post("/chat", response_model=ChatOut, dependencies=[Depends(require_token)])
async def chat(body: ChatIn, x_device_id: str = Header(default="", max_length=64)) -> ChatOut:
    limiter: RateLimiter = app.state.chat_limiter
    if wait := limiter.retry_after():
        raise HTTPException(429, "Troppe richieste: rallenta un momento", headers={"Retry-After": str(wait)})
    limiter.hit()
    try:
        reply = await app.state.agent.reply(body.message, body.session_id, voice=body.voice, model=body.model, skills=[body.skill] if body.skill else None)
        app.state.notifier.sync("chat", x_device_id)
        return ChatOut(reply=reply)
    except LLMError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(default=""),
) -> dict:
    s = app.state.settings
    if not (app.state.tg.enabled and s.telegram_webhook_secret) or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, s.telegram_webhook_secret
    ):
        raise HTTPException(403, "Forbidden")
    update = await request.json()
    # whitelist: chiunque non sia il proprietario viene ignorato in silenzio
    # risposta immediata a Telegram; l'elaborazione (lenta) va in background per evitare retry
    if app.state.bot.accepts(update):
        background.add_task(app.state.bot.handle_update, update)
    return {"ok": True}


@app.websocket("/ws/pc")
async def ws_pc(ws: WebSocket) -> None:
    ip = client_ip(ws)
    if throttle.retry_after(ip):
        await ws.close(code=4429)
        return
    await app.state.pc.serve(ws, app.state.settings.jarvis_api_token, on_auth_fail=lambda: throttle.fail(ip))
