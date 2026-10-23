import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.config import Settings
from app.memory import MemoryStore
from app.reminders import ReminderService, _clean
from app.tools import ToolRegistry
from app.tools.basic import register_basic_tools

TZ = ZoneInfo("Europe/Rome")


class FakeCalendar:
    """Google Calendar finto: tiene gli eventi in un dizionario e risponde come l'API vera."""

    enabled = True

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.n = 0

    async def request(self, method, url, **kw):
        self.calls.append((method, url.rsplit("/events", 1)[-1] or "/"))
        resp = lambda data, code=200: httpx.Response(code, json=data, request=httpx.Request(method, url))  # noqa: E731
        if url.endswith("/events") and method == "POST":
            self.n += 1
            ev = {**kw["json"], "id": f"ev{self.n}", "status": "confirmed"}
            self.events[ev["id"]] = ev
            return resp(ev)
        if url.endswith("/events") and method == "GET":
            p, items = kw["params"], list(self.events.values())
            if p.get("privateExtendedProperty"):
                items = [e for e in items if (e.get("extendedProperties") or {}).get("private", {}).get("jarvis") == "reminder"]
            if p.get("q"):
                items = [e for e in items if p["q"].lower() in e.get("summary", "").lower()]
            if p.get("showDeleted") != "true":
                items = [e for e in items if e.get("status") != "cancelled"]
            return resp({"items": items})
        eid = url.rsplit("/", 1)[-1]
        if method == "DELETE":
            if eid not in self.events:
                raise httpx.HTTPStatusError("gone", request=httpx.Request(method, url), response=httpx.Response(410))
            self.events[eid]["status"] = "cancelled"
            return resp({})
        if eid not in self.events:
            raise httpx.HTTPStatusError("nf", request=httpx.Request(method, url), response=httpx.Response(404))
        if method == "PATCH":
            for k, v in kw["json"].items():
                self.events[eid][k] = {**self.events[eid].get(k, {}), **v} if isinstance(v, dict) else v
        return resp(self.events[eid])


def make(linked=True):
    s = Settings(jarvis_api_token="t", timezone="Europe/Rome")
    store, cal = MemoryStore(), FakeCalendar()
    svc = ReminderService(s, store, cal if linked else None)
    return svc, store, cal


def soon(minutes=60):
    return datetime.now(TZ) + timedelta(minutes=minutes)


@pytest.mark.asyncio
async def test_creating_a_reminder_creates_a_linked_calendar_event():
    svc, store, cal = make()
    r = await svc.create("chiamare Luca", soon())
    assert r["calendar"] and r["event_id"] == "ev1"
    ev = cal.events["ev1"]
    assert ev["summary"] == "⏰ chiamare Luca" and ev["extendedProperties"]["private"]["jarvis"] == "reminder"
    assert ev["reminders"]["overrides"] == [{"method": "popup", "minutes": 0}] and ev["transparency"] == "transparent"
    assert (await store.list_reminders())[0]["event_id"] == "ev1"


@pytest.mark.asyncio
async def test_without_google_it_stays_in_the_app_and_a_calendar_outage_is_recovered_by_sync():
    svc, store, _ = make(linked=False)
    assert (await svc.create("solo app", soon()))["calendar"] is False
    assert await svc.sync() == {"created": 0, "updated": 0, "removed": 0, "imported": 0}

    svc, store, cal = make()
    real = cal.request

    async def down(method, url, **kw):
        raise httpx.ConnectError("giù")

    cal.request = down
    r = await svc.create("durante il guasto", soon())
    assert r["calendar"] is False and len(await store.list_reminders()) == 1  # il promemoria c'è comunque
    cal.request = real
    assert (await svc.sync())["created"] == 1  # ...e alla sincronizzazione riceve il suo evento
    assert (await store.list_reminders())[0]["event_id"] == "ev1"


@pytest.mark.asyncio
async def test_calendar_is_the_master_moves_and_deletions_flow_into_the_app():
    svc, store, cal = make()
    a = await svc.create("riunione con Anna", soon(120))
    b = await svc.create("pagare la bolletta", soon(180))
    new_due = soon(300)
    cal.events["ev1"]["start"] = {"dateTime": new_due.isoformat()}  # spostato dall'utente sul Calendario
    cal.events["ev1"]["summary"] = "⏰ riunione con Anna e Luca"
    cal.events["ev2"]["status"] = "cancelled"  # eliminato sul Calendario
    res = await svc.sync()
    assert res["updated"] == 1 and res["removed"] == 1
    rows = await store.list_reminders()
    assert [r["text"] for r in rows] == ["riunione con Anna e Luca"]
    assert abs((datetime.fromisoformat(rows[0]["due_at"]) - new_due).total_seconds()) < 2
    assert a["id"] == rows[0]["id"] and b["id"] not in [r["id"] for r in rows]
    assert await svc.sync() == {"created": 0, "updated": 0, "removed": 0, "imported": 0}  # stabile: nessuna modifica in più


@pytest.mark.asyncio
async def test_event_purged_from_calendar_removes_the_reminder_and_manual_events_are_imported():
    svc, store, cal = make()
    await svc.create("vecchio", soon())
    del cal.events["ev1"]  # sparito del tutto (GET singolo → 404)
    assert (await svc.sync())["removed"] == 1 and await store.list_reminders() == []

    when = soon(240)
    cal.events["manual"] = {"id": "manual", "summary": "Promemoria: portare fuori l'umido", "status": "confirmed", "start": {"dateTime": when.isoformat()}}
    cal.events["meeting"] = {"id": "meeting", "summary": "Riunione trimestrale", "status": "confirmed", "start": {"dateTime": when.isoformat()}}
    res = await svc.sync()
    assert res["imported"] == 1
    rows = await store.list_reminders()
    assert [(r["text"], r["event_id"]) for r in rows] == [("portare fuori l'umido", "manual")]
    assert cal.events["manual"]["extendedProperties"]["private"]["jarvis"] == "reminder"  # marcato: non si reimporta
    assert (await svc.sync())["imported"] == 0 and len(await store.list_reminders()) == 1


@pytest.mark.asyncio
async def test_delete_and_snooze_follow_the_calendar_event():
    svc, store, cal = make()
    a = await svc.create("A", soon(30))
    b = await svc.create("B", soon(30))
    due = await svc.snooze(a["id"], 90)
    assert abs((datetime.fromisoformat(cal.events["ev1"]["start"]["dateTime"]) - due).total_seconds()) < 2
    assert abs((datetime.fromisoformat((await store.list_reminders())[-1]["due_at"]) - due).total_seconds()) < 2
    assert await svc.snooze(999, 5) is None
    assert await svc.delete(b["id"]) is True and cal.events["ev2"]["status"] == "cancelled"
    cal.events["ev1"]["status"] = "cancelled"
    assert await svc.delete(a["id"]) is True and await store.list_reminders() == []  # evento già sparito: nessun errore


@pytest.mark.asyncio
async def test_tools_tell_the_user_it_is_on_the_calendar():
    s = Settings(jarvis_api_token="t", timezone="Europe/Rome")
    store, cal = MemoryStore(), FakeCalendar()
    svc = ReminderService(s, store, cal)
    reg = ToolRegistry()
    register_basic_tools(reg, s, store, reminders=svc)
    out = await reg.call("remind_in", json.dumps({"minutes": 30, "text": "bere acqua"}))
    assert "Calendario Google" in out and cal.events["ev1"]["summary"] == "⏰ bere acqua"
    listed = await reg.call("list_reminders", "{}")
    assert "📅" in listed
    out = await reg.call("add_reminder", json.dumps({"text": "dentista", "when": soon(600).strftime("%Y-%m-%dT%H:%M:%S")}))
    assert "Calendario Google" in out
    await reg.call("reminder_snooze", json.dumps({"reminder_id": 1, "minutes": 15}))
    assert "eliminato (anche dal Calendario)" in await reg.call("delete_reminder", json.dumps({"reminder_id": 2}))
    plain = ToolRegistry()
    register_basic_tools(plain, s, MemoryStore())
    assert "Google non è collegato" in await plain.call("remind_in", json.dumps({"minutes": 5, "text": "x"}))


def test_titles_are_cleaned_in_both_directions():
    assert _clean("⏰ chiamare Luca") == "chiamare Luca" and _clean("Promemoria: dentista") == "dentista" and _clean("Promemoria - spesa") == "spesa" and _clean("Promemoria") == "Promemoria"


@pytest.mark.asyncio
async def test_failed_calendar_delete_is_retried_and_fired_reminders_leave_the_calendar():
    svc, store, cal = make()
    a = await svc.create("A", soon(30))
    real = cal.request

    async def down(method, url, **kw):
        raise httpx.ConnectError("giù")

    cal.request = down
    assert await svc.delete(a["id"]) is True and await store.list_reminders() == []  # via dall'app...
    cal.request = real
    assert cal.events["ev1"]["status"] == "confirmed"  # ...ma l'evento è rimasto
    assert (await svc.sync())["cleaned"] == 1 and cal.events["ev1"]["status"] == "cancelled"
    assert await svc._orphans() == []

    b = await svc.create("B", soon(30))
    await store.mark_reminder_done(b["id"])  # è scattato
    assert (await svc.sync())["cleaned"] == 1 and cal.events["ev2"]["status"] == "cancelled"
    assert "cleaned" not in await svc.sync()  # fatto una volta sola

    c = await svc.create("C", soon(30))
    await store.mark_reminder_done(c["id"])
    assert await svc.delete(c["id"]) is True and cal.events["ev3"]["status"] == "cancelled"  # anche se già scattato


@pytest.mark.asyncio
async def test_leftover_jarvis_events_without_a_reminder_are_removed_but_fresh_ones_are_spared():
    svc, store, cal = make()
    cal.events["old"] = {"id": "old", "status": "confirmed", "summary": "⏰ vecchio", "created": "2026-01-01T10:00:00Z", "extendedProperties": {"private": {"jarvis": "reminder"}}, "start": {"dateTime": soon(60).isoformat()}}
    cal.events["new"] = {"id": "new", "status": "confirmed", "summary": "⏰ nuovo", "created": datetime.now(TZ).isoformat(), "extendedProperties": {"private": {"jarvis": "reminder"}}, "start": {"dateTime": soon(60).isoformat()}}
    keep = await svc.create("tengo", soon(60))
    cal.events[keep["event_id"]]["created"] = "2026-01-01T10:00:00Z"
    assert (await svc.sync())["cleaned"] == 1
    assert cal.events["old"]["status"] == "cancelled" and cal.events["new"]["status"] == "confirmed" and cal.events[keep["event_id"]]["status"] == "confirmed"


def test_next_due_for_each_repeat_keeps_the_time_and_skips_weekends():
    from app.reminders import next_due, norm_repeat

    mon = datetime(2026, 10, 19, 9, 30, tzinfo=TZ)  # lunedì
    now = datetime(2026, 10, 19, 9, 31, tzinfo=TZ)
    assert next_due(mon, "daily", now) == datetime(2026, 10, 20, 9, 30, tzinfo=TZ)
    assert next_due(mon, "weekly", now) == datetime(2026, 10, 26, 9, 30, tzinfo=TZ)
    fri = datetime(2026, 10, 23, 9, 30, tzinfo=TZ)
    assert next_due(fri, "weekdays", fri + timedelta(minutes=1)) == datetime(2026, 10, 26, 9, 30, tzinfo=TZ)
    jan31 = datetime(2026, 1, 31, 8, 0, tzinfo=TZ)
    assert next_due(jan31, "monthly", jan31 + timedelta(minutes=1)) == datetime(2026, 2, 28, 8, 0, tzinfo=TZ)  # febbraio ha meno giorni
    assert next_due(datetime(2024, 2, 29, 8, 0, tzinfo=TZ), "yearly", datetime(2024, 3, 1, tzinfo=TZ)) == datetime(2025, 2, 28, 8, 0, tzinfo=TZ)
    old = datetime(2026, 10, 1, 7, 0, tzinfo=TZ)  # server spento per giorni: salta alla prossima occorrenza futura
    assert next_due(old, "daily", now) == datetime(2026, 10, 20, 7, 0, tzinfo=TZ)
    assert norm_repeat("Settimanale") == "weekly" and norm_repeat("") == "" and norm_repeat(None) == ""
    with pytest.raises(ValueError):
        norm_repeat("ogni tanto")


@pytest.mark.asyncio
async def test_recurring_reminder_renews_itself_when_it_fires_and_shows_on_the_calendar():
    from app.notify import Notifier
    from app.scheduler import deliver_due_reminders

    svc, store, cal = make()
    r = await svc.create("Riunione di team", soon(5), "weekly")
    assert "Si ripete ogni settimana" in cal.events["ev1"]["description"]
    assert (await store.list_reminders())[0]["repeat"] == "weekly"
    n = Notifier(Settings(jarvis_api_token="t"), store)
    assert await deliver_due_reminders(store, n, datetime.now(TZ) + timedelta(minutes=10), None, svc) == 1
    rows = await store.list_reminders()
    assert len(rows) == 1 and rows[0]["id"] != r["id"] and rows[0]["repeat"] == "weekly"  # il prossimo è già pronto
    wall = lambda s: datetime.fromisoformat(s).replace(tzinfo=None)  # noqa: E731  (l'ora sul quadrante resta la stessa anche se in mezzo cambia l'ora legale)
    assert wall(rows[0]["due_at"]) - wall(cal.events["ev1"]["start"]["dateTime"]) == timedelta(weeks=1)
    assert len(cal.events) == 2
    out = await _repeat_tool_checks(svc, store)
    assert "ogni giorno" in out


async def _repeat_tool_checks(svc, store):
    reg = ToolRegistry()
    register_basic_tools(reg, svc.s, store, reminders=svc)
    when = soon(600).strftime("%Y-%m-%dT%H:%M:%S")
    msg = await reg.call("add_reminder", json.dumps({"text": "vitamine", "when": when, "repeat": "daily"}))
    assert "si ripete ogni giorno" in msg
    assert "Errore" in await reg.call("add_reminder", json.dumps({"text": "x", "when": when, "repeat": "boh"}))
    return await reg.call("list_reminders", "{}")
