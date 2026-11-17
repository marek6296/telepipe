"""Owner previews use live context without crossing any send/read boundary."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import owner_drafts
from behavior import Behavior


def command(channel='telegram', **patch):
    return dict(id='draft-1', channel=channel, external_id='555', brief='',
                account_scope={'telegram': 'primary', 'instagram': 'ig-account',
                               'fanvue': 'fanvue:creator'}[channel],
                expected_source=12, **patch)


def telegram():
    hub = SimpleNamespace(day=AsyncMock(return_value=(None, {'mood': 'warm'})),
                          context=AsyncMock(return_value=' SHARED MEMORY'),
                          mood_prompt=Mock(return_value=' SHARED MOOD'))
    db = SimpleNamespace(
        get_user=AsyncMock(return_value={'tg_id': 555, 'partner_name': 'Don', 'summary': 'old friend'}),
        get_persona=AsyncMock(return_value={'name': 'Simona'}),
        recent_messages=AsyncMock(return_value=[{'role': 'user', 'content': 'hello there'}]),
        facts_for=AsyncMock(return_value=[{'key': 'work', 'value': 'engineer'}]),
        episodes_for=AsyncMock(return_value=[{'body': 'talked about his trip'}]),
        open_loops=AsyncMock(return_value=[{'what': 'ask how the trip went'}]),
        self_claims=AsyncMock(return_value=[{'claim': 'I love hiking'}]), search_archive=AsyncMock(return_value=[]),
        hub=hub,
    )
    return SimpleNamespace(_db=db, _cfg=SimpleNamespace(context_messages=30, supabase_schema='model'),
                           _behavior=AsyncMock(return_value=Behavior()), _rozvrh=AsyncMock(),
                           _sync_native_outgoing=AsyncMock(),
                           _llm=SimpleNamespace(suggest=AsyncMock(return_value=['hello Don'])),
                           send=AsyncMock(), seen=AsyncMock(), take_over=AsyncMock())


async def test_telegram_builds_fresh_persona_memory_day_and_owner_brief(monkeypatch):
    sender = telegram()
    build = Mock(return_value='FRESH PERSONA')
    monkeypatch.setattr(owner_drafts, 'build_system_prompt', build)
    job = command()
    job['brief'] = 'thank him for visiting'
    before = deepcopy(job)
    result = await owner_drafts.generate(sender, job)
    assert result == {'suggestions': ['hello Don'], 'hint': ''}
    assert job == before
    assert build.call_args.args[:2] == ({'name': 'Simona'}, await sender._db.get_user(555))
    assert 'engineer' in build.call_args.kwargs['fact_sheet']
    assert 'talked about his trip' in build.call_args.kwargs['episodes']
    assert 'ask how the trip went' in build.call_args.kwargs['loops']
    assert 'I love hiking' in build.call_args.kwargs['claims']
    assert build.call_args.kwargs['no_photos'] is True
    assert build.call_args.kwargs['can_speak'] is False
    system, messages = sender._llm.suggest.await_args.args
    assert 'FRESH PERSONA' in system and 'SHARED MEMORY' in system and 'SHARED MOOD' in system
    assert 'thank him for visiting' in system
    assert messages[-1]['content'].endswith('hello there')
    assert sender._llm.suggest.await_args.kwargs['seed'] == job['id']
    assert sender._sync_native_outgoing.await_count == 2
    sender.send.assert_not_awaited()
    sender.seen.assert_not_awaited()
    sender.take_over.assert_not_awaited()


async def test_telegram_real_builder_works_without_pending_or_mode_checks():
    sender = telegram()
    result = await owner_drafts.generate(sender, command())
    assert result['suggestions']
    assert 'Simona' in sender._llm.suggest.await_args.args[0]


@pytest.mark.parametrize('channel,scope', [('telegram', 'other'), ('fanvue', 'fanvue:other'),
                                          ('instagram', 'other')])
async def test_scope_mismatch_stops_before_provider_or_llm(channel, scope):
    sender = telegram()
    sender._db.settings = AsyncMock(return_value={'connected': True, 'ig_user_id': 'ig-account',
                                                  'creator_uuid': 'creator', 'access_token': 'private'})
    sender.regenerate = AsyncMock()
    job = command(channel)
    job['account_scope'] = scope
    assert await owner_drafts.generate(sender, job) == {'suggestions': [], 'hint': ''}
    sender._llm.suggest.assert_not_awaited()
    sender._sync_native_outgoing.assert_not_awaited()
    sender.regenerate.assert_not_awaited()


async def test_fanvue_reuses_full_context_regeneration_without_pending():
    sender = SimpleNamespace(_db=SimpleNamespace(settings=AsyncMock(return_value={
        'connected': True, 'creator_uuid': 'creator'}), fan=AsyncMock(return_value={'fan_uuid': '555'})),
        _reconcile=AsyncMock(return_value=True),
        regenerate=AsyncMock(return_value={'suggestions': ['thanks', '[[PHOTO]]', '[whispers] hi', 'thanks'], 'hint': 'internal'}))
    result = await owner_drafts.generate(sender, command('fanvue'))
    sender.regenerate.assert_awaited_once_with('555', seed='draft-1', brief='')
    sender._reconcile.assert_awaited_once_with({'uuid': '555', 'text': ''}, {'fan_uuid': '555'},
                                              mark_read=False, sync_only=True, process_media=False)
    assert result == {'suggestions': ['thanks', 'hi'], 'hint': ''}


def instagram():
    cfg = {'connected': True, 'access_token': 'private', 'ig_user_id': 'ig-account'}
    db = SimpleNamespace(settings=AsyncMock(return_value=cfg),
                         actions=AsyncMock(return_value=[{'target_id': 'thread', 'payload': {'account_id': 'ig-account'}}]),
                         user=AsyncMock(return_value={'igsid': '555'}))
    delivery = SimpleNamespace(ingest=AsyncMock(), offer_state=AsyncMock(return_value={}))
    return SimpleNamespace(_db=db, _delivery=delivery,
        _navrhy=AsyncMock(return_value=(['nice to meet you', '[[PHOTO]]', '[[REMIND]] hello', '[[UNKNOWN]]'], [])),
        regenerate=AsyncMock(), seen=AsyncMock(), send=AsyncMock())


async def test_instagram_refreshes_exact_thread_before_and_after_without_approval(monkeypatch):
    import instagram_api
    sender = instagram()
    raw = {'id': 'thread'}
    fetch = Mock(return_value=raw)
    monkeypatch.setattr(instagram_api, 'conversation', fetch)
    monkeypatch.setattr(instagram_api, 'rozober', Mock(return_value={'igsid': '555', 'spravy': [{'mid': 'x'}]}))
    job = command('instagram')
    before = deepcopy(job)
    assert await owner_drafts.generate(sender, job) == {'suggestions': ['nice to meet you'], 'hint': ''}
    assert job == before
    assert fetch.call_count == 2
    assert sender._delivery.ingest.await_count == 2
    assert all(c.kwargs == {'bootstrap': True, 'process_media': False}
               for c in sender._delivery.ingest.await_args_list)
    sender._navrhy.assert_awaited_once_with({'igsid': '555'}, '555', await sender._db.settings(), seed='draft-1', brief='')
    sender.regenerate.assert_not_awaited()
    sender.seen.assert_not_awaited()
    sender.send.assert_not_awaited()


async def test_instagram_discovers_manual_contact_across_pages(monkeypatch):
    import instagram_api
    sender = instagram()
    sender._db.actions.return_value = []
    page = Mock(side_effect=[{'data': [{'igsid': 'other'}], 'after': 'next'},
                             {'data': [{'igsid': '555', 'id': 'thread'}], 'after': ''}])
    monkeypatch.setattr(instagram_api, 'conversation_page', page)
    monkeypatch.setattr(instagram_api, 'conversation', Mock(return_value={'igsid': '555', 'id': 'thread'}))
    monkeypatch.setattr(instagram_api, 'rozober', lambda raw, account: {**raw, 'spravy': [{'mid': 'x'}]})
    assert (await owner_drafts.generate(sender, command('instagram')))['suggestions']
    assert page.call_count == 2
    assert page.call_args.args[-1] == 'next'


async def test_instagram_wrong_remote_identity_never_imports_or_generates(monkeypatch):
    import instagram_api
    sender = instagram()
    monkeypatch.setattr(instagram_api, 'conversation', Mock(return_value={}))
    monkeypatch.setattr(instagram_api, 'rozober', Mock(return_value={'igsid': 'other', 'spravy': []}))
    assert await owner_drafts.generate(sender, command('instagram')) == {'suggestions': [], 'hint': ''}
    sender._delivery.ingest.assert_not_awaited()
    sender._navrhy.assert_not_awaited()


async def test_instagram_account_switch_during_generation_discards_output(monkeypatch):
    import instagram_api
    sender = instagram()
    cfg = await sender._db.settings()
    sender._db.settings.side_effect = [cfg, cfg, {**cfg, 'ig_user_id': 'other'}]
    monkeypatch.setattr(instagram_api, 'conversation', Mock(return_value={'id': 'thread'}))
    monkeypatch.setattr(instagram_api, 'rozober', Mock(return_value={'igsid': '555', 'spravy': [{'mid': 'x'}]}))
    assert await owner_drafts.generate(sender, command('instagram')) == {'suggestions': [], 'hint': ''}
    sender._navrhy.assert_awaited_once()


async def test_instagram_renders_only_current_configured_link_offer(monkeypatch):
    import instagram_api
    sender = instagram()
    sender._db.settings.return_value.update(funnel_target='telegram', telegram_handle='simona',
                                           telegram_url='https://t.me/simona')
    sender._delivery.offer_state.return_value = {'telegram_link': True, 'link': True}
    sender._navrhy.return_value = (['find me [[TELEGRAM]]', 'https://evil.com', '[[PHOTO]]'], [])
    monkeypatch.setattr(instagram_api, 'conversation', Mock(return_value={'id': 'thread'}))
    monkeypatch.setattr(instagram_api, 'rozober', Mock(return_value={'igsid': '555', 'spravy': [{'mid': 'x'}]}))
    result = await owner_drafts.generate(sender, command('instagram'))
    assert result == {'suggestions': ['find me https://t.me/simona'], 'hint': ''}
    sender._delivery.offer_state.return_value = {'telegram_link': False, 'link': False}
    assert await owner_drafts.generate(sender, command('instagram')) == {'suggestions': [], 'hint': ''}


async def test_telegram_preview_discards_media_directives_and_keeps_plain_prose():
    sender = telegram()
    sender._llm.suggest.return_value = ['[[PHOTO]] here it is', '[[VOICE]] hello', '[whispers] hello',
                                        '[[UNKNOWN]]', '[[broken', 'SKIP', None, 'hello']
    assert (await owner_drafts.generate(sender, command()))['suggestions'] == ['hello']


async def test_telegram_contact_missing_never_generates():
    sender = telegram()
    sender._db.get_user.return_value = None
    assert await owner_drafts.generate(sender, command()) == {'suggestions': [], 'hint': ''}
    sender._llm.suggest.assert_not_awaited()


async def test_fanvue_account_switch_after_llm_discards_output():
    sender = SimpleNamespace(_db=SimpleNamespace(settings=AsyncMock(side_effect=[
        {'connected': True, 'creator_uuid': 'creator'}, {'connected': True, 'creator_uuid': 'other'}])),
        regenerate=AsyncMock(return_value={'suggestions': ['hello']}))
    assert await owner_drafts.generate(sender, command('fanvue')) == {'suggestions': [], 'hint': ''}


async def test_fanvue_explicit_owner_followup_after_native_reply_reuses_live_situation():
    from fanvue_agent import FanvueAgent
    row = {'fan_uuid': '555', 'handle': 'don', 'msg_count': 10}
    db = SimpleNamespace(settings=AsyncMock(return_value={'connected': True, 'creator_uuid': 'creator'}),
                         fan=AsyncMock(return_value=row), behavior=AsyncMock(return_value={}))
    sender = SimpleNamespace(_db=db, _reconcile=AsyncMock(return_value=False),
        _history_rows=AsyncMock(return_value=[{'role': 'assistant', 'content': 'see you later'}]),
        _situacia=AsyncMock(return_value=SimpleNamespace(prompt='LIVE PERSONA SHARED DAY MOOD', tip='')),
        _llm=SimpleNamespace(suggest=AsyncMock(return_value=['how did your day go?'])),
        seen=AsyncMock(), send=AsyncMock())
    sender.regenerate = FanvueAgent.regenerate.__get__(sender)
    job = command('fanvue')
    job['brief'] = 'ask how his day went'
    assert await owner_drafts.generate(sender, job) == {'suggestions': ['how did your day go?'], 'hint': ''}
    assert sender._reconcile.await_count == 2
    assert all(c.kwargs == {'mark_read': False, 'sync_only': True, 'process_media': False}
               for c in sender._reconcile.await_args_list)
    sender._situacia.assert_awaited_once()
    assert sender._situacia.await_args.args[0]['uuid'] == '555'
    system = sender._llm.suggest.await_args.args[0]
    assert 'LIVE PERSONA SHARED DAY MOOD' in system and 'ask how his day went' in system
    assert sender._llm.suggest.await_args.kwargs['seed'] == 'draft-1'
    sender.seen.assert_not_awaited()
    sender.send.assert_not_awaited()


async def test_fanvue_read_failure_cannot_fall_back_to_stored_history():
    sender = SimpleNamespace(_db=SimpleNamespace(settings=AsyncMock(return_value={
        'connected': True, 'creator_uuid': 'creator'})),
        regenerate=AsyncMock(side_effect=TimeoutError('provider unavailable')),
        _llm=SimpleNamespace(suggest=AsyncMock()))
    with pytest.raises(TimeoutError):
        await owner_drafts.generate(sender, command('fanvue'))
    sender._llm.suggest.assert_not_awaited()


async def test_instagram_discovery_cycle_is_bounded(monkeypatch):
    import instagram_api
    sender = instagram()
    sender._db.actions.return_value = []
    page = Mock(return_value={'data': [], 'after': 'same'})
    monkeypatch.setattr(instagram_api, 'conversation_page', page)
    assert await owner_drafts.generate(sender, command('instagram')) == {'suggestions': [], 'hint': ''}
    assert page.call_count == 2
    sender._navrhy.assert_not_awaited()
