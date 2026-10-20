from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agent import Agent
from .auth import require_token
from .config import get_settings
from .llm import LLMClient, LLMError
from .memory import build_store
from .tools import ToolRegistry
from .tools.basic import register_basic_tools


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str = "default"


class ChatOut(BaseModel):
    reply: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = build_store(settings)
    tools = ToolRegistry()
    register_basic_tools(tools, settings, store)
    app.state.agent = Agent(settings, LLMClient(settings), store, tools)
    yield


app = FastAPI(title="JARVIS", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatOut, dependencies=[Depends(require_token)])
async def chat(body: ChatIn) -> ChatOut:
    try:
        return ChatOut(reply=await app.state.agent.reply(body.message, body.session_id))
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
