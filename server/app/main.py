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
from .scheduler import reminder_loop
from .telegram import Telegram
from .tools import ToolRegistry
from .google import GoogleClient
from .tools.basic import register_basic_tools
from .tools.google_tools import register_google_tools
from .tools.pc_tools import register_pc_tools


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    voice: bool = False  # risposta destinata alla sintesi vocale


class ChatOut(BaseModel):
    reply: str


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
    pending = app.state.pending = PendingStore(settings.pending_ttl_s)
    app.state.chat_limiter = RateLimiter(settings.chat_per_minute)
    google = GoogleClient(settings)
    if google.enabled:
        register_google_tools(tools, settings, google, pending)
    app.state.agent = Agent(settings, LLMClient(settings), store, tools)
    tg = app.state.tg = Telegram(settings)
    app.state.settings = settings
    if tg.enabled:
        def notify_pending(p) -> None:
            asyncio.get_running_loop().create_task(
                tg.send_buttons(settings.telegram_owner_id, f"Conferma richiesta: {p.summary}",
                                [("Approva", f"ok:{p.id}"), ("Rifiuta", f"no:{p.id}")])
            )

        pending.on_create = notify_pending
    task = None
    if tg.enabled:
        base = settings.public_url or settings.render_external_url
        if base and settings.telegram_webhook_secret:
            try:
                await tg.set_webhook(f"{base.rstrip('/')}/telegram/webhook")
            except Exception:
                log.exception("setWebhook fallito")
        task = asyncio.create_task(reminder_loop(settings, store, tg))
    yield
    if task:
        task.cancel()
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
    allow_methods=["GET", "POST", "OPTIONS"],
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


async def _handle_telegram_text(chat_id: int, text: str) -> None:
    tg: Telegram = app.state.tg
    try:
        await tg.typing(chat_id)
        reply = await app.state.agent.reply(text, f"tg-{chat_id}")
    except Exception:
        log.exception("errore gestione messaggio Telegram")
        reply = "Si è verificato un problema, signore. Riprovi tra un momento."
    await tg.send(chat_id, reply or "…")


async def _handle_telegram_callback(cb: dict) -> None:
    tg: Telegram = app.state.tg
    action, _, pid = (cb.get("data") or "").partition(":")
    msg = cb.get("message") or {}
    if action not in ("ok", "no") or not pid:
        return await tg.answer_callback(cb["id"])
    p = await app.state.pending.decide(pid, action == "ok")
    if p is None or p.status == "expired":
        outcome = "Richiesta scaduta o inesistente."
    else:
        outcome = {"approved": f"Approvata. {p.result}", "rejected": "Rifiutata.", "failed": p.result}.get(p.status, p.status)
    await tg.answer_callback(cb["id"], outcome[:150])
    if msg.get("message_id"):
        await tg.clear_buttons(msg["chat"]["id"], msg["message_id"], f"{p.summary if p else 'Richiesta'}: {outcome}")


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
    if cb := update.get("callback_query"):
        if cb.get("from", {}).get("id") == s.telegram_owner_id:
            background.add_task(_handle_telegram_callback, cb)
        return {"ok": True}
    msg = update.get("message") or {}
    # whitelist: chiunque non sia il proprietario viene ignorato in silenzio
    if msg.get("from", {}).get("id") == s.telegram_owner_id and msg.get("text"):
        # risposta immediata a Telegram; l'elaborazione (lenta) va in background per evitare retry
        background.add_task(_handle_telegram_text, msg["chat"]["id"], msg["text"])
    return {"ok": True}


@app.websocket("/ws/pc")
async def ws_pc(ws: WebSocket) -> None:
    ip = client_ip(ws)
    if throttle.retry_after(ip):
        await ws.close(code=4429)
        return
    await app.state.pc.serve(ws, app.state.settings.jarvis_api_token, on_auth_fail=lambda: throttle.fail(ip))
