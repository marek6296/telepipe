from datetime import datetime, timezone

import pytest

from conversation_hub import ConversationHub


class Store:
    def __init__(self):
        self.rows = {}
        self.calls = []

    async def _get(self, path, params):
        self.calls.append((path, params))
        rows = self.rows.get(path, [])
        return [dict(r) for r in rows if all(
            not str(v).startswith('eq.') or str(r.get(k)) == str(v)[3:]
            for k, v in params.items())]

    async def _post(self, path, body, upsert=False):
        self.rows.setdefault(path, []).append(body)
        return [body]

    async def _patch(self, path, params, body):
        for row in self.rows.get(path, []):
            if all(str(row.get(k)) == str(v)[3:] for k, v in params.items()):
                row.update(body)


def identity(id, platform, external, status='verified', person='p'):
    return dict(model_id='m', id=id, person_id=person, platform=platform,
                external_id=external, status=status, account_scope='primary')


@pytest.mark.asyncio
async def test_recognition_never_reads_other_contacts_transcript():
    t = Store()
    t.rows['/conversation_identities'] = [identity('a', 'telegram', '1', 'recognized')]
    hub = ConversationHub(t, 'm')
    result = await hub.context('telegram', '1')
    assert 'likely' in result
    assert all('messages' not in path for path, _ in t.calls)


@pytest.mark.asyncio
async def test_verified_context_has_source_and_model_filters():
    t = Store()
    t.rows['/conversation_identities'] = [identity('a', 'telegram', '1'), identity('b', 'instagram', '2')]
    t.rows['/ig_messages'] = [dict(model_id='m', igsid='2', role='user', content='my dog is Rex')]
    hub = ConversationHub(t, 'm')
    result = await hub.context('telegram', '1')
    assert 'Rex' in result and 'instagram' in result
    assert all(params['model_id'] == 'eq.m' for _, params in t.calls)


@pytest.mark.asyncio
async def test_same_saved_day_across_channels_and_schedule_edits():
    t = Store()
    a, b = ConversationHub(t, 'm'), ConversationHub(t, 'm')
    now = datetime(2026, 11, 16, 15, tzinfo=timezone.utc)
    block, mood = await a.day(now, None)
    assert (await b.day(now, None)) == (block, mood)
    assert len(t.rows['/conversation_days']) == 1


@pytest.mark.asyncio
async def test_multiple_account_scopes_fail_closed():
    t = Store()
    t.rows['/conversation_identities'] = [identity('a', 'instagram', '1'), identity('b', 'instagram', '1')]
    assert await ConversationHub(t, 'm').identity('instagram', '1') is None


@pytest.mark.asyncio
async def test_denial_detaches_current_identity_and_does_not_rematch():
    class RpcStore(Store):
        async def _rpc(self, name, args):
            self.calls.append((name, args))
            if name == 'conversation_ensure_identity':
                return {**identity('current', 'telegram', '1', 'recognized'), 'candidate_id': 'old'}
            return identity('current', 'telegram', '1', 'local', 'new-person')
    t = RpcStore()
    result = await ConversationHub(t, 'm').observe('telegram', '1', text='no thats not me')
    assert result['person_id'] == 'new-person'
    assert t.calls[-1] == ('conversation_pair', dict(p_model='m', p_identity='current',
        p_other='old', p_decision='rejected', p_evidence={'reason': 'contact_denial'}))


@pytest.mark.asyncio
async def test_stopped_contact_can_request_new_answer_but_not_old_or_proactive_one():
    t = Store()
    t.rows['/conversation_identities'] = [identity('a', 'telegram', '1')]
    t.rows['/conversation_people'] = [dict(model_id='m', id='p', no_initiate=True, no_links=True,
        stopped_at='2026-11-16T10:00:00+00:00')]
    t.rows['/dm_messages'] = [dict(model_id='m', tg_id='1', role='user', content='how are you?', created_at='2026-11-16T11:00:00+00:00')]
    hub = ConversationHub(t, 'm')
    assert await hub.can_reply('telegram', '1')
    assert not await hub.can_reply('telegram', '1', proactive=True)
    t.rows['/dm_messages'][0]['created_at'] = '2026-11-16T09:00:00+00:00'
    assert not await hub.can_reply('telegram', '1')
    assert (await hub.restrictions('telegram', '1'))['no_links'] is True


@pytest.mark.asyncio
async def test_explicit_reactive_optin_preserves_marketing_optout():
    class RpcStore(Store):
        async def _rpc(self, name, args):
            return identity('a', 'telegram', '1')
    t = RpcStore()
    t.rows['/conversation_identities'] = [identity('a', 'telegram', '1')]
    t.rows['/conversation_people'] = [dict(model_id='m', id='p', no_initiate=True, no_links=True,
        stopped_at='2026-11-16T10:00:00+00:00')]
    hub = ConversationHub(t, 'm')
    await hub.observe('telegram', '1', text='you can reply to me again', source_at='2026-11-16T11:00:00+00:00')
    assert t.rows['/conversation_people'][0]['no_initiate'] is False
    assert t.rows['/conversation_people'][0]['no_links'] is True
