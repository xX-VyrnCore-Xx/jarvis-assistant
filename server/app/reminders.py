"""Promemoria collegati al Calendario Google: l'evento del Calendario è la fonte, il promemoria dell'app lo segue.
Creare, rimandare o eliminare un promemoria nell'app lo fa anche sul Calendario; spostare o cancellare l'evento sul Calendario
aggiorna o toglie il promemoria dell'app (sincronizzazione ogni 5 minuti); un evento «Promemoria: …» scritto a mano sul Calendario
diventa un promemoria dell'app. Senza Google collegato funziona tutto solo nell'app."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .config import Settings
from .tools.google_tools import CAL

log = logging.getLogger("jarvis.reminders")
PREFIX = "⏰ "
TAG = {"jarvis": "reminder"}


def _clean(summary: str) -> str:
    s = (summary or "").strip()
    for p in (PREFIX.strip(), "promemoria:", "promemoria -", "promemoria"):
        if s.lower().startswith(p.lower()):
            s = s[len(p):].lstrip(" :-–")
            break
    return s.strip() or "Promemoria"


def _is_reminder_title(summary: str) -> bool:
    s = (summary or "").strip().lower()
    return s.startswith("promemoria") or s.startswith(PREFIX.strip())


class ReminderService:
    def __init__(self, settings: Settings, store, google=None):
        self.s, self.store, self.google = settings, store, google
        self.tz = ZoneInfo(settings.timezone)

    @property
    def linked(self) -> bool:
        return bool(self.google and self.google.enabled)

    # ------------------------------------------------------------------ Calendario
    def _body(self, text: str, due: datetime) -> dict:
        end = due + timedelta(minutes=15)
        body = {"summary": PREFIX + text, "description": "Promemoria di JARVIS (si aggiorna da solo con l'app).",
                "start": {"dateTime": due.isoformat(), "timeZone": self.s.timezone}, "end": {"dateTime": end.isoformat(), "timeZone": self.s.timezone},
                "transparency": "transparent",  # non occupa l'agenda come una riunione
                "extendedProperties": {"private": TAG}}
        body["reminders"] = ({"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]} if self.s.reminder_calendar_popup else {"useDefault": False, "overrides": []})
        return body

    async def _create_event(self, text: str, due: datetime) -> str:
        r = await self.google.request("POST", f"{CAL}/events", params={"sendUpdates": "none"}, json=self._body(text, due))
        return r.json()["id"]

    async def _delete_event(self, event_id: str) -> None:
        try:
            await self.google.request("DELETE", f"{CAL}/events/{event_id}", params={"sendUpdates": "none"})
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (404, 410):
                raise

    async def _move_event(self, event_id: str, due: datetime, text: str | None = None) -> None:
        body: dict = {"start": {"dateTime": due.isoformat(), "timeZone": self.s.timezone}, "end": {"dateTime": (due + timedelta(minutes=15)).isoformat(), "timeZone": self.s.timezone}}
        if text is not None:
            body["summary"] = PREFIX + text
        await self.google.request("PATCH", f"{CAL}/events/{event_id}", params={"sendUpdates": "none"}, json=body)

    # ------------------------------------------------------------------ operazioni usate da tool, API e bot
    async def create(self, text: str, due: datetime) -> dict:
        event_id = ""
        if self.linked:
            try:
                event_id = await self._create_event(text, due)
            except Exception as e:  # il Calendario non risponde: il promemoria c'è comunque e la sincronizzazione lo collega più tardi
                log.warning("promemoria non aggiunto al Calendario (%s): riprovo alla prossima sincronizzazione", type(e).__name__)
        rid = await self.store.add_reminder(text, due, event_id)
        return {"id": rid, "event_id": event_id, "calendar": bool(event_id)}

    async def delete(self, reminder_id: int) -> bool:
        row = next((r for r in await self.store.list_reminders() if r["id"] == reminder_id), None)
        if row and row.get("event_id") and self.linked:
            try:
                await self._delete_event(row["event_id"])
            except Exception as e:
                log.warning("evento del Calendario non eliminato (%s)", type(e).__name__)
        await self.store.delete_reminder(reminder_id)
        return row is not None

    async def snooze(self, reminder_id: int, minutes: int) -> datetime | None:
        row = next((r for r in await self.store.list_reminders() if r["id"] == reminder_id), None)
        if not row:
            return None
        due = datetime.now(self.tz) + timedelta(minutes=max(1, minutes))
        await self.store.update_reminder(reminder_id, due_at=due)
        if self.linked:
            try:
                if row.get("event_id"):
                    await self._move_event(row["event_id"], due)
                else:
                    await self.store.update_reminder(reminder_id, event_id=await self._create_event(row["text"], due))
            except Exception as e:
                log.warning("evento del Calendario non spostato (%s)", type(e).__name__)
        return due

    async def snooze_delivered(self, text: str, minutes: int, event_id: str = "") -> dict:
        """Dal promemoria già scattato (pulsante «+10 min»): ne crea uno nuovo (e il suo evento) tra N minuti."""
        return await self.create(text, datetime.now(self.tz) + timedelta(minutes=max(1, minutes)))

    # ------------------------------------------------------------------ sincronizzazione: il Calendario comanda
    async def _tagged_events(self, now: datetime) -> dict[str, dict]:
        r = await self.google.request("GET", f"{CAL}/events", params={
            "timeMin": (now - timedelta(days=1)).isoformat(), "timeMax": (now + timedelta(days=365)).isoformat(), "singleEvents": "true",
            "showDeleted": "true", "privateExtendedProperty": "jarvis=reminder", "maxResults": 250})
        return {e["id"]: e for e in r.json().get("items", [])}

    async def _untagged_candidates(self, now: datetime) -> list[dict]:
        out: dict[str, dict] = {}
        for q in ("promemoria", PREFIX.strip()):
            r = await self.google.request("GET", f"{CAL}/events", params={
                "timeMin": now.isoformat(), "timeMax": (now + timedelta(days=60)).isoformat(), "singleEvents": "true", "q": q, "maxResults": 50})
            for e in r.json().get("items", []):
                if e.get("status") != "cancelled" and (e.get("extendedProperties") or {}).get("private", {}).get("jarvis") != "reminder" and _is_reminder_title(e.get("summary", "")):
                    out[e["id"]] = e
        return list(out.values())

    async def sync(self) -> dict:
        res = {"created": 0, "updated": 0, "removed": 0, "imported": 0}
        if not self.linked:
            return res
        now = datetime.now(self.tz)
        local = await self.store.list_reminders()
        events = await self._tagged_events(now)
        for r in local:
            eid = r.get("event_id") or ""
            if not eid:
                if datetime.fromisoformat(r["due_at"]) > now:  # senza evento: si crea (promemoria di prima del collegamento o Calendario momentaneamente giù)
                    try:
                        await self.store.update_reminder(r["id"], event_id=await self._create_event(r["text"], datetime.fromisoformat(r["due_at"]).astimezone(self.tz)))
                        res["created"] += 1
                    except Exception as e:
                        log.info("collegamento al Calendario rimandato: %s", type(e).__name__)
                continue
            ev = events.get(eid)
            if ev is None:  # fuori finestra o già eliminato: si controlla l'evento singolo
                try:
                    ev = (await self.google.request("GET", f"{CAL}/events/{eid}")).json()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (404, 410):
                        ev = {"status": "cancelled"}
                    else:
                        continue
            if ev.get("status") == "cancelled":  # eliminato sul Calendario → sparisce anche dall'app
                await self.store.delete_reminder(r["id"])
                res["removed"] += 1
                continue
            start = (ev.get("start") or {}).get("dateTime")
            text = _clean(ev.get("summary", ""))
            fields: dict = {}
            if start:
                new_due = datetime.fromisoformat(start.replace("Z", "+00:00"))
                if abs((new_due - datetime.fromisoformat(r["due_at"])).total_seconds()) > 60:
                    fields["due_at"] = new_due.astimezone(self.tz)
            if text != r["text"]:
                fields["text"] = text
            if fields:
                await self.store.update_reminder(r["id"], **fields)
                res["updated"] += 1
        known = {r.get("event_id") for r in await self.store.list_reminders()}
        for e in await self._untagged_candidates(now):  # «Promemoria: …» scritto a mano sul Calendario
            start = (e.get("start") or {}).get("dateTime")
            if not start or e["id"] in known:
                continue
            due = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(self.tz)
            if due <= now:
                continue
            await self.store.add_reminder(_clean(e.get("summary", "")), due, e["id"])
            try:
                await self.google.request("PATCH", f"{CAL}/events/{e['id']}", params={"sendUpdates": "none"}, json={"extendedProperties": {"private": TAG}})
            except Exception as ex:
                log.info("evento importato non marcato (%s)", type(ex).__name__)
            res["imported"] += 1
        if any(res.values()):
            log.info("promemoria ↔ Calendario: %s", res)
        return res
