import asyncio
import json
import time

import httpx
import pytest

from app import tgwatch
from app.bot import TelegramBot
from app.config import Settings
from app.memory import MemoryStore
from app.telegram import Telegram, split_text, to_html


REAL_SLEEP = asyncio.sleep


def tg_with(handler):
    s = Settings(telegram_bot_token="1:a", telegram_owner_id=42, telegram_webhook_secret="sec", public_url="https://j.onrender.com")
    return Telegram(s, httpx.AsyncClient(transport=httpx.MockTransport(handler))), s


def test_rich_formatting_tables_quotes_code_hr_strike_spoiler_and_safe_splitting():
    out = to_html("# T\n| A | B |\n|---|---|\n| x | 12 |\n\n> citato\n\n---\n```python\nprint('<')\n```\n~~no~~ ||sì||\n- a\n  - b")
    assert "<b>▎T</b>" in out and "<pre>A │ B" in out and "<blockquote>citato</blockquote>" in out and "──────────" in out
    assert '<pre><code class="language-python">print(\'&lt;\')</code></pre>' in out and "<s>no</s>" in out and "<tg-spoiler>sì</tg-spoiler>" in out and "    ◦ b" in out
    parts = split_text("```py\n" + "riga\n" * 2000 + "```", 3500)
    assert all(p.count("```") % 2 == 0 for p in parts) and parts[1].startswith("```py")


@pytest.mark.asyncio
async def test_post_retries_transient_errors_and_rate_limits(monkeypatch):
    async def fast(_):  # niente attese vere
        return None
    monkeypatch.setattr("app.telegram.asyncio.sleep", fast)
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("giù", request=req)
        if len(calls) == 2:
            return httpx.Response(429, json={"parameters": {"retry_after": 1}})
        if len(calls) == 3:
            return httpx.Response(502)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    tg, _ = tg_with(handler)
    assert await tg.send_id(42, "ciao") == 7 and len(calls) == 4
    dead, _ = tg_with(lambda r: httpx.Response(502))
    with pytest.raises(httpx.HTTPError):
        await dead.send(42, "x")


@pytest.mark.asyncio
async def test_webhook_check_takes_back_control_and_rearms_after_delivery_errors():
    state = {"url": "https://altro.onrender.com/telegram/webhook", "err": 0, "msg": ""}
    sets = []

    def handler(req):
        method = req.url.path.rsplit("/", 1)[-1]
        body = json.loads(req.content) if req.content else {}
        if method == "getWebhookInfo":
            return httpx.Response(200, json={"result": {"url": state["url"], "pending_update_count": 3, "last_error_date": state["err"], "last_error_message": state["msg"]}})
        if method == "setWebhook":
            sets.append(body)
            state.update(url=body["url"], err=0, msg="")
        return httpx.Response(200, json={"ok": True, "result": True})

    tg, s = tg_with(handler)
    hook = "https://j.onrender.com/telegram/webhook"
    assert await tg.check_webhook(hook) == "ripreso" and sets[-1]["drop_pending_updates"] is True and sets[-1]["secret_token"] == "sec"
    assert await tg.check_webhook(hook) == "ok" and tg.health["url_ok"] and tg.health["pending"] == 3
    state.update(err=int(time.time()) - 60, msg="Wrong response from the webhook: 502 Bad Gateway")
    assert await tg.check_webhook(hook) == "riarmato" and sets[-1]["drop_pending_updates"] is False
    assert await tg.check_webhook(hook) == "ok"
    state.update(err=int(time.time()) - 7200, msg="vecchio errore")
    assert await tg.check_webhook(hook) == "ok"  # errore di ore fa: non si riarma


def test_mode_selection_and_status_line():
    assert tgwatch.mode_for(Settings(public_url="https://x", telegram_webhook_secret="s")) == "webhook"
    assert tgwatch.mode_for(Settings(telegram_webhook_secret="s", public_url="", render_external_url="")) == "polling"
    assert tgwatch.mode_for(Settings(telegram_mode="polling", public_url="https://x", telegram_webhook_secret="s")) == "polling"

    class A:
        class state:  # noqa: N801
            settings = Settings(telegram_owner_id=42)
            tg = Telegram(Settings(telegram_bot_token="1:a", telegram_owner_id=42))

    bot = TelegramBot(A)
    assert bot.tg_line()[0] is None
    A.state.tg.health = {"mode": "webhook", "url_ok": True, "pending": 2, "last_error": "", "last_error_at": 0}
    bot.last_update_at = time.time() - 300
    ok, text = bot.tg_line()
    assert ok and "webhook attivo" in text and "2 in coda" in text and "5 min fa" in text
    A.state.tg.health["last_error"] = "Connection timed out"
    assert bot.tg_line()[0] is False


@pytest.mark.asyncio
async def test_polling_loop_hands_updates_to_owner_only_and_recovers_from_errors(monkeypatch):
    async def fast(_):
        return None
    monkeypatch.setattr("app.tgwatch.asyncio.sleep", fast)
    tg, _ = tg_with(lambda r: httpx.Response(200, json={}))
    batches = [RuntimeError("rete"), [{"update_id": 1, "message": {"from": {"id": 42}}}, {"update_id": 2, "message": {"from": {"id": 99}}}]]
    offsets = []
    handled = []

    async def get_updates(offset, timeout=25):
        offsets.append(offset)
        b = batches.pop(0) if batches else None
        if isinstance(b, Exception):
            raise b
        if b is None:
            raise asyncio.CancelledError
        return b

    class Bot:
        async def handle_update(self, u):
            handled.append(u["update_id"])

    tg.get_updates = get_updates
    with pytest.raises(asyncio.CancelledError):
        await tgwatch.poll_loop(tg, Bot(), lambda u: u["message"]["from"]["id"] == 42)
    await REAL_SLEEP(0)
    assert handled == [1] and offsets == [0, 0, 3] and tg.health["mode"] == "polling"


@pytest.mark.asyncio
async def test_return_online_notice_only_after_a_long_gap_and_silent():
    sent = []

    class FakeTG:
        class s:  # noqa: N801
            telegram_owner_id = 42

        async def send_id(self, chat_id, text, markup=None, silent=False):
            sent.append((text, silent))

    store = MemoryStore()
    await tgwatch.announce_return(FakeTG(), store, "0.8.0")  # primo avvio: nessun avviso
    assert not sent and await store.get_setting("last_alive")
    await store.set_setting("last_alive", "2020-01-01T00:00:00+00:00")
    await tgwatch.announce_return(FakeTG(), store, "0.8.0")
    assert len(sent) == 1 and sent[0][1] is True and "di nuovo online" in sent[0][0] and "v0.8.0" in sent[0][0]
    await tgwatch.announce_return(FakeTG(), store, "0.8.0")  # appena segnato «vivo»: niente di nuovo
    assert len(sent) == 1
