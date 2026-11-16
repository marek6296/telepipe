from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock
import pytest
import instagram_api as api
from instagram_agent import InstagramAgent
from test_instagram_kolo import FakeDb,FakeLlm,FakeControl,mock_threads
from test_instagram_delivery import thread

@pytest.mark.asyncio
async def test_recent_unanswered_before_enable_is_recovered_once(monkeypatch):
    now=datetime.now(timezone.utc)
    db=FakeDb(reply_mode='semi',replies_started_at=now.isoformat())
    agent=InstagramAgent(db,FakeLlm())
    incoming=thread(now-timedelta(hours=2))
    await agent._delivery.ingest(incoming,db.nastavenia)
    await agent._delivery.ingest(incoming,db.nastavenia)
    assert len(db.queue)==1
    assert datetime.fromisoformat(db.queue['1']['due_at']) <= datetime.now(timezone.utc)
    assert db.queue['1']['source_at']==(now-timedelta(hours=2)).isoformat()

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['semi','auto'])
async def test_semi_proposal_and_approval_ignore_schedule_but_auto_waits(monkeypatch,mode):
    now=datetime.now(timezone.utc)
    db=FakeDb(reply_mode=mode)
    db.hub.day.return_value=(None,'calm')
    ctrl=FakeControl()
    agent=InstagramAgent(db,FakeLlm(),control=ctrl)
    incoming=thread(now)
    mock_threads(monkeypatch,[incoming])
    seen=[]; sent=[]
    monkeypatch.setattr(api,'mark_seen',lambda *a,**k:seen.append('seen'),raising=False)
    monkeypatch.setattr(api,'posli_text',lambda *a,**k:sent.append('sent') or {'message_id':'out'})
    await agent._delivery.ingest(incoming,db.nastavenia)
    db.queue['1']['due_at']=(now-timedelta(seconds=1)).isoformat()
    await agent._delivery.process_one(db.nastavenia)
    assert not seen and not sent
    if mode=='auto':
        assert db.queue['1']['reason']=='sleeping'
        assert not ctrl.karty
        return
    assert len(ctrl.karty)==1
    assert await agent._delivery.approve('fan:1','hello')
    await agent._delivery.process_one(db.nastavenia)
    assert seen==['seen'] and sent==['sent']

@pytest.mark.asyncio
async def test_seen_only_after_reservation_not_during_ingest_or_generation(monkeypatch):
    now=datetime.now(timezone.utc)
    db=FakeDb()
    agent=InstagramAgent(db,FakeLlm())
    incoming=thread(now)
    mock_threads(monkeypatch,[incoming])
    events=[]
    monkeypatch.setattr(api,'mark_seen',lambda *a,**k:events.append('seen'),raising=False)
    monkeypatch.setattr(api,'posli_text',lambda *a,**k:events.append('send') or {'message_id':'out'})
    async def generate(*args):
        events.append('generate')
        return 'hello'
    agent._napis=generate
    original=db.rpc
    async def rpc(name,**kw):
        if name=='reserve': events.append('reserve')
        return await original(name,**kw)
    db.rpc=rpc
    await agent._delivery.ingest(incoming,db.nastavenia)
    assert not events
    db.queue['1']['due_at']=(now-timedelta(seconds=1)).isoformat()
    await agent._delivery.process_one(db.nastavenia)
    assert events==['generate','reserve','seen','send']


def test_provider_reads_do_not_mark_seen_and_explicit_receipt_is_separate(monkeypatch):
    calls=[]
    monkeypatch.setattr(api,'_volaj',lambda url,data=None,**kw: calls.append((url,data)) or {})
    api.conversation_page('test','account')
    api.conversation('test','thread')
    assert all(data is None for _,data in calls)
    api.mark_seen('test','account','fan')
    assert calls[-1][1]=={'recipient':{'id':'fan'},'sender_action':'mark_seen'}


@pytest.mark.asyncio
@pytest.mark.parametrize('flip_at',['refresh','seen'])
@pytest.mark.parametrize('new_mode',['auto','off'])
async def test_mode_change_to_auto_never_sends_a_semi_reply_outside_hours(monkeypatch,flip_at,new_mode):
    now=datetime.now(timezone.utc)
    db=FakeDb(reply_mode='semi')
    agent=InstagramAgent(db,FakeLlm())
    incoming=thread(now)
    mock_threads(monkeypatch,[incoming])
    await agent._delivery.ingest(incoming,db.nastavenia)
    db.queue['1'].update(state='ready',text='approved reply',due_at=(now-timedelta(seconds=1)).isoformat())
    db.queue['1']['payload']['approved_source_mid']='incoming'
    db.hub.day.return_value=(None,'calm')
    events=[]
    def refresh(*a,**k):
        if flip_at=='refresh': db.nastavenia['reply_mode']=new_mode
        return incoming
    def seen(*a,**k):
        events.append('seen')
        if flip_at=='seen': db.nastavenia['reply_mode']=new_mode
    monkeypatch.setattr(api,'conversation',refresh)
    monkeypatch.setattr(api,'mark_seen',seen)
    monkeypatch.setattr(api,'posli_text',lambda *a,**k:events.append('send') or {'message_id':'out'})
    await agent._delivery.process_one(dict(db.nastavenia))
    assert 'send' not in events
    if flip_at=='refresh': assert not events
    assert db.queue['1']['state']=='pending'
    assert db.queue['1'].get('reserved_at') is None
