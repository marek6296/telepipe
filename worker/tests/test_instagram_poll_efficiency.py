"""Background sync must not repeatedly expand unchanged message histories."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import instagram_api as api
import instagram_delivery as delivery
from instagram_agent import InstagramAgent
from test_instagram_kolo import FakeDb, FakeLlm, MOJE_ID
from test_instagram_delivery import thread


def setup_poll(monkeypatch):
    stamp=datetime.now(timezone.utc)
    raw=thread(stamp)
    raw['updated_time']=stamp.isoformat()
    index={'id':raw['id'],'updated_time':raw['updated_time']}
    calls=[]
    def page(*args,**kwargs):
        calls.append(kwargs)
        return {'data':[deepcopy(index if kwargs.get('summary_only') else raw)],'after':''}
    monkeypatch.setattr(api,'conversation_page',page)
    details=[]
    def detail(*a,**kw):
        details.append(a[1])
        return deepcopy(raw)
    monkeypatch.setattr(api,'conversation',detail)
    agent=InstagramAgent(FakeDb(reply_mode='semi'),FakeLlm())
    agent._db.preview_source=AsyncMock(return_value={})
    agent._delivery.ingest=AsyncMock()
    agent._delivery.process_one=AsyncMock()
    return agent,raw,index,calls,details


async def test_poll_reads_light_index_and_reuses_unchanged_history(monkeypatch):
    agent,raw,index,calls,details=setup_poll(monkeypatch)
    await agent._delivery.poll()
    await agent._delivery.poll()
    assert all(c.get('summary_only') for c in calls)
    assert details==['thread']
    # Re-run DB effects/enqueue even when the provider snapshot is unchanged.
    assert agent._delivery.ingest.await_count==2
    assert agent._delivery.process_one.await_count==2


async def test_changed_index_fetches_and_ingests_new_message(monkeypatch):
    agent,raw,index,calls,details=setup_poll(monkeypatch)
    await agent._delivery.poll()
    index['updated_time']=(datetime.now(timezone.utc)+timedelta(seconds=3)).isoformat()
    raw['messages']['data'][0]['id']='new-message'
    await agent._delivery.poll()
    assert details==['thread','thread']
    assert agent._delivery.ingest.call_args.args[0]['messages']['data'][0]['id']=='new-message'


async def test_unchanged_index_periodically_refreshes_details(monkeypatch):
    agent,raw,index,calls,details=setup_poll(monkeypatch)
    now=delivery.utcnow()
    monkeypatch.setattr(delivery,'utcnow',lambda:now)
    await agent._delivery.poll()
    now+=timedelta(minutes=11)
    await agent._delivery.poll()
    assert details==['thread','thread']


async def test_failed_ingest_does_not_cache_thread_as_synchronised(monkeypatch):
    agent,raw,index,calls,details=setup_poll(monkeypatch)
    agent._delivery.ingest.side_effect=[RuntimeError('db unavailable'),None]
    with pytest.raises(RuntimeError):await agent._delivery.poll()
    await agent._delivery.poll()
    assert details==['thread','thread']


async def test_same_thread_in_new_account_cannot_reuse_old_snapshot(monkeypatch):
    agent,raw,index,calls,details=setup_poll(monkeypatch)
    await agent._delivery.poll()
    agent._db.nastavenia['ig_user_id']='new-account'
    await agent._delivery.poll()
    assert details==['thread','thread']


def test_poll_index_does_not_expand_messages_or_attachments(monkeypatch):
    from urllib.parse import urlparse,parse_qs
    urls=[]
    monkeypatch.setattr(api,'_volaj',lambda url:urls.append(url) or {'data':[]})
    api.conversation_page('test','account','cursor',summary_only=True)
    params=parse_qs(urlparse(urls[0]).query)
    assert params['fields']==['id,updated_time']
    assert params['after']==['cursor']


async def test_newer_database_message_forces_provider_refresh(monkeypatch):
    agent,raw,index,calls,details=setup_poll(monkeypatch)
    await agent._delivery.poll()
    # A delivery/native refresh imported a newer message between poll cycles.
    agent._db.preview_source=AsyncMock(return_value={'mid':'new-native-reply','role':'assistant'})
    await agent._delivery.poll()
    assert details==['thread','thread']


@pytest.mark.parametrize('known_boundary',[True,False])
async def test_completed_sync_reads_recent_tail_and_expands_only_for_missing_messages(monkeypatch,known_boundary):
    agent=InstagramAgent(FakeDb(reply_mode='semi'),FakeLlm())
    stamp=datetime.now(timezone.utc)
    raw=thread(stamp)
    raw['messages']['data']=[{'id':f'm{i}','created_time':(stamp+timedelta(seconds=i)).isoformat(),'from':{'id':'fan'},'message':f'question {i}'} for i in reversed(range(5))]
    full=deepcopy(raw)
    full['messages']['data'].append({'id':'older','created_time':(stamp-timedelta(seconds=1)).isoformat(),'from':{'id':'fan'},'message':'earlier question'})
    agent._db.known_mids=AsyncMock(return_value={'m0'} if known_boundary else set())
    calls=[]
    def detail(*a,**kw):
        calls.append(kw.get('recent_only',False))
        return deepcopy(raw if kw.get('recent_only') else full)
    monkeypatch.setattr(api,'conversation',detail)
    snapshot=await agent._delivery.poll_snapshot(agent._db.nastavenia,'thread')
    assert calls==([True] if known_boundary else [True,False])
    assert len(snapshot['messages']['data'])==(5 if known_boundary else 6)
