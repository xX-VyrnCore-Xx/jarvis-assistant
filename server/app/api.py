"""API per le app (Windows e Android): stato, token, cronologia, promemoria e conferme."""
import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from .auth import require_token
from .freellm_admin import AdminError
from .coding import CodingError
from .llm import LLMError
from .voice import TTSError
from .tools.basic import parse_due

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
STARTED = time.time()
VERSION = "0.4.0"


class ReminderIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    when: str  # data/ora locale ISO 8601
    repeat: str = Field("", max_length=20)  # daily, weekdays, weekly, monthly, yearly (vuoto: una volta)


class TaskIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    list: str = Field("attività", min_length=1, max_length=40)


class TaskPatch(BaseModel):
    done: bool


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
        "security": {"encryption": bool(getattr(st, "vault", None) and st.vault.enabled), "weak_key": bool(getattr(st, "vault", None) and st.vault.strength(s.jarvis_api_token).get("weak")),
                     "key_is_token": bool(getattr(st, "vault", None) and st.vault.strength(s.jarvis_api_token).get("shared_with_token")), "redaction": s.privacy_mode},
        "tools_down": sorted(getattr(st, "toolwatch", None).tools.down) if getattr(st, "toolwatch", None) else [],
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
    try:
        r = await request.app.state.reminders.create(body.text, due, body.repeat)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"ok": True, "id": r["id"], "calendar": r["calendar"], "calendar_error": r.get("error", "")}


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int, request: Request) -> dict:
    await request.app.state.reminders.delete(reminder_id)
    return {"ok": True}


@router.get("/tasks")
async def tasks(request: Request, done: bool = False) -> list[dict]:
    return await request.app.state.store.list_tasks(None, done)


@router.post("/tasks", status_code=201)
async def add_task(body: TaskIn, request: Request) -> dict:
    tid = await request.app.state.store.add_task(body.text.strip(), body.list.strip().lower() or "attività")
    return {"ok": True, "id": tid}


@router.patch("/tasks/{task_id}")
async def patch_task(task_id: int, body: TaskPatch, request: Request) -> dict:
    await request.app.state.store.set_task_done(task_id, body.done)
    return {"ok": True}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, request: Request) -> dict:
    await request.app.state.store.delete_task(task_id)
    return {"ok": True}


class PhoneResultIn(BaseModel):
    id: str = Field(min_length=4, max_length=40)
    ok: bool
    data: dict | list | None = None
    error: str = Field("", max_length=200)


@router.post("/phone/result")
async def phone_result(body: PhoneResultIn, request: Request) -> dict:
    """L'app risponde a un ordine del server (es. ricerca in rubrica). Nessun dato resta sul server: va solo a chi lo aspettava."""
    return {"ok": request.app.state.phone.resolve(body.id, body.ok, body.data, body.error)}


class ContactsAccessIn(BaseModel):
    enabled: bool


@router.get("/contacts/access")
async def contacts_access(request: Request) -> dict:
    """Interruttore e registro degli accessi alla rubrica: chi ha cercato cosa e quando (solo in memoria, mai i numeri)."""
    b = request.app.state.phone
    return {"enabled": b.enabled, "log": list(b.log)[-20:]}


@router.post("/contacts/access")
async def set_contacts_access(body: ContactsAccessIn, request: Request) -> dict:
    request.app.state.phone.enabled = body.enabled
    await request.app.state.store.set_setting("contacts_access", "on" if body.enabled else "off")
    return {"ok": True, "enabled": body.enabled}


@router.post("/chat/new")
async def chat_new(request: Request, x_device_id: str = Header(default="", max_length=64)) -> dict:
    """Cancella la conversazione corrente (condivisa da app e Telegram) e ne fa partire una nuova. Ricordi, cervello e promemoria restano."""
    await request.app.state.store.clear_messages("main")
    request.app.state.notifier.sync("chat", x_device_id)
    return {"ok": True}


class CallsIn(BaseModel):
    mode: str = Field(max_length=10)  # off | allowed | all
    numbers: list[dict] = Field(default_factory=list, max_length=50)
    greeting: str = Field("", max_length=300)


@router.get("/calls/config")
async def calls_config(request: Request) -> dict:
    """Segreteria telefonica con voce (Twilio): impostazioni e indirizzi da dare a Twilio."""
    from .voiceline import public_url

    line = request.app.state.voiceline
    base = public_url(request.app.state.settings, request)
    return {"enabled": line.enabled, "voice_url": base + "/twilio/voice", "status_url": base + "/twilio/status", **await line.config()}


@router.post("/calls/config")
async def calls_config_set(body: CallsIn, request: Request) -> dict:
    try:
        return {"ok": True, **await request.app.state.voiceline.save(body.mode, body.numbers, body.greeting)}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/backup/run")
async def backup_run(request: Request) -> dict:
    """Esegue subito il backup su Hugging Face (di solito è notturno) e dice com'è andata, con il motivo se fallisce."""
    from .backup import BackupError

    st = request.app.state
    if not st.backup.enabled:
        raise HTTPException(409, "Backup non configurato: servono FREEAPI_DB_BACKUP_URL, FREEAPI_DB_BACKUP_TOKEN e Supabase.")
    lock = getattr(st, "backup_lock", None) or asyncio.Lock()
    st.backup_lock = lock
    if lock.locked():
        raise HTTPException(409, "Un backup è già in corso.")
    async with lock:
        tz = ZoneInfo(st.settings.timezone)
        try:
            detail, ok = await st.backup.run(force=True), True
        except Exception as e:
            ok, detail = False, (str(e)[:240] if isinstance(e, BackupError) else type(e).__name__)
        await st.store.set_setting("backup_status", json.dumps({"ok": ok, "at": datetime.now(tz).isoformat(), "detail": detail}))
    return {"ok": ok, "detail": detail}


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
        audio, mime = await voice.speak_any(body.text.strip())
        return Response(audio, media_type=mime, headers={"Cache-Control": "no-store"})
    except TTSError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/tools/health")
async def tools_health(request: Request) -> dict:
    """Stato degli strumenti esterni (meteo, notizie, cambi, Wikipedia…): ultima prova, esito e quali sono fuori servizio."""
    w = request.app.state.toolwatch
    return {"down": w.tools.down, "checks": w.status, "last_run": w.last_run, "tools": len(w.tools.names)}


@router.post("/tools/health")
async def tools_health_run(request: Request) -> dict:
    """Prova subito gli strumenti esterni."""
    w = request.app.state.toolwatch
    return {"ok": True, "results": await asyncio.wait_for(w.run(), 120), "down": w.tools.down}


# ---------------------------------------------------------------- privacy e sicurezza
@router.get("/privacy")
async def privacy(request: Request) -> dict:
    """Che cosa è protetto e che cosa esce dal server (e verso chi): la risposta alla domanda «quanto è privato JARVIS?»."""
    st = request.app.state
    s = st.settings
    vault = getattr(st, "vault", None)
    strength = vault.strength(s.jarvis_api_token) if vault else {"enabled": False}
    edge = st.voice.edge
    flows = [
        {"id": "llm", "label": "Modelli di linguaggio (provider gratuiti tramite FreeLLMAPI)", "data": "il testo delle richieste: email, IBAN, carte, telefoni e chiavi sono sostituiti da segnaposto prima dell'invio" if s.privacy_mode != "off" else "il testo delle richieste, SENZA mascheramento", "on": True, "masked": s.privacy_mode != "off"},
        {"id": "tts", "label": "Voce neurale (servizio Microsoft Edge)", "data": "il testo delle risposte lette ad alta voce, senza dati personali (email, IBAN, telefoni, link diventano parole generiche)", "on": bool(edge and edge.on), "toggle": True},
        {"id": "stt", "label": "Dettatura (Whisper del router)", "data": "l'audio registrato mentre detti; non viene conservato sul server", "on": True},
        {"id": "github", "label": "GitHub", "data": "il codice dei repository privati creati da JARVIS", "on": st.coding.enabled},
        {"id": "google", "label": "Google", "data": "agenda, email e Drive, solo se hai collegato l'account", "on": st.google.enabled},
        {"id": "supabase", "label": "Supabase", "data": "messaggi, ricordi e attività, cifrati AES-256-GCM prima di uscire dal server", "on": bool(s.supabase_url and s.supabase_service_key)},
        {"id": "backup", "label": "Hugging Face (dataset privato)", "data": "backup notturno cifrato AES-256-GCM", "on": st.backup.enabled},
        {"id": "telegram", "label": "Telegram", "data": "i messaggi che scambi con il bot", "on": st.tg.enabled},
    ]
    return {"encryption": strength, "redaction": s.privacy_mode, "flows": flows,
            "protections": ["Token di accesso confrontato in tempo costante, con blocco dopo i tentativi falliti", "Intestazioni di sicurezza (HSTS, no-store, CSP) su tutte le risposte",
                            "Nessun dato personale nei log; i corpi degli errori dei provider non vengono mai registrati", "Cache in memoria (mai su disco) con scadenza e tetto di dimensione; email, calendario, file e ricordi restano 45 secondi",
                            "La rubrica non lascia mai il telefono: al server arrivano solo nomi e codici, filtrati"]}


class PrivacyToggle(BaseModel):
    neural_voice: bool


@router.post("/privacy/neural-voice")
async def privacy_neural_voice(body: PrivacyToggle, request: Request) -> dict:
    """Voce neurale sì/no: spenta, il testo delle risposte non lascia mai il server (si usa la voce del dispositivo)."""
    e = request.app.state.voice.edge
    if e:
        e.on = body.neural_voice
        if not body.neural_voice:
            e.clear()
    await request.app.state.store.set_setting("tts_neural", "on" if body.neural_voice else "off")
    return {"ok": True, "neural_voice": body.neural_voice}


@router.post("/privacy/wipe")
async def privacy_wipe(request: Request, x_device_id: str = Header(default="", max_length=64)) -> dict:
    """«Cancella chat e cache»: conversazioni (normale e Codice), notifiche, risultati in cache e audio in memoria. Ricordi, cervello, promemoria e attività restano."""
    st = request.app.state
    await st.store.clear_messages("main")
    await st.store.clear_messages("code")
    await st.store.clear_notifications(False)
    cache = st.agent.tools.clear_cache()
    audio = st.voice.clear_caches()
    st.notifier.sync("chat", x_device_id)
    st.notifier.sync("code", x_device_id)
    return {"ok": True, "cache_entries": cache, "audio_clips": audio}


# ---------------------------------------------------------------- dettatura e correttore grammaticale
HALLUCINATION = re.compile(r"sottotitoli|amara\.org|grazie (a tutti )?per (la visione|aver guardato|l'attenzione)|iscriviti al canale|alla prossima|subtitles|thanks for watching|www\.", re.I)


class CorrectIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    level: str = Field("full", pattern="^(quick|full)$")


@router.post("/correct")
async def correct(body: CorrectIn, request: Request) -> dict:
    """Correttore grammaticale: `quick` (regole, istantaneo) o `full` (regole + modello, senza cambiare il senso)."""
    limiter = request.app.state.chat_limiter
    if wait := limiter.retry_after():
        raise HTTPException(429, "Troppe richieste: rallenta un momento", headers={"Retry-After": str(wait)})
    limiter.hit()
    out = await request.app.state.corrector.fix(body.text, body.level)
    return {"text": out, "changed": out != body.text.strip()}


@router.post("/stt")
async def stt(request: Request, fix: str = Query("quick", pattern="^(none|quick|full)$")) -> dict:
    """Dettatura di qualità: l'app registra la voce e la manda qui; la trascrizione è del modello Whisper del router (molto più precisa del riconoscimento del telefono),
    poi, se richiesto, passa dal correttore grammaticale. Corpo: l'audio (webm/ogg/mp4/wav), al massimo 4 MB."""
    st = request.app.state
    limiter = st.chat_limiter
    if wait := limiter.retry_after():
        raise HTTPException(429, "Troppe richieste: rallenta un momento", headers={"Retry-After": str(wait)})
    audio = await request.body()
    if len(audio) < 800:
        raise HTTPException(422, "Registrazione troppo breve")
    if len(audio) > 4_000_000:
        raise HTTPException(413, "Registrazione troppo lunga")
    mime = (request.headers.get("content-type") or "audio/webm").split(";")[0].strip().lower()
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/aac": "aac"}.get(mime)
    if not ext:
        raise HTTPException(415, "Formato audio non supportato")
    limiter.hit()
    try:
        raw = await st.agent.llm.transcribe(audio, f"voce.{ext}", mime)
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    if HALLUCINATION.search(raw) and len(raw) < 90:  # Whisper su silenzio o rumore «inventa» frasi di repertorio: meglio nulla
        return {"text": "", "raw": raw}
    text = raw if fix == "none" else await st.corrector.fix(raw, fix)
    return {"text": text, "raw": raw}


# ---------------------------------------------------------------- sezione Codice
def _code(request: Request):
    c = request.app.state.coding
    if not c.enabled:
        raise HTTPException(404, "Il coding non è attivo: manca GITHUB_TOKEN sul server")
    return c


class CodeResume(BaseModel):
    repo: str = Field(min_length=1, max_length=100)


class CodeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field("", max_length=300)
    readme: bool = True
    license: str = Field("mit", max_length=12)
    scaffold: str = Field("", max_length=30)  # python-cli, fastapi-api, node-express-api, static-site, telegram-bot (vuoto: nessuno)


@router.post("/code/create")
async def code_create(body: CodeCreate, request: Request) -> dict:
    """Crea un repository PRIVATO nuovo dalla sezione Codice (il tocco dell'utente sul pulsante è la conferma), con README, licenza e, se richiesto, uno scheletro con test e CI già committato."""
    from .coding import SCAFFOLDS

    c = _code(request)
    if body.scaffold and body.scaffold not in SCAFFOLDS:
        raise HTTPException(422, "Modello sconosciuto: " + ", ".join(SCAFFOLDS))
    try:
        msg = await c.create_repo(body.name.strip(), body.description.strip(), body.readme, body.license.strip().lower() or "nessuna")
        if body.scaffold:
            c.scaffold(body.scaffold, body.name.strip())
            msg += " " + await c.commit("Scheletro iniziale", direct=True)
    except CodingError as e:
        raise HTTPException(409, str(e)) from e
    request.app.state.notifier.sync("code")
    return {"ok": True, "message": msg, "session": c.snapshot()}


@router.get("/code/overview")
async def code_overview(request: Request) -> dict:
    """Tutto ciò che serve alla sezione Codice: stato del progetto, repository di JARVIS, competenze di programmazione e modello in uso."""
    st = request.app.state
    c = st.coding
    snap = c.snapshot() if c.enabled else {"active": False}
    try:
        repos = await c.repos() if c.enabled else []
    except Exception:
        repos = []
    sk = st.skills.coding_skills() if st.skills else []
    last = st.llm.router.last
    from .coding import LICENSES, SCAFFOLDS

    return {"enabled": c.enabled, "session": snap, "repos": repos, "templates": list(SCAFFOLDS), "licenses": [k for k in LICENSES if k], "skills": [s.card() for s in sk], "tools": len([n for n in st.agent.tools.names if n.startswith("code_")]),
            "model": {"profile": last.profile, "why": last.reason} if last else None, "jobs_active": st.codejobs.active}


@router.get("/code/history")
async def code_history(request: Request, limit: int = Query(40, ge=1, le=100)) -> list[dict]:
    return await request.app.state.store.recent_messages("code", limit)


@router.post("/code/new")
async def code_new(request: Request, x_device_id: str = Header(default="", max_length=64)) -> dict:
    """Cancella la conversazione di coding (il progetto aperto e il suo codice restano)."""
    await request.app.state.store.clear_messages("code")
    request.app.state.notifier.sync("code", x_device_id)
    return {"ok": True}


@router.get("/code/files")
async def code_files(request: Request) -> dict:
    c = _code(request)
    try:
        return {"files": c.file_list()}
    except CodingError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/code/file")
async def code_file(request: Request, path: str = Query(min_length=1, max_length=200), start: int = Query(1, ge=1), lines: int = Query(300, ge=1, le=800)) -> dict:
    c = _code(request)
    try:
        return {"path": path, "text": c.read(path, start, lines)}
    except CodingError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/code/diff")
async def code_diff(request: Request, path: str = Query("", max_length=200)) -> dict:
    c = _code(request)
    try:
        return {"diff": c.diff(path), "review": c.review()}
    except CodingError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/code/checks")
async def code_checks(request: Request) -> dict:
    c = _code(request)
    try:
        return await c.checks()
    except CodingError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/code/resume")
async def code_resume(body: CodeResume, request: Request) -> dict:
    c = _code(request)
    try:
        msg = await c.resume(body.repo)
    except CodingError as e:
        raise HTTPException(409, str(e)) from e
    request.app.state.notifier.sync("code")
    return {"ok": True, "message": msg, "session": c.snapshot()}


class VoiceIn(BaseModel):
    voice: str = Field(max_length=20)


@router.get("/voice")
async def voice_config(request: Request) -> dict:
    """Voce neurale del server: quale è in uso e quali sono disponibili."""
    from .edgetts import VOICES

    e = request.app.state.voice.edge
    return {"active": e.voice if e else "", "options": [{"id": k, "label": v[1]} for k, v in VOICES.items()], "available": bool(e and e.enabled),
            "pc": request.app.state.voice.pc_enabled, "error": e.last_error if e else "", "neural": bool(e and e.on)}


@router.post("/voice")
async def set_voice(body: VoiceIn, request: Request) -> dict:
    e = request.app.state.voice.edge
    if not e or not e.set_voice(body.voice):
        raise HTTPException(422, "Voce sconosciuta")
    await request.app.state.store.set_setting("tts_voice", body.voice)
    return {"ok": True, "active": body.voice}


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


# ---------------------------------------------------------------- lavori di coding in background
class JobIn(BaseModel):
    task: str = Field(min_length=4, max_length=6000)
    repo: str = Field("", max_length=100)
    model: str | None = Field(None, max_length=80)
    skill: str = Field("", max_length=60)
    notify: bool = True


def _jobs(request: Request):
    return request.app.state.codejobs


@router.get("/code/commands")
async def code_commands() -> list[dict]:
    """I comandi rapidi della sezione Codice (/review, /test, /fix…)."""
    from .codecmds import listing

    return listing()


@router.get("/code/jobs")
async def code_jobs(request: Request) -> dict:
    j = _jobs(request)
    return {"jobs": j.listing(), "active": j.active}


@router.post("/code/jobs", status_code=201)
async def code_job_start(body: JobIn, request: Request) -> dict:
    """Avvia un lavoro di coding in background: va avanti sul server anche con l'app chiusa e avvisa a fine lavoro."""
    try:
        return await _jobs(request).start(body.task, body.repo, body.model, body.skill, body.notify)
    except CodingError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/code/jobs/{job_id}")
async def code_job(job_id: str, request: Request) -> dict:
    j = _jobs(request).get(job_id)
    if not j:
        raise HTTPException(404, "Lavoro non trovato")
    return j


@router.post("/code/jobs/{job_id}/cancel")
async def code_job_cancel(job_id: str, request: Request) -> dict:
    if not await _jobs(request).cancel(job_id):
        raise HTTPException(409, "Il lavoro non è in coda né in corso")
    return {"ok": True}
