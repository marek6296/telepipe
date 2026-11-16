from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from conversation_policy import opt_out
from fanvue_agent import FanvueAgent


@pytest.mark.parametrize('text,expected', [("don't message me", 'contact'), ('don’t send links', 'links'), ("don't send links", 'links')])
def test_contracted_opt_out(text, expected):
    assert opt_out(text) == expected


@pytest.mark.asyncio
async def test_attribution_formatter_cannot_mark_nonpayment_as_paid():
    db = AsyncMock()
    db.hub.linked.return_value = [{'external_id': '42'}]
    db.get_user.return_value = {'first_name': 'Roberto', 'tg_id': 42}
    agent = FanvueAgent(db, AsyncMock(), AsyncMock())
    result = await agent._z_telegramu({'type': 'creator.post.liked'}, {'uuid': 'fan'})
    db.update_user.assert_not_called()
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_payment_does_not_trust_legacy_heuristic_tg_id():
    db = AsyncMock()
    db.hub.linked.return_value = []
    db.fan.return_value = {'tg_id': 42}
    agent = FanvueAgent(db, AsyncMock(), AsyncMock())
    await agent._oznac_zaplateneho({}, {'uuid': 'fan'})
    db.update_user.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['text', 'photo'])
async def test_fanvue_approval_respects_current_shared_stop(kind):
    db, api = AsyncMock(), AsyncMock()
    db.hub.can_reply.return_value = False
    db.hub.restrictions.return_value = {'no_initiate': True, 'no_links': True}
    db.settings.return_value = {'reply_mode': 'auto'}
    db.fan.return_value = {'msg_count': 1}
    api.send.return_value = 'sent'
    agent = FanvueAgent(db, api, AsyncMock())
    agent._dobehni = AsyncMock()
    if kind == 'text':
        result = await agent.deliver_text('fan', 'old approved reply')
    else:
        result = await agent.deliver_photo('fan', 'photo', 'old caption')
    assert result is False
    api.send.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_approval_respects_current_shared_stop(monkeypatch):
    from userbot import UserBot
    import humanize
    monkeypatch.setattr(humanize, 'typing_delay', lambda text: 0)
    bot = object.__new__(UserBot)
    bot._db = AsyncMock()
    bot._db.hub.can_reply.return_value = False
    bot._db.hub.restrictions.return_value = {'no_initiate': True}
    bot._client = MagicMock()
    bot._client.send_message = AsyncMock()
    bot._reply_times = []
    bot._semi_post_update = AsyncMock()
    assert await bot.deliver_text('42', 'old approved reply') is False
    bot._client.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_known_manual_mid_retries_effects_after_import_crash():
    from instagram_delivery import InstagramDelivery
    from test_instagram_delivery import thread, settings
    now = datetime.now(timezone.utc)
    db = AsyncMock(model_id='model')
    db.ensure_user.return_value = {}
    db.known_mids.return_value = {'outbound'}
    db.actions.return_value = []
    await InstagramDelivery(db, AsyncMock()).ingest(thread(now, 'assistant', 'outbound'), settings(sync_completed_at=(now-timedelta(hours=1)).isoformat()))
    assert any(c.args == ('record_manual',) for c in db.rpc.call_args_list)
    db.cancel_actions.assert_any_await('fan', 'manual_reply')


@pytest.mark.asyncio
async def test_deferred_photo_is_not_sent_after_age_conflict(monkeypatch):
    from test_instagram_kolo import FakeDb, FakeLlm, mock_threads
    from test_instagram_delivery import thread
    from instagram_agent import InstagramAgent
    import instagram_api as api
    now = datetime.now(timezone.utc)
    db = FakeDb(photos_enabled=True)
    db.sfw_photo = AsyncMock(return_value={'id': 1, 'url': 'https://example.test/sfw.jpg'})
    agent = InstagramAgent(db, FakeLlm())
    agent._napis = AsyncMock(side_effect=['[[PHOTO]]', 'sure lets talk'])
    mock_threads(monkeypatch, [thread(now)])
    await agent._delivery.ingest(thread(now), db.nastavenia)
    db.queue['1']['due_at'] = (now-timedelta(minutes=1)).isoformat()
    original = db.rpc
    reservations = []
    async def rpc(name, **kw):
        if name == 'reserve':
            reservations.append(kw)
            if len(reservations) == 1:
                db.queue['1']['state'] = 'pending'
                return {'ok': False, 'reason': 'quota'}
        return await original(name, **kw)
    db.rpc = rpc
    sent = []
    monkeypatch.setattr(api, 'send_photo', lambda *a, **k: sent.append(1) or {'message_id': 'photo'})
    monkeypatch.setattr(api, 'posli_text', lambda *a, **k: {'message_id': 'text'})
    await agent._delivery.process_one(db.nastavenia)
    db.hub.restrictions.return_value = {'age_state': 'minor_or_conflicting'}
    await agent._delivery.process_one(db.nastavenia)
    assert sent == []


def test_reactive_return_is_distinct_from_marketing_opt_in():
    from conversation_policy import direct_request, reactive_opt_in
    assert direct_request('how are you doing?')
    assert not direct_request('dont message me again')
    assert reactive_opt_in('you can reply to me again')
    assert reactive_opt_in('uz mi mozes normalne odpisovat')


@pytest.mark.asyncio
async def test_approved_instagram_text_never_gets_an_added_typo(monkeypatch):
    from test_instagram_kolo import FakeDb, FakeLlm, mock_threads
    from test_instagram_delivery import thread
    from instagram_agent import InstagramAgent
    import instagram_api as api
    now = datetime.now(timezone.utc)
    db = FakeDb(typo_enabled=True)
    agent = InstagramAgent(db, FakeLlm())
    mock_threads(monkeypatch, [thread(now)])
    await agent._delivery.ingest(thread(now), db.nastavenia)
    action = db.queue['1']
    action['due_at'] = (now-timedelta(minutes=1)).isoformat()
    action['payload']['approved_source_mid'] = action['source_mid']
    action['text'] = 'really thanks'
    def unexpected(*args):
        raise AssertionError('approved content must not be changed')
    monkeypatch.setattr('instagram_interactions.small_typo', unexpected)
    sent = []
    monkeypatch.setattr(api, 'posli_text', lambda token, who, text, **k: sent.append(text) or {'message_id': 'sent'})
    await agent._delivery.process_one(db.nastavenia)
    assert sent == ['really thanks']
