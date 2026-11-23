"""A read backoff must not suppress drafts for already imported input."""
from datetime import datetime, timedelta, timezone
import pytest
import instagram_api as api
from test_instagram_native_replies import prepared, INCOMING, NATIVE, snapshot


async def synced_source(db, igsid):
    rows = [m for m in db.spravy if m['igsid'] == igsid]
    return dict(rows[-1]) if rows else {}


@pytest.mark.asyncio
async def test_rate_limit_prepares_existing_inbound_without_seen_or_send(monkeypatch):
    db, control, agent = await prepared()
    db.preview_source = lambda igsid: synced_source(db, igsid)
    reads, seen, sent = [], [], []
    def limited(*args, **kw):
        reads.append(True)
        raise api.InstagramError('rate limited', kod=4)
    monkeypatch.setattr(api, 'conversation', limited)
    monkeypatch.setattr(api, 'mark_seen', lambda *a, **kw: seen.append(True))
    monkeypatch.setattr(api, 'posli_text', lambda *a, **kw: sent.append(True))
    await agent._delivery.process_one(db.nastavenia)
    assert len(control.karty) == 1
    assert db.queue['1']['state'] == 'approval'
    assert control.karty[0]['source_message_id'] == 1
    assert len(reads) == 1 and not seen and not sent


@pytest.mark.asyncio
async def test_existing_rate_circuit_prepares_synced_input_without_provider_calls(monkeypatch):
    db, control, agent = await prepared()
    db.preview_source = lambda igsid: synced_source(db, igsid)
    db.nastavenia.update(circuit_reason='meta_4', circuit_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: pytest.fail('circuit must not call Meta'))
    monkeypatch.setattr(api, 'conversation_page', lambda *a, **kw: pytest.fail('circuit must not call Meta'))
    await agent._delivery.poll()
    assert len(control.karty) == 1
    assert db.queue['1']['state'] == 'approval'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['new_input','native_reply','takeover','mode','account','revoked'])
async def test_fallback_rejects_context_or_permission_changes(monkeypatch,change):
    db, control, agent = await prepared()
    db.preview_source = lambda igsid: synced_source(db, igsid)
    def limited(*a, **kw): raise api.InstagramError('rate',kod=4 if change!='revoked' else 190)
    monkeypatch.setattr(api, 'conversation', limited)
    original = agent._navrhy
    async def generate(*args, **kw):
        result = await original(*args, **kw)
        if change=='new_input': await db.add_message('fan','user','new question','in-2')
        if change=='native_reply': await agent._delivery.ingest(snapshot(INCOMING,NATIVE),db.nastavenia)
        if change=='takeover': db.users['fan']['human_takeover']=True
        if change=='mode': db.nastavenia['reply_mode']='auto'
        if change=='account': db.nastavenia['ig_user_id']='another-account'
        return result
    agent._navrhy=generate
    await agent._delivery.process_one(db.nastavenia)
    assert not control.karty
    assert db.queue['1']['state'] != 'approval'


@pytest.mark.asyncio
async def test_preview_source_is_tenant_scoped_and_orders_by_provider_time():
    from unittest.mock import AsyncMock
    from instagram_tenant import TenantInstagramDb
    transport=AsyncMock()
    transport._get.return_value=[{'mid':'provider-mid','role':'user'}]
    db=TenantInstagramDb(transport,'model','')
    assert await db.preview_source('fan') == {'mid':'provider-mid','role':'user'}
    transport._get.assert_awaited_once_with('/ig_messages',{'model_id':'eq.model',
        'igsid':'eq.fan','select':'mid,role','order':'occurred_at.desc.nullslast,id.desc','limit':'1'})


async def test_normal_semi_poll_does_not_refetch_meta_to_generate_private_draft(monkeypatch):
    db,control,agent=await prepared()
    db.preview_source=lambda igsid:synced_source(db,igsid)
    monkeypatch.setattr(api,'conversation_page',lambda *a,**kw:{'data':[snapshot(INCOMING)],'after':''})
    monkeypatch.setattr(api,'conversation',lambda *a,**kw:pytest.fail('Private drafts use the history just synchronised'))
    await agent._delivery.poll()
    assert len(control.karty)==1
    assert db.queue['1']['state']=='approval'


async def test_read_rate_cooldown_is_bounded_and_increases_on_repeated_failures(monkeypatch):
    import instagram_delivery
    db,_,agent=await prepared()
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(instagram_delivery,'utcnow',lambda:now)
    for minutes in [5,10,20,40,60,60]:
        await agent._delivery.provider_error(api.InstagramError('rate',kod=4,http_status=400),during_read=True)
        until=datetime.fromisoformat(db.nastavenia['circuit_until'])
        assert until-now==timedelta(minutes=minutes)


async def test_rate_cooldown_respects_provider_wait_but_unknown_post_keeps_hour(monkeypatch):
    import instagram_delivery
    db,_,agent=await prepared()
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(instagram_delivery,'utcnow',lambda:now)
    await agent._delivery.provider_error(api.InstagramError('rate',kod=4,http_status=400,retry_after_seconds=1200),during_read=True)
    assert datetime.fromisoformat(db.nastavenia['circuit_until'])-now==timedelta(minutes=20)
    await agent._delivery.provider_error(api.InstagramError('ambiguous',kod=4,http_status=500))
    assert datetime.fromisoformat(db.nastavenia['circuit_until'])-now==timedelta(hours=1)


async def test_late_read_rejection_cannot_shorten_existing_send_cooldown(monkeypatch):
    import instagram_delivery
    db,_,agent=await prepared()
    now=datetime.now(timezone.utc)
    monkeypatch.setattr(instagram_delivery,'utcnow',lambda:now)
    db.nastavenia.update(circuit_reason='meta_4',circuit_until=(now+timedelta(hours=1)).isoformat())
    await agent._delivery.provider_error(api.InstagramError('rate',kod=4,http_status=400),during_read=True)
    assert datetime.fromisoformat(db.nastavenia['circuit_until'])==now+timedelta(hours=1)


async def test_semi_poll_retires_non_text_actions_instead_of_deferring_forever(monkeypatch):
    db,control,agent=await prepared()
    db.preview_source=lambda igsid:synced_source(db,igsid)
    db.queue['1']['kind']='reaction'
    monkeypatch.setattr(api,'conversation_page',lambda *a,**kw:{'data':[snapshot(INCOMING)],'after':''})
    await agent._delivery.poll()
    assert db.queue['1']['state']=='skipped'
    assert not control.karty
