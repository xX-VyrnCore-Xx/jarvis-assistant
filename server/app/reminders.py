"""Promemoria collegati al Calendario Google: l'evento del Calendario è la fonte, il promemoria dell'app lo segue.
Creare, rimandare o eliminare un promemoria nell'app lo fa anche sul Calendario; spostare o cancellare l'evento sul Calendario
aggiorna o toglie il promemoria dell'app (sincronizzazione ogni 5 minuti); un evento «Promemoria: …» scritto a mano sul Calendario
diventa un promemoria dell'app. Senza Google collegato funziona tutto solo nell'app."""
import json
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


def explain(e: Exception) -> str:
    """Causa dell'errore del Calendario in italiano, con il motivo indicato da Google (mai il corpo della risposta intero, mai token)."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        reason = msg = ""
        try:
            err = e.response.json()
            err = err.get("error", err)
            if isinstance(err, dict):
                reason = str((err.get("errors") or [{}])[0].get("reason") or err.get("status") or "")
                msg = str(err.get("message") or "")[:120]
            else:
                reason = str(err)[:40]
                msg = str(e.response.json().get("error_description", ""))[:120]
        except (ValueError, AttributeError, IndexError):
            pass
        low = f"{reason} {msg}".lower()
        if "invalid_grant" in low or code == 401:
            return "Autorizzazione Google scaduta o revocata: ricollega Google da Telegram (/google) o dall'app."
        if "accessnotconfigured" in low or "has not been used" in low or "disabled" in low:
            return "L'API Google Calendar non è abilitata nel progetto Google Cloud: abilitala e riprova."
        if code == 403 and ("insufficient" in low or "scope" in low):
            return "Permessi insufficienti: ricollega Google concedendo l'accesso al Calendario."
        if code == 403 and ("ratelimit" in low or "quota" in low):
            return "Limite di richieste di Google raggiunto: riprovo da solo più tardi."
        if code == 404:
            return "Calendario o evento non trovato."
        if code >= 500:
            return f"Google ha avuto un problema (HTTP {code}): riprovo da solo."
        return f"Google ha rifiutato la richiesta (HTTP {code}{', ' + reason if reason else ''})."
    if isinstance(e, httpx.TransportError):
        return "Google non raggiungibile (rete o timeout): riprovo da solo."
    return f"Errore inatteso ({type(e).__name__})."


class ReminderService:
    def __init__(self, settings: Settings, store, google=None):
        self.s, self.store, self.google = settings, store, google
        self.tz = ZoneInfo(settings.timezone)
        self.on_change = None  # callable(): avvisa gli altri dispositivi che i promemoria sono cambiati
        self.status: dict = {"ok": None, "at": "", "detail": "", "counts": {}, "failures": 0}
        self._last_logged = ""

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def _record(self, ok: bool, detail: str = "", counts: dict | None = None) -> None:
        s = self.status
        s["ok"], s["at"], s["detail"] = ok, datetime.now(self.tz).isoformat(timespec="seconds"), detail
        s["failures"] = 0 if ok else s["failures"] + 1
        if counts is not None:
            s["counts"] = counts
        if not ok and detail != self._last_logged:  # un solo avviso per causa: niente log ripetuti ogni 5 minuti
            log.warning("sincronizzazione Calendario: %s", detail)
        self._last_logged = "" if ok else detail

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
        event_id, error = "", ""
        if self.linked:
            try:
                event_id = await self._create_event(text, due)
            except Exception as e:  # il Calendario non risponde: il promemoria c'è comunque e la sincronizzazione lo collega più tardi
                error = explain(e)
                self._record(False, error)
        rid = await self.store.add_reminder(text, due, event_id)
        self._changed()
        return {"id": rid, "event_id": event_id, "calendar": bool(event_id), "error": error}

    async def _orphans(self) -> list[str]:
        try:
            return [e for e in json.loads(await self.store.get_setting("calendar_orphans") or "[]") if isinstance(e, str)]
        except ValueError:
            return []

    async def _set_orphans(self, ids: list[str]) -> None:
        await self.store.set_setting("calendar_orphans", json.dumps(list(dict.fromkeys(ids))[-200:]))

    async def delete(self, reminder_id: int) -> bool:
        row = await self.store.get_reminder(reminder_id)  # anche se già scattato: il suo evento va tolto comunque
        eid = (row or {}).get("event_id") or ""
        if eid and self.linked:
            try:
                await self._delete_event(eid)
            except Exception as e:  # Google non risponde: l'evento si toglie alla prossima sincronizzazione, senza restare orfano per sempre
                self._record(False, explain(e))
                await self._set_orphans(await self._orphans() + [eid])
        await self.store.delete_reminder(reminder_id)
        self._changed()
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
                self._record(False, explain(e))
        self._changed()
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
        """Allinea con il Calendario; il risultato (o la causa dell'errore) resta in `status` per l'app, e i dispositivi vengono avvisati se qualcosa cambia."""
        if not self.linked:
            self.status.update(ok=None, detail="Google non è collegato: i promemoria restano solo nell'app.")
            return {"created": 0, "updated": 0, "removed": 0, "imported": 0}
        try:
            res = await self._sync()
        except Exception as e:
            self._record(False, explain(e))
            raise
        self._record(not res.get("error"), res.get("error", ""), {k: v for k, v in res.items() if k != "error"})
        if any(res.get(k) for k in ("updated", "removed", "imported", "created")):
            self._changed()
        return res

    async def _cleanup(self, res: dict, now: datetime, events: dict[str, dict]) -> None:
        """Toglie dal Calendario gli eventi rimasti senza promemoria: cancellazioni andate male e promemoria già scattati."""
        left = []
        for eid in await self._orphans():
            try:
                await self._delete_event(eid)
                res["cleaned"] = res.get("cleaned", 0) + 1
            except Exception as e:
                left.append(eid)
                res["error"] = explain(e)
        if left != await self._orphans():
            await self._set_orphans(left)
        if not self.s.reminder_calendar_cleanup:
            return
        done = await self.store.done_reminders_with_event()
        active = await self.store.list_reminders()
        known = {r.get("event_id") for r in active} | {r["event_id"] for r in done}
        for eid, ev in (events.items() if len(active) < 100 else ()):  # con l'elenco al limite non si può sapere quali eventi siano orfani  # eventi di JARVIS senza più promemoria (cancellazioni andate male in passato); i più recenti di 10 minuti sono forse in creazione
            created = ev.get("created")
            if eid in known or ev.get("status") == "cancelled" or not created:
                continue
            if (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds() < 600:
                continue
            try:
                await self._delete_event(eid)
                res["cleaned"] = res.get("cleaned", 0) + 1
            except Exception as e:
                res["error"] = explain(e)
        for r in done:
            try:
                await self._delete_event(r["event_id"])
                await self.store.update_reminder(r["id"], event_id="")
                res["cleaned"] = res.get("cleaned", 0) + 1
            except Exception as e:
                res["error"] = explain(e)

    async def _sync(self) -> dict:
        res: dict = {"created": 0, "updated": 0, "removed": 0, "imported": 0}
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
                        res["error"] = explain(e)
                continue
            ev = events.get(eid)
            if ev is None:  # fuori finestra o già eliminato: si controlla l'evento singolo
                try:
                    ev = (await self.google.request("GET", f"{CAL}/events/{eid}")).json()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (404, 410):
                        ev = {"status": "cancelled"}
                    else:
                        res["error"] = explain(e)
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
        await self._cleanup(res, now, events)
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
                res["error"] = explain(ex)
            res["imported"] += 1
        if any(res[k] for k in ("updated", "removed", "imported", "created")):
            log.info("promemoria ↔ Calendario: %s", {k: v for k, v in res.items() if k != "error"})
        return res
