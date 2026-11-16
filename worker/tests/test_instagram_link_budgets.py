from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from instagram_interactions import prepare_response, link_budgets
from instagram_delivery import InstagramDelivery
NOW = datetime(2026, 11, 17, 3, tzinfo=timezone.utc)
CFG = dict(funnel_target='both', telegram_handle='simapussina', bio_link='https://linkovne.com/simonakralova', ig_user_id='account', highlights_link=True)
OFFER = dict(link=True, telegram_link=True, bio_link=True)
def prior(target, hours):
    return dict(reserved_at=(NOW-timedelta(hours=hours)).isoformat(), payload={'link_target':target})

def test_both_destinations_are_exact_and_selected_per_reply():
    for marker,target,url in [('TELEGRAM','telegram','https://t.me/simapussina'),('LINKPAGE','bio_link',CFG['bio_link']),('LINK','telegram','https://t.me/simapussina')]:
        result=prepare_response('come say hi [['+marker+']]',CFG,OFFER)
        assert result['text']=='come say hi '+url
        assert result['link_target']==target
        assert prepare_response('come say hi '+url,CFG,OFFER)['text']==result['text']
    assert not prepare_response('[[TELEGRAM]] [[LINKPAGE]]',CFG,OFFER)['text']
    assert not prepare_response('hi https://t.me/somebody_else',CFG,OFFER)['text']

def test_a_stale_approved_url_never_silently_changes_destination():
    limited=dict(OFFER, bio_link=False)
    assert not prepare_response('hi '+CFG['bio_link'],CFG,limited)['text']
    assert prepare_response('hi [[TELEGRAM]]',CFG,limited)['link']
    assert not prepare_response('hi [[TELEGRAM]]',dict(CFG,funnel_target='bio_link'),OFFER)['text']

def test_telegram_has_four_slots_linkpage_two_with_rolling_la_and_gaps():
    assert link_budgets([prior('bio_link',5),prior('bio_link',10)],CFG,NOW)=={'telegram':True,'bio_link':False}
    assert link_budgets([prior('telegram',3),prior('telegram',6),prior('telegram',9)],CFG,NOW)['telegram']
    assert not link_budgets([prior('telegram',3),prior('telegram',6),prior('telegram',9),prior('telegram',12)],CFG,NOW)['telegram']
    assert not link_budgets([prior('telegram',1.5)],CFG,NOW)['telegram']
    assert not link_budgets([prior('bio_link',3)],CFG,NOW)['bio_link']
    assert not any(link_budgets([prior('bio_link',.5)],CFG,NOW).values())
    assert not link_budgets([prior('bio_link',5),prior('bio_link',23)],CFG,NOW)['bio_link']
    assert link_budgets([prior('bio_link',25)],CFG,NOW)['bio_link']

def test_unknown_manual_urls_count_conservatively_in_both_budgets():
    assert not link_budgets([prior('unknown',5),prior('unknown',10)],CFG,NOW)['bio_link']
    assert not any(link_budgets([prior('unknown',h) for h in (3,6,9,12)],CFG,NOW).values())

@pytest.mark.asyncio
async def test_offer_still_never_sends_second_url_to_same_person(monkeypatch):
    monkeypatch.setattr('instagram_delivery.utcnow',lambda:NOW)
    db=AsyncMock(model_id='model'); db.actions.return_value=[]
    db.hub.restrictions.return_value={}; db.hub.linked.return_value=[]
    offer=await InstagramDelivery(db,AsyncMock()).offer_state(CFG,dict(igsid='fan',age_state='adult_self_declared',link_sent_at=NOW.isoformat()))
    assert not offer['telegram_link'] and not offer['bio_link']
    assert offer['remind']

@pytest.mark.asyncio
async def test_highlights_can_replace_spent_linkpage_while_telegram_remains(monkeypatch):
    monkeypatch.setattr('instagram_delivery.utcnow',lambda:NOW)
    db=AsyncMock(model_id='model'); db.actions.return_value=[prior('bio_link',5),prior('bio_link',10)]
    db.hub.restrictions.return_value={}; db.hub.linked.return_value=[]
    offer=await InstagramDelivery(db,AsyncMock()).offer_state(CFG,dict(igsid='fan',age_state='adult_self_declared'))
    assert offer['telegram_link'] and not offer['bio_link'] and offer['highlights']

@pytest.mark.asyncio
async def test_semi_proposals_show_the_exact_url_before_owner_approval():
    from instagram_agent import InstagramAgent
    from test_instagram_kolo import FakeDb, FakeLlm
    db=FakeDb(**CFG)
    user=await db.ensure_user('fan')
    db.spravy=[dict(igsid='fan',role='user',content='where can we keep chatting?',mid='source')]
    agent=InstagramAgent(db,FakeLlm(navrhy=['come say hi [[TELEGRAM]]']))
    proposals,_=await agent._navrhy(user,'fan',db.nastavenia)
    assert len(proposals)==1
    assert 'https://t.me/simapussina' in proposals[0]
    assert '[[' not in proposals[0]


def test_conversation_pages_bound_nested_read_cost(monkeypatch):
    import urllib.parse
    import instagram_api as api
    queries=[]
    monkeypatch.setattr(api,'_volaj',lambda url: queries.append(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)) or {'data':[]})
    api.conversation_page('test','account','cursor')
    assert int(queries[0]['limit'][0]) <= 5
    assert queries[0]['after']==['cursor']


@pytest.mark.asyncio
@pytest.mark.parametrize('reply,expected', [('already in our chat [[REMIND]]',None), ('check my highlights [[HIGHLIGHTS]]','linkpage')])
async def test_reminders_keep_original_identity_destination(monkeypatch,reply,expected):
    from test_instagram_kolo import FakeDb, FakeLlm, mock_threads
    from test_instagram_delivery import thread
    from instagram_agent import InstagramAgent
    import instagram_api as api
    now=datetime.now(timezone.utc)
    db=FakeDb(**CFG)
    agent=InstagramAgent(db,FakeLlm())
    mock_threads(monkeypatch,[thread(now)])
    await agent._delivery.ingest(thread(now),db.nastavenia)
    db.queue['1']['due_at']=(now-timedelta(minutes=1)).isoformat()
    agent._napis=AsyncMock(return_value=reply)
    agent._delivery.offer_state=AsyncMock(return_value={'remind':True,'highlights':True})
    monkeypatch.setattr(api,'posli_text',lambda *a,**k:{'message_id':'sent'})
    await agent._delivery.process_one(db.nastavenia)
    assert db.queue['1']['state']=='sent'
    if expected:
        assert db.hub.record_invite.call_args.args[2]==expected
    else:
        db.hub.record_invite.assert_not_called()
