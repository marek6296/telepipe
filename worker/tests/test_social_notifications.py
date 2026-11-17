"""The control bot is an inbox doorbell, never a second reply surface."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon import events
from telethon.tl import types

from control_bot import ControlBot


def notification_bot(owner=42):
    cfg = SimpleNamespace(owner_chat_id=owner, model_id='model-1', name='Model')
    db = SimpleNamespace(supersede_open=AsyncMock(return_value=[]),
                         create_pending=AsyncMock(return_value={'id': 'pending-1'}),
                         pair_control_bot=AsyncMock(return_value=True))
    client = SimpleNamespace(send_message=AsyncMock())
    return ControlBot(cfg, db, client, notifications_only=True), db, client


async def test_paired_notifications_bot_keeps_proposals_headless():
    bot, db, client = notification_bot()
    assert await bot.post_approval(channel='telegram', conv_key='555', display_name='Fan',
                                   incoming_preview='Hi', suggestions=['Hello'])
    db.create_pending.assert_awaited_once()
    client.send_message.assert_not_awaited()


async def test_generic_startup_and_old_alerts_are_quiet():
    bot, _, client = notification_bot()
    await bot.notify('AI replying is live', buttons=[['legacy']])
    client.send_message.assert_not_awaited()


@pytest.mark.parametrize('text', ['/start', '/menu', '/den', '/reset'])
async def test_old_commands_only_open_web_and_remove_old_keyboard(text):
    bot, _, client = notification_bot()
    bot._send_main = AsyncMock()
    event = SimpleNamespace(chat_id=42, raw_text=text, reply=AsyncMock())
    with pytest.raises(events.StopPropagation):
        await bot._on_command(event)
    assert 'inside Telegram' in event.reply.await_args.args[0]
    assert isinstance(event.reply.await_args.kwargs['buttons'], types.ReplyKeyboardHide)
    bot._send_main.assert_not_awaited()
    client.send_message.assert_not_awaited()


async def test_old_callback_cannot_approve_or_change_mode():
    bot, _, _ = notification_bot()
    bot._route = AsyncMock()
    event = SimpleNamespace(chat_id=42, data=b'ap:0', answer=AsyncMock())
    await bot._on_callback(event)
    bot._route.assert_not_awaited()
    assert 'Social sites' in event.answer.await_args.args[0]


async def test_old_freeform_reply_cannot_send_to_fan():
    bot, _, _ = notification_bot()
    bot._awaiting[42] = ('semi_custom', '123')
    sender = SimpleNamespace(deliver_text=AsyncMock())
    bot.register_sender('telegram', sender)
    event = SimpleNamespace(chat_id=42, raw_text='send this', reply=AsyncMock())
    await bot._on_value(event)
    assert 'inside Telegram' in event.reply.await_args.args[0]
    sender.deliver_text.assert_not_awaited()


async def test_pairing_still_works_without_menu():
    bot, db, _ = notification_bot(owner=0)
    bot._send_main = AsyncMock()
    event = SimpleNamespace(chat_id=42, raw_text='TP-4F9K2X', is_private=True, reply=AsyncMock())
    assert await bot._try_pair(event)
    assert bot._cfg.owner_chat_id == 42
    assert 'inside Telegram' in event.reply.await_args.args[0]
    bot._send_main.assert_not_awaited()


async def test_unknown_person_cannot_open_owner_inbox():
    bot, _, _ = notification_bot()
    event = SimpleNamespace(chat_id=99, data=b'ap:0', answer=AsyncMock())
    await bot._on_callback(event)
    event.answer.assert_not_awaited()


def inbound(**patch):
    return {'id': 'batch-1', 'channel': 'instagram', 'external_id': '12345',
            'owner_chat_id': 42,
            'account_scope': 'ig-account', 'display_name': 'Fan _name_',
            'preview': 'First line\nsecond line', 'message_count': 3, **patch}


async def test_durable_claim_consumes_before_single_send_across_worker_restarts():
    from social_notifications import SocialNotifications
    bot, _, client = notification_bot()
    queued = [inbound()]
    async def claim(name, args):
        assert name == 'social_notification_claim'
        assert args == {'p_model': 'model-1', 'p_worker': 'replica'}
        return queued.pop() if queued else None
    transport = SimpleNamespace(_rpc=AsyncMock(side_effect=claim))
    await SocialNotifications(transport, 'model-1', 'replica', bot).tick()
    await SocialNotifications(transport, 'model-1', 'replica', bot).tick()
    client.send_message.assert_awaited_once()
    call = client.send_message.await_args
    assert call.args == (42, 'Instagram · Fan _name_\n3 new messages\nFirst line second line')
    assert call.kwargs['parse_mode'] is None
    assert call.kwargs['buttons'][0][0].url == 'https://telepipe.me/mini?bot=model-1&contact=instagram%3A12345'
    assert isinstance(call.kwargs['buttons'][0][0], types.KeyboardButtonWebView)


async def test_uncertain_notification_send_is_not_requeued():
    from social_notifications import SocialNotifications
    bot, _, client = notification_bot()
    client.send_message.side_effect = TimeoutError('response lost')
    transport = SimpleNamespace(_rpc=AsyncMock(side_effect=[inbound(), None]))
    notifications = SocialNotifications(transport, 'model-1', 'replica', bot)
    with pytest.raises(TimeoutError):
        await notifications.tick()
    await notifications.tick()
    client.send_message.assert_awaited_once()
    assert all(c.args[0] == 'social_notification_claim' for c in transport._rpc.await_args_list)


@pytest.mark.parametrize('owner,bot_ready', [(0, True), (42, False)])
async def test_unpaired_or_disconnected_bot_does_not_consume_alerts(owner, bot_ready):
    from social_notifications import SocialNotifications
    bot, _, _ = notification_bot(owner)
    bot._mirror_enabled = bot_ready
    transport = SimpleNamespace(_rpc=AsyncMock())
    await SocialNotifications(transport, 'model-1', 'replica', bot).tick()
    transport._rpc.assert_not_awaited()


async def test_auto_or_stale_batch_filtered_by_database_does_not_send():
    from social_notifications import SocialNotifications
    bot, _, client = notification_bot()
    transport = SimpleNamespace(_rpc=AsyncMock(return_value=None))
    await SocialNotifications(transport, 'model-1', 'replica', bot).tick()
    client.send_message.assert_not_awaited()


@pytest.mark.parametrize('owner', [None, 99])
async def test_stale_paired_owner_never_receives_new_owners_inbox(owner):
    bot, _, client = notification_bot()
    await bot.notify_inbound(inbound(owner_chat_id=owner))
    client.send_message.assert_not_awaited()


def test_notification_is_compact_plain_text_and_link_encodes_contact():
    from social_notifications import notification_text, social_url
    text = notification_text(inbound(display_name='x' * 200, preview='z' * 300))
    assert len(text) < 300
    assert social_url('m', 'fanvue', 'fan:?x=1&z=2') == (
        'https://telepipe.me/app/m/m/social?contact=fanvue%3Afan%3A%3Fx%3D1%26z%3D2')


@pytest.mark.parametrize('enabled,mode', [(False, 'auto'), (True, 'off')])
@pytest.mark.parametrize('text', ['hello', ''])
@pytest.mark.parametrize('trailing_payment', [False, True])
async def test_manual_fanvue_ingests_without_seen_ai_feed_or_send(enabled, mode, text, trailing_payment, monkeypatch):
    from fanvue_agent import FanvueAgent
    import fanvue_agent
    event = {'id': 1, 'type': 'creator.message.received', 'payload': {'data': {
        'object': 'message', 'sender': 'fan', 'text': text, 'hasMedia': not text,
        'user': {'uuid': 'fan-1'}}}}
    pending = [event] + ([{'id': 2, 'type': 'creator.payment.succeeded', 'payload': {}}] if trailing_payment else [])
    db = SimpleNamespace(settings=AsyncMock(return_value={'enabled': enabled, 'reply_mode': mode}),
                         pending=AsyncMock(return_value=pending),
                         control_bot_settings=AsyncMock(return_value={}),
                         claim_event_notification=AsyncMock(return_value=True),
                         mark_handled=AsyncMock())
    agent = FanvueAgent(db, SimpleNamespace(), SimpleNamespace())
    agent._ensure_fan = AsyncMock(return_value={})
    agent._reconcile = AsyncMock(return_value=True)
    agent._dispatch = AsyncMock()
    agent._post_to_feed = AsyncMock()
    agent._retry_pending_thanks = AsyncMock()
    monkeypatch.setattr(fanvue_agent.fvmedia, 'due_to_post', lambda *a: True)
    await agent.tick()
    agent._reconcile.assert_awaited_once()
    assert agent._reconcile.await_args.kwargs == {'mark_read': False, 'sync_only': True}
    assert not any(c.args[0] == event for c in agent._dispatch.await_args_list)
    agent._post_to_feed.assert_not_awaited()
    agent._retry_pending_thanks.assert_not_awaited()
    db.mark_handled.assert_any_await(1)


async def test_fanvue_takeover_still_imports_inbound_without_thanks_or_seen():
    from fanvue_agent import FanvueAgent
    event = {'type': 'creator.message.received', 'payload': {'data': {
        'sender': 'fan', 'text': 'hello', 'user': {'uuid': 'fan-1'}}}}
    agent = FanvueAgent(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
    agent._ensure_fan = AsyncMock(return_value={'human_takeover': True})
    agent._reconcile = AsyncMock(return_value=True)
    await agent._reply(event, {'enabled': True, 'reply_mode': 'auto'})
    assert agent._reconcile.await_args.kwargs == {'mark_read': False, 'sync_only': True}


async def test_fanvue_failed_inbox_import_keeps_event_for_retry():
    from fanvue_agent import FanvueAgent
    event = {'id': 1, 'type': 'creator.message.received', 'payload': {'data': {
        'sender': 'fan', 'text': 'hello', 'user': {'uuid': 'fan-1'}}}}
    db = SimpleNamespace(settings=AsyncMock(return_value={'enabled': False, 'reply_mode': 'off'}),
                         pending=AsyncMock(return_value=[event]),
                         control_bot_settings=AsyncMock(return_value={}),
                         claim_event_notification=AsyncMock(return_value=True),
                         mark_handled=AsyncMock())
    agent = FanvueAgent(db, SimpleNamespace(), SimpleNamespace())
    agent._ensure_fan = AsyncMock(return_value={})
    agent._reconcile = AsyncMock(side_effect=TimeoutError('read failed'))
    await agent.tick()
    db.mark_handled.assert_not_awaited()


async def test_fanvue_webhook_fallback_keeps_provider_time_and_dedupes_uuid():
    from fanvue_agent import FanvueAgent, fan_of
    event = {'payload': {'data': {'user': {'uuid': 'fan-1'}, 'uuid': 'message-1',
                                 'text': 'hello', 'sentAt': '2026-11-16T19:00:00Z'}}}
    db = SimpleNamespace(settings=AsyncMock(return_value={'creator_uuid': 'creator'}),
                         known_message_uuids=AsyncMock(side_effect=[set(), {'message-1'}]),
                         add_messages=AsyncMock(), add_message=AsyncMock())
    api = SimpleNamespace(chat_messages=AsyncMock(return_value=[]))
    agent = FanvueAgent(db, api, SimpleNamespace())
    for _ in range(2):
        await agent._reconcile(fan_of(event), {}, mark_read=False, sync_only=True)
    db.add_messages.assert_awaited_once_with('fan-1', [{
        'message_uuid': 'message-1', 'role': 'user', 'content': 'hello',
        'occurred_at': '2026-11-16T19:00:00+00:00',
    }])
    db.add_message.assert_not_awaited()
    assert all(c.kwargs['mark_read'] is False for c in api.chat_messages.await_args_list)


@pytest.mark.parametrize('sent_at', [None, 'bad', '2026-11-16T19:00:00'])
def test_unknown_fanvue_message_time_is_not_replaced_with_import_time(sent_at):
    from fanvue_agent import fan_of
    fan = fan_of({'created_at': '2026-11-16T19:01:00Z', 'payload': {'data': {
        'user': {'uuid': 'fan-1'}, 'uuid': 'message-1', 'sentAt': sent_at}}})
    assert '_occurred_at' not in fan


async def test_obsolete_generation_cannot_close_a_newer_web_proposal():
    bot, db, client = notification_bot()
    # SQL rejects an obsolete source; Python must not have superseded the
    # current proposal before the atomic insert guard makes that decision.
    db.create_pending.return_value = None
    assert not await bot.post_approval(channel='telegram', conv_key='555', display_name='Fan',
                                       incoming_preview='old input', suggestions=['old reply'],
                                       source_message_id=12)
    db.supersede_open.assert_not_awaited()
    assert db.create_pending.await_args.kwargs['source_message_id'] == 12
    client.send_message.assert_not_awaited()
