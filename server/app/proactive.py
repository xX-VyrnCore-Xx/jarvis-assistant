"""JARVIS proattivo: non aspetta le domande. Avvisa degli eventi in arrivo, delle email nuove, prepara il riepilogo serale e quello settimanale.
Niente chiamate al modello (zero token): testi assemblati dai dati. Tetto giornaliero, deduplicazione e ore silenziose evitano il rumore."""
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import Settings
from .agenda import fetch_events
from .tools.google_tools import GMAIL

log = logging.getLogger("jarvis.proactive")
STATE_KEY = "proactive_state"
AWAKE = (7, 23)  # fuori da queste ore non si inviano avvisi non urgenti


def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


class Proactive:
    def __init__(self, settings: Settings, store, notifier, google=None, brain=None, budget=None):
        self.s, self.store, self.notifier, self.google, self.brain, self.budget = settings, store, notifier, google, brain, budget
        self.tz = ZoneInfo(settings.timezone)
        self._last: dict[str, float] = {}
        self._state: dict | None = None

    # ------------------------------------------------------------------ stato (persistente: sopravvive ai riavvii di Render)
    async def _load(self, today: str) -> dict:
        if self._state is None:
            try:
                self._state = json.loads(await self.store.get_setting(STATE_KEY) or "{}")
            except ValueError:
                self._state = {}
        st = self._state
        if st.get("day") != today:
            st["day"], st["n"] = today, 0
        st.setdefault("seen", {})
        cutoff = time.time() - 4 * 86400
        st["seen"] = {k: v for k, v in st["seen"].items() if v > cutoff}
        return st

    async def _save(self) -> None:
        await self.store.set_setting(STATE_KEY, json.dumps(self._state))

    def _due(self, job: str, every_s: float) -> bool:
        now = time.monotonic()
        if now - self._last.get(job, -1e9) < every_s:
            return False
        self._last[job] = now
        return True

    async def _send(self, st: dict, key: str, title: str, body: str, urgent: bool = False, telegram: bool | None = None) -> bool:
        if key in st["seen"] or (not urgent and st["n"] >= self.s.proactive_max_per_day):
            return False
        st["seen"][key] = time.time()
        if not urgent:
            st["n"] += 1
        await self.notifier.push("proactive", title, body[:600], telegram=telegram)
        await self._save()
        return True

    # ------------------------------------------------------------------ cicli
    async def tick(self, now: datetime | None = None) -> list[str]:
        """Un giro di controlli. Restituisce i nomi dei lavori che hanno inviato qualcosa (utile ai test)."""
        if not self.s.proactive_enabled or await self.store.get_setting("proactive_paused") == "1":
            return []
        now = (now or datetime.now(self.tz)).astimezone(self.tz)
        st = await self._load(now.date().isoformat())
        sent = []
        awake = AWAKE[0] <= now.hour < AWAKE[1]
        jobs = [("heads_up", self.heads_up, awake and self._due("heads_up", 240)),
                ("emails", self.emails, awake and self._due("emails", 2 * 3600)),
                ("evening", self.evening, bool(self.s.evening_hour) and self.s.evening_hour <= now.hour < self.s.evening_hour + 2),
                ("weekly", self.weekly, now.weekday() == 6 and now.hour >= 18),
                ("forecast", self.forecast, awake and self._due("forecast", 6 * 3600)),
                ("profile", self.profile, self._due("profile", 6 * 3600))]
        for name, fn, go in jobs:
            if not go:
                continue
            try:
                if await fn(st, now):
                    sent.append(name)
            except Exception as e:  # un servizio esterno che non risponde non ferma gli altri controlli
                log.info("controllo proattivo %s saltato: %s", name, type(e).__name__)
        return sent

    # ------------------------------------------------------------------ eventi imminenti
    async def _events(self, start: datetime, end: datetime) -> list[dict]:
        return await fetch_events(self.google, start, end, 20)

    async def heads_up(self, st: dict, now: datetime) -> bool:
        """Evento in partenza tra 10 e 45 minuti: avviso immediato anche su Telegram (non conta nel tetto giornaliero)."""
        if not (self.google and self.google.enabled):
            return False
        sent = False
        for e in await self._events(now + timedelta(minutes=10), now + timedelta(minutes=45)):
            start = (e.get("start") or {}).get("dateTime")
            if not start or e.get("status") == "cancelled":
                continue
            when = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(self.tz)
            mins = max(1, round((when - now).total_seconds() / 60))
            place = f" · {e['location']}" if e.get("location") else ""
            sent |= await self._send(st, f"ev:{_h(e.get('id', '') + start)}", f"Tra {mins} minuti: {e.get('summary', 'evento')}",
                                     f"Alle {when:%H:%M}{place}.", urgent=True, telegram=True)
        return sent

    # ------------------------------------------------------------------ email nuove
    async def emails(self, st: dict, now: datetime) -> bool:
        if not (self.google and self.google.enabled):
            return False
        r = await self.google.request("GET", f"{GMAIL}/messages", params={"q": "is:unread category:primary newer_than:1d", "maxResults": 8})
        fresh = [m["id"] for m in r.json().get("messages", []) if f"mail:{m['id']}" not in st["seen"]]
        if not fresh:
            return False
        rows = []
        for mid in fresh[:3]:
            d = (await self.google.request("GET", f"{GMAIL}/messages/{mid}", params={"format": "metadata", "metadataHeaders": ["From", "Subject"]})).json()
            hdr = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
            rows.append(f"{hdr.get('From', '?').split('<')[0].strip()[:30]}: {hdr.get('Subject', '(senza oggetto)')[:60]}")
        for mid in fresh:
            st["seen"][f"mail:{mid}"] = time.time()
        more = f" (+{len(fresh) - 3} altre)" if len(fresh) > 3 else ""
        return await self._send(st, f"mailbatch:{_h(','.join(fresh))}", f"{len(fresh)} email nuove da leggere", "\n".join(rows) + more)

    # ------------------------------------------------------------------ riepilogo serale
    async def evening(self, st: dict, now: datetime) -> bool:
        day = now.date().isoformat()
        parts = []
        if self.google and self.google.enabled:
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            evs = [e for e in await self._events(tomorrow, tomorrow + timedelta(days=1)) if e.get("status") != "cancelled"]
            if evs:
                lines = []
                for e in evs[:5]:
                    t = (e.get("start") or {}).get("dateTime")
                    lines.append(f"{datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(self.tz):%H:%M} {e.get('summary', 'evento')}" if t else f"tutto il giorno: {e.get('summary', 'evento')}")
                parts.append("Domani:\n" + "\n".join(lines))
        tasks = await self.store.list_tasks(None, False)
        if tasks:
            parts.append(f"{len(tasks)} attività aperte: " + "; ".join(t["text"][:50] for t in tasks[:3]) + ("…" if len(tasks) > 3 else ""))
        rems = [r for r in await self.store.list_reminders() if datetime.fromisoformat(r["due_at"]).astimezone(self.tz).date() == (now + timedelta(days=1)).date()]
        if rems:
            parts.append("Promemoria di domani: " + "; ".join(r["text"][:40] for r in rems[:3]))
        if not parts:
            return False
        return await self._send(st, f"evening:{day}", "Il punto della sera, signore", "\n\n".join(parts))

    # ------------------------------------------------------------------ riepilogo settimanale
    async def weekly(self, st: dict, now: datetime) -> bool:
        if not (self.brain and self.brain.enabled):
            return False
        iso = now.isocalendar()
        week_ago = (now - timedelta(days=7)).astimezone(timezone.utc).isoformat()
        docs = [d for d in await self.brain.store.list_docs(300) if d.created_at >= week_ago and d.source not in ("profile", "wiki", "skill")]
        if not docs:
            return False
        learned = sum(1 for d in docs if "appreso" in d.tags)
        top = await self.brain.store.top_entities(3)
        lines = [f"Questa settimana il secondo cervello è cresciuto di {len(docs)} documenti" + (f", {learned} appresi da solo dalle nostre conversazioni" if learned else "") + "."]
        if top:
            lines.append("Più presenti: " + ", ".join(f"{n} ({c})" for _, _, n, c in top) + ".")
        review = await self.brain.resurface(2)
        if review:
            lines.append("Da ripassare: " + "; ".join(f"«{d.title[:50]}» (#{d.id})" for d in review) + ".")
        return await self._send(st, f"week:{iso[0]}-{iso[1]}", "Riepilogo della settimana", "\n".join(lines))

    # ------------------------------------------------------------------ token
    async def forecast(self, st: dict, now: datetime) -> bool:
        if not (self.budget and self.budget.enabled):
            return False
        from .api import forecast

        b = await self.budget.get()
        f = forecast(b)
        if not f["runs_out_before_reset"] or f["days_left"] is None or f["days_left"] > 10:
            return False
        return await self._send(st, f"fc:{now.toordinal() // 3}", "Token: a questo ritmo finiscono prima del reset",
                                f"Restano ~{int(f['days_left'])} giorni di token al consumo attuale (circa il {f['depletes_on'][8:]}/{f['depletes_on'][5:7]}). Posso usare modelli più leggeri o ridurre le ricerche.")

    # ------------------------------------------------------------------ manutenzione silenziosa
    async def profile(self, st: dict, now: datetime) -> bool:
        if self.brain and self.brain.enabled:
            await self.brain.refresh_profile()
        return False
