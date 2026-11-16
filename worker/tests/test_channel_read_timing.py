"""Polling/drafts stay unread; only a reply committed to send acknowledges it."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import behavior as bhv
import fanvue_agent
import userbot
from test_reply_flow import build, user_row
from test_fvvidene import _agent as fanvue_test_agent

pytestmark = pytest.mark.usefixtures("fast")


def telegram_semi():
    bot, db, llm, client, _ = build(
        user_row(reply_after=(datetime.now(timezone.utc) + timedelta(hours=10)).isoformat()),
        [{"role": "user", "content": "hey how are you"}], "all good",
        behavior={"active_start_min": 600, "active_end_min": 1200,
                  "active_tz": "America/Los_Angeles", "voices_enabled": False},
    )
    db.reply_mode = "semi"
    cards = []

    async def post_approval(**card):
        cards.append(card)
        return True

    bot.set_control(SimpleNamespace(post_approval=post_approval))
    llm.suggest = AsyncMock(return_value=["all good", "hey there"])
    return bot, db, llm, client, cards


async def test_telegram_semi_drafts_outside_hours_stay_unread(monkeypatch):
    bot, db, llm, client, cards = telegram_semi()
    monkeypatch.setattr(bhv, "in_active_window", lambda *a: False)
    await bot.reply_to(555)
    assert len(cards) == 1
    assert client.sent == [] and client.files == []
    assert client.read == []
    assert db.users[555]["pending_reply"] is False


async def test_telegram_auto_generation_and_delays_stay_unread(monkeypatch):
    bot, db, llm, client, _ = build(user_row(), [{"role": "user", "content": "hey"}], "all good")
    events = []

    async def reply(*args):
        events.append(("generate", list(client.read)))
        return "all good"

    async def pause(seconds):
        if seconds:
            events.append(("delay", list(client.read)))

    llm.reply = reply
    monkeypatch.setattr(userbot.asyncio, "sleep", pause)
    monkeypatch.setattr(bhv, "reply_delay", lambda *a, **kw: 120)
    await bot.reply_to(555)
    assert events == [("generate", []), ("delay", [])]
    assert client.read == [555]
    assert client.sent == [(555, "all good")]


async def test_telegram_semi_night_voice_waits_for_owner(monkeypatch):
    bot, db, llm, client, cards = telegram_semi()
    db.behavior["voices_enabled"] = True
    db.voices = [{"id": 1, "url": "https://example.test/goodnight.ogg", "active": True,
                  "transcript": "good night", "slot": "night", "parts": [], "is_cta": False}]
    monkeypatch.setattr(bhv, "winding_down", lambda *a: True)
    monkeypatch.setattr(userbot.voices_mod, "night_voice", lambda *a: db.voices[0])
    monkeypatch.setattr(userbot, "_download", AsyncMock(return_value=b"voice"))
    await bot.reply_to(555)
    assert client.files == [] and client.sent == []
    assert client.read == []
    assert len(cards) == 1


@pytest.mark.parametrize("kind", ["text", "photo", "voice"])
async def test_telegram_approved_delivery_marks_read_immediately_before_send(kind, monkeypatch):
    bot, db, llm, client, cards = telegram_semi()
    order = []
    original_read, original_text, original_file = client.send_read_acknowledge, client.send_message, client.send_file

    async def read(*args):
        order.append("seen")
        await original_read(*args)

    async def text(*args):
        order.append("send")
        await original_text(*args)

    async def file(*args, **kwargs):
        order.append("send")
        await original_file(*args, **kwargs)

    async def sleep(seconds):
        order.append("delay")

    client.send_read_acknowledge, client.send_message, client.send_file = read, text, file
    llm.charge_unit = AsyncMock()
    monkeypatch.setattr(userbot.asyncio, "sleep", sleep)
    monkeypatch.setattr(userbot, "_download", AsyncMock(return_value=b"photo"))
    monkeypatch.setattr(userbot, "_to_opus", AsyncMock(return_value=b"voice"))
    if kind == "text":
        result = await bot.deliver_text("555", "approved reply")
    elif kind == "photo":
        db.photos = [{"id": 7, "url": "https://example.test/photo.jpg"}]
        result = await bot.deliver_photo("555", "7", "approved photo")
    else:
        result = await bot.deliver_voice("555", "approved voice", b"voice")
    assert result is True
    assert order[-2:] == ["seen", "send"]
    assert "seen" not in order[:-2]


async def test_telegram_auto_outside_hours_never_reads_or_sends(monkeypatch):
    bot, _, _, client, _ = build(user_row(), [{"role": "user", "content": "hey"}], "hi")
    monkeypatch.setattr(bhv, "in_active_window", lambda *a: False)
    await bot.reply_to(555)
    assert client.read == [] and client.sent == []


@pytest.mark.parametrize("mode", ["auto", "semi"])
async def test_fanvue_incoming_sync_never_marks_read_outside_hours(mode):
    a = fanvue_test_agent()
    a._ensure_fan = AsyncMock(return_value={"tg_id": 555})
    a._situacia = AsyncMock(return_value=SimpleNamespace(
        persona={}, behavior={}, teraz=datetime(2026, 11, 16, 3), blok=None,
        kde="home", moment="", foto_ok=False, dlzi=False, pyta_fotku=False,
        pyta_ostre=False, prompt="persona", tip="", tah=None,
    ))
    a._db.history = AsyncMock(return_value=[{"role": "user", "content": "hey"}])
    cards = []
    async def card(**kw):
        cards.append(kw)
        return True
    a._control = SimpleNamespace(post_approval=card)
    a._llm = SimpleNamespace(suggest=AsyncMock(return_value=["hi"]))
    await a._reply({"payload": {"data": {"user": {"uuid": "fan-1"}, "text": "hey"}}},
                   {"reply_mode": mode, "active_start_min": 600, "active_end_min": 1200})
    assert a._api.citania == [("fan-1", False)]
    assert a._api.odoslane == []
    assert len(cards) == (1 if mode == "semi" else 0)


@pytest.mark.parametrize("kind", ["text", "photo"])
async def test_fanvue_approved_delivery_reads_before_send_only(kind):
    a = fanvue_test_agent()
    order = []
    original_read, original_send = a._api.chat_messages, a._api.send
    async def read(uuid, limit=30, mark_read=False):
        order.append("seen" if mark_read else "sync")
        return await original_read(uuid, limit, mark_read)
    async def send(*args):
        order.append("send")
        return await original_send(*args)
    a._api.chat_messages, a._api.send = read, send
    if kind == "text":
        assert await a.deliver_text("fan-1", "approved reply")
    else:
        assert await a.deliver_photo("fan-1", "photo-1", "approved photo")
    assert order == ["seen", "send", "sync"]


async def test_fanvue_reconcile_defaults_to_unread():
    a = fanvue_test_agent()
    await a._reconcile({"uuid": "fan-1", "text": "hey"}, {})
    assert a._api.citania == [("fan-1", False)]


async def test_fanvue_api_poll_defaults_to_mark_as_read_false():
    import httpx
    from fanvue_api import Fanvue
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": []})
    api = object.__new__(Fanvue)
    api._headers = AsyncMock(return_value={})
    async with httpx.AsyncClient(base_url="https://example.test", transport=httpx.MockTransport(handler)) as client:
        api._client = client
        await api.chat_messages("fan-1")
        await api.chat_messages("fan-1", mark_read=True)
    assert [r.url.params["markAsRead"] for r in requests] == ["false", "true"]


async def test_fanvue_auto_generation_and_delay_stay_unread(monkeypatch):
    a = fanvue_test_agent()
    a._ensure_fan = AsyncMock(return_value={"tg_id": 555})
    a._situacia = AsyncMock(return_value=SimpleNamespace(
        persona={}, behavior={}, teraz=datetime(2026, 11, 16, 13), blok=None,
        kde="home", moment="", foto_ok=False, dlzi=False, pyta_fotku=False,
        pyta_ostre=False, prompt="persona", tip="", tah=None,
    ))
    a._db.history = AsyncMock(return_value=[{"role": "user", "content": "hey"}])
    observations = []
    async def reply(*args):
        observations.append(("generation", list(a._api.citania)))
        return "all good"
    async def delay(seconds):
        observations.append((seconds, list(a._api.citania)))
    a._llm = SimpleNamespace(reply=reply)
    a._voice = AsyncMock(return_value=None)
    a._remember = AsyncMock()
    monkeypatch.setattr(fanvue_agent.asyncio, "sleep", delay)
    monkeypatch.setattr(fanvue_agent.random, "random", lambda: 1)
    await a._reply({"payload": {"data": {"user": {"uuid": "fan-1"}, "text": "hey"}}},
                   {"reply_mode": "auto", "active_start_min": 600, "active_end_min": 1200,
                    "reply_min_s": 120, "reply_max_s": 120})
    assert observations == [("generation", [("fan-1", False)]), (120, [("fan-1", False)])]
    assert a._api.citania == [("fan-1", False), ("fan-1", True)]
    assert a._api.odoslane == ["all good"]


@pytest.mark.parametrize("channel", ["telegram", "fanvue"])
async def test_current_shared_stop_does_not_read_or_send(channel):
    hub = SimpleNamespace(can_reply=AsyncMock(return_value=False))
    if channel == "telegram":
        bot, db, _, client, _ = telegram_semi()
        db.hub = hub
        assert await bot.deliver_text("555", "old approved text") is False
        assert client.read == [] and client.sent == []
    else:
        agent = fanvue_test_agent()
        agent._db.hub = hub
        assert await agent.deliver_text("fan-1", "old approved text") is False
        assert agent._api.citania == [] and agent._api.odoslane == []


async def test_telegram_missing_approved_photo_stays_unread(monkeypatch):
    bot, db, _, client, _ = telegram_semi()
    db.photos = [{"id": 7, "url": "https://example.test/photo.jpg"}]
    monkeypatch.setattr(userbot, "_download", AsyncMock(return_value=None))
    assert await bot.deliver_photo("555", "7", "caption") is False
    assert client.read == [] and client.files == []
