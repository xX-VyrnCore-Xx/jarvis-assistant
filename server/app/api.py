"""API per le app (Windows e Android): stato, token, cronologia, promemoria e conferme."""
import asyncio
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .auth import require_token
from .freellm_admin import AdminError
from .voice import TTSError
from .tools.basic import parse_due

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
STARTED = time.time()
VERSION = "0.2.0"


class ReminderIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    when: str  # data/ora locale ISO 8601


class DeviceIn(BaseModel):
    platform: str = Field(pattern=r"^(android|windows|web)$")
    token: str = Field(min_length=8, max_length=4096)
    label: str = Field(default="", max_length=80)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ReadIn(BaseModel):
    ids: list[int] | None = None  # None = tutte


@router.get("/tokens")
async def tokens(request: Request, refresh: bool = False) -> dict:
    budget = request.app.state.budget
    if not budget.enabled:
        raise HTTPException(404, "FreeLLMAPI non è in questo container")
    try:
        return await budget.get(force=refresh)
    except AdminError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/status")
async def status(request: Request) -> dict:
    st = request.app.state
    s = st.settings
    out = {
        "version": VERSION,
        "uptime_s": int(time.time() - STARTED),
        "freellm": {"enabled": st.budget.enabled, "ready": await st.admin.ready() if st.budget.enabled else False},
        "pc_connected": st.pc.connected,
        "telegram": st.tg.enabled,
        "google": st.google.enabled,
        "memory": "supabase" if s.supabase_url and s.supabase_service_key else "ram",
        "voice": st.voice.enabled,
        "pending_actions": len(st.pending.list_pending()),
        "tokens": None,
    }
    if st.budget.enabled:
        try:
            b = await st.budget.get()
            out["tokens"] = {k: b[k] for k in ("remaining_tokens", "documented_monthly_tokens", "used_tokens", "resets_at")}
        except AdminError:
            pass
    return out


@router.get("/history")
async def history(request: Request, session_id: str = Query("default", pattern=r"^[A-Za-z0-9_.:-]{1,64}$"),
                  limit: int = Query(40, ge=1, le=200)) -> list[dict]:
    return await request.app.state.store.recent_messages(session_id, limit)


@router.get("/reminders")
async def reminders(request: Request) -> list[dict]:
    return await request.app.state.store.list_reminders()


@router.post("/reminders", status_code=201)
async def add_reminder(body: ReminderIn, request: Request) -> dict:
    tz = ZoneInfo(request.app.state.settings.timezone)
    try:
        due = parse_due(body.when, tz)
    except ValueError as e:
        raise HTTPException(422, "Data non valida (usa il formato ISO 8601)") from e
    if due <= datetime.now(tz):
        raise HTTPException(422, "La data è nel passato")
    await request.app.state.store.add_reminder(body.text, due)
    return {"ok": True}


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int, request: Request) -> dict:
    await request.app.state.store.delete_reminder(reminder_id)
    return {"ok": True}


@router.get("/pending")
async def pending(request: Request) -> list[dict]:
    return [p.public() for p in request.app.state.pending.list_pending()]


@router.post("/pending/{pid}/{decision}")
async def decide(pid: str, decision: str, request: Request) -> dict:
    if decision not in ("approve", "reject"):
        raise HTTPException(404, "Decisione sconosciuta")
    p = await request.app.state.pending.decide(pid, decision == "approve")
    if p is None:
        raise HTTPException(404, "Richiesta inesistente o scaduta")
    return p.public()


@router.get("/notifications")
async def notifications(request: Request, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    return await request.app.state.store.list_notifications(limit)


@router.post("/notifications/read")
async def notifications_read(body: ReadIn, request: Request) -> dict:
    await request.app.state.store.mark_notifications_read(body.ids)
    return {"ok": True}


@router.post("/notifications/test")
async def notifications_test(request: Request) -> dict:
    return await request.app.state.notifier.push("info", "Notifica di prova", "Tutto funziona, signore.")


@router.post("/devices", status_code=201)
async def register_device(body: DeviceIn, request: Request) -> dict:
    await request.app.state.store.upsert_device(body.platform, body.token, body.label)
    return {"ok": True, "push": request.app.state.notifier.fcm.enabled}


@router.delete("/devices")
async def unregister_device(request: Request, token: str = Query(min_length=8, max_length=4096)) -> dict:
    await request.app.state.store.delete_device(token)
    return {"ok": True}


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Flusso SSE: ogni notifica arriva alle app aperte in tempo reale (heartbeat ogni 20 s per tenere viva la connessione)."""
    notifier = request.app.state.notifier
    q = notifier.subscribe()

    async def gen():
        try:
            yield "retry: 3000\n: connesso\n\n"
            while not await request.is_disconnected():
                try:
                    row = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"event: notification\ndata: {json.dumps(row)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            notifier.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/tts")
async def tts(body: SpeakIn, request: Request) -> Response:
    voice = request.app.state.voice
    if not voice.enabled:
        raise HTTPException(404, "La voce non è disponibile: il PC con JARVIS non è collegato")
    try:
        return Response(await voice.speak(body.text.strip()), media_type="audio/wav", headers={"Cache-Control": "no-store"})
    except TTSError as e:
        raise HTTPException(503, str(e)) from e
