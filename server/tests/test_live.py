import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.config import Settings
from app.live import LiveFeeds, fmt, parse_feed, register_live_tools
from app.memory import MemoryStore
from app.tools import ToolRegistry
from app.tools.select import ToolSelector


def rss(items, title="Feed"):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><description><![CDATA[<p>{d} &amp; altro</p>]]></description><pubDate>{format_datetime(ts)}</pubDate></item>" for t, l, d, ts in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>{title}</title>{body}</channel></rss>'.encode()


NOW = datetime.now(timezone.utc)
ATOM = (b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>M 6.1 - Grecia</title><link href="https://eq.example/1"/>'
        b'<updated>' + NOW.isoformat().encode() + b'</updated><summary>Terremoto forte</summary></entry></feed>')


def test_parse_rss_atom_and_reject_entities():
    items = parse_feed(rss([("Titolo uno", "https://a.it/1", "testo", NOW)]), "A")
    assert items[0]["title"] == "Titolo uno" and items[0]["text"] == "testo & altro" and items[0]["ts"] is not None
    assert parse_feed(ATOM, "USGS")[0]["link"] == "https://eq.example/1"
    assert parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title><link>https://x.it</link></item></channel></rss>', "x") == []
    assert parse_feed(b"non e' xml", "x") == [] and parse_feed(rss([("T", "javascript:alert(1)", "d", NOW)]), "x") == []


def make(handler):
    return LiveFeeds(Settings(jarvis_api_token="t"), MemoryStore(), httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True))


def handler(req: httpx.Request) -> httpx.Response:
    host = req.url.host
    if host == "www.ansa.it":
        return httpx.Response(200, content=rss([("Terremoto in Grecia, scossa forte", "https://ansa.it/1", "magnitudo 6", NOW - timedelta(minutes=30)),
                                                ("Vecchia notizia", "https://ansa.it/old", "x", NOW - timedelta(days=9))]))
    if host == "earthquake.usgs.gov":
        return httpx.Response(200, content=ATOM)
    return httpx.Response(503)


@pytest.mark.asyncio
async def test_headlines_filter_by_topic_age_and_survive_broken_feeds():
    live = make(handler)
    rows = await live.headlines(category="italia")
    assert [r["title"] for r in rows] == ["Terremoto in Grecia, scossa forte"]  # la notizia di 9 giorni fa è fuori
    assert "ANSA" not in live.errors and {"Repubblica", "Corriere"} <= set(live.errors)
    assert (await live.headlines(topic="terremoti", category="italia"))[0]["source"] == "ANSA"
    assert await live.headlines(topic="calcio", category="italia") == []
    assert (await live.headlines(category="terremoti"))[0]["title"].startswith("M 6.1")
    assert "min fa" in fmt(rows) and fmt(rows).startswith("[")  # marcata come contenuto esterno
    # cache: un secondo giro non rifà le richieste
    calls = []
    live._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(1) or httpx.Response(500)))
    await live.headlines(category="italia")
    assert not calls


class FakeBrain:
    enabled = True

    def __init__(self):
        self.docs, self.store = {}, self
        self.forgotten = []

    async def ingest(self, text, title="", source="", uri="", tags=None, importance=0.5, pinned=False):
        if uri in self.docs:
            return {"status": "duplicato", "doc_id": self.docs[uri]}
        self.docs[uri] = len(self.docs) + 1
        return {"status": "creato", "doc_id": self.docs[uri]}

    async def update_doc(self, *a, **k): pass

    async def list_docs(self, limit, source=None):
        from app.brain.store import Doc
        return [Doc(99, "news", "vecchia", "u", "", [], [], "h", 0.3, False, created_at="2020-01-01T00:00:00+00:00")]

    async def forget(self, doc_id):
        self.forgotten.append(doc_id)


@pytest.mark.asyncio
async def test_ingest_saves_new_items_once_and_prunes_old_news():
    live, brain = make(handler), FakeBrain()
    assert await live.ingest(brain, 10) == 1 and brain.forgotten == [99]
    assert await live.ingest(brain, 10) == 0  # già presente
    assert live.last_ingest


@pytest.mark.asyncio
async def test_custom_feeds_tools_and_status():
    live = make(handler)
    reg = ToolRegistry()
    register_live_tools(reg, live, version="0.7.0")
    out = await reg.call("news_headlines", json.dumps({"category": "terremoti"}))
    assert "Grecia" in out
    assert "Errore" in await reg.call("feed_add", json.dumps({"url": "http://127.0.0.1/rss"}))
    live.custom = [{"url": "https://www.ansa.it/sito/ansait_rss.xml", "name": "Mio", "category": "miei"}]
    assert "miei" in await reg.call("feed_list", "{}")
    assert "rimosso" in (await reg.call("feed_remove", json.dumps({"name": "mio"}))).lower()
    assert "0.7.0" in await reg.call("jarvis_status", "{}")


def test_selector_activates_news_tools():
    sel = ToolSelector()
    assert "notizie" in sel.groups_for("che notizie ci sono oggi in Italia?")
    assert "notizie" in sel.groups_for("c'è stato un terremoto?")
