"""Native Fanvue replies refresh the inbox and fence old generated replies."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from fanvue_agent import FanvueAgent


def message(mid, sender, text, second=0):
    return {'uuid': mid, 'sender': {'uuid': sender}, 'text': text,
            'sentAt': f'2026-11-17T00:00:{second:02d}+00:00'}


class Db:
    def __init__(self):
        self.rows = [{'message_uuid': 'incoming', 'role': 'user', 'content': 'hello',
                      'occurred_at': '2026-11-17T00:00:00+00:00'}]
        self.user = {'fan_uuid': 'fan', 'ai_enabled': True, 'msg_count': 1}
        self.config = {'connected': True, 'enabled': True, 'reply_mode': 'semi', 'creator_uuid': 'creator'}
        self.pending_draft = True
        self.events = []
        self.handled = []

    async def settings(self): return dict(self.config)
    async def behavior(self): return {}
    async def fan(self, key): return dict(self.user)
    async def upsert_fan(self, key, patch): self.user.update(patch)
    async def update_fan(self, key, patch): self.user.update(patch)
    async def known_message_uuids(self, key): return {r['message_uuid'] for r in self.rows}
    async def texty_bez_uuid(self, key): return set()
    async def history(self, key): return list(self.rows)
    async def history_rows(self, key): return list(self.rows)
    async def source_snapshot(self, channel, key): return str(len(self.rows))
    async def sync_contacts(self, *, after='', limit=5): return [{'fan_uuid': 'fan'}] if not after else []
    async def pending_contacts(self, *, offset=0, limit=5): return []
    async def pending(self, **kw): return [e for e in self.events if e['id'] not in self.handled]
    async def pending_thanks(self): return []
    async def control_bot_settings(self): return {}
    async def claim_event_notification(self, event_id): return False
    async def mark_handled(self, event_id): self.handled.append(event_id)
    async def add_messages(self, key, rows):
        known = {r['message_uuid'] for r in self.rows}
        self.rows.extend(r for r in rows if r['message_uuid'] not in known)
        # The shared SQL migration invalidates drafts atomically on new
        # assistant inserts. Keep that real DB boundary explicit in this fake.
        if any(row['role'] == 'assistant' for row in rows): self.pending_draft = False


class Api:
    def __init__(self):
        self.messages = [message('incoming', 'fan', 'hello')]
        self.reads, self.seen, self.sent = [], [], []
        self.before_http = None
        self.fail = False

    async def sync_messages(self, key, known):
        self.reads.append(key)
        if self.fail: raise RuntimeError('provider unavailable')
        return list(self.messages)

    async def chat_messages(self, key, limit=30, mark_read=False):
        if mark_read: self.seen.append(key)
        return list(self.messages[:limit])

    async def send(self, key, text, *args):
        self.sent.append(text)
        return 'outgoing'

    async def send_operator(self, key, text, before_send):
        from social_commands import DeliveryResult
        if self.before_http: self.before_http()
        if not await before_send(): return DeliveryResult.blocked('stale_context')
        self.sent.append(text)
        return DeliveryResult.sent('outgoing')


def setup():
    db, api = Db(), Api()
    cards = []
    async def post_approval(**card): cards.append(card); return True
    control = SimpleNamespace(_db=db, post_approval=post_approval)
    agent = FanvueAgent(db, api, SimpleNamespace(suggest=AsyncMock(return_value=['generated'])), control)
    return agent, db, api, cards


@pytest.mark.parametrize('mode', ['off', 'semi', 'auto'])
async def test_background_imports_native_reply_without_webhook_seen_or_sending(mode):
    agent, db, api, _ = setup()
    db.config.update(reply_mode=mode, enabled=mode != 'off')
    api.messages.insert(0, message('native', 'creator', 'I already replied', 1))
    await agent.sync_native_chats()
    assert [(r['role'], r['content']) for r in db.rows] == [('user', 'hello'), ('assistant', 'I already replied')]
    assert not db.pending_draft
    assert api.seen == [] and api.sent == []
    await agent.sync_native_chats()
    assert len(db.rows) == 2


async def test_native_reply_during_semi_generation_cannot_publish_old_draft():
    agent, db, api, cards = setup()
    async def suggest(*a, **kw):
        api.messages.insert(0, message('native', 'creator', 'Handled in the app', 1))
        return ['stale generated reply']
    agent._llm.suggest = suggest
    assert not await agent._handoff_semi({'uuid': 'fan', 'text': 'hello'}, db.user, 'prompt', list(db.rows))
    assert cards == [] and api.sent == [] and api.seen == []
    assert db.rows[-1]['content'] == 'Handled in the app'


async def test_auto_preflight_detects_native_reply_after_generation():
    agent, db, api, _ = setup()
    db.config['reply_mode'] = 'auto'
    agent._require_auto_hours = AsyncMock()
    api.messages.insert(0, message('native', 'creator', 'Handled', 1))
    assert not await agent._send_checked('fan', 'stale', source_message_id='1')
    assert api.sent == [] and api.seen == []


async def test_operator_final_boundary_refreshes_native_outbound_before_db_fence():
    agent, db, api, _ = setup()
    command = {'external_id': 'fan', 'text': 'stale approval', 'operation': 'approve', 'account_scope': 'fanvue:creator'}
    async def fence(): return len(db.rows) == 1
    api.before_http = lambda: api.messages.insert(0, message('native', 'creator', 'Native answer', 1))
    result = await agent.deliver_operator(command, fence)
    assert result.status == 'blocked'
    assert api.sent == []
    assert db.rows[-1]['content'] == 'Native answer'


async def test_unavailable_provider_never_allows_operator_send():
    agent, _, api, _ = setup()
    api.fail = True
    command = {'external_id': 'fan', 'text': 'approval', 'operation': 'approve', 'account_scope': 'fanvue:creator'}
    result = await agent.deliver_operator(command, AsyncMock(return_value=True))
    assert result.status == 'blocked'
    assert api.sent == [] and api.seen == []


async def test_sent_webhook_is_read_only_context_work():
    agent, db, api, _ = setup()
    db.config.update(enabled=False, reply_mode='off')
    api.messages.insert(0, message('native', 'creator', 'App reply', 1))
    db.events = [{'id': 3, 'type': 'creator.message.sent', 'payload': {'data': {
        'uuid': 'native', 'object': 'message', 'fan': {'uuid': 'fan'}, 'creator': {'uuid': 'creator'},
        'sender': 'creator', 'text': 'App reply', 'created_at': '2026-11-17T00:00:01Z'}}}]
    await agent.tick()
    assert db.rows[-1]['content'] == 'App reply' and db.rows[-1]['role'] == 'assistant'
    assert db.handled == [3]
    assert api.sent == [] and api.seen == []


async def test_strict_api_pages_until_known_anchor_and_never_marks_read():
    from fanvue_api import Fanvue
    requests = []
    def handler(req):
        requests.append(req)
        data = ([message('new', 'creator', 'native', 2), message('middle', 'fan', 'next', 1)]
                if 'beforeMessageUuid' not in req.url.params else [message('incoming', 'fan', 'hello')])
        return httpx.Response(200, json={'data': data, 'pagination': {'hasMore': True}})
    api = Fanvue.__new__(Fanvue)
    api._headers = AsyncMock(return_value={})
    api._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='https://api.fanvue.com')
    try:
        rows = await api.sync_messages('fan', {'incoming'})
        assert [r['uuid'] for r in rows] == ['new', 'middle', 'incoming']
        assert len(requests) == 2 and requests[1].url.params['beforeMessageUuid'] == 'middle'
        assert all(r.url.params['markAsRead'] == 'false' for r in requests)
    finally:
        await api._client.aclose()


async def test_strict_api_failure_and_backoff_are_not_empty_success():
    from fanvue_api import Fanvue
    calls = []
    def handler(req): calls.append(req); return httpx.Response(429, headers={'Retry-After': '60'})
    api = Fanvue.__new__(Fanvue)
    api._headers = AsyncMock(return_value={})
    api._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='https://api.fanvue.com')
    try:
        for _ in range(2):
            with pytest.raises(Exception): await api.sync_messages('fan', set())
        assert len(calls) == 1
    finally:
        await api._client.aclose()


async def test_native_chat_list_discovers_previously_unknown_contact():
    agent, db, api, _ = setup()
    users = {}
    async def fan(key): return users.get(key)
    async def upsert(key, patch): users[key] = dict(patch)
    db.fan, db.upsert_fan = fan, upsert
    db.rows = []
    db.sync_contacts = AsyncMock(return_value=[])
    api.chat_page = AsyncMock(return_value={'data': [{'user': {
        'uuid': 'new-fan', 'displayName': 'New Fan', 'handle': 'new-handle', 'avatarUrl': ''}}], 'nextCursor': None})
    api.messages = [message('native', 'creator', 'Native first message', 1)]
    await agent.sync_native_chats()
    assert users['new-fan']['display_name'] == 'New Fan'
    assert db.rows[-1]['role'] == 'assistant' and db.rows[-1]['content'] == 'Native first message'
    assert api.seen == [] and api.sent == []


async def test_bounded_history_gap_makes_progress_before_it_becomes_sendable():
    from fanvue_api import Fanvue, FanvueHistoryGap
    calls = []
    pages = {None: ['m5'], 'm5': ['m4'], 'm4': ['m3'], 'm3': ['m2'], 'm2': ['incoming']}
    def handler(req):
        anchor = req.url.params.get('beforeMessageUuid')
        calls.append(anchor)
        return httpx.Response(200, json={'data': [message(mid, 'fan', mid) for mid in pages[anchor]],
                                        'pagination': {'hasMore': anchor != 'm2'}})
    api = Fanvue.__new__(Fanvue)
    api._headers = AsyncMock(return_value={})
    api._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='https://api.fanvue.com')
    try:
        with pytest.raises(FanvueHistoryGap) as gap:
            await api.sync_messages('fan', {'incoming'})
        assert [m['uuid'] for m in gap.value.messages] == ['m5', 'm4', 'm3', 'm2']
        gap.value.messages.acknowledge()  # the agent does this only after DB import
        with pytest.raises(FanvueHistoryGap) as old_gap:
            await api.sync_messages('fan', {'incoming', 'm5', 'm4', 'm3', 'm2'})
        assert 'incoming' in [m['uuid'] for m in old_gap.value.messages]
        old_gap.value.messages.acknowledge()
        rows = await api.sync_messages('fan', {'incoming', 'm5', 'm4', 'm3', 'm2'})
        assert rows[0]['uuid'] == 'm5'
        assert calls == [None, 'm5', 'm4', 'm3', 'm2', None]
    finally:
        await api._client.aclose()


def test_legacy_text_match_never_hides_new_inbound_or_later_native_reply():
    import fvsync
    fetched = [message('user-hi', 'fan', 'hi', 20), message('native-hi', 'creator', 'hi', 10)]
    old = [{'role': 'assistant', 'content': 'hi', 'occurred_at': '2026-11-17T00:00:00+00:00'}]
    assert [r['message_uuid'] for r in fvsync.missing(set(), fetched, 'creator', legacy_rows=old)] == ['native-hi', 'user-hi']
    fetched = [message('same-old', 'creator', 'hi', 2)]
    assert fvsync.missing(set(), fetched, 'creator', legacy_rows=old) == []


@pytest.mark.parametrize('mode,skipped', [('auto', False), ('off', False), ('semi', True)])
async def test_targeted_refresh_never_overrides_mode_or_owner_skip(mode, skipped):
    agent, db, _, cards = setup()
    db.config['reply_mode'] = mode
    db.user['history_sync_state'] = {'complete': True, 'refresh_pending_id': 'old'}
    db.refreshable_pending = AsyncMock(return_value=not skipped)
    agent._reply = AsyncMock()
    await agent._refresh_native_draft('fan', db.user)
    agent._reply.assert_not_awaited()
    assert cards == [] and db.user['history_sync_state'] is None


async def test_targeted_refresh_only_replaces_a_superseded_existing_semi_draft():
    agent, db, _, _ = setup()
    db.user['history_sync_state'] = {'complete': True, 'refresh_pending_id': 'old'}
    db.refreshable_pending = AsyncMock(side_effect=[True, False])
    agent._reply = AsyncMock()
    await agent._refresh_native_draft('fan', db.user)
    assert agent._reply.await_args.args[0]['payload']['data']['text'] == 'hello'
    assert db.user['history_sync_state'] is None


@pytest.mark.parametrize('crash_after_insert', [False, True])
async def test_restart_and_new_burst_do_not_hide_the_middle_of_a_history_gap(crash_after_insert):
    from fanvue_api import Fanvue, FanvueHistoryGap
    from datetime import datetime, timedelta, timezone
    agent, db, _, _ = setup()
    base = datetime(2026, 11, 17, tzinfo=timezone.utc)
    def item(index):
        return {'uuid': f'm{index}', 'sender': {'uuid': 'fan'}, 'text': f'message {index}',
                'sentAt': (base + timedelta(seconds=index)).isoformat()}
    remote = [item(i) for i in range(250, 0, -1)] + [message('incoming', 'fan', 'hello')]
    calls = []
    def handler(req):
        cursor = req.url.params.get('beforeMessageUuid')
        calls.append(cursor)
        start = next((i + 1 for i, m in enumerate(remote) if m['uuid'] == cursor), 0)
        return httpx.Response(200, json={'data': remote[start:start + 50],
                                        'pagination': {'hasMore': start + 50 < len(remote)}})
    clients = []
    def fresh_api():
        api = Fanvue.__new__(Fanvue)
        api._headers = AsyncMock(return_value={})
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='https://api.fanvue.com')
        clients.append(api._client)
        return api
    persist = db.add_messages
    async def partial_commit(key, rows):
        await persist(key, rows)
        raise RuntimeError('connection lost after committed insert')
    if crash_after_insert: db.add_messages = partial_commit
    agent._api = fresh_api()
    try:
        with pytest.raises((FanvueHistoryGap, RuntimeError)):
            await agent._reconcile({'uuid': 'fan', 'text': ''}, db.user, sync_only=True)
        assert db.user['history_sync_state']['cursor'] == ('' if crash_after_insert else 'm51')
        assert len(db.rows) == 201
        db.add_messages = persist
        # New traffic arrives while the older hole is still being walked.
        remote[:0] = [item(i) for i in range(330, 250, -1)]
        agent = FanvueAgent(db, fresh_api(), None)
        for _ in range(6):
            before = len(calls)
            try:
                await agent._reconcile({'uuid': 'fan', 'text': ''}, db.user, sync_only=True)
                break
            except FanvueHistoryGap:
                assert db.user['history_sync_state'] is not None
            assert len(calls) - before <= 4
        else:
            pytest.fail('history cursor did not complete')
        assert db.user['history_sync_state'] is None
        assert {r['message_uuid'] for r in db.rows} == {r['uuid'] for r in remote}
        assert len(db.rows) == 331
    finally:
        for client in clients: await client.aclose()


async def test_auto_native_reply_during_seen_request_still_blocks_provider_send():
    agent, db, api, _ = setup()
    db.config['reply_mode'] = 'auto'
    agent._require_auto_hours = AsyncMock()
    async def seen(*args, **kwargs):
        api.messages.insert(0, message('native', 'creator', 'Handled during seen', 1))
        return list(api.messages)
    api.chat_messages = seen
    assert not await agent._send_checked('fan', 'stale', source_message_id='1')
    assert api.sent == []


def prepare_semi_turn(agent, db):
    db.user['tg_id'] = 1
    db.defer_event = AsyncMock()
    agent._situacia = AsyncMock(return_value=SimpleNamespace(
        persona={}, behavior={}, teraz=None, blok=None, kde='home', moment=None,
        foto_ok=False, dlzi=False, pyta_fotku=False, pyta_ostre=False,
        prompt='current context', tip='', tah=None))


async def test_first_semi_inbound_is_deferred_until_gap_finishes_then_published_once():
    from fanvue_api import FanvueHistoryGap
    agent, db, api, cards = setup()
    prepare_semi_turn(agent, db)
    db.pending_draft = False
    db.events = [{'id': 1, 'type': 'creator.message.received', 'payload': {'data': {
        'sender': 'fan', 'text': 'hello', 'fan': {'uuid': 'fan'}}}}]
    original = api.sync_messages
    reads = 0
    async def gap_once(key, known):
        nonlocal reads
        reads += 1
        if reads == 1: raise FanvueHistoryGap(list(api.messages))
        return await original(key, known)
    api.sync_messages = gap_once
    await agent.tick()
    assert db.handled == [] and cards == []
    await agent.tick()
    await agent.tick()
    assert db.handled == [1] and len(cards) == 1
    assert api.sent == [] and api.seen == []


async def test_late_outbound_webhook_cannot_consume_newer_inbound_trigger():
    agent, db, api, cards = setup()
    prepare_semi_turn(agent, db)
    api.messages = [message('new-inbound', 'fan', 'new question', 2),
                    message('native', 'creator', 'earlier answer', 1), message('incoming', 'fan', 'hello')]
    db.events = [
        {'id': 1, 'type': 'creator.message.received', 'payload': {'data': {
            'sender': 'fan', 'text': 'new question', 'fan': {'uuid': 'fan'}}}},
        {'id': 2, 'type': 'creator.message.sent', 'payload': {'data': {
            'sender': 'creator', 'text': 'earlier answer', 'fan': {'uuid': 'fan'}}}},
    ]
    await agent.tick()
    assert len(cards) == 1 and db.handled == [1, 2]
    assert api.sent == [] and api.seen == []


async def test_switch_to_manual_during_generation_does_not_publish_new_draft():
    agent, db, api, cards = setup()
    async def suggest(*args, **kwargs):
        db.config['reply_mode'] = 'off'
        return ['generated too late']
    agent._llm.suggest = suggest
    assert not await agent._handoff_semi({'uuid': 'fan'}, db.user, 'prompt', list(db.rows))
    assert cards == []


@pytest.mark.parametrize('unknown_count', [0, 50])
async def test_recent_known_context_survives_deep_late_import_before_limit(unknown_count):
    from fanvue_tenant import TenantFanvueDb
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    rows = [{'id': 1, 'role': 'user', 'content': 'newest question', 'occurred_at': now.isoformat()}]
    rows += [{'id': i + 2, 'role': 'assistant', 'content': f'old {i}',
              'occurred_at': (now - timedelta(days=1, seconds=i)).isoformat()} for i in range(200)]
    rows += [{'id': 300 + i, 'role': 'assistant', 'content': f'unknown {i}', 'occurred_at': None}
             for i in range(unknown_count)]
    db = TenantFanvueDb.__new__(TenantFanvueDb)
    db.model_id = 'model'
    async def get(path, params):
        selected = [r for r in rows if bool(r['occurred_at']) == (params['occurred_at'] == 'not.is.null')]
        selected.sort(key=(lambda r: (r['occurred_at'], r['id'])) if 'occurred_at.desc' in params['order'] else lambda r: r['id'], reverse=True)
        return selected[:int(params['limit'])]
    db._get = get
    for history in (await db.history_rows('fan'), await db.history('fan')):
        assert len(history) == 16 and any(r['content'] == 'newest question' for r in history)
