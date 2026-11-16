from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import conversation_timing
from instagram_agent import InstagramAgent
from test_instagram_kolo import FakeDb, FakeLlm, FakeControl, mock_threads, MOJE_ID


def conversation(*, text_age=10, answered=False, question=True):
    now = datetime.now(timezone.utc)
    messages = []
    if question:
        messages.append({'id': 'question', 'from': {'id': 'fan'},
                         'created_time': (now-timedelta(hours=text_age)).isoformat(),
                         'message': 'Are you busy? Is the distance a problem?'})
    if answered:
        messages.append({'id': 'answer', 'from': {'id': MOJE_ID},
                         'created_time': (now-timedelta(hours=8)).isoformat(), 'message': 'not a problem'})
    messages.append({'id': 'media', 'from': {'id': 'fan'},
                     'created_time': (now-timedelta(hours=2)).isoformat(), 'attachments': {'data': []}})
    return {'id': 'thread', 'messages': {'data': list(reversed(messages))}}


def rich_history(raw):
    import instagram_api
    return [dict(role=m['role'], content=m['content'], occurred_at=m['created_time'],
                 metadata={'kind':m['kind']}) for m in instagram_api.rozober(raw, MOJE_ID)['spravy']]


@pytest.mark.parametrize('mode', ['semi', 'auto'])
async def test_trailing_unknown_does_not_hide_unanswered_text_or_extend_its_window(mode):
    db = FakeDb(reply_mode=mode)
    agent = InstagramAgent(db, FakeLlm())
    raw = conversation()
    await agent._delivery.ingest(raw, db.nastavenia)
    await agent._delivery.ingest(raw, db.nastavenia)
    assert len(db.queue) == 1
    action = db.queue['1']
    assert action['kind'] == 'dm'
    assert action['source_mid'] == 'media', 'freshness is still tied to the latest remote event'
    assert action['payload']['reply_to_mid'] == 'question'
    question_time = datetime.fromisoformat(raw['messages']['data'][-1]['created_time'])
    assert datetime.fromisoformat(action['source_at']) == question_time
    assert datetime.fromisoformat(action['expires_at']) == question_time + timedelta(hours=24)


@pytest.mark.parametrize('changes', [{'text_age':25}, {'answered':True}, {'question':False}])
async def test_unknown_does_not_revive_expired_answered_or_nonexistent_question(changes):
    db = FakeDb(reply_mode='semi')
    await InstagramAgent(db, FakeLlm())._delivery.ingest(conversation(**changes), db.nastavenia)
    assert not db.queue


@pytest.mark.parametrize('state', ['skipped', 'sent', 'sending', 'uncertain'])
@pytest.mark.parametrize('fallback_before', [False, True])
async def test_unknown_cannot_revive_terminal_or_inflight_question(state, fallback_before):
    db = FakeDb(reply_mode='semi')
    db.queue['old'] = dict(id='old', igsid='fan', state=state,
                          source_mid='old-media' if fallback_before else 'question',
                          payload={'reply_to_mid':'question'} if fallback_before else {})
    await InstagramAgent(db, FakeLlm())._delivery.ingest(conversation(), db.nastavenia)
    assert len(db.queue) == 1


async def test_unreadable_tail_does_not_turn_contact_optout_into_reply():
    db = FakeDb(reply_mode='semi')
    raw = conversation()
    raw['messages']['data'][-1]['message'] = 'stop messaging me'
    await InstagramAgent(db, FakeLlm())._delivery.ingest(raw, db.nastavenia)
    assert not db.queue
    assert db.users['fan']['no_initiate'] is True


@pytest.mark.parametrize('when', ['before_generation', 'after_generation'])
@pytest.mark.parametrize('closed', ['skipped', 'deleted', 'optout'])
async def test_target_must_still_be_available_and_not_skipped_before_sending(monkeypatch, when, closed):
    import instagram_api as api
    raw = conversation()
    db, llm = FakeDb(), FakeLlm(odpoved='not a problem')
    agent = InstagramAgent(db,llm)
    await agent._delivery.ingest(raw,db.nastavenia)
    db.queue['1']['due_at'] = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    calls = 0
    def refresh(*args,**kwargs):
        nonlocal calls
        calls += 1
        if when == 'before_generation' or calls >= 2:
            if closed == 'skipped':
                db.queue['old'] = dict(id='old',igsid='fan',state='skipped',source_mid='question',payload={})
            elif closed == 'deleted':
                return {'id':'thread','messages':{'data':raw['messages']['data'][:1]}}
            else:
                raw['messages']['data'][-1]['message'] = 'stop messaging me'
        return raw
    monkeypatch.setattr(api,'conversation',refresh)
    sends=[]
    monkeypatch.setattr(api,'mark_seen',lambda *a,**k:None)
    monkeypatch.setattr(api,'posli_text',lambda *a,**k:sends.append(1))
    await agent._delivery.process_one(db.nastavenia)
    assert not sends
    assert db.queue['1']['state'] == 'cancelled'


def test_media_gap_keeps_unanswered_question_in_focus_without_inventing_media():
    turn = conversation_timing.analyze(rich_history(conversation()))
    assert 'Are you busy?' in turn.latest_text
    assert len(turn.incoming) == 2
    assert 'unreadable attachment' in turn.prompt
    assert 'Do not infer' in turn.prompt


def test_real_new_greeting_after_media_still_starts_new_session():
    rows = rich_history(conversation())
    rows.append(dict(role='user',content='Hi beautiful',metadata={'kind':'dm'},occurred_at=datetime.now(timezone.utc).isoformat()))
    turn = conversation_timing.analyze(rows)
    assert turn.latest_text == 'Hi beautiful'
    assert turn.has_greeting


async def test_semi_media_tail_generates_owner_card_without_seen_or_send(monkeypatch):
    import instagram_api as api
    raw = conversation()
    db, llm, ctrl = FakeDb(reply_mode='semi'), FakeLlm(navrhy=['not a problem']), FakeControl()
    db.history = AsyncMock(return_value=rich_history(raw))
    agent = InstagramAgent(db,llm,ctrl)
    mock_threads(monkeypatch,[raw])
    seen, sent = [], []
    monkeypatch.setattr(api,'mark_seen',lambda *a,**k:seen.append(1))
    monkeypatch.setattr(api,'posli_text',lambda *a,**k:sent.append(1))
    await agent._delivery.ingest(raw,db.nastavenia)
    await agent._delivery.process_one(db.nastavenia)
    assert len(ctrl.karty) == 1
    assert 'latest 2 unanswered' in llm.prompty[0]
    assert not seen and not sent
    assert db.queue['1']['state'] == 'approval'
