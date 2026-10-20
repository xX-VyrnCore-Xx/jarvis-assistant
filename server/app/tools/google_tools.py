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


def register_google_tools(reg: ToolRegistry, settings: Settings, g: GoogleClient, pending: PendingStore, brain=None) -> None:
    tz = ZoneInfo(settings.timezone)

    def R(name, description, parameters, fn, ttl=0):
        # i tool compaiono solo quando Google è davvero collegato (anche dopo il collegamento guidato, senza riavvio)
        reg.register(name, description, parameters, fn, available=lambda: g.enabled, cache_ttl=ttl)

    def wrote(fn):
        """Dopo una scrittura sul calendario le letture in cache non valgono più."""
        async def inner(**kw):
            try:
                return await fn(**kw)
            finally:
                reg.invalidate("calendar_")
        return inner

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

    def _when(e: dict) -> str:
        st, en = e["start"], e.get("end", {})
        if st.get("date"):  # giornata intera
            return f"{st['date']} (tutto il giorno)"
        end = (en.get("dateTime") or "")[11:16]
        return f"{st['dateTime'][:16].replace('T', ' ')}" + (f"–{end}" if end else "")

    def _line(e: dict) -> str:
        extra = (f" @ {e['location']}" if e.get("location") else "") + (f" · {len(e['attendees'])} invitati" if e.get("attendees") else "")
        return f"[{e['id']}] {_when(e)} — {e.get('summary', '(senza titolo)')}{extra}"

    def _local(value: str) -> datetime:
        d = datetime.fromisoformat(value)
        return d.replace(tzinfo=tz) if d.tzinfo is None else d.astimezone(tz)

    async def calendar_list_events(days: int = 7, query: str = "", from_date: str = "") -> str:
        start = _local(from_date) if from_date else datetime.now(tz)
        params = {"timeMin": start.isoformat(), "timeMax": (start + timedelta(days=max(1, min(days, 90)))).isoformat(),
                  "singleEvents": "true", "orderBy": "startTime", "maxResults": 40}
        if query:
            params["q"] = query
        r = await g.request("GET", f"{CAL}/events", params=params)
        rows = [_line(e) for e in r.json().get("items", [])]
        return UNTRUSTED + "\n".join(rows) if rows else "Nessun evento nel periodo."

    async def calendar_create_event(summary: str, start: str, duration_minutes: int = 60, description: str = "",
                                    location: str = "", all_day: bool = False, attendees: str = "") -> str:
        s0 = _local(start)
        body: dict = {"summary": summary, "description": description, "location": location}
        if all_day:
            body["start"] = {"date": f"{s0:%Y-%m-%d}"}
            body["end"] = {"date": f"{s0 + timedelta(days=max(1, duration_minutes // 1440 or 1)):%Y-%m-%d}"}
        else:
            body["start"] = {"dateTime": s0.isoformat(), "timeZone": settings.timezone}
            body["end"] = {"dateTime": (s0 + timedelta(minutes=duration_minutes)).isoformat(), "timeZone": settings.timezone}
        mails = [m.strip() for m in attendees.split(",") if "@" in m]
        if mails:
            body["attendees"] = [{"email": m} for m in mails]
        # sendUpdates=none: nessun invito parte da solo
        r = await g.request("POST", f"{CAL}/events", params={"sendUpdates": "none"}, json=body)
        return f"Evento creato: {summary} il {s0:%d/%m/%Y %H:%M} ({r.json()['id']})." + (" Inviti non spediti." if mails else "")

    async def calendar_update_event(event_id: str, summary: str = "", start: str = "", duration_minutes: int = 0,
                                    description: str = "", location: str = "") -> str:
        patch: dict = {}
        if summary:
            patch["summary"] = summary
        if description:
            patch["description"] = description
        if location:
            patch["location"] = location
        if start:
            s0 = _local(start)
            minutes = duration_minutes
            if not minutes:  # mantiene la durata che l'evento aveva
                cur = (await g.request("GET", f"{CAL}/events/{event_id}")).json()
                try:
                    minutes = int((datetime.fromisoformat(cur["end"]["dateTime"]) - datetime.fromisoformat(cur["start"]["dateTime"])).total_seconds() // 60)
                except (KeyError, ValueError):
                    minutes = 60
            patch["start"] = {"dateTime": s0.isoformat(), "timeZone": settings.timezone}
            patch["end"] = {"dateTime": (s0 + timedelta(minutes=minutes)).isoformat(), "timeZone": settings.timezone}
        elif duration_minutes:
            cur = (await g.request("GET", f"{CAL}/events/{event_id}")).json()
            s0 = datetime.fromisoformat(cur["start"]["dateTime"])
            patch["end"] = {"dateTime": (s0 + timedelta(minutes=duration_minutes)).isoformat(), "timeZone": settings.timezone}
        if not patch:
            return "Errore: indica almeno un campo da modificare."
        r = await g.request("PATCH", f"{CAL}/events/{event_id}", params={"sendUpdates": "none"}, json=patch)
        return "Evento aggiornato: " + _line(r.json())

    async def calendar_delete_event(event_id: str) -> str:
        # Cancellare è distruttivo: come per l'invio di email, lo decide l'utente (app o Telegram), non il modello.
        try:
            e = (await g.request("GET", f"{CAL}/events/{event_id}")).json()
            label = f"{e.get('summary', '(senza titolo)')} — {_when(e)}"
        except Exception:
            return "Errore: evento non trovato."

        async def delete() -> str:
            await g.request("DELETE", f"{CAL}/events/{event_id}", params={"sendUpdates": "none"})
            reg.invalidate("calendar_")
            return "Evento eliminato."

        p = pending.create("calendar_delete", f"Eliminare l'evento «{label}»", delete)
        return (f"Eliminazione in attesa di conferma dell'utente (richiesta {p.id}): l'evento NON è stato eliminato. "
                "L'utente deve approvarla dall'app o da Telegram.")

    async def calendar_find_free_time(date: str, duration_minutes: int = 60, day_start: int = 9, day_end: int = 19) -> str:
        day = _local(date).replace(hour=0, minute=0, second=0, microsecond=0)
        lo, hi = day.replace(hour=day_start), day.replace(hour=day_end)
        r = await g.request("POST", "https://www.googleapis.com/calendar/v3/freeBusy",
                            json={"timeMin": lo.isoformat(), "timeMax": hi.isoformat(), "timeZone": settings.timezone, "items": [{"id": "primary"}]})
        busy = sorted((datetime.fromisoformat(b["start"]).astimezone(tz), datetime.fromisoformat(b["end"]).astimezone(tz))
                      for b in r.json()["calendars"]["primary"]["busy"])
        free, cursor = [], lo
        for b0, b1 in busy + [(hi, hi)]:
            if b0 - cursor >= timedelta(minutes=duration_minutes):
                free.append(f"{cursor:%H:%M}–{b0:%H:%M}")
            cursor = max(cursor, b1)
        return f"Fasce libere il {day:%d/%m/%Y} (almeno {duration_minutes} min): " + (", ".join(free) or "nessuna.")

    async def gmail_reply_draft(message_id: str, body: str) -> str:
        d = (await g.request("GET", f"{GMAIL}/messages/{message_id}", params={"format": "metadata", "metadataHeaders": ["From", "Reply-To", "Subject", "Message-ID", "References"]})).json()
        m = EmailMessage()
        m["To"] = _header(d, "Reply-To") or _header(d, "From")
        subj = _header(d, "Subject")
        m["Subject"] = subj if subj.lower().startswith("re:") else f"Re: {subj}"
        if mid := _header(d, "Message-ID"):
            m["In-Reply-To"], m["References"] = mid, f"{_header(d, 'References')} {mid}".strip()
        m.set_content(body)
        raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
        r = await g.request("POST", f"{GMAIL}/drafts", json={"message": {"raw": raw, "threadId": d.get("threadId")}})
        return f"Bozza di risposta creata (id {r.json()['id']}) per {m['To']}. Non è stata inviata."

    async def drive_recent(count: int = 10) -> str:
        r = await g.request("GET", f"{DRIVE}/files", params={"orderBy": "modifiedTime desc", "pageSize": min(count, 25),
                                                              "q": "trashed = false", "fields": "files(id,name,mimeType,modifiedTime)"})
        rows = [f"[{f['id']}] {f['name']} ({f['mimeType'].split('.')[-1]}, {f['modifiedTime'][:10]})" for f in r.json()["files"]]
        return UNTRUSTED + "\n".join(rows) if rows else "Nessun file."

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

    async def drive_save_to_brain(file_id: str) -> str:
        meta = (await g.request("GET", f"{DRIVE}/files/{file_id}", params={"fields": "name,mimeType"})).json()
        if meta["mimeType"].startswith("application/vnd.google-apps."):
            r = await g.request("GET", f"{DRIVE}/files/{file_id}/export", params={"mimeType": "text/plain"})
        elif meta["mimeType"].startswith("text/"):
            r = await g.request("GET", f"{DRIVE}/files/{file_id}", params={"alt": "media"})
        else:
            return f"Errore: formato non leggibile come testo ({meta['mimeType']})."
        res = await brain.ingest(r.text, title=meta["name"], source="drive", uri=f"drive:{file_id}", importance=0.5)
        return f"Salvato nel secondo cervello (#{res['doc_id']}: {meta['name']}, {res['chunks']} frammenti, {res['status']})."

    async def gmail_save_to_brain(message_id: str) -> str:
        d = (await g.request("GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"})).json()
        subject = _header(d, "Subject") or "(senza oggetto)"
        text = f"Da: {_header(d, 'From')}\nData: {_header(d, 'Date')}\nOggetto: {subject}\n\n{_body_text(d['payload']) or d.get('snippet', '')}"
        res = await brain.ingest(text, title=f"Email: {subject}", source="gmail", uri=f"gmail:{message_id}", importance=0.5)
        return f"Email salvata nel secondo cervello (#{res['doc_id']}, {res['status']})."

    obj = lambda props, req: {"type": "object", "properties": props, "required": req}  # noqa: E731
    s_ = {"type": "string"}
    i_ = {"type": "integer"}
    R("gmail_search", "Cerca email (sintassi Gmail, es. 'is:unread from:mario').", obj({"query": s_, "max_results": i_}, ["query"]), gmail_search, ttl=60)
    R("gmail_read", "Legge il contenuto di una email dato il suo id.", obj({"message_id": s_}, ["message_id"]), gmail_read, ttl=600)
    R("gmail_create_draft", "Crea una bozza email (NON la invia).", obj({"to": s_, "subject": s_, "body": s_}, ["to", "subject", "body"]), gmail_create_draft)
    R("gmail_send_draft", "Chiede all'utente di approvare l'invio di una bozza (non la invia da sola: serve la sua conferma nell'app o su Telegram).", obj({"draft_id": s_}, ["draft_id"]), gmail_send_draft)
    b_ = {"type": "boolean"}
    R("gmail_reply_draft", "Crea la bozza di risposta a una email (nello stesso thread). NON la invia.", obj({"message_id": s_, "body": s_}, ["message_id", "body"]), gmail_reply_draft)
    R("calendar_list_events", "Elenca gli eventi del calendario (con id). 'days' = quanti giorni (default 7), 'from_date' = data di partenza ISO (anche nel passato), 'query' = testo da cercare.",
      obj({"days": i_, "query": s_, "from_date": s_}, []), calendar_list_events, ttl=60)
    R("calendar_create_event", "Crea un evento. 'start' è data/ora locale ISO 8601 (calcolala da get_datetime); 'attendees' = email separate da virgola (gli inviti NON partono).",
      obj({"summary": s_, "start": s_, "duration_minutes": i_, "description": s_, "location": s_, "all_day": b_, "attendees": s_}, ["summary", "start"]), wrote(calendar_create_event))
    R("calendar_update_event", "Modifica un evento esistente (id da calendar_list_events): titolo, orario di inizio (mantiene la durata se non indicata), durata, descrizione, luogo.",
      obj({"event_id": s_, "summary": s_, "start": s_, "duration_minutes": i_, "description": s_, "location": s_}, ["event_id"]), wrote(calendar_update_event))
    R("calendar_delete_event", "Elimina un evento (id da calendar_list_events). Serve la conferma dell'utente nell'app o su Telegram: dopo la chiamata di' che l'attende.",
      obj({"event_id": s_}, ["event_id"]), wrote(calendar_delete_event))
    R("calendar_find_free_time", "Trova le fasce libere di un giorno (data ISO) di almeno N minuti, tra 'day_start' e 'day_end' (ore, default 9-19).",
      obj({"date": s_, "duration_minutes": i_, "day_start": i_, "day_end": i_}, ["date"]), calendar_find_free_time, ttl=60)
    R("drive_recent", "Elenca i file di Drive modificati più di recente.", obj({"count": i_}, []), drive_recent, ttl=120)
    R("drive_search", "Cerca file su Google Drive per contenuto o nome.", obj({"query": s_}, ["query"]), drive_search, ttl=300)
    R("drive_read", "Legge il testo di un file di Drive (Docs, Sheets, testo).", obj({"file_id": s_}, ["file_id"]), drive_read, ttl=300)
    if brain is not None:
        R("drive_save_to_brain", "Salva nel secondo cervello il testo di un file di Drive (id da drive_search), per ritrovarlo per significato.", obj({"file_id": s_}, ["file_id"]), drive_save_to_brain)
        R("gmail_save_to_brain", "Salva nel secondo cervello una email (id da gmail_search), per ritrovarla per significato.", obj({"message_id": s_}, ["message_id"]), gmail_save_to_brain)
