import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field

from .agent import Agent
from .api import router as api_router
from .auth import require_token, throttle
from .backup import HFBackup
from .bot import COMMANDS, TelegramBot
from .voice import VoiceService
from .budget_service import BudgetService
from .freellm_admin import FreeLLMAdmin
from .pending import PendingStore
from .security import RateLimiter, SecurityHeaders, client_ip
from .config import get_settings
from .llm import LLMClient, LLMError
from .gateway import make_client
from .gateway import router as gateway_router
from .memory import build_store
from .pc import PCBridge
from .notify import Notifier
from .scheduler import background_loop
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


class ChatOut(BaseModel):
    reply: str


async def _webhook_guard(tg: Telegram, hook: str) -> None:
    """Se un vecchio servizio con lo stesso bot ripristina il suo webhook, lo riprende (controllo ogni 10 minuti)."""
    while True:
        await asyncio.sleep(600)
        try:
            await tg.ensure_webhook(hook)
        except Exception:
            log.warning("controllo del webhook Telegram fallito")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = app.state.store = build_store(settings)
    tools = ToolRegistry()
    admin = app.state.admin = FreeLLMAdmin(settings)
    budget = app.state.budget = BudgetService(admin)
    register_basic_tools(tools, settings, store, budget=budget.text if budget.enabled else None)
    app.state.gateway_client = make_client()
    pc = app.state.pc = PCBridge()
    register_pc_tools(tools, pc)
    register_web_tools(tools)
    pending = app.state.pending = PendingStore(settings.pending_ttl_s)
    app.state.chat_limiter = RateLimiter(settings.chat_per_minute)
    google = GoogleClient(settings)
    if google.enabled:
        register_google_tools(tools, settings, google, pending)
    app.state.agent = Agent(settings, LLMClient(settings), store, tools)
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
    task = asyncio.create_task(background_loop(settings, store, notifier, budget, app.state.backup))
    if tg.enabled:
        base = settings.public_url or settings.render_external_url
        if base and settings.telegram_webhook_secret:
            hook = f"{base.rstrip('/')}/telegram/webhook"
            try:
                # prende il posto di un eventuale vecchio bot con lo stesso token e imposta il menu dei comandi
                await tg.set_webhook(hook, drop_pending=await tg.webhook_url() != hook)
                await tg.set_commands(COMMANDS)
            except Exception:
                log.exception("configurazione del bot Telegram fallita")
            guard = asyncio.create_task(_webhook_guard(tg, hook))
    yield
    task.cancel()
    if guard:
        guard.cancel()
    await app.state.gateway_client.aclose()


log = logging.getLogger("jarvis")
app = FastAPI(title="JARVIS", lifespan=lifespan)
app.include_router(gateway_router)
app.include_router(api_router)

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
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
app.add_middleware(SecurityHeaders)


@app.api_route("/", methods=["GET", "HEAD"])
async def root() -> dict:
    return {"name": "JARVIS", "status": "ok"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatOut, dependencies=[Depends(require_token)])
async def chat(body: ChatIn) -> ChatOut:
    limiter: RateLimiter = app.state.chat_limiter
    if wait := limiter.retry_after():
        raise HTTPException(429, "Troppe richieste: rallenta un momento", headers={"Retry-After": str(wait)})
    limiter.hit()
    try:
        return ChatOut(reply=await app.state.agent.reply(body.message, body.session_id, voice=body.voice))
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
