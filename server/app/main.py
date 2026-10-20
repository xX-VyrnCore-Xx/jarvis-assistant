import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field

from .agent import Agent
from .auth import require_token
from .config import get_settings
from .llm import LLMClient, LLMError
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
    session_id: str = "default"
    voice: bool = False  # risposta destinata alla sintesi vocale


class ChatOut(BaseModel):
    reply: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = build_store(settings)
    tools = ToolRegistry()
    register_basic_tools(tools, settings, store)
    pc = app.state.pc = PCBridge()
    register_pc_tools(tools, pc)
    google = GoogleClient(settings)
    if google.enabled:
        register_google_tools(tools, settings, google)
    app.state.agent = Agent(settings, LLMClient(settings), store, tools)
    tg = app.state.tg = Telegram(settings)
    app.state.settings = settings
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


log = logging.getLogger("jarvis")
app = FastAPI(title="JARVIS", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatOut, dependencies=[Depends(require_token)])
async def chat(body: ChatIn) -> ChatOut:
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
    msg = (await request.json()).get("message") or {}
    # whitelist: chiunque non sia il proprietario viene ignorato in silenzio
    if msg.get("from", {}).get("id") == s.telegram_owner_id and msg.get("text"):
        # risposta immediata a Telegram; l'elaborazione (lenta) va in background per evitare retry
        background.add_task(_handle_telegram_text, msg["chat"]["id"], msg["text"])
    return {"ok": True}


@app.websocket("/ws/pc")
async def ws_pc(ws: WebSocket) -> None:
    await app.state.pc.serve(ws, app.state.settings.jarvis_api_token)
