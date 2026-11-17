"""The web queue uses only a live tenant's senders; provider outcomes never guess."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from social_commands import DeliveryResult, SocialCommands


def command(**patch):
    result = {**dict(id='c1', model_id='model', operation='send_text', channel='telegram',
                external_id='555', account_scope='primary', text='exact owner text',
                lease_token='lease', status='working'), **patch}
    if result['operation'] == 'approve' and 'expected_suggestions' not in result:
        result['expected_suggestions'] = [result['text']]
    return result


def setup(job=None):
    job = job or command()
    async def rpc(name, args):
        if name == 'social_claim':
            return job
        if name == 'social_start_send':
            return {**job, 'status': 'sending'}
        return True
    transport = SimpleNamespace(_rpc=AsyncMock(side_effect=rpc), _get=AsyncMock(return_value=[{'conv_key':job['external_id'],'suggestions':job.get('expected_suggestions')}]))
    control = SimpleNamespace(_senders={}, sync_social_cards=AsyncMock())
    dispatcher = SocialCommands(transport, 'model', 'replica', control)
    return dispatcher, transport, control


async def test_command_uses_live_sender_and_fences_at_external_boundary():
    dispatcher, transport, control = setup()
    async def deliver(job, before_send):
        assert await before_send()
        return DeliveryResult.sent('provider-1')
    sender = SimpleNamespace(deliver_operator=AsyncMock(side_effect=deliver))
    control._senders['telegram'] = sender
    await dispatcher.tick()
    sender.deliver_operator.assert_awaited_once()
    calls = transport._rpc.await_args_list
    assert calls[0].args == ('social_claim', {'p_model': 'model', 'p_worker': 'replica'})
    assert calls[-1].args[1]['p_status'] == 'done'
    assert calls[-1].args[1]['p_result']['provider_message_id'] == 'provider-1'


async def test_missing_sender_is_a_safe_failure_without_claiming_draft():
    dispatcher, transport, _ = setup()
    await dispatcher.tick()
    assert [c.args[0] for c in transport._rpc.await_args_list] == ['social_claim', 'social_finish']
    assert transport._rpc.await_args.args[1]['p_result']['safe_to_retry'] is True


async def test_provider_exception_after_send_boundary_becomes_uncertain():
    dispatcher, transport, control = setup()
    async def deliver(job, before_send):
        assert await before_send()
        raise TimeoutError('response lost')
    control._senders['telegram'] = SimpleNamespace(deliver_operator=deliver)
    await dispatcher.tick()
    assert transport._rpc.await_args.args[1]['p_status'] == 'uncertain'
    assert not transport._rpc.await_args.args[1]['p_result'].get('safe_to_retry')


async def test_stale_start_send_never_calls_provider():
    dispatcher, transport, control = setup()
    transport._rpc.side_effect = [command(), None, True]
    provider = AsyncMock()
    async def deliver(job, before_send):
        if not await before_send():
            return DeliveryResult.blocked('stale_context')
        await provider()
        return DeliveryResult.sent('x')
    control._senders['telegram'] = SimpleNamespace(deliver_operator=deliver)
    await dispatcher.tick()
    provider.assert_not_awaited()


async def test_regenerate_replaces_only_original_proposal_array():
    job = command(operation='regenerate', pending_id='p1', expected_suggestions=['old'], brief='be kind')
    dispatcher, transport, control = setup(job)
    control._senders['telegram'] = SimpleNamespace(regenerate=AsyncMock(return_value={'suggestions': ['new']}))
    await dispatcher.tick()
    replace = next(c.args[1] for c in transport._rpc.await_args_list if c.args[0] == 'social_replace_suggestions')
    assert replace['p_expected'] == ['old']
    assert replace['p_suggestions'] == ['new']
    assert not any(c.args[0] == 'social_start_send' for c in transport._rpc.await_args_list)


async def test_headless_approval_keeps_durable_draft_without_telegram_write():
    from control_bot import ControlBot
    cfg = SimpleNamespace(owner_chat_id=0, model_id='model', name='Model')
    db = SimpleNamespace(supersede_open=AsyncMock(return_value=[]),
                         create_pending=AsyncMock(return_value={'id': 'p1'}))
    client = SimpleNamespace(send_message=AsyncMock())
    bot = ControlBot(cfg, db, client)
    bot._mirror_enabled = False
    assert await bot.post_approval(channel='telegram', conv_key='555', display_name='Fan',
                                   incoming_preview='hello', suggestions=['hey'])
    db.create_pending.assert_awaited_once()
    client.send_message.assert_not_awaited()


async def test_tg_operator_manual_takeover_keeps_flood_and_budget_guards(monkeypatch):
    from test_reply_flow import build, user_row
    bot, db, _, client, _ = build(user_row(human_takeover=True), [{'role': 'user', 'content': 'hey'}], 'unused')
    db.tg_reply_mode = AsyncMock(return_value={'mode': 'off'})
    bot._flood_ok = AsyncMock(return_value=False)
    before = AsyncMock(return_value=True)
    result = await bot.deliver_operator(command(), before)
    assert result.status == 'blocked'
    assert client.sent == [] and client.read == []
    before.assert_not_awaited()


@pytest.mark.usefixtures('fast')
async def test_tg_operator_can_send_exact_text_while_manual_and_taken_over(monkeypatch):
    from test_reply_flow import build, user_row
    bot, db, _, client, _ = build(user_row(human_takeover=True), [{'role': 'user', 'content': 'hey'}], 'unused')
    db.tg_reply_mode = AsyncMock(return_value={'mode': 'off'})
    bot._flood_ok = AsyncMock(return_value=True)
    bot._rate_ok = AsyncMock(return_value=True)
    bot._denny_strop_ok = AsyncMock(return_value=True)
    bot._semi_post_update = AsyncMock()
    client.send_message = AsyncMock(return_value=SimpleNamespace(id=123))
    import operator_delivery
    client.send_read_acknowledge = AsyncMock()
    async def pause(text):
        assert client.send_read_acknowledge.await_count == 1
        client.send_message.assert_not_awaited()
    monkeypatch.setattr(operator_delivery,'composition_pause',AsyncMock(side_effect=pause))
    result = await bot.deliver_operator(command(), AsyncMock(return_value=True))
    assert result.status == 'done'
    client.send_message.assert_awaited_once_with(555, 'exact owner text', parse_mode=None)


async def test_fanvue_operator_send_does_not_treat_timeout_as_rejection():
    import httpx
    from fanvue_api import Fanvue
    api = Fanvue.__new__(Fanvue)
    api._headers = AsyncMock(return_value={})
    api._client = SimpleNamespace(post=AsyncMock(side_effect=httpx.ReadTimeout('lost')))
    result = await api.send_operator('fan', 'text')
    assert result.status == 'uncertain'


@pytest.mark.parametrize('code,expected', [(302, 'uncertain'), (400, 'blocked'), (429, 'blocked'), (500, 'uncertain')])
async def test_fanvue_operator_classifies_response(code, expected):
    import httpx
    from fanvue_api import Fanvue
    api = Fanvue.__new__(Fanvue)
    api._headers = AsyncMock(return_value={})
    api._client = SimpleNamespace(post=AsyncMock(return_value=httpx.Response(code)))
    result = await api.send_operator('fan', 'text')
    assert result.status == expected


async def test_fanvue_operator_uses_current_credentials_after_reconnect():
    import httpx
    from datetime import datetime, timedelta, timezone
    from fanvue_api import Fanvue
    api = Fanvue.__new__(Fanvue)
    api._token = 'old-test-token'
    api._expires = datetime.now(timezone.utc) + timedelta(hours=1)
    api._db = SimpleNamespace(settings=AsyncMock(return_value={'connected': True,
        'access_token': 'new-test-token', 'expires_at': api._expires.isoformat()}))
    api._client = SimpleNamespace(post=AsyncMock(return_value=httpx.Response(200, json={'uuid': 'sent'})))
    result = await api.send_operator('fan', 'text')
    assert result.status == 'done'
    assert api._client.post.await_args.kwargs['headers']['Authorization'] == 'Bearer new-test-token'


async def test_fanvue_operator_refences_after_slow_auth_before_send():
    from fanvue_api import Fanvue
    api = Fanvue.__new__(Fanvue)
    api._headers = AsyncMock(return_value={})
    api._client = SimpleNamespace(post=AsyncMock())
    result = await api.send_operator('fan', 'text', before_send=AsyncMock(return_value=False))
    assert result.status == 'blocked'
    api._client.post.assert_not_awaited()


@pytest.mark.parametrize('gate,reason', [('_rate_ok', 'hourly_limit'), ('_denny_strop_ok', 'daily_limit')])
async def test_tg_operator_quota_blocks_before_seen(gate, reason):
    from test_reply_flow import build, user_row
    bot, db, _, client, _ = build(user_row(), [{'role': 'user', 'content': 'hey'}], 'unused')
    bot._flood_ok = AsyncMock(return_value=True)
    bot._rate_ok = AsyncMock(return_value=True)
    bot._denny_strop_ok = AsyncMock(return_value=True)
    setattr(bot, gate, AsyncMock(return_value=False))
    result = await bot.deliver_operator(command(), AsyncMock(return_value=True))
    assert result.status == 'blocked' and result.reason == reason
    assert client.sent == [] and client.read == []


async def test_tg_operator_never_uses_old_client_after_account_reconnect():
    from test_reply_flow import build, user_row
    bot, db, _, client, _ = build(user_row(), [{'role': 'user', 'content': 'hey'}], 'unused')
    bot._cfg = SimpleNamespace(**{**vars(bot._cfg), 'tg_account_scope': 'telegram:original-client'})
    before = AsyncMock(return_value=True)  # DB now describes the newly connected account.
    result = await bot.deliver_operator(command(account_scope='telegram:new-client'), before)
    assert result.status == 'blocked' and result.reason == 'telegram_account_changed'
    assert client.sent == [] and client.read == []
    before.assert_not_awaited()


@pytest.mark.parametrize('mode', ['off', 'semi', 'auto'])
async def test_fv_manual_sender_preserves_exact_text_and_takeover(mode):
    from fanvue_agent import FanvueAgent
    db = SimpleNamespace(settings=AsyncMock(return_value={'connected': True, 'reply_mode': mode, 'creator_uuid': 'creator'}),
                         fan=AsyncMock(return_value={'human_takeover': True}),
                         update_fan=AsyncMock(), add_message=AsyncMock())
    api = SimpleNamespace(chat_messages=AsyncMock(return_value=[]),
                          send_operator=AsyncMock(return_value=DeliveryResult.sent('fv-message')))
    agent = FanvueAgent(db, api, None)
    agent._reconcile = AsyncMock(return_value=True)
    result = await agent.deliver_operator(command(channel='fanvue', external_id='fan', account_scope='fanvue:creator'), AsyncMock(return_value=True))
    assert result.status == 'done'
    assert api.send_operator.await_args.args == ('fan', 'exact owner text')
    assert callable(api.send_operator.await_args.kwargs['before_send'])
    assert all(call.kwargs.get('mark_read') is False for call in agent._reconcile.await_args_list)
    assert not any(call.args[1].get('human_takeover') is False for call in db.update_fan.await_args_list)


async def test_fv_stale_source_does_not_mark_seen():
    from fanvue_agent import FanvueAgent
    db = SimpleNamespace(settings=AsyncMock(return_value={'connected': True}), fan=AsyncMock(return_value={}))
    api = SimpleNamespace(chat_messages=AsyncMock(), send_operator=AsyncMock())
    agent = FanvueAgent(db, api, None)
    db.fan.return_value = {'fan_uuid': 'fan'}
    agent._reconcile = AsyncMock(return_value=True)
    result = await agent.deliver_operator(command(channel='fanvue', external_id='fan'), AsyncMock(return_value=False))
    assert result.status == 'blocked'
    api.chat_messages.assert_not_awaited()
    api.send_operator.assert_not_awaited()


async def test_dispatcher_cancellation_does_not_finish_or_retry_inflight_send():
    import asyncio
    dispatcher, transport, control = setup()
    reached = asyncio.Event()
    async def deliver(job, before_send):
        await before_send()
        reached.set()
        await asyncio.Event().wait()
    control._senders['telegram'] = SimpleNamespace(deliver_operator=deliver)
    task = asyncio.create_task(dispatcher.tick())
    await reached.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not any(c.args[0] == 'social_finish' for c in transport._rpc.await_args_list)


async def test_bot_skip_does_not_overwrite_web_claim():
    from test_active_chats import bot, row, Event
    b = bot([row(1)])
    b._db.skip_pending_version = AsyncMock(return_value=False)
    event = Event(1)
    await b._route_approval(event, 'as', '')
    assert b._db.rows['p1']['status'] == 'awaiting'
    b._db.skip_pending_version.assert_awaited_once_with('p1', ['reply 1'])
    event.edit.assert_not_awaited()


async def test_bot_regenerate_rejects_concurrent_array_change():
    from test_active_chats import bot, row
    original = row(1)
    b = bot([original])
    b._senders['instagram'].regenerate = AsyncMock(return_value={'suggestions': ['new']})
    b._db.compare_and_replace_suggestions = AsyncMock(return_value=False)
    message = await b._new_suggestions(1, 'p1', original)
    assert 'changed' in message
    assert b._db.rows['p1']['suggestions'] == ['reply 1']
    b._db.compare_and_replace_suggestions.assert_awaited_once_with('p1', ['reply 1'], ['new'], '')


async def test_slow_telegram_mirror_cannot_resurrect_web_sent_draft():
    from test_active_chats import bot, row
    b = bot([])
    created = row(1, channel='telegram')
    created['control_msg_id'] = None
    async def create(**kwargs):
        b._db.rows['p1'] = created
        return dict(created)
    async def suspended_mirror(*args, **kwargs):
        # The web claimed and delivered while Telegram was sending the mirror.
        b._db.rows['p1'].update(status='sent', decision_command_id='web-command', chosen_text='reply 1')
        return SimpleNamespace(id=100)
    b._db.create_pending = AsyncMock(side_effect=create)
    b._db.supersede_open = AsyncMock(return_value=[])
    b._client.send_message = AsyncMock(side_effect=suspended_mirror)
    assert await b.post_approval(channel='telegram', conv_key='1', display_name='Fan',
                                 incoming_preview='hi', suggestions=['reply 1'])
    assert b._db.rows['p1']['status'] == 'sent'
    assert 100 not in b._cards
    assert b._db.rows['p1']['control_msg_id'] is None

async def test_instagram_say_this_uses_exact_pending_conversation_key():
    job=command(operation='regenerate',channel='instagram',external_id='fan',account_scope='ig-account',pending_id='pending',expected_suggestions=['old'],brief='say you enjoyed the walk')
    dispatcher,t,control=setup(job)
    t._get=AsyncMock(return_value=[{'conv_key':'fan:action-id','suggestions':['old']}])
    sender=SimpleNamespace(regenerate=AsyncMock(return_value={'suggestions':['i loved that walk']}))
    control._senders['instagram']=sender
    await dispatcher.tick()
    sender.regenerate.assert_awaited_once_with('fan:action-id',seed='c1',brief='say you enjoyed the walk')
    assert t._get.await_args.args[1]['model_id']=='eq.model'
    assert t._get.await_args.args[1]['id']=='eq.pending'
    assert not any(c.args[0]=='social_start_send' for c in t._rpc.await_args_list)

async def test_changed_draft_blocks_say_this_before_paid_generation():
    job=command(operation='regenerate',pending_id='pending',expected_suggestions=['old'])
    dispatcher,t,control=setup(job)
    t._get=AsyncMock(return_value=[{'conv_key':'555','suggestions':['new']}])
    sender=SimpleNamespace(regenerate=AsyncMock())
    control._senders['telegram']=sender
    await dispatcher.tick()
    sender.regenerate.assert_not_awaited()
    assert t._rpc.await_args.args[1]['p_status']=='stale'

async def test_temporary_limit_keeps_same_command_in_durable_wait_queue():
    job=command(channel='instagram')
    dispatcher,t,control=setup(job)
    control._senders['instagram']=SimpleNamespace(deliver_operator=AsyncMock(return_value=DeliveryResult('deferred','action_gap',{'action_id':'ig-action'})))
    await dispatcher.tick()
    names=[call.args[0] for call in t._rpc.await_args_list]
    assert 'social_defer' in names and 'social_finish' not in names
    call=next(c for c in t._rpc.await_args_list if c.args[0]=='social_defer')
    assert call.args[1]['p_command']=='c1' and call.args[1]['p_action']=='ig-action'
    assert call.args[1]['p_lease']=='lease' and call.args[1]['p_worker']=='replica'

async def test_failed_defer_is_not_guessed_as_queued():
    dispatcher,t,control=setup(command(channel='instagram'))
    async def rpc(name,args):
        if name=='social_claim':return command(channel='instagram')
        return False
    t._rpc.side_effect=rpc
    control._senders['instagram']=SimpleNamespace(deliver_operator=AsyncMock(return_value=DeliveryResult('deferred','action_gap',{'action_id':'ig'})))
    await dispatcher.tick()
    assert t._rpc.await_args.args[0]=='social_finish'
    assert t._rpc.await_args.args[1]['p_status']=='blocked'

async def test_owner_requests_suggestions_without_pending_and_never_sends(monkeypatch):
    import owner_drafts
    job=command(operation='regenerate',pending_id=None,text='',brief='tell him the walk was lovely')
    dispatcher,t,control=setup(job)
    sender=SimpleNamespace(deliver_operator=AsyncMock())
    control._senders['telegram']=sender
    generate=AsyncMock(return_value={'suggestions':['the walk was lovely','i loved that walk']})
    monkeypatch.setattr(owner_drafts,'generate',generate)
    await dispatcher.tick()
    generate.assert_awaited_once_with(sender,job)
    names=[c.args[0] for c in t._rpc.await_args_list]
    assert names==['social_claim','social_store_owner_draft']
    sender.deliver_operator.assert_not_awaited()
    assert t._rpc.await_args.args[1]['p_suggestions']==['the walk was lovely','i loved that walk']
