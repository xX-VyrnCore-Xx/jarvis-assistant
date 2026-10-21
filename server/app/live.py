"""Notizie e informazioni in tempo reale: feed RSS/Atom (Italia, mondo, tecnologia, IA, scienza, economia, sport, terremoti più quelli personali),
letti dal vivo con cache breve e salvati ogni poco nel secondo cervello (fonte «news», con scadenza) così JARVIS resta aggiornato anche tra una domanda e l'altra.
Tutto il contenuto dei feed è esterno: dati, mai istruzioni."""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from .config import Settings
from .tools import UNTRUSTED, ToolRegistry

log = logging.getLogger("jarvis.live")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JARVIS-personal-assistant/0.7)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
SETTING = "live_feeds"
CACHE_S = 300
RETRY_AFTER_ERROR_S = 600
MAX_BYTES = 2_000_000

FEEDS: dict[str, list[tuple[str, str]]] = {
    "italia": [("ANSA", "https://www.ansa.it/sito/ansait_rss.xml"), ("Repubblica", "https://www.repubblica.it/rss/homepage/rss2.0.xml"),
               ("Corriere", "https://xml2.corriereobjects.it/rss/homepage.xml"), ("Il Sole 24 Ore", "https://www.ilsole24ore.com/rss/italia.xml"),
               ("Il Post", "https://www.ilpost.it/feed/")],
    "mondo": [("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"), ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
              ("The Guardian", "https://www.theguardian.com/world/rss"), ("NPR", "https://feeds.npr.org/1001/rss.xml"), ("Deutsche Welle", "https://rss.dw.com/xml/rss-en-all")],
    "tecnologia": [("Wired Italia", "https://www.wired.it/feed/rss"), ("Hacker News", "https://hnrss.org/frontpage"), ("The Verge", "https://www.theverge.com/rss/index.xml"),
                   ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"), ("TechCrunch", "https://techcrunch.com/feed/"), ("GitHub Blog", "https://github.blog/feed/")],
    "ai": [("Hugging Face", "https://huggingface.co/blog/feed.xml"), ("arXiv cs.AI", "http://export.arxiv.org/rss/cs.AI")],
    "scienza": [("NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss"), ("ScienceDaily", "https://www.sciencedaily.com/rss/top.xml")],
    "economia": [("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml"), ("BCE", "https://www.ecb.europa.eu/rss/press.html"),
                 ("Il Sole 24 Ore", "https://www.ilsole24ore.com/rss/italia.xml")],
    "sport": [("Gazzetta", "https://www.gazzetta.it/rss/home.xml"), ("BBC Sport", "http://feeds.bbci.co.uk/sport/rss.xml")],
    "terremoti": [("USGS", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.atom")],
}
INGEST_CATEGORIES = ("italia", "mondo", "tecnologia", "ai", "scienza", "economia")  # sport e terremoti si leggono solo dal vivo


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    raw = "".join(el.itertext()).strip()
    raw = re.sub(r"<[^>]+>", " ", raw)  # molti feed mettono HTML nel riassunto
    raw = raw.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#8217;", "'").replace("&#39;", "'")
    return re.sub(r"\s+", " ", raw).strip()


def _when(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_feed(raw: bytes, source: str) -> list[dict]:
    """RSS 2.0, RSS 1.0 (RDF) e Atom -> [{title, link, text, ts, source}]. Rifiuta DOCTYPE/ENTITY (attacchi a espansione di entità)."""
    if b"<!ENTITY" in raw[:50000].upper():
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    items = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        d: dict = {}
        for ch in el:
            n = _local(ch.tag)
            if n == "link":
                d.setdefault("link", (ch.get("href") or _text(ch)).strip())
            elif n in ("title", "description", "summary", "content", "encoded"):
                d.setdefault(n, _text(ch))
            elif n in ("pubdate", "published", "updated", "date"):
                d.setdefault("date", _text(ch))
        title, link = d.get("title", ""), d.get("link", "")
        if not title or not link.startswith(("http://", "https://")):
            continue
        body = d.get("description") or d.get("summary") or d.get("content") or d.get("encoded") or ""
        items.append({"title": title[:200], "link": link, "text": body[:600], "ts": _when(d.get("date", "")), "source": source})
    return items


def _stems(text: str) -> set[str]:
    from .skills.registry import tokens

    return set(tokens(text))


class LiveFeeds:
    def __init__(self, settings: Settings, store, client: httpx.AsyncClient | None = None):
        self.s, self.store = settings, store
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(12, connect=6), headers=HEADERS, follow_redirects=True)
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._failed: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.last_ingest = ""
        self.last_ingest_count = 0
        self._gate = asyncio.Semaphore(6)
        self.custom: list[dict] = []

    # ------------------------------------------------------------------ elenco
    async def load_custom(self) -> None:
        try:
            self.custom = [f for f in json.loads(await self.store.get_setting(SETTING) or "[]") if isinstance(f, dict) and f.get("url")]
        except (ValueError, TypeError):
            self.custom = []

    def feeds(self, category: str = "") -> list[tuple[str, str, str]]:
        cat = (category or "").strip().lower()
        out = [(n, u, c) for c, rows in FEEDS.items() for n, u in rows if not cat or c == cat]
        out += [(f.get("name") or urlparse(f["url"]).hostname or "feed", f["url"], f.get("category", "personale")) for f in self.custom if not cat or f.get("category", "personale") == cat]
        seen, uniq = set(), []
        for n, u, c in out:
            if u not in seen:
                seen.add(u)
                uniq.append((n, u, c))
        return uniq

    def categories(self) -> list[str]:
        return sorted({*FEEDS, *(f.get("category", "personale") for f in self.custom)})

    # ------------------------------------------------------------------ lettura
    async def fetch(self, name: str, url: str) -> list[dict]:
        now = time.monotonic()
        hit = self._cache.get(url)
        if hit and hit[0] > now:
            return hit[1]
        if self._failed.get(url, 0) > now:
            return hit[1] if hit else []
        try:
            async with self._gate:
                async with self._client.stream("GET", url) as r:
                    r.raise_for_status()
                    buf = bytearray()
                    async for chunk in r.aiter_bytes():
                        buf += chunk
                        if len(buf) > MAX_BYTES:
                            break
            items = parse_feed(bytes(buf), name)
            if not items:
                raise ValueError("nessun elemento")
            self._cache[url] = (now + CACHE_S, items)
            self.errors.pop(name, None)
            return items
        except Exception as e:
            self._failed[url] = now + RETRY_AFTER_ERROR_S
            self.errors[name] = type(e).__name__
            return hit[1] if hit else []

    async def headlines(self, topic: str = "", category: str = "", limit: int = 8, max_age_h: int = 72) -> list[dict]:
        feeds = self.feeds(category)
        batches = await asyncio.gather(*(self.fetch(n, u) for n, u, _ in feeds))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_h)
        want = _stems(topic) if topic.strip() else set()
        rows, seen = [], set()
        for (name, url, cat), items in zip(feeds, batches):
            for it in items:
                if it["link"] in seen or (it["ts"] and it["ts"] < cutoff):
                    continue
                if want and not (want & _stems(it["title"] + " " + it["text"])):
                    continue
                seen.add(it["link"])
                rows.append({**it, "category": cat})
        rows.sort(key=lambda r: r["ts"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        if not category and not want:  # panoramica: varietà di fonti invece delle sole più prolifiche
            per: dict[str, int] = {}
            mixed = []
            for r in rows:
                per[r["source"]] = per.get(r["source"], 0) + 1
                if per[r["source"]] <= 2:
                    mixed.append(r)
            rows = mixed
        return rows[:max(1, min(limit, 25))]

    # ------------------------------------------------------------------ secondo cervello
    async def ingest(self, brain, per_cycle: int = 20, keep_days: int = 10) -> int:
        """Salva le notizie nuove (ultime 24 ore) nel secondo cervello e toglie quelle vecchie. Solo parole e vettori: nessun token del modello."""
        if not brain or not brain.enabled:
            return 0
        done = 0
        for cat in INGEST_CATEGORIES:
            rows = await self.headlines(category=cat, limit=6, max_age_h=24)
            for r in rows:
                if done >= per_cycle:
                    break
                res = await brain.ingest(f"{r['title']}\n{r['text']}\n{r['source']} · {r['link']}", title=r["title"], source="news", uri=r["link"], tags=[cat, "notizie"], importance=0.3)
                if res["status"] == "creato":
                    await brain.store.update_doc(res["doc_id"], enriched=True)
                    done += 1
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
        for d in await brain.store.list_docs(400, source="news"):
            if d.created_at < cutoff:
                await brain.forget(d.id)
        self.last_ingest, self.last_ingest_count = datetime.now(timezone.utc).isoformat(timespec="seconds"), done
        return done

    # ------------------------------------------------------------------ feed personali
    async def add(self, url: str, name: str, category: str, public_check) -> str:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname or not await asyncio.to_thread(public_check, u.hostname):
            return "Errore: indirizzo non valido o non pubblico (solo http/https)."
        if len(self.custom) >= 30:
            return "Errore: massimo 30 feed personali."
        items = await self.fetch(name or u.hostname, url)
        if not items:
            self._failed.pop(url, None)
            return "Errore: non riesco a leggere un feed RSS/Atom valido a quell'indirizzo."
        self.custom = [f for f in self.custom if f["url"] != url] + [{"url": url, "name": (name or u.hostname)[:40], "category": (category or "personale").strip().lower()[:20]}]
        await self.store.set_setting(SETTING, json.dumps(self.custom))
        return f"Feed aggiunto: {name or u.hostname} ({len(items)} notizie lette)."

    async def remove(self, name: str) -> str:
        keep = [f for f in self.custom if (f.get("name") or "").lower() != name.strip().lower()]
        if len(keep) == len(self.custom):
            return "Errore: nessun feed personale con quel nome (quelli integrati non si tolgono)."
        self.custom = keep
        await self.store.set_setting(SETTING, json.dumps(keep))
        return "Feed rimosso."


def fmt(rows: list[dict]) -> str:
    out = []
    for r in rows:
        age = ""
        if r["ts"]:
            h = (datetime.now(timezone.utc) - r["ts"]).total_seconds() / 3600
            age = f"{int(h * 60)} min fa" if h < 1 else f"{int(h)} h fa" if h < 48 else f"{int(h // 24)} giorni fa"
        out.append(f"• {r['title']} — {r['source']}{', ' + age if age else ''}\n  {r['link']}" + (f"\n  {r['text'][:220]}" if r["text"] else ""))
    return UNTRUSTED + "\n".join(out) if out else "Nessuna notizia trovata."


def register_live_tools(reg: ToolRegistry, live: LiveFeeds, updates=None, brain=None, knowledge=None, version: str = "") -> None:
    from .tools.web import _public

    s = {"type": "string"}
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731

    async def news_headlines(topic: str = "", category: str = "", limit: int = 8) -> str:
        rows = await live.headlines(topic, category, limit)
        return fmt(rows) if rows else (f"Nessuna notizia recente su «{topic}»" + (f" in «{category}»" if category else "") + ". Prova web_search o web_news.")

    async def feed_list() -> str:
        lines = [f"{c}: " + ", ".join(n for n, _, cc in live.feeds() if cc == c) for c in live.categories()]
        bad = f"\nNon raggiungibili ora: {', '.join(sorted(live.errors))}." if live.errors else ""
        return "\n".join(lines) + bad

    async def feed_add(url: str, name: str = "", category: str = "personale") -> str:
        return await live.add(url, name.strip(), category, _public)

    async def feed_remove(name: str) -> str:
        return await live.remove(name)

    async def jarvis_status() -> str:
        parts = [f"Versione server: {version or 'sconosciuta'}."]
        if updates is not None:
            rel = await updates.latest()
            parts.append(f"Ultima Release: {rel['version']} ({rel['published_at'][:10]})." if rel else "Nessuna Release pubblicata.")
        if live.last_ingest:
            parts.append(f"Notizie nel secondo cervello aggiornate il {live.last_ingest.replace('T', ' ')} ({live.last_ingest_count} nuove).")
        if knowledge is not None:
            done, total = await knowledge.progress()
            parts.append(f"Conoscenza di base: {done}/{total} voci, aggiornate a rotazione.")
        if live.errors:
            parts.append(f"Feed non raggiungibili: {', '.join(sorted(live.errors))}.")
        parts.append("Il server si aggiorna da solo a ogni nuova versione del codice; le app avvisano quando c'è una Release.")
        return " ".join(parts)

    reg.register("news_headlines", "Notizie in tempo reale (ultimi giorni) dai feed di ANSA, Repubblica, Corriere, BBC, Guardian, NASA, Hacker News, ecc. 'category': italia, mondo, tecnologia, ai, scienza, economia, sport, terremoti o personali; 'topic' filtra per argomento. Per qualsiasi domanda su cosa sta succedendo ora, usala per prima.",
                 obj({"topic": s, "category": s, "limit": {"type": "integer"}}), news_headlines, cache_ttl=120)
    reg.register("feed_list", "Elenco dei feed di notizie usati da JARVIS, per categoria, e quelli non raggiungibili.", obj({}), feed_list)
    reg.register("feed_add", "Aggiunge un feed RSS/Atom personale (blog, giornale, canale) alle notizie di JARVIS.", obj({"url": s, "name": s, "category": s}, ["url"]), feed_add)
    reg.register("feed_remove", "Rimuove un feed personale per nome.", obj({"name": s}, ["name"]), feed_remove)
    reg.register("jarvis_status", "Stato di aggiornamento di JARVIS: versione, ultima Release, ultimo aggiornamento delle notizie e della conoscenza di base, feed non raggiungibili.", obj({}), jarvis_status, cache_ttl=60)
