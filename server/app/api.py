"""API per le app (Windows e Android): stato, token, cronologia, promemoria e conferme."""
import asyncio
import json
import time
from datetime import datetime, timedelta
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
VERSION = "0.4.0"


class ReminderIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    when: str  # data/ora locale ISO 8601


class DeviceIn(BaseModel):
    platform: str = Field(pattern=r"^(android|windows|web)$")
    token: str = Field(min_length=8, max_length=4096)
    label: str = Field(default="", max_length=80)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class NoteIn(BaseModel):
    text: str = Field(min_length=3, max_length=100_000)
    title: str = Field(default="", max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=12)
    important: bool = False


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=12)


class PinIn(BaseModel):
    pinned: bool = True


def _doc(d) -> dict:
    return {"id": d.id, "source": d.source, "title": d.title, "summary": d.summary, "tags": d.tags, "importance": d.importance,
            "pinned": d.pinned, "created_at": d.created_at, "updated_at": d.updated_at, "entities": [{"kind": k, "name": n} for k, n in d.entities]}


class ReadIn(BaseModel):
    ids: list[int] | None = None  # None = tutte


def forecast(b: dict) -> dict:
    """Quando finiscono i token al ritmo di consumo di questo mese (stima dal consumo medio giornaliero)."""
    now = datetime.now(ZoneInfo("UTC"))
    elapsed = max(1.0, now.day - 1 + now.hour / 24)
    used, remaining = b.get("used_tokens") or 0, b.get("remaining_tokens")
    burn = used / elapsed
    out = {"burn_per_day": int(burn), "days_left": None, "depletes_on": None, "runs_out_before_reset": False}
    if remaining is not None and burn > 0:
        days = remaining / burn
        out["days_left"] = round(days, 1)
        end = now + timedelta(days=days)
        out["depletes_on"] = end.strftime("%Y-%m-%d")
        try:
            reset = datetime.fromisoformat(str(b.get("resets_at", "")).replace("Z", "+00:00"))
            out["runs_out_before_reset"] = end < reset
        except ValueError:
            pass
    return out


@router.get("/tokens")
async def tokens(request: Request, refresh: bool = False) -> dict:
    budget = request.app.state.budget
    if not budget.enabled:
        raise HTTPException(404, "FreeLLMAPI non è in questo container")
    try:
        b = await budget.get(force=refresh)
    except AdminError as e:
        raise HTTPException(503, str(e)) from e
    return {**b, "forecast": forecast(b), "jarvis_today": request.app.state.usage.today()}


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
        "brain": st.brain.enabled,
        "pending_actions": len(st.pending.list_pending()),
        "calendar_sync": {**st.reminders.status, "linked": st.reminders.linked},
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
    r = await request.app.state.reminders.create(body.text, due)
    return {"ok": True, "id": r["id"], "calendar": r["calendar"], "calendar_error": r.get("error", "")}


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int, request: Request) -> dict:
    await request.app.state.reminders.delete(reminder_id)
    return {"ok": True}


@router.post("/reminders/sync")
async def reminders_sync(request: Request) -> dict:
    """Allinea ora i promemoria con il Calendario (di solito lo fa da solo ogni 5 minuti). Non risponde mai con un errore del server: l'esito e la causa stanno in `status`."""
    svc = request.app.state.reminders
    try:
        counts = await svc.sync()
    except Exception:
        counts = {}
    return {"counts": counts, "status": svc.status, "linked": svc.linked}


@router.get("/reminders/sync")
async def reminders_sync_status(request: Request) -> dict:
    svc = request.app.state.reminders
    return {"status": svc.status, "linked": svc.linked}


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
    await request.app.state.notifier.mark_read(body.ids)
    return {"ok": True}


@router.delete("/notifications")
async def notifications_clear(request: Request, read_only: bool = True) -> dict:
    await request.app.state.store.clear_notifications(read_only)
    return {"ok": True}


class SnoozeIn(BaseModel):
    minutes: int = Field(default=10, ge=0, le=1440)  # 0 = fatto, nessun nuovo promemoria


@router.post("/notifications/{notification_id}/snooze")
async def notification_snooze(notification_id: int, body: SnoozeIn, request: Request) -> dict:
    """Dal promemoria scattato: rimanda di N minuti (crea un nuovo promemoria con lo stesso testo)."""
    st = request.app.state
    n = await st.store.get_notification(notification_id)
    if not n or n["kind"] != "reminder":
        raise HTTPException(404, "Notifica inesistente")
    if body.minutes:
        due = datetime.now(ZoneInfo(st.settings.timezone)) + timedelta(minutes=body.minutes)
        await st.reminders.create(n["body"], due)
    await st.notifier.mark_read([notification_id])
    return {"ok": True}


@router.get("/notify/prefs")
async def notify_prefs(request: Request) -> dict:
    return await request.app.state.notifier.prefs()


@router.post("/notify/prefs")
async def notify_prefs_set(request: Request) -> dict:
    return await request.app.state.notifier.set_prefs(await request.json())


@router.get("/models")
async def models(request: Request) -> list[dict]:
    try:
        return [{"id": "auto", "owned_by": "router"}, *await request.app.state.agent.llm.models()]
    except Exception as e:
        raise HTTPException(503, "Elenco dei modelli non disponibile: FreeLLMAPI si sta avviando") from e


@router.get("/usage")
async def usage(request: Request, days: int = Query(14, ge=1, le=90)) -> dict:
    st = request.app.state
    await st.usage.flush(st.store)
    rows = await st.store.usage_series(days)
    by_day: dict[str, dict] = {}
    for r in rows:
        d = by_day.setdefault(str(r["day"]), {"day": str(r["day"]), "requests": 0, "errors": 0, "tokens": 0, "latency_ms": 0})
        d["requests"] += r["requests"]
        d["errors"] += r["errors"]
        d["tokens"] += r["prompt_tokens"] + r["completion_tokens"]
        d["latency_ms"] += r["latency_ms"]
    series = sorted(by_day.values(), key=lambda d: d["day"])
    for d in series:
        d["avg_latency_ms"] = int(d["latency_ms"] / max(1, d["requests"] - d["errors"]))
    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + r["prompt_tokens"] + r["completion_tokens"]
    return {"series": series, "by_kind": by_kind, "today": st.usage.today()}


@router.get("/health")
async def health(request: Request) -> dict:
    from .health import deep_health

    return await deep_health(request.app)


@router.get("/app/update")
async def app_update(request: Request, platform: str = Query(pattern="^(android|windows)$"), version: str = Query("0.0.0", max_length=20)) -> dict:
    return await request.app.state.updates.check_for(platform, version)


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


@router.post("/finetune/export")
async def finetune_export(request: Request, days: int = Query(180, ge=1, le=730)) -> dict:
    """Prepara il dataset LoRA (conversazioni ripulite dai dati sensibili) e lo salva cifrato su Hugging Face."""
    from .finetune import export_dataset

    st = request.app.state
    try:
        return await export_dataset(st.settings, st.store, st.backup, days)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


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
                    yield f"event: {row.get('event', 'notification')}\ndata: {json.dumps(row)}\n\n"
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


# ---------------------------------------------------------------- secondo cervello
def _brain(request: Request):
    b = request.app.state.brain
    if not b.enabled:
        raise HTTPException(404, "Il secondo cervello è disattivato")
    return b


@router.get("/brain/search")
async def brain_search(request: Request, q: str = Query(min_length=2, max_length=500), k: int = Query(8, ge=1, le=20), source: str = "") -> list[dict]:
    res = await _brain(request).search(q, k=k, source=source or None)
    return [{k2: v for k2, v in r.items() if k2 != "uri"} | {"snippet": r["text"][:600]} for r in res]


@router.get("/brain/docs")
async def brain_docs(request: Request, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), source: str = "") -> list[dict]:
    return [_doc(d) for d in await _brain(request).store.list_docs(limit, offset, source or None)]


@router.get("/brain/docs/{doc_id}")
async def brain_doc(doc_id: int, request: Request) -> dict:
    r = await _brain(request).read(doc_id, 20_000)
    if not r:
        raise HTTPException(404, "Documento inesistente")
    return {**_doc(r["doc"]), "text": r["text"], "truncated": r["truncated"], "related": await _brain(request).related(doc_id, 4)}


@router.post("/brain/notes", status_code=201)
async def brain_note(body: NoteIn, request: Request) -> dict:
    out = await _brain(request).ingest(body.text, title=body.title, source="note", tags=body.tags, importance=0.85 if body.important else 0.55)
    request.app.state.notifier.sync("brain")
    return out


@router.post("/brain/url", status_code=201)
async def brain_url(body: UrlIn, request: Request) -> dict:
    from .tools.web import fetch_page_data

    data = await fetch_page_data(body.url, request.app.state.gateway_client)
    if isinstance(data, str):
        raise HTTPException(422, data)
    title, text, final = data
    out = await _brain(request).ingest(text, title=title or final, source="web", uri=final, tags=body.tags)
    request.app.state.notifier.sync("brain")
    return out


@router.post("/brain/docs/{doc_id}/pin")
async def brain_pin(doc_id: int, body: PinIn, request: Request) -> dict:
    b = _brain(request)
    if not await b.store.get_doc(doc_id):
        raise HTTPException(404, "Documento inesistente")
    await b.store.update_doc(doc_id, pinned=body.pinned)
    request.app.state.notifier.sync("brain")
    return {"ok": True}


@router.delete("/brain/docs/{doc_id}")
async def brain_forget(doc_id: int, request: Request) -> dict:
    if not await _brain(request).forget(doc_id):
        raise HTTPException(404, "Documento inesistente")
    request.app.state.notifier.sync("brain")
    return {"ok": True}


@router.get("/brain/stats")
async def brain_stats(request: Request) -> dict:
    return await _brain(request).stats()


@router.get("/brain/profile")
async def brain_profile(request: Request) -> dict:
    """Il profilo che JARVIS ha compilato su di te dai ricordi (trasparenza: puoi leggerlo e correggere i ricordi alla fonte)."""
    return {"profile": await _brain(request).profile_text()}


@router.post("/brain/profile/refresh")
async def brain_profile_refresh(request: Request) -> dict:
    b = _brain(request)
    status = await b.refresh_profile(force=True)
    return {"status": status, "profile": await b.profile_text()}


@router.get("/skills")
async def skills_list(request: Request, domain: str = "") -> dict:
    """Le competenze di JARVIS (integrate e personali), raggruppate per ambito."""
    from .skills.registry import DOMAINS

    sk = request.app.state.skills
    return {"domains": DOMAINS, "skills": [s.card() for s in sk.by_domain(domain)]}


@router.get("/skills/{name}")
async def skills_get(name: str, request: Request) -> dict:
    s = request.app.state.skills.get(name)
    if not s:
        raise HTTPException(404, "Competenza inesistente")
    return {**s.card(), "triggers": s.triggers, "body": s.body}
