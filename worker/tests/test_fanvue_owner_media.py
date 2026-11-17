from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from fanvue_owner_media import FanvueOwnerMedia, ready_media, media_item
from fanvue_api import Fanvue
A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
def api(body,status=200):
    return SimpleNamespace(_headers=AsyncMock(return_value={}),_client=SimpleNamespace(request=AsyncMock(return_value=httpx.Response(status,json=body,request=httpx.Request('GET','https://api.fanvue.com/media')))))
async def test_ready_bundle_is_scoped_and_all_ready():
    client=api({'data':{A:{'uuid':A,'status':'ready','mediaType':'image'},B:{'uuid':B,'status':'processing','mediaType':'video'}}})
    assert not await ready_media(client,[A,B])
    assert not await ready_media(client,[A,A])
    assert await ready_media(client,[A])
    assert client._client.request.call_args.kwargs['params']['variants']=='thumbnail,main'
async def test_vault_and_status_never_mark_seen_or_send():
    client=api({'data':[{'uuid':A,'status':'ready','mediaType':'image','variants':[{'variantType':'thumbnail','url':'https://cdn.fanvue.com/test'}]}],'pagination':{'hasMore':True}})
    sender=SimpleNamespace(_api=client,_db=SimpleNamespace(folders=AsyncMock(return_value=[{'name':'Photos'}])))
    manager=FanvueOwnerMedia(None,'model','worker',None)
    result=await manager.handle(sender,{'action':'list','input':{'page':1}})
    assert result['hasMore'] and result['items'][0]['uuid']==A
    client._client.request.assert_awaited_once()
    assert client._client.request.call_args.args[:2]==('GET','/media')
async def test_complete_requires_exact_parts_before_provider_call():
    manager=FanvueOwnerMedia(None,'model','worker',None)
    manager.upload_session=AsyncMock(return_value={'uploadId':'private/session','totalParts':2,'mediaUuid':A})
    sender=SimpleNamespace(_api=api({}))
    with pytest.raises(ValueError,match='missing parts'):
        await manager.handle(sender,{'action':'complete','input':{'parts':[{'PartNumber':1,'ETag':'etag'}]}})
    sender._api._client.request.assert_not_awaited()
async def test_wrong_account_request_fails_without_provider_access():
    t=SimpleNamespace(_rpc=AsyncMock(side_effect=[{'id':A,'lease_token':'lease','account_scope':'fanvue:old'},True]))
    sender=SimpleNamespace(_db=SimpleNamespace(settings=AsyncMock(return_value={'connected':True,'creator_uuid':'new'})))
    manager=FanvueOwnerMedia(t,'model','worker',SimpleNamespace(_senders={'fanvue':sender}))
    await manager.tick()
    assert 'account changed' in t._rpc.call_args.args[1]['p_error']
@pytest.mark.parametrize('price',[0,1250])
async def test_send_operator_exact_media_price_and_provider_id(price):
    client=Fanvue.__new__(Fanvue);client._headers=AsyncMock(return_value={})
    client._client=SimpleNamespace(post=AsyncMock(return_value=httpx.Response(201,json={'messageUuid':'provider-id'})))
    result=await client.send_operator('fan','caption',media_uuids=[A,B],price_cents=price,before_send=AsyncMock(return_value=True))
    assert result.status=='done' and result.result['provider_message_id']=='provider-id'
    payload=client._client.post.call_args.kwargs['json']
    assert payload['mediaUuids']==[A,B] and payload['text']=='caption'
    assert payload.get('price',0)==price
    assert ('price' in payload)==bool(price)
async def test_media_send_timeout_is_never_guessed_as_failure():
    client=Fanvue.__new__(Fanvue);client._headers=AsyncMock(return_value={})
    client._client=SimpleNamespace(post=AsyncMock(side_effect=httpx.ReadTimeout('lost')))
    assert (await client.send_operator('fan','',media_uuids=[A],price_cents=300)).status=='uncertain'
def test_thumbnail_rejects_unsafe_urls():
    assert not media_item({'variants':[{'variantType':'thumbnail','url':'javascript:bad'}]})['thumb']

async def test_media_not_ready_blocks_before_seen(monkeypatch):
    from test_fanvue_native_sync import setup
    agent, db, client, cards = setup()
    monkeypatch.setattr('fanvue_owner_media.ready_media',AsyncMock(return_value=False))
    job={'operation':'send_media','external_id':'fan','account_scope':'fanvue:creator','text':'','media_uuids':[A],'price_cents':300}
    result=await agent.deliver_operator(job,AsyncMock(return_value=True))
    assert result.reason=='media_not_ready' and client.seen==[] and client.sent==[]

async def test_owner_metadata_and_chat_share_one_rotating_token_refresh(monkeypatch):
    import asyncio
    from datetime import datetime, timedelta, timezone
    state={'connected':True,'refresh_token':'old','expires_at':None,'access_token':''}
    async def save(patch): state.update(patch)
    async def settings():return dict(state)
    async def respond(*args,**kwargs):
        await asyncio.sleep(0)
        return httpx.Response(200,json={'access_token':'new-access','refresh_token':'new-refresh','expires_in':3600})
    post=AsyncMock(side_effect=respond)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:SimpleNamespace(post=post))
    client=Fanvue.__new__(Fanvue);client._token='';client._expires=None;client._id='app';client._secret='secret'
    client._db=SimpleNamespace(settings=settings,save=save)
    tokens=await asyncio.gather(client._access_token(fresh=True),client._access_token(fresh=True))
    assert tokens==['new-access','new-access']
    post.assert_awaited_once()
    assert state['refresh_token']=='new-refresh'

async def test_new_uploaded_media_gets_parent_before_send_receipt():
    client=api({'data':{A:{'uuid':A,'status':'ready','mediaType':'video'}}})
    db=SimpleNamespace(upsert_media=AsyncMock())
    assert await ready_media(client,[A],db=db)
    saved=db.upsert_media.call_args.args[0][0]
    assert saved['media_uuid']==A and saved['kind']=='video'
    assert 'price_cents' not in saved and 'active' not in saved and 'caption' not in saved
