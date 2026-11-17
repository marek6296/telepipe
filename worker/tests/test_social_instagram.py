"""Operator IG uses the durable action reservation and never an ad-hoc send."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from instagram_agent import InstagramAgent
from test_instagram_kolo import FakeDb, FakeLlm, MOJE_ID
from test_instagram_delivery import thread
from test_social_commands import command


class OperatorDb(FakeDb):
    async def prepare_operator_action(self, cmd, target, source_mid, source_at):
        action = dict(id='op', igsid=cmd['external_id'], kind='dm', state='leased',
            target_id=target, source_mid=source_mid, source_at=source_at,
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            lease_token='action-lease', payload={'origin': 'operator', 'command_id': cmd['id'],
                'operator_operation': cmd['operation'],
                'approved_intent': cmd.get('approved_intent'),
                'approved_source_mid': source_mid, 'account_id': MOJE_ID}, text=cmd['text'])
        self.queue['op'] = action
        return dict(action)

    async def cancel_actions(self, igsid='', reason='channel_off'):
        for action in self.queue.values():
            if action.get('payload', {}).get('origin') == 'operator':
                continue
            if action['state'] in ('pending', 'ready', 'leased', 'approval'):
                action.update(state='cancelled', reason=reason)

    async def rpc(self, name, **kwargs):
        if name == 'reserve' and self.queue[kwargs['action']].get('payload', {}).get('origin') == 'operator':
            self.queue[kwargs['action']]['state'] = 'sending'
            return {'ok': True}
        return await super().rpc(name, **kwargs)


@pytest.mark.parametrize('mode', ['off', 'semi', 'auto'])
async def test_operator_text_uses_reservation_and_exact_text_even_when_off(monkeypatch, mode):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode=mode, enabled=False)
    agent = InstagramAgent(db, FakeLlm())
    await db.ensure_user('fan')
    db.users['fan']['human_takeover'] = True
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: raw)
    agent._delivery.ingest = AsyncMock(wraps=agent._delivery.ingest)
    seen, sends = [], []
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **k: seen.append(True))
    def send(*args, **kwargs):
        assert db.queue['op']['state'] == 'sending'
        sends.append(args[2])
        return {'message_id': 'sent-1'}
    monkeypatch.setattr(api, 'posli_text', send)
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID),
                                          AsyncMock(return_value=True))
    assert result.status == 'done'
    assert sends == ['exact owner text'] and seen == [True]
    assert agent._delivery.ingest.await_count == 1, 'Unchanged provider snapshot must not be reconciled twice during one send'


async def test_operator_expired_window_has_no_seen_or_send(monkeypatch):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc)-timedelta(hours=25))
    db = OperatorDb(reply_mode='off', enabled=False)
    agent = InstagramAgent(db, FakeLlm())
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    before = AsyncMock(return_value=True)
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID), before)
    assert result.status == 'blocked' and result.reason == 'window_expired'
    assert result.result['restore_pending'] is False
    before.assert_not_awaited()


async def test_operator_provider_timeout_is_not_requeued(monkeypatch):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode='off', enabled=False)
    agent = InstagramAgent(db, FakeLlm())
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: raw)
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **k: None)
    def timeout(*args, **kwargs):
        raise api.InstagramError('lost response')
    monkeypatch.setattr(api, 'posli_text', timeout)
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID),
                                          AsyncMock(return_value=True))
    assert result.status == 'uncertain'
    assert db.queue['op']['state'] == 'uncertain'


async def test_operator_does_not_depend_on_automatic_schedule(monkeypatch):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode='off', enabled=False)
    db.behavior = AsyncMock(side_effect=RuntimeError('schedule unavailable'))
    agent = InstagramAgent(db, FakeLlm())
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: raw)
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **k: None)
    monkeypatch.setattr(api, 'posli_text', lambda *a, **k: {'message_id': 'sent-1'})
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID),
                                          AsyncMock(return_value=True))
    assert result.status == 'done'
    db.behavior.assert_not_awaited()


async def test_safe_budget_failure_restores_original_ig_approval_action(monkeypatch):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode='semi')
    agent = InstagramAgent(db, FakeLlm())
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: raw)
    original_rpc = db.rpc
    async def rpc(name, **kwargs):
        if name == 'reserve':
            db.queue[kwargs['action']].update(state='pending', lease_token=None, reason='dm_limit')
            return {'ok': False}
        return await original_rpc(name, **kwargs)
    db.rpc = rpc
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID,
                                                  pending_id='pending', operation='approve'), AsyncMock(return_value=True))
    assert result.status == 'blocked' and result.result['safe_to_retry']
    assert db.queue['op']['state'] == 'approval'
    assert 'command_id' not in db.queue['op']['payload']


async def test_operator_action_updates_compare_command_ownership():
    from types import SimpleNamespace
    from instagram_tenant import TenantInstagramDb
    transport = SimpleNamespace(_patch_returning=AsyncMock(return_value=[]))
    db = TenantInstagramDb(transport, 'model', '')
    action = {'id': 'a', 'state': 'pending', 'payload': {'origin': 'operator', 'command_id': 'old-command'}}
    await db.change_action(action, {'state': 'approval', 'payload': {}}, state='pending')
    params = transport._patch_returning.await_args.args[1]
    assert params['payload->>command_id'] == 'eq.old-command'


async def test_terminal_ig_action_never_restores_unusable_pending(monkeypatch):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode='semi')
    agent = InstagramAgent(db, FakeLlm())
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    async def expired(cfg, action=None, before_send=None, **kwargs):
        db.queue['op'].update(state='expired', reason='window_expired')
    agent._delivery.process_one = expired
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID,
                                                  pending_id='pending', operation='approve'), AsyncMock(return_value=True))
    assert result.status == 'blocked' and result.result['safe_to_retry']
    assert result.result['restore_pending'] is False


@pytest.mark.parametrize('operation,text,expected', [
    ('approve', '[[REMIND]] hey, you can find it there', 'hey, you can find it there'),
    ('send_text', '[[REMIND]] hey, you can find it there', None),
    ('approve', '[[PHOTO]]', None),
    ('approve', '[[REMIND]] [[PHOTO]] hey', None),
])
async def test_only_approved_legacy_text_markers_are_rendered(monkeypatch, operation, text, expected):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode='semi')
    agent = InstagramAgent(db, FakeLlm())
    await db.ensure_user('fan')
    db.users['fan']['link_sent_at'] = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: raw)
    sent, seen = [], []
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **k: seen.append(True))
    monkeypatch.setattr(api, 'posli_text', lambda *a, **k: sent.append(a[2]) or {'message_id': 'sent'})
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID,
        pending_id='pending' if operation == 'approve' else None, operation=operation,
        text=expected or text, expected_suggestions=[text]), AsyncMock(return_value=True))
    assert result.status == ('done' if expected else 'blocked')
    assert sent == ([expected] if expected else [])
    assert seen == ([True] if expected else [])
    if expected:
        assert db.queue['op']['text'] == expected
        assert db.queue['op']['payload']['approved_intent'] == text


async def test_approved_marker_cannot_authorize_unrelated_text_transformation(monkeypatch):
    import instagram_api as api
    import instagram_interactions as interactions
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode='semi')
    agent = InstagramAgent(db, FakeLlm())
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: raw)
    monkeypatch.setattr(interactions, 'prepare_response', lambda *a, **k: {
        'kind': 'dm', 'text': 'unreviewed different words', 'link': False, 'reminder': True, 'link_target': ''})
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID,
        pending_id='pending', operation='approve', text='reviewed words',
        expected_suggestions=['[[REMIND]] reviewed words']), AsyncMock(return_value=True))
    assert result.status == 'blocked'
    assert result.reason == 'approved_text_unavailable'


@pytest.mark.parametrize('current_handle,allowed', [('simona_here', True), ('changed_here', False)])
async def test_approved_marker_keeps_the_exact_displayed_url(monkeypatch, current_handle, allowed):
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    db = OperatorDb(reply_mode='semi', telegram_handle=current_handle)
    agent = InstagramAgent(db, FakeLlm())
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: raw)
    sent = []
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **k: None)
    monkeypatch.setattr(api, 'posli_text', lambda *a, **k: sent.append(a[2]) or {'message_id': 'sent'})
    canonical = 'come chat https://t.me/simona_here'
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID,
        pending_id='pending', operation='approve', text=canonical,
        expected_suggestions=['come chat [[TELEGRAM]]']), AsyncMock(return_value=True))
    assert result.status == ('done' if allowed else 'blocked')
    assert sent == ([canonical] if allowed else [])

async def test_operator_still_imports_changed_snapshot_before_sending(monkeypatch):
    import copy
    import instagram_api as api
    raw = thread(datetime.now(timezone.utc))
    changed = copy.deepcopy(raw)
    changed['messages']['data'][0]['message'] = 'new provider message content'
    db = OperatorDb(reply_mode='off', enabled=False)
    agent = InstagramAgent(db, FakeLlm())
    agent._delivery.ingest = AsyncMock(wraps=agent._delivery.ingest)
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **k: {'data': [raw], 'after': ''})
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: changed)
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **k: None)
    monkeypatch.setattr(api, 'posli_text', lambda *a, **k: {'message_id': 'sent'})
    await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID), AsyncMock(return_value=True))
    assert any(call.args[0] == changed for call in agent._delivery.ingest.await_args_list), 'Changed remote history must still be reconciled'
