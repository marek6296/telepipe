import pytest
from instagram_interactions import prepare_response

URL='https://www.fanvue.com/sima.sima'


def test_owner_may_send_configured_fanvue_but_automatic_agent_stays_unchanged():
    from instagram_interactions import prepare_operator_response
    text='come chat with me '+URL
    assert prepare_operator_response(text,{}, {},{'cta_link':URL})==dict(kind='dm',text=text,link=True,reminder=False,link_target='fanvue')
    assert not prepare_response(text,{}, {})['text']


@pytest.mark.parametrize('text,configured',[
    ('https://fanvue.com/someone-else',URL),
    (URL+' https://evil.example',URL),
    ('[[LINK]] '+URL,URL),
    (URL,'https://evil.example'),
    ('https://www.fanvue.com.evil.example/sima.sima',URL),
])
def test_owner_exception_is_only_one_exact_configured_fanvue_destination(text,configured):
    from instagram_interactions import prepare_operator_response
    assert not prepare_operator_response(text,{}, {},{'cta_link':configured})['text']


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['send_text','approve'])
@pytest.mark.parametrize('kind',['fanvue','telegram','bio_link'])
async def test_owner_fanvue_uses_existing_seen_pause_reserved_send(monkeypatch,operation,kind):
    from datetime import datetime,timezone
    from unittest.mock import AsyncMock
    import instagram_api as api
    import operator_delivery
    from instagram_agent import InstagramAgent
    from test_social_instagram import OperatorDb
    from test_instagram_delivery import thread
    from test_instagram_kolo import FakeLlm,MOJE_ID
    from test_social_commands import command
    raw=thread(datetime.now(timezone.utc))
    db=OperatorDb(reply_mode='semi',funnel_target='both',telegram_handle='simapussina',bio_link='https://linkovne.com/simonakralova')
    text={'fanvue':URL,'telegram':'https://t.me/simapussina','bio_link':'https://linkovne.com/simonakralova'}[kind]
    db.persona=AsyncMock(return_value={'cta_link':URL})
    agent=InstagramAgent(db,FakeLlm())
    await db.ensure_user('fan')
    db.users['fan']['age_state']='unknown'
    monkeypatch.setattr(api,'conversation_page',lambda *a,**kw:{'data':[raw],'after':''})
    monkeypatch.setattr(api,'conversation',lambda *a,**kw:raw)
    events=[]
    monkeypatch.setattr(api,'mark_seen',lambda *a,**kw:events.append('seen'))
    async def pause(text):events.append('pause')
    monkeypatch.setattr(operator_delivery,'composition_pause',pause)
    monkeypatch.setattr(api,'posli_text',lambda token,fan,text,**kw:events.append(text) or {'message_id':'sent'})
    original=db.rpc
    async def rpc(name,**kwargs):
        if name=='reserve':assert kwargs['link'] is True
        return await original(name,**kwargs)
    db.rpc=rpc
    result=await agent.deliver_operator(command(operation=operation,channel='instagram',external_id='fan',account_scope=MOJE_ID,text=text),AsyncMock(return_value=True))
    assert result.status=='done'
    assert events==['seen','pause',text]
    db.hub.record_invite.assert_awaited_once_with('instagram','fan','linkpage' if kind=='bio_link' else kind,scope=MOJE_ID)


@pytest.mark.parametrize('target,url',[
    ('telegram','https://t.me/simapussina'),('bio_link','https://linkovne.com/simonakralova')])
def test_owner_configured_site_is_not_gated_by_automatic_invitation_eligibility(target,url):
    from instagram_interactions import prepare_operator_response
    cfg={'funnel_target':'off','telegram_handle':'simapussina','bio_link':'https://linkovne.com/simonakralova'}
    assert prepare_operator_response(url,cfg,{'age_unknown':True,'telegram_link':False,'bio_link':False},{})['text']==url
    assert not prepare_response(url,cfg,{'age_unknown':True,'telegram_link':False,'bio_link':False})['text']
