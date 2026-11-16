from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from instagram_delivery import InstagramDelivery


def settings(**changes):
    return dict(connected=True, enabled=True, reply_mode='auto', access_token='test',
                ig_user_id='account', sync_enabled=True, **changes)


def thread(stamp, role='user', mid='incoming'):
    return {'id': 'thread', 'participants': {'data': [{'id': 'fan'}]},
        'messages': {'data': [{'id': mid, 'from': {'id': 'fan' if role == 'user' else 'account'},
                              'created_time': stamp.isoformat(), 'message': 'hey'}]}}


@pytest.mark.asyncio
async def test_import_preserves_timestamp_and_never_schedules_bootstrap():
    now = datetime.now(timezone.utc)
    db = AsyncMock(model_id='model')
    db.ensure_user.return_value = {}
    db.hub.restrictions.return_value = {}
    db.known_mids.return_value = set()
    db.actions.return_value = []
    delivery = InstagramDelivery(db, AsyncMock())
    await delivery.ingest(thread(now - timedelta(days=2)), settings(), bootstrap=True)
    assert db.add_message.call_args.kwargs['occurred_at'] == (now-timedelta(days=2)).isoformat()
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_known_current_input_retries_durable_enqueue_after_crash():
    now = datetime.now(timezone.utc)
    db = AsyncMock(model_id='model')
    db.ensure_user.return_value = {}
    db.hub.restrictions.return_value = {}
    db.known_mids.return_value = {'incoming'}
    db.actions.return_value = []
    delivery = InstagramDelivery(db, AsyncMock())
    cfg = settings(replies_started_at=(now-timedelta(hours=1)).isoformat())
    await delivery.ingest(thread(now), cfg)
    db.add_message.assert_not_called()
    assert db.rpc.call_args.args == ('enqueue',)
    assert db.rpc.call_args.kwargs['source_at'] == now.isoformat()
    assert datetime.fromisoformat(db.rpc.call_args.kwargs['due']) > now


@pytest.mark.asyncio
async def test_new_manual_reply_cancels_pending_without_changing_takeover():
    now = datetime.now(timezone.utc)
    db = AsyncMock(model_id='model')
    db.ensure_user.return_value = {}
    db.hub.restrictions.return_value = {}
    db.known_mids.return_value = set()
    db.actions.return_value = []
    delivery = InstagramDelivery(db, AsyncMock())
    await delivery.ingest(thread(now, 'assistant'), settings(sync_completed_at=(now-timedelta(hours=1)).isoformat()))
    db.cancel_actions.assert_any_await('fan', 'manual_reply', through=now.isoformat())
    db.native_reply.assert_awaited_once_with('fan', 'account', now.isoformat())
    assert not any('human_takeover' in c.args[1] for c in db.update_user.call_args_list)


@pytest.mark.asyncio
async def test_stale_approval_cannot_approve_different_source():
    db = AsyncMock()
    db.action.return_value = dict(id='a', state='cancelled', igsid='fan')
    assert not await InstagramDelivery(db, AsyncMock()).approve('fan:a', 'hello')
    db.change_action.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_is_uncertain_and_never_replayed(monkeypatch):
    from test_instagram_kolo import FakeDb, FakeLlm, mock_threads
    from instagram_agent import InstagramAgent
    import instagram_api as api
    now = datetime.now(timezone.utc)
    db, llm = FakeDb(), FakeLlm()
    agent = InstagramAgent(db, llm)
    mock_threads(monkeypatch, [thread(now)])
    sends = []
    def timeout(*args, **kwargs):
        sends.append(1)
        raise api.InstagramError('timeout')
    monkeypatch.setattr(api, 'posli_text', timeout)
    await agent._delivery.ingest(thread(now), db.nastavenia)
    for a in db.queue.values():
        a['due_at'] = (now-timedelta(minutes=1)).isoformat()
    await agent._delivery.process_one(db.nastavenia)
    assert db.queue['1']['state'] == 'uncertain'
    await agent._delivery.process_one(db.nastavenia)
    assert sends == [1]


@pytest.mark.asyncio
async def test_final_remote_refresh_cancels_reply_to_stale_input(monkeypatch):
    from test_instagram_kolo import FakeDb, FakeLlm
    from instagram_agent import InstagramAgent
    import instagram_api as api
    now = datetime.now(timezone.utc)
    db = FakeDb()
    agent = InstagramAgent(db, FakeLlm())
    await agent._delivery.ingest(thread(now), db.nastavenia)
    db.queue['1']['due_at'] = (now-timedelta(minutes=1)).isoformat()
    snapshots = iter([thread(now), thread(now, mid='new-input')])
    monkeypatch.setattr(api, 'conversation', lambda *a, **k: next(snapshots))
    sends = []
    monkeypatch.setattr(api, 'posli_text', lambda *a, **k: sends.append(1))
    await agent._delivery.process_one(db.nastavenia)
    assert not sends
    assert db.queue['1']['reason'] == 'remote_context_changed'


@pytest.mark.asyncio
async def test_reservation_failure_is_not_sent(monkeypatch):
    from test_instagram_kolo import FakeDb, FakeLlm, mock_threads
    from instagram_agent import InstagramAgent
    import instagram_api as api
    now = datetime.now(timezone.utc)
    db = FakeDb()
    agent = InstagramAgent(db, FakeLlm())
    mock_threads(monkeypatch, [thread(now)])
    await agent._delivery.ingest(thread(now), db.nastavenia)
    db.queue['1']['due_at'] = (now-timedelta(minutes=1)).isoformat()
    original = db.rpc
    async def rpc(name, **kw):
        return {'ok': False, 'reason': 'quota'} if name == 'reserve' else await original(name, **kw)
    db.rpc = rpc
    sends = []
    monkeypatch.setattr(api, 'posli_text', lambda *a, **k: sends.append(1))
    await agent._delivery.process_one(db.nastavenia)
    assert not sends


@pytest.mark.asyncio
@pytest.mark.parametrize('age,no_links,expected', [('adult_self_declared',False,True),('unknown',False,False),('minor_or_conflicting',False,False),('adult_self_declared',True,False)])
async def test_existing_customer_return_keeps_age_optout_and_reminder_guards(age,no_links,expected):
    db = AsyncMock()
    db.hub.restrictions.return_value = {'no_links': no_links}
    db.hub.linked.return_value = [{'id':'fv'}]
    db.actions.return_value = []
    delivery = InstagramDelivery(db, AsyncMock())
    cfg = settings(funnel_target='both',telegram_handle='someone',bio_link='https://linkovne.com/someone')
    user = {'igsid':'fan','age_state':age}
    offer = await delivery.offer_state(cfg,user)
    assert offer['fanvue_customer']
    assert offer['fanvue_return'] is expected
    assert not offer['telegram_link'] and not offer['bio_link']
    user['last_reminder_at'] = datetime.now(timezone.utc).isoformat()
    assert not (await delivery.offer_state(cfg,user))['fanvue_return']
