import json

import httpx
import pytest

from app.bot import TelegramBot
from app.config import Settings
from app.memory import MemoryStore
from app.telegram import Telegram, split_text, to_html
from app.tools import ToolRegistry, check_args
from app.tools.web import calc, fetch_page, html_to_text, register_web_tools


def test_to_html_formats_and_escapes():
    out = to_html("**Ciao** <b>x</b> e `a<b` con [sito](https://a.it/x?y=1&z=2)\n- uno\n- due\n```py\nx = 1 < 2\n```")
    assert "<b>Ciao</b>" in out and "&lt;b&gt;x&lt;/b&gt;" in out
    assert "<code>a&lt;b</code>" in out and '<a href="https://a.it/x?y=1&amp;z=2">sito</a>' in out
    assert "• uno" in out and "<pre>x = 1 &lt; 2</pre>" in out
    assert "<i>" not in to_html("2 * 3 * 4")  # asterischi aritmetici non diventano corsivo


def test_split_text_keeps_chunks_small_and_complete():
    text = ("parola " * 200 + "\n\n") * 6
    parts = split_text(text, 500)
    assert all(len(p) <= 500 for p in parts) and " ".join(parts).split() == text.split()


def test_check_args_validates_and_coerces():
    schema = {"type": "object", "required": ["n", "mode"], "properties": {
        "n": {"type": "integer"}, "mode": {"type": "string", "enum": ["a", "b"]}, "flag": {"type": "boolean"}}}
    assert check_args(schema, {"n": "5", "mode": "a", "flag": "true", "inventato": 1}) == ({"n": 5, "mode": "a", "flag": True}, "")
    assert "mancanti" in check_args(schema, {"n": 1})[1]
    assert "uno tra" in check_args(schema, {"n": 1, "mode": "z"})[1]
    assert "intero" in check_args(schema, {"n": "x", "mode": "a"})[1]


@pytest.mark.asyncio
async def test_registry_reports_errors_timeouts_and_truncates():
    import asyncio

    reg = ToolRegistry()

    async def slow(**_):
        await asyncio.sleep(5)

    async def big(**_):
        return "x" * 20000

    obj = {"type": "object", "properties": {}}
    reg.register("slow", "", obj, slow, timeout=0.05)
    reg.register("big", "", obj, big)
    assert "non ha risposto" in await reg.call("slow", "{}")
    assert "troncato" in await reg.call("big", "{}") and len(await reg.call("big", "{}")) < 8200
    assert "non JSON" not in await reg.call("big", "")  # argomenti vuoti = oggetto vuoto
    assert "JSON valido" in await reg.call("big", "{rotto")
    assert "inesistente" in await reg.call("nope", "{}")


def test_calculator_is_safe():
    assert calc("2+3*4") == 14 and calc("sqrt(16)+2^3") == 12 and round(calc("pi*2"), 4) == 6.2832
    for bad in ("__import__('os').system('x')", "9**9**9", "open('f')", "a+1"):
        with pytest.raises((ValueError, SyntaxError, TypeError)):
            calc(bad)


@pytest.mark.asyncio
async def test_fetch_blocks_private_addresses_and_wraps_untrusted():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, headers={"content-type": "text/html"}, text="<html><title>T</title><script>x()</script><p>Ciao mondo</p></html>"))) as c:
        assert "non pubblico" in await fetch_page("http://127.0.0.1/admin", c)
        assert "non pubblico" in await fetch_page("http://localhost:3001/", c)
        assert "non valido" in await fetch_page("file:///etc/passwd", c)
        out = await fetch_page("http://example.com/", c)
    assert out.startswith("[CONTENUTO ESTERNO") and "Ciao mondo" in out and "x()" not in out
    assert html_to_text("<title>A</title><p>b</p>") == ("A", "b")


@pytest.mark.asyncio
async def test_weather_tool_formats_open_meteo():
    def handler(req: httpx.Request) -> httpx.Response:
        if "geocoding" in str(req.url):
            return httpx.Response(200, json={"results": [{"name": "Roma", "country": "Italia", "latitude": 41.9, "longitude": 12.5}]})
        return httpx.Response(200, json={"current": {"temperature_2m": 21.4, "apparent_temperature": 20.0, "weather_code": 2, "wind_speed_10m": 9, "precipitation": 0},
                                         "daily": {"time": ["2026-10-21"], "weather_code": [61], "temperature_2m_max": [23], "temperature_2m_min": [14], "precipitation_probability_max": [60]}})

    reg = ToolRegistry()
    register_web_tools(reg, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    out = await reg.call("get_weather", json.dumps({"city": "Roma"}))
    assert "Roma" in out and "parzialmente nuvoloso" in out and "pioggia debole" in out and "60%" in out


class FakeTG(Telegram):
    def __init__(self):
        super().__init__(Settings(telegram_bot_token="1:a", telegram_owner_id=42))
        self.out, self.hook = [], ""

    async def send(self, chat_id, text, markup=None):
        self.out.append((text, markup))

    async def typing(self, chat_id):
        pass

    async def answer_callback(self, callback_id, text=""):
        self.out.append(("cb:" + text, None))

    async def webhook_url(self):
        return self.hook

    async def set_webhook(self, url, drop_pending=False):
        self.hook, self.dropped = url, drop_pending


class FakeApp:
    class state:  # noqa: N801
        pass


def make_bot():
    st = FakeApp.state
    st.settings = Settings(telegram_owner_id=42, owner_name="signore")
    st.tg, st.store = FakeTG(), MemoryStore()

    class Agent:
        async def reply(self, text, session):
            return f"eco:{text}"

    st.agent = Agent()
    return TelegramBot(FakeApp), st


@pytest.mark.asyncio
async def test_bot_owner_only_dedup_commands_and_buttons():
    bot, st = make_bot()
    msg = lambda uid, text, i=1: {"update_id": i, "message": {"from": {"id": uid}, "chat": {"id": uid}, "text": text}}  # noqa: E731
    assert bot.accepts(msg(42, "x")) and not bot.accepts(msg(99, "x"))

    await bot.handle_update(msg(42, "ciao", 1))
    await bot.handle_update(msg(42, "ciao", 1))  # duplicato di Telegram
    assert [o[0] for o in st.tg.out] == ["eco:ciao"]

    from datetime import datetime, timedelta, timezone
    await st.store.add_reminder("bere", datetime.now(timezone.utc) + timedelta(hours=1))
    await st.store.add_memory("ama il caffè")
    await bot.handle_update(msg(42, "/promemoria", 2))
    text, markup = st.tg.out[-1]
    assert "bere" in text and markup["inline_keyboard"][0][0]["callback_data"] == "rd:1"
    await bot.handle_update({"update_id": 3, "callback_query": {"id": "c", "from": {"id": 42}, "data": "rd:1", "message": {}}})
    assert await st.store.list_reminders() == [] and st.tg.out[-1][0] == "cb:Promemoria eliminato."

    await bot.handle_update(msg(42, "/ricordi", 4))
    assert "caffè" in st.tg.out[-1][0]
    await st.store.add_message("tg-42", "user", "a")
    await bot.handle_update(msg(42, "/nuova", 5))
    assert await st.store.recent_messages("tg-42", 10) == []
    await bot.handle_update({"update_id": 6, "message": {"from": {"id": 42}, "chat": {"id": 42}, "voice": {}}})
    assert "vocale" in st.tg.out[-1][0]


@pytest.mark.asyncio
async def test_telegram_takes_over_a_foreign_webhook():
    tg = FakeTG()
    tg.hook = "https://old-service.onrender.com/telegram/webhook"
    assert await tg.ensure_webhook("https://new.onrender.com/telegram/webhook") is True
    assert tg.hook.startswith("https://new") and tg.dropped is True
    assert await tg.ensure_webhook("https://new.onrender.com/telegram/webhook") is False


@pytest.mark.asyncio
async def test_google_guided_link_stores_encrypted_token_only_for_issued_state():
    from urllib.parse import parse_qs, urlparse

    from app.google import GoogleClient

    def handler(req: httpx.Request) -> httpx.Response:
        assert b"code=abc" in req.content and b"redirect_uri=" in req.content
        return httpx.Response(200, json={"refresh_token": "rt-segreto", "access_token": "at"})

    store = MemoryStore()
    s = Settings(jarvis_api_token="t", google_client_id="cid", google_client_secret="sec")
    g = GoogleClient(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)), store=store)
    assert g.has_client and not g.enabled
    url = g.authorize_url("https://x.onrender.com/google/callback")
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"] and q["client_id"] == ["cid"]
    with pytest.raises(ValueError):  # state non emesso da /google
        await g.complete("abc", "inventato", "https://x.onrender.com/google/callback")
    await g.complete("abc", q["state"][0], "https://x.onrender.com/google/callback")
    assert g.enabled and g.refresh_token == "rt-segreto"
    assert "rt-segreto" not in store.settings["google_refresh_token"]  # cifrato a riposo
    with pytest.raises(ValueError):  # lo state vale una volta sola
        await g.complete("abc", q["state"][0], "https://x.onrender.com/google/callback")
    g2 = GoogleClient(s, store=store)
    await g2.load()
    assert g2.enabled and g2.refresh_token == "rt-segreto"  # sopravvive al riavvio
