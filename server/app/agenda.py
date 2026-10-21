"""Agenda ed email in forma di testo: servono ai comandi del bot e ai riepiloghi, senza passare dal modello (zero token)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .tools.google_tools import CAL, GMAIL


async def fetch_events(google, start: datetime, end: datetime, limit: int = 25) -> list[dict]:
    r = await google.request("GET", f"{CAL}/events", params={"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                                                              "singleEvents": "true", "orderBy": "startTime", "maxResults": limit})
    return [e for e in r.json().get("items", []) if e.get("status") != "cancelled"]


def event_line(e: dict, tz: ZoneInfo) -> str:
    t = (e.get("start") or {}).get("dateTime")
    when = f"{datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(tz):%H:%M}" if t else "tutto il giorno"
    place = f" 📍 {e['location'].split(',')[0][:30]}" if e.get("location") else ""
    return f"{when} — {e.get('summary', '(senza titolo)')}{place}"


async def agenda_text(google, tz: ZoneInfo, days: int = 2, now: datetime | None = None) -> str:
    """Eventi di oggi (da adesso) e dei giorni seguenti, raggruppati per giorno."""
    now = (now or datetime.now(tz)).astimezone(tz)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    events = await fetch_events(google, now - timedelta(minutes=1), midnight + timedelta(days=days))
    by_day: dict[str, list[str]] = {}
    for e in events:
        t = (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date")
        day = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(tz).date() if "T" in t else datetime.fromisoformat(t).date()
        by_day.setdefault(day.isoformat(), []).append(event_line(e, tz))
    if not by_day:
        return "Nessun impegno in agenda, signore."
    names = {midnight.date().isoformat(): "Oggi", (midnight + timedelta(days=1)).date().isoformat(): "Domani"}
    label = lambda d: names.get(d) or f"{datetime.fromisoformat(d):%d/%m}"  # noqa: E731
    return "\n\n".join(f"<b>{label(d)}</b>\n" + "\n".join(f"• {line}" for line in lines) for d, lines in sorted(by_day.items()))


async def unread_digest(google, limit: int = 8) -> list[str]:
    """Email non lette nella posta principale (ultimi 2 giorni): 'Mittente: Oggetto'."""
    r = await google.request("GET", f"{GMAIL}/messages", params={"q": "is:unread category:primary newer_than:2d", "maxResults": limit})
    rows = []
    for m in r.json().get("messages", []):
        d = (await google.request("GET", f"{GMAIL}/messages/{m['id']}", params={"format": "metadata", "metadataHeaders": ["From", "Subject"]})).json()
        h = {x["name"]: x["value"] for x in d.get("payload", {}).get("headers", [])}
        rows.append(f"{h.get('From', '?').split('<')[0].strip().strip(chr(34))[:28]}: {h.get('Subject', '(senza oggetto)')[:60]}")
    return rows
