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
    async def expired(cfg, action=None, before_send=None):
        db.queue['op'].update(state='expired', reason='window_expired')
    agent._delivery.process_one = expired
    result = await agent.deliver_operator(command(channel='instagram', external_id='fan', account_scope=MOJE_ID,
                                                  pending_id='pending', operation='approve'), AsyncMock(return_value=True))
    assert result.status == 'blocked' and result.result['safe_to_retry']
    assert result.result['restore_pending'] is False
