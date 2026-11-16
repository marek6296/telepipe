"""Auto rechecks local hours at delivery; Semi retries do not wait for them."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import behavior as bhv
import fanvue_agent as fa
import userbot
from test_reply_flow import build, user_row
from test_channel_read_timing import telegram_semi
from test_fvsemi_brana import _agent as fv_agent, FAN

pytestmark = pytest.mark.usefixtures('fast')
LA = ZoneInfo('America/Los_Angeles')


class Clock(datetime):
    value = datetime(2026, 11, 16, 19, 59, tzinfo=LA)

    @classmethod
    def now(cls, tz=None):
        return cls.value.astimezone(tz) if tz else cls.value.replace(tzinfo=None)


@pytest.fixture
def clock(monkeypatch):
    Clock.value = datetime(2026, 11, 16, 19, 59, tzinfo=LA)
    monkeypatch.setattr(userbot, 'datetime', Clock)
    monkeypatch.setattr(fa, 'datetime', Clock)
    return Clock


@pytest.mark.parametrize('pending', [True, False])
async def test_tg_semi_sweeper_recovers_outside_hours_and_future_reply_after(pending, clock):
    clock.value = datetime(2026, 11, 16, 3, tzinfo=LA)
    bot, db, _, client, cards = telegram_semi()
    db.users[555].update(pending_reply=pending,
        last_incoming_at=datetime.now(timezone.utc).isoformat(),
        reply_after=(clock.value + timedelta(hours=12)).isoformat())
    await bot._sweep_once()
    assert len(cards) == 1
    assert client.sent == [] and client.read == []


@pytest.mark.parametrize('morning', [False, True])
async def test_tg_auto_cannot_cross_closing_time_during_generation(morning, clock):
    bot, db, llm, client, _ = build(user_row(), [{'role': 'user', 'content': 'hey'}], 'all good',
        behavior={'active_tz': 'America/Los_Angeles', 'active_start_min': 600, 'active_end_min': 1200})
    async def reply(*args):
        clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
        return 'all good'
    llm.reply = reply
    await bot.reply_to(555, morning=morning)
    assert client.sent == [] and client.read == []
    assert db.users[555]['pending_reply'] is True


@pytest.mark.parametrize('kind', ['photo', 'voice', 'generated_voice'])
async def test_tg_auto_media_checks_hours_after_preparation(kind, clock, monkeypatch):
    bot, db, llm, client, _ = build(user_row(), [{'role': 'user', 'content': 'hey'}], 'all good',
        behavior={'active_tz': 'America/Los_Angeles', 'active_start_min': 600, 'active_end_min': 1200})
    async def preparation(*args):
        clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
        return b'media'
    monkeypatch.setattr(userbot, '_download', preparation)
    monkeypatch.setattr(userbot, '_to_opus', preparation)
    monkeypatch.setattr(userbot.asyncio, 'sleep', AsyncMock())
    llm.charge_unit = AsyncMock()
    if kind == 'photo':
        await bot._send_photo(555, {'id': 1, 'url': 'https://example.test/p.jpg'})
    elif kind == 'voice':
        await bot._send_voice(555, {'id': 1, 'url': 'https://example.test/v.ogg', 'transcript': 'hey'})
    else:
        await bot._send_generated_voice(555, b'voice', 'hey')
    assert client.files == [] and client.sent == [] and client.read == []
    assert db.users[555]['pending_reply'] is True


@pytest.mark.parametrize('kind', ['thank', 'greet'])
async def test_fv_auto_proactive_outside_hours_is_deferred(kind, clock):
    clock.value = datetime(2026, 11, 16, 3, tzinfo=LA)
    a = fv_agent()
    settings = {'reply_mode': 'auto', 'active_start_min': 600, 'active_end_min': 1200}
    a._db.settings = AsyncMock(return_value=settings)
    a._db.behavior = AsyncMock(return_value={'active_tz': 'America/Los_Angeles'})
    try:
        if kind == 'thank':
            await a._thank(FAN, {'ai_enabled': True}, settings, 3099, 1)
        else:
            await a._greet({'payload': {'data': {'user': FAN}}}, settings)
    except Exception as exc:
        assert type(exc).__name__ == 'ReplyDeferred'
    assert a._api.sent == []
    assert a._db.patches == []


@pytest.mark.parametrize('kind', ['text', 'photo'])
async def test_fv_approved_send_outside_hours_is_allowed(kind, clock):
    clock.value = datetime(2026, 11, 16, 3, tzinfo=LA)
    a = fv_agent()
    a._db.settings = AsyncMock(return_value={'reply_mode': 'semi', 'active_start_min': 600, 'active_end_min': 1200})
    a._db.behavior = AsyncMock(return_value={'active_tz': 'America/Los_Angeles'})
    a._api.chat_messages = AsyncMock(return_value=[])
    if kind == 'text':
        assert await a.deliver_text(FAN['uuid'], 'approved')
    else:
        assert await a.deliver_photo(FAN['uuid'], 'media-1', 'approved')
    assert a._api.sent == ['approved']


@pytest.mark.parametrize('media', [None, ['voice-1']])
async def test_fv_automatic_send_boundary_defers_outside_hours(media, clock):
    clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
    a = fv_agent()
    a._db.settings = AsyncMock(return_value={'reply_mode': 'auto', 'active_start_min': 600, 'active_end_min': 1200})
    a._db.behavior = AsyncMock(return_value={'active_tz': 'America/Los_Angeles'})
    a._api.chat_messages = AsyncMock(return_value=[])
    try:
        await a._send_checked(FAN['uuid'], 'delayed reply', media, 0)
    except Exception as exc:
        assert type(exc).__name__ == 'ReplyDeferred'
    assert a._api.sent == []
    a._api.chat_messages.assert_not_awaited()


def shared_hub(block=None):
    return SimpleNamespace(can_reply=AsyncMock(return_value=True),
        restrictions=AsyncMock(return_value={}), day=AsyncMock(return_value=(block, '')))


async def test_tg_auto_shared_day_can_be_asleep_inside_active_window(clock):
    bot, db, _, client, _ = build(user_row(), [{'role': 'user', 'content': 'hey'}], 'hi',
        behavior={'active_tz': 'America/Los_Angeles', 'active_start_min': 0, 'active_end_min': 0})
    db.hub = shared_hub()
    assert await bot._auto_send_time_ok(555) is False
    assert db.users[555]['pending_reply'] is True


@pytest.mark.parametrize('shared_start,shared_end,block', [(600,1200,object()), (0,0,None)])
async def test_fv_shared_schedule_restricts_unlimited_channel_hours(shared_start, shared_end, block, clock):
    clock.value = datetime(2026, 11, 16, 3, tzinfo=LA)
    a = fv_agent()
    a._db.settings = AsyncMock(return_value={'reply_mode': 'auto', 'active_start_min': 0, 'active_end_min': 0})
    a._db.behavior = AsyncMock(return_value={'active_tz': 'America/Los_Angeles',
        'active_start_min': shared_start, 'active_end_min': shared_end})
    a._db.schedule = AsyncMock(return_value={})
    a._db.hub = shared_hub(block)
    try:
        await a._send_checked(FAN['uuid'], 'sleeping')
    except Exception as exc:
        assert type(exc).__name__ == 'ReplyDeferred'
    assert a._api.sent == []


class EventDb:
    def __init__(self, event, mode='auto'):
        self.event = dict(event)
        self.row = {'ai_enabled': True, 'tg_id': 555, 'spent_cents': 0, 'bought_count': 0}
        self.mode = mode
        self.messages = []
        self.payment_applications = 0

    async def settings(self):
        return {'enabled': True, 'reply_mode': self.mode, 'greet_new': True,
                'active_start_min': 600, 'active_end_min': 1200}
    async def behavior(self): return {'active_tz': 'America/Los_Angeles'}
    async def persona(self): return {'name': 'Simona'}
    async def history(self, uuid): return list(self.messages)
    async def fan(self, uuid): return dict(self.row)
    async def update_fan(self, uuid, patch): self.row.update(patch)
    async def update_user(self, tg_id, patch): pass
    async def get_user(self, tg_id): return None
    async def add_message(self, uuid, role, text, ref=''): self.messages.append({'role': role, 'content': text})
    async def control_bot_settings(self): return {}
    async def pending(self, limit=20, *, include_deferred=True):
        if self.event.get('processed_at') or (not include_deferred and self.event.get('reply_deferred')):
            return []
        return [dict(self.event)]
    async def pending_thanks(self, limit=20):
        return [{'fan_uuid': FAN['uuid']}] if self.row.get('pending_thanks') else []
    async def mark_handled(self, eid): self.event['processed_at'] = Clock.now(timezone.utc).isoformat()
    async def defer_event(self, eid): self.event['reply_deferred'] = True
    async def claim_event_notification(self, eid):
        if self.event.get('notified_at'): return False
        self.event['notified_at'] = Clock.now(timezone.utc).isoformat()
        return True
    async def record_payment_once(self, eid, uuid, cents):
        if not self.event.get('payment_recorded_at'):
            self.payment_applications += 1
            self.row.update(spent_cents=self.row['spent_cents'] + cents,
                bought_count=self.row['bought_count'] + 1, pending_offer_at=None)
            self.event['payment_recorded_at'] = Clock.now(timezone.utc).isoformat()
        return dict(self.row)


def event_agent(kind='payment', mode='auto'):
    typ = {'payment': 'creator.payment.succeeded', 'greet': 'creator.subscription.activated',
           'reply': 'creator.message.received'}[kind]
    event = {'id': 77, 'type': typ, 'payload': {'data': {'user': FAN, 'amount': 3099,
        'object': 'message', 'sender': 'fan', 'text': 'hey'}}, 'created_at': Clock.now(timezone.utc).isoformat()}
    a = fv_agent()
    a._db = EventDb(event, mode)
    notifications, cards = [], []
    async def notify(text): notifications.append(text)
    async def post_approval(**card): cards.append(card); return True
    a._control = SimpleNamespace(notify=notify, post_approval=post_approval)
    a._api.chat_messages = AsyncMock(return_value=[])
    a._situacia = AsyncMock(side_effect=lambda *args: SimpleNamespace(
        persona={}, behavior={}, teraz=Clock.now(LA), blok=None, kde='home', moment='',
        foto_ok=False, dlzi=False, pyta_fotku=False, pyta_ostre=False, prompt='persona', tip='', tah=None))
    a._voice = AsyncMock(return_value=None)
    a._remember = AsyncMock()
    return a, notifications, cards


@pytest.mark.parametrize('kind', ['payment', 'greet', 'reply'])
async def test_fv_night_event_survives_restart_and_sends_after_opening(kind, clock, monkeypatch):
    clock.value = datetime(2026, 11, 16, 3, tzinfo=LA)
    a, notifications, _ = event_agent(kind)
    monkeypatch.setattr(fa.random, 'random', lambda: 1)
    monkeypatch.setattr(fa.asyncio, 'sleep', AsyncMock())
    await a.tick()
    assert a._api.sent == []
    assert not a._db.event.get('processed_at')
    assert a._db.event.get('reply_deferred') is True
    notices = len(notifications)
    await a.tick()
    assert len(notifications) == notices
    # Recreate the agent, retaining only durable DB state and provider fake.
    resumed = fa.FanvueAgent(a._db, a._api, a._llm, a._control)
    resumed._situacia, resumed._voice, resumed._remember = a._situacia, a._voice, a._remember
    clock.value = datetime(2026, 11, 16, 13, tzinfo=LA)
    await resumed.tick()
    assert len(a._api.sent) == 1
    assert a._db.event.get('processed_at')
    assert len(notifications) == notices
    if kind == 'payment':
        assert a._db.row['spent_cents'] == 3099
        assert a._db.row['bought_count'] == 1
        assert a._db.payment_applications == 1


async def test_fv_payment_retry_after_window_closes_never_counts_purchase_twice(clock):
    a, notifications, _ = event_agent()
    original = a._llm.reply
    async def crosses_close(*args):
        clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
        return await original(*args)
    a._llm.reply = crosses_close
    await a.tick()
    assert a._api.sent == []
    assert not a._db.event.get('processed_at')
    assert a._db.row['spent_cents'] == 3099
    clock.value = datetime(2026, 11, 17, 13, tzinfo=LA)
    a._llm.reply = original
    await a.tick()
    assert a._db.row['spent_cents'] == 3099 and a._db.row['bought_count'] == 1
    assert len(a._api.sent) == 1 and len(notifications) == 1


async def test_fv_switching_deferred_event_to_semi_produces_card_at_night(clock):
    clock.value = datetime(2026, 11, 16, 3, tzinfo=LA)
    a, _, cards = event_agent('greet')
    await a.tick()
    assert not a._db.event.get('processed_at')
    a._db.mode = 'semi'
    await a.tick()
    assert len(cards) == 1 and a._api.sent == []
    assert a._db.event.get('processed_at')


async def test_tg_auto_rechecks_hours_after_read_receipt_await(clock):
    bot, db, _, client, _ = build(user_row(), [{'role': 'user', 'content': 'hey'}], 'all good',
        behavior={'active_tz': 'America/Los_Angeles', 'active_start_min': 600, 'active_end_min': 1200})
    original = client.send_read_acknowledge
    async def ack(*args):
        await original(*args)
        clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
    client.send_read_acknowledge = ack
    await bot.reply_to(555)
    assert client.sent == []
    assert db.users[555]['pending_reply'] is True


@pytest.mark.parametrize('channel', ['telegram', 'fanvue'])
async def test_automatic_reply_does_not_escape_when_mode_changes_to_semi(channel, clock):
    if channel == 'telegram':
        bot, db, llm, client, _ = build(user_row(), [{'role': 'user', 'content': 'hey'}], 'hi')
        async def reply(*args):
            db.reply_mode = 'semi'
            return 'hi'
        llm.reply = reply
        await bot.reply_to(555)
        assert client.sent == [] and client.read == []
        assert db.users[555]['pending_reply'] is True
    else:
        a, _, cards = event_agent('greet')
        async def reply(*args):
            a._db.mode = 'semi'
            return 'hi'
        a._llm.reply = reply
        await a.tick()
        assert a._api.sent == [] and not a._db.event.get('processed_at')
        await a.tick()
        assert len(cards) == 1 and a._db.event.get('processed_at')


@pytest.mark.parametrize('kind', ['text', 'photo', 'voice'])
async def test_tg_approved_send_respects_off_changed_during_read_receipt(kind, clock, monkeypatch):
    clock.value = datetime(2026, 11, 16, 3, tzinfo=LA)
    bot, db, llm, client, _ = telegram_semi()
    original = client.send_read_acknowledge
    async def ack(*args):
        await original(*args)
        db.reply_mode = 'off'
    client.send_read_acknowledge = ack
    db.photos = [{'id': 1, 'url': 'https://example.test/photo.jpg'}]
    monkeypatch.setattr(userbot, '_download', AsyncMock(return_value=b'media'))
    monkeypatch.setattr(userbot, '_to_opus', AsyncMock(return_value=b'voice'))
    monkeypatch.setattr(userbot.asyncio, 'sleep', AsyncMock())
    llm.charge_unit = AsyncMock()
    if kind == 'text': result = await bot.deliver_text('555', 'approved')
    elif kind == 'photo': result = await bot.deliver_photo('555', '1', 'approved')
    else: result = await bot.deliver_voice('555', 'approved', b'voice')
    assert result is False
    assert client.sent == [] and client.files == []


@pytest.mark.parametrize('kind', ['text', 'photo'])
async def test_fv_approved_send_respects_off_changed_during_read_receipt(kind, clock):
    a, _, _ = event_agent(mode='semi')
    async def ack(*args, **kwargs):
        a._db.mode = 'off'
        return []
    a._api.chat_messages = ack
    if kind == 'text': result = await a.deliver_text(FAN['uuid'], 'approved')
    else: result = await a.deliver_photo(FAN['uuid'], 'photo-1', 'approved')
    assert result is False and a._api.sent == []


@pytest.mark.parametrize('kind', ['photo', 'voice'])
@pytest.mark.parametrize('deferred', [True, False])
async def test_tg_media_only_reply_is_complete_only_after_delivery(kind, deferred, clock, monkeypatch):
    from test_reply_flow import TestJednoMediumNaOdpoved

    incoming = 'send me a pic' if kind == 'photo' else 'how was the gym today'
    bot, db, llm, client, _ = TestJednoMediumNaOdpoved._bot(incoming, monkeypatch)
    db.behavior.update(active_tz='America/Los_Angeles', active_start_min=600, active_end_min=1200)
    # A single stray letter is removed by the normal chunk filter; repeated
    # voice transcript is removed because the library recording says it.
    llm.reply_text = 'w' if kind == 'photo' else db.voices[0]['transcript']
    llm.charge_unit = AsyncMock()
    async def download(_url):
        if deferred:
            clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
        return b'media'
    monkeypatch.setattr(userbot, '_download', download)
    await bot.reply_to(555)
    assert client.sent == []
    assert bool(client.files) is not deferred
    assert db.users[555]['pending_reply'] is deferred
    assert bool(db.users[555].get('last_reply_at')) is not deferred


async def test_tg_text_then_deferred_voice_does_not_replay_text(clock, monkeypatch):
    from test_reply_flow import TestJednoMediumNaOdpoved

    bot, db, _, client, _ = TestJednoMediumNaOdpoved._bot('how was the gym today', monkeypatch)
    db.behavior.update(active_tz='America/Los_Angeles', active_start_min=600, active_end_min=1200)
    async def download(_url):
        clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
        return b'media'
    monkeypatch.setattr(userbot, '_download', download)
    await bot.reply_to(555)
    assert len(client.sent) == 1 and client.files == []
    assert db.users[555]['pending_reply'] is False
    clock.value = datetime(2026, 11, 17, 13, tzinfo=LA)
    await bot._sweep_once()
    assert len(client.sent) == 1 and client.files == []


@pytest.mark.parametrize('first_has_link', [True, False])
async def test_tg_partial_chunks_finalize_only_delivered_text(first_has_link, clock):
    link = 'https://fanvue.com/lucia'
    first, second = (link, 'talk tomorrow') if first_has_link else ('here it is', link)
    bot, db, _, client, _ = build(user_row(msg_count=16),
        [{'role': 'user', 'content': 'send me your link'}], f'{first}\n\n{second}',
        behavior={'active_tz': 'America/Los_Angeles', 'active_start_min': 600, 'active_end_min': 1200})
    original = client.send_message
    async def send(*args):
        await original(*args)
        clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
    client.send_message = send
    await bot.reply_to(555)
    assert len(client.sent) == 1
    assert db.users[555]['link_push_count'] == int(first_has_link)
    assert bool(db.users[555].get('link_sent_at')) is first_has_link
    assert db.users[555].get('last_reply_at')
    assert len(bot._reply_times) == 1
    assert db.users[555]['pending_reply'] is False
    clock.value = datetime(2026, 11, 17, 13, tzinfo=LA)
    await bot._sweep_once()
    assert len(client.sent) == 1


@pytest.mark.parametrize('resume_mode', ['auto', 'semi'])
async def test_fv_reconciled_purchase_thanks_survives_restart_without_webhook(resume_mode, clock):
    a, notices, cards = event_agent('reply')
    a._db.event['processed_at'] = Clock.now(timezone.utc).isoformat()
    a._db.known_message_uuids = AsyncMock(return_value=set())
    a._db.texty_bez_uuid = AsyncMock(return_value=set())
    a._db.add_messages = AsyncMock()
    fetched = [{'uuid': 'purchase-1', 'sender': {'uuid': 'creator-1'}, 'text': 'for you',
        'purchasedAt': '2026-11-16T18:00:00Z'}]
    a._api.chat_messages = AsyncMock(return_value=fetched)
    original = a._llm.reply
    async def closes_during_thanks(*args):
        clock.value = datetime(2026, 11, 16, 20, 1, tzinfo=LA)
        return await original(*args)
    a._llm.reply = closes_during_thanks
    with pytest.raises(fa.ReplyDeferred):
        await a._reconcile({**FAN, 'text': 'hey'}, dict(a._db.row))
    assert a._db.row['bought_count'] == 1
    assert a._api.sent == []
    # No new webhook is required: only the durable fan row survives restart.
    a._llm.reply = original
    a._db.mode = resume_mode
    resumed = fa.FanvueAgent(a._db, a._api, a._llm, a._control)
    clock.value = datetime(2026, 11, 17, 13 if resume_mode == 'auto' else 3, tzinfo=LA)
    await resumed.tick()
    assert len(a._api.sent) == int(resume_mode == 'auto')
    assert len(cards) == int(resume_mode == 'semi')
    assert a._db.row.get('pending_thanks') is False
    assert a._db.row['bought_count'] == 1 and a._db.payment_applications == 0
    assert notices == []
    await resumed.tick()
    assert len(a._api.sent) + len(cards) == 1


async def test_fv_pending_thanks_kept_when_off_changes_during_receipt(clock):
    a, notices, _ = event_agent('reply')
    a._db.event['processed_at'] = Clock.now(timezone.utc).isoformat()
    a._db.row.update(pending_thanks=True, bought_count=1)
    async def ack(*args, **kwargs):
        a._db.mode = 'off'
        return []
    a._api.chat_messages = ack
    await a.tick()
    assert a._api.sent == [] and a._db.row['pending_thanks'] is True
    a._db.mode = 'auto'
    a._api.chat_messages = AsyncMock(return_value=[])
    await a.tick()
    assert len(a._api.sent) == 1 and a._db.row['pending_thanks'] is False
    assert notices == []
