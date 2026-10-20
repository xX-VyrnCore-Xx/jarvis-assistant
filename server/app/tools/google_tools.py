import base64
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from ..config import Settings
from ..google import GoogleClient
from ..pending import PendingStore
from . import UNTRUSTED, ToolRegistry

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CAL = "https://www.googleapis.com/calendar/v3/calendars/primary"
DRIVE = "https://www.googleapis.com/drive/v3"
MAX_TEXT = 6000


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _body_text(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _body_text(part)
        if text:
            return text
    return ""


def register_google_tools(reg: ToolRegistry, settings: Settings, g: GoogleClient, pending: PendingStore) -> None:
    tz = ZoneInfo(settings.timezone)

    async def gmail_search(query: str, max_results: int = 5) -> str:
        r = await g.request("GET", f"{GMAIL}/messages", params={"q": query, "maxResults": min(max_results, 10)})
        out = []
        for m in r.json().get("messages", []):
            d = (
                await g.request(
                    "GET",
                    f"{GMAIL}/messages/{m['id']}",
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                )
            ).json()
            out.append(
                f"[{m['id']}] {_header(d, 'Date')} | {_header(d, 'From')} | {_header(d, 'Subject')}\n  {d.get('snippet', '')}"
            )
        return UNTRUSTED + "\n".join(out) if out else "Nessuna email trovata."

    async def gmail_read(message_id: str) -> str:
        d = (await g.request("GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"})).json()
        head = f"Da: {_header(d, 'From')}\nA: {_header(d, 'To')}\nOggetto: {_header(d, 'Subject')}\nData: {_header(d, 'Date')}"
        return f"{UNTRUSTED}{head}\n\n{_body_text(d['payload'])[:MAX_TEXT] or d.get('snippet', '')}"

    async def gmail_create_draft(to: str, subject: str, body: str) -> str:
        m = EmailMessage()
        m["To"], m["Subject"] = to, subject
        m.set_content(body)
        raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
        r = await g.request("POST", f"{GMAIL}/drafts", json={"message": {"raw": raw}})
        return f"Bozza creata (id {r.json()['id']}) per {to}. Non è stata inviata."

    async def gmail_send_draft(draft_id: str) -> str:
        # Mai inviata dal modello: crea una richiesta che solo l'utente può approvare (app o Telegram).
        try:
            d = (await g.request("GET", f"{GMAIL}/drafts/{draft_id}", params={"format": "metadata"})).json()
            msg = d.get("message", {})
            who = f"A: {_header(msg, 'To')}, oggetto: {_header(msg, 'Subject')}"
        except Exception:
            who = f"bozza {draft_id}"

        async def send() -> str:
            await g.request("POST", f"{GMAIL}/drafts/send", json={"id": draft_id})
            return "Email inviata."

        p = pending.create("gmail_send", f"Inviare l'email ({who})", send)
        return (f"Invio in attesa di conferma dell'utente (richiesta {p.id}): NON è stata inviata. "
                "L'utente deve approvarla dall'app o da Telegram.")

    async def calendar_list_events(days: int = 7) -> str:
        now = datetime.now(tz)
        r = await g.request(
            "GET",
            f"{CAL}/events",
            params={
                "timeMin": now.isoformat(),
                "timeMax": (now + timedelta(days=min(days, 60))).isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 25,
            },
        )
        rows = []
        for e in r.json().get("items", []):
            start = e["start"].get("dateTime") or e["start"].get("date")
            rows.append(f"[{e['id']}] {start} — {e.get('summary', '(senza titolo)')}")
        return "\n".join(rows) or "Nessun evento nel periodo."

    async def calendar_create_event(summary: str, start: str, duration_minutes: int = 60, description: str = "") -> str:
        s = datetime.fromisoformat(start)
        s = s.replace(tzinfo=tz) if s.tzinfo is None else s
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": s.isoformat(), "timeZone": settings.timezone},
            "end": {"dateTime": (s + timedelta(minutes=duration_minutes)).isoformat(), "timeZone": settings.timezone},
        }
        r = await g.request("POST", f"{CAL}/events", json=body)
        return f"Evento creato: {summary} il {s:%d/%m/%Y %H:%M} ({r.json()['id']})."

    async def drive_search(query: str) -> str:
        safe = query.replace("\\", "\\\\").replace("'", "\\'")
        r = await g.request(
            "GET",
            f"{DRIVE}/files",
            params={
                "q": f"fullText contains '{safe}' and trashed = false",
                "pageSize": 10,
                "fields": "files(id,name,mimeType,modifiedTime)",
            },
        )
        rows = [f"[{f['id']}] {f['name']} ({f['mimeType']}, {f['modifiedTime'][:10]})" for f in r.json()["files"]]
        return UNTRUSTED + "\n".join(rows) if rows else "Nessun file trovato."

    async def drive_read(file_id: str) -> str:
        meta = (await g.request("GET", f"{DRIVE}/files/{file_id}", params={"fields": "name,mimeType"})).json()
        if meta["mimeType"].startswith("application/vnd.google-apps."):
            r = await g.request("GET", f"{DRIVE}/files/{file_id}/export", params={"mimeType": "text/plain"})
        elif meta["mimeType"].startswith("text/"):
            r = await g.request("GET", f"{DRIVE}/files/{file_id}", params={"alt": "media"})
        else:
            return f"Formato non leggibile come testo: {meta['mimeType']}."
        return f"{UNTRUSTED}{meta['name']}\n\n{r.text[:MAX_TEXT]}"

    obj = lambda props, req: {"type": "object", "properties": props, "required": req}  # noqa: E731
    s_ = {"type": "string"}
    i_ = {"type": "integer"}
    reg.register("gmail_search", "Cerca email (sintassi Gmail, es. 'is:unread from:mario').", obj({"query": s_, "max_results": i_}, ["query"]), gmail_search)
    reg.register("gmail_read", "Legge il contenuto di una email dato il suo id.", obj({"message_id": s_}, ["message_id"]), gmail_read)
    reg.register("gmail_create_draft", "Crea una bozza email (NON la invia).", obj({"to": s_, "subject": s_, "body": s_}, ["to", "subject", "body"]), gmail_create_draft)
    reg.register("gmail_send_draft", "Chiede all'utente di approvare l'invio di una bozza (non la invia da sola: serve la sua conferma nell'app o su Telegram).", obj({"draft_id": s_}, ["draft_id"]), gmail_send_draft)
    reg.register("calendar_list_events", "Elenca i prossimi eventi del calendario.", obj({"days": i_}, []), calendar_list_events)
    reg.register(
        "calendar_create_event",
        "Crea un evento. 'start' è data/ora locale ISO 8601; calcolala da get_datetime.",
        obj({"summary": s_, "start": s_, "duration_minutes": i_, "description": s_}, ["summary", "start"]),
        calendar_create_event,
    )
    reg.register("drive_search", "Cerca file su Google Drive per contenuto o nome.", obj({"query": s_}, ["query"]), drive_search)
    reg.register("drive_read", "Legge il testo di un file di Drive (Docs, Sheets, testo).", obj({"file_id": s_}, ["file_id"]), drive_read)
