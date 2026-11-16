"""Native Instagram replies are history, not a permanent takeover toggle."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import instagram_api as api
from instagram_agent import InstagramAgent
from instagram_tenant import TenantInstagramDb
from test_instagram_kolo import FakeDb, FakeLlm, FakeControl, MOJE_ID


BASE = datetime.now(timezone.utc) - timedelta(minutes=10)


def snapshot(*rows):
    return {'id': 'thread', 'participants': {'data': [{'id': 'fan'}, {'id': MOJE_ID}]},
            'messages': {'data': [
                {'id': mid, 'from': {'id': MOJE_ID if role == 'assistant' else 'fan'},
                 'created_time': (BASE + timedelta(seconds=offset)).isoformat(), 'message': text}
                for role, mid, text, offset in reversed(rows)
            ]}}


INCOMING = ('user', 'in-1', 'how are you?', 0)
NATIVE = ('assistant', 'native-1', 'I just came back from a walk', 10)
NEXT = ('user', 'in-2', 'where did you walk?', 20)


class NativeDb(FakeDb):
    def __init__(self, **settings):
        super().__init__(**settings)
        self.native_calls = []

    async def native_reply(self, igsid, account, occurred_at):
        assert any(m['role'] == 'assistant' for m in self.spravy), 'Persist before invalidating'
        self.native_calls.append((igsid, account, occurred_at))
        return True

    async def latest_message_id(self, igsid):
        return max((i for i, m in enumerate(self.spravy, 1) if m['igsid'] == igsid), default=0)


async def prepared(mode='semi'):
    db, control = NativeDb(reply_mode=mode), FakeControl()
    agent = InstagramAgent(db, FakeLlm(), control=control)
    await agent._delivery.ingest(snapshot(INCOMING), db.nastavenia)
    db.queue['1']['due_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    return db, control, agent


async def test_native_reply_invalidates_draft_after_persistence_without_taking_over():
    db, _, agent = await prepared()
    db.queue['1']['state'] = 'approval'
    await agent._delivery.ingest(snapshot(INCOMING, NATIVE), db.nastavenia)
    assert db.native_calls == [('fan', MOJE_ID, (BASE+timedelta(seconds=10)).isoformat())]
    assert db.queue['1']['state'] == 'cancelled'
    assert db.users['fan']['human_takeover'] is False
    assert [m['content'] for m in db.spravy] == [INCOMING[2], NATIVE[2]]


async def test_explicit_takeover_is_preserved_when_native_reply_is_imported():
    db, _, agent = await prepared()
    db.users['fan']['human_takeover'] = True
    await agent._delivery.ingest(snapshot(INCOMING, NATIVE, NEXT), db.nastavenia)
    assert db.users['fan']['human_takeover'] is True
    assert len(db.queue) == 1


@pytest.mark.parametrize('mode', ['semi', 'auto'])
async def test_next_fan_message_continues_in_selected_mode_with_native_history(mode, monkeypatch):
    db, _, agent = await prepared(mode)
    await agent._delivery.ingest(snapshot(INCOMING, NATIVE, NEXT), db.nastavenia)
    assert not db.users['fan']['human_takeover']
    latest = [a for a in db.queue.values() if a['source_mid'] == NEXT[1]]
    assert latest, 'The next input must remain eligible for the selected Semi/Auto mode'
    captured = []
    async def suggest(user, key, cfg, **kw):
        history = await db.history(key)
        captured.extend(history)
        return ['a quiet path near home'], history
    async def reply(user, key, cfg):
        captured.extend(await db.history(key))
        return 'a quiet path near home'
    agent._navrhy, agent._napis = suggest, reply
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: snapshot(INCOMING, NATIVE, NEXT))
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **kw: {})
    monkeypatch.setattr(api, 'posli_text', lambda *a, **kw: {'message_id': 'ours-1'})
    latest[0]['due_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    await agent._delivery.process_one(db.nastavenia)
    assert any(m['role'] == 'assistant' and m['content'] == NATIVE[2] for m in captured)


@pytest.mark.parametrize('mode', ['semi', 'auto'])
async def test_native_reply_during_generation_is_imported_and_aborts_draft_or_send(mode, monkeypatch):
    db, control, agent = await prepared(mode)
    snapshots = iter([snapshot(INCOMING), snapshot(INCOMING, NATIVE)])
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: next(snapshots))
    seen, sends = [], []
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **kw: seen.append(True))
    monkeypatch.setattr(api, 'posli_text', lambda *a, **kw: sends.append(True))
    await agent._delivery.process_one(db.nastavenia)
    assert not control.karty and not seen and not sends
    assert any(m['mid'] == NATIVE[1] for m in db.spravy), 'Final freshness read must also become shared history'
    assert db.native_calls


async def test_semi_publication_freezes_database_source_before_generation(monkeypatch):
    db, control, agent = await prepared()
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: snapshot(INCOMING))
    await agent._delivery.process_one(db.nastavenia)
    assert control.karty[0]['source_message_id'] == 1


async def test_native_invalidation_failure_retries_without_duplicate_history(monkeypatch):
    db, _, agent = await prepared()
    original = db.native_reply
    failing = True
    async def invalidate(*args):
        nonlocal failing
        if failing:
            failing = False
            raise RuntimeError('temporary database failure')
        return await original(*args)
    db.native_reply = invalidate
    with pytest.raises(RuntimeError):
        await agent._delivery.ingest(snapshot(INCOMING, NATIVE), db.nastavenia)
    await agent._delivery.ingest(snapshot(INCOMING, NATIVE), db.nastavenia)
    assert len([m for m in db.spravy if m['mid'] == NATIVE[1]]) == 1
    assert len(db.native_calls) == 1


async def test_native_invalidation_rpc_is_tenant_and_account_scoped():
    transport = AsyncMock()
    transport._rpc.return_value = True
    db = TenantInstagramDb(transport, 'model-a', '')
    assert await db.native_reply('fan', 'account-a', BASE.isoformat())
    transport._rpc.assert_awaited_once_with('social_native_reply', {
        'p_model': 'model-a', 'p_channel': 'instagram', 'p_external': 'fan',
        'p_scope': 'account-a', 'p_occurred_at': BASE.isoformat(),
    })


async def test_late_native_import_only_cancels_actions_it_actually_answered():
    transport = AsyncMock()
    db = TenantInstagramDb(transport, 'model-a', '')
    await db.cancel_actions('fan', 'manual_reply', through=BASE.isoformat())
    params = transport._patch.await_args.args[1]
    assert params['model_id'] == 'eq.model-a' and params['igsid'] == 'eq.fan'
    assert params['source_at'] == 'lte.' + BASE.isoformat()


@pytest.mark.parametrize('change_during_generation', [False, True])
async def test_regenerate_refreshes_native_history_before_and_after_llm(change_during_generation, monkeypatch):
    db, _, agent = await prepared()
    db.queue['1']['state'] = 'approval'
    snapshots = iter([snapshot(INCOMING), snapshot(INCOMING, NATIVE)] if change_during_generation
                     else [snapshot(INCOMING, NATIVE)])
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: next(snapshots))
    output = await agent.regenerate('fan:1', brief='tell him about your walk')
    assert output == {}
    assert any(m['mid'] == NATIVE[1] for m in db.spravy)
    assert db.native_calls


async def test_our_confirmed_echo_is_not_a_native_reply():
    db, _, agent = await prepared()
    db.queue['1'].update(state='sent', provider_id='native-1', kind='dm')
    await agent._delivery.ingest(snapshot(INCOMING, NATIVE), db.nastavenia)
    assert not db.native_calls and not db.users['fan']['human_takeover']


async def test_recorded_manual_quota_entry_does_not_disguise_native_retry_as_our_echo():
    db, _, agent = await prepared()
    db.queue['manual'] = {'id': 'manual', 'igsid': 'fan', 'state': 'sent', 'kind': 'dm',
                          'provider_id': NATIVE[1], 'payload': {'manual': True}}
    await agent._delivery.ingest(snapshot(INCOMING, NATIVE), db.nastavenia)
    assert db.native_calls


async def test_unknown_native_source_time_is_invalidated_without_inventing_time():
    db, _, agent = await prepared()
    raw = snapshot(INCOMING, NATIVE)
    raw['messages']['data'][0]['created_time'] = None
    await agent._delivery.ingest(raw, db.nastavenia)
    assert db.native_calls == [('fan', MOJE_ID, None)]
    assert db.queue['1']['state'] == 'cancelled'


async def test_late_history_during_auto_generation_retries_with_complete_context(monkeypatch):
    db, _, agent = await prepared('auto')
    older_native = ('assistant', 'late-native', 'I promised to explain my walk', -10)
    snapshots = iter([snapshot(INCOMING), snapshot(older_native, INCOMING)])
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: next(snapshots))
    seen, sends = [], []
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **kw: seen.append(True))
    monkeypatch.setattr(api, 'posli_text', lambda *a, **kw: sends.append(True) or {'message_id': 'out'})
    await agent._delivery.process_one(db.nastavenia)
    assert not seen and not sends, 'Same latest MID is insufficient if earlier native context arrived during LLM'
    assert db.queue['1']['state'] == 'pending' and db.queue['1']['reason'] == 'history_changed'
    assert any(m['mid'] == 'late-native' for m in db.spravy)


async def test_native_history_arriving_during_receipt_prevents_following_auto_send(monkeypatch):
    db, _, agent = await prepared('auto')
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: snapshot(INCOMING))
    def receipt(*args, **kwargs):
        # A concurrent importer commits while Meta acknowledges mark_seen.
        db.spravy.append({'igsid': 'fan', 'role': 'assistant', 'content': NATIVE[2], 'mid': NATIVE[1]})
        return {'success': True}
    sends = []
    monkeypatch.setattr(api, 'mark_seen', receipt)
    monkeypatch.setattr(api, 'posli_text', lambda *a, **kw: sends.append(True) or {'message_id': 'out'})
    await agent._delivery.process_one(db.nastavenia)
    assert not sends
    assert db.queue['1']['state'] == 'pending' and db.queue['1'].get('reserved_at') is None
    assert db.queue['1']['reason'] == 'history_changed'


async def test_publication_cas_rejection_retries_fresh_context_on_next_poll(monkeypatch):
    db, control, agent = await prepared()
    control.post_approval = AsyncMock(return_value=False)
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: snapshot(INCOMING))
    await agent._delivery.process_one(db.nastavenia)
    assert db.queue['1']['state'] == 'pending'
    assert datetime.fromisoformat(db.queue['1']['due_at']) <= datetime.now(timezone.utc)


async def test_late_native_history_recovers_orphaned_approval_with_fresh_proposal(monkeypatch):
    db, control, agent = await prepared()
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: snapshot(INCOMING))
    await agent._delivery.process_one(db.nastavenia)
    assert len(control.karty) == 1 and db.queue['1']['state'] == 'approval'
    # The SQL context trigger supersedes the proposal when history changes.
    # Its transport action still needs an atomic orphan-to-pending transition.
    calls = []
    async def recover(igsid, source_mid, source_message_id):
        calls.append((igsid, source_mid, source_message_id))
        a = db.queue['1']
        assert a['state'] == 'approval' and source_mid == INCOMING[1]
        a.update(state='pending', due_at=datetime.now(timezone.utc).isoformat(), text='')
        return True
    db.requeue_stale_approval = recover
    older_native = ('assistant', 'late-native', 'I promised to explain my walk', -10)
    fresh = snapshot(older_native, INCOMING)
    await agent._delivery.ingest(fresh, db.nastavenia)
    assert calls == [('fan', INCOMING[1], 2)]
    assert db.queue['1']['state'] == 'pending'
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: fresh)
    await agent._delivery.process_one(db.nastavenia)
    assert len(control.karty) == 2 and control.karty[-1]['source_message_id'] == 2


async def test_orphan_approval_recovery_uses_atomic_tenant_scoped_rpc():
    transport = AsyncMock()
    transport._rpc.return_value = True
    db = TenantInstagramDb(transport, 'model-a', '')
    assert await db.requeue_stale_approval('fan', 'provider-mid', 123)
    transport._rpc.assert_awaited_once_with('instagram_requeue_stale_approval', {
        'p_model': 'model-a', 'p_igsid': 'fan', 'p_source_mid': 'provider-mid',
        'p_source_message_id': 123,
    })
