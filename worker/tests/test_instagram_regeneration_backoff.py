from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import instagram_api as api
from test_instagram_native_replies import prepared
from test_instagram_semi_rate_preview import synced_source


@pytest.mark.parametrize('limited_during_read', [False, True])
async def test_say_this_can_replace_preview_during_meta_read_backoff(monkeypatch, limited_during_read):
    db, _, agent = await prepared()
    db.queue['1']['state'] = 'approval'
    db.preview_source = lambda igsid: synced_source(db, igsid)
    if not limited_during_read:
        db.nastavenia.update(circuit_reason='meta_4', circuit_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
    def limited(*a, **kw):
        if not limited_during_read: pytest.fail('active circuit must not call Meta')
        raise api.InstagramError('rate', kod=4)
    monkeypatch.setattr(api, 'conversation', limited)
    agent._navrhy = AsyncMock(return_value=(['im from cali, u?'], []))
    result = await agent.regenerate('fan:1', brief='Ja som z Cali a ty? :)')
    assert result['suggestions'] == ['im from cali, u?']
    assert agent._navrhy.call_args.kwargs['brief'] == 'Ja som z Cali a ty? :)'


@pytest.mark.parametrize('change', ['history', 'native', 'account', 'takeover'])
async def test_synced_regeneration_rejects_changes_while_generating(monkeypatch, change):
    db, _, agent = await prepared()
    db.queue['1']['state'] = 'approval'
    db.preview_source = lambda igsid: synced_source(db, igsid)
    db.nastavenia.update(circuit_reason='meta_4', circuit_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: pytest.fail('no provider read'))
    async def generate(*a, **kw):
        if change == 'history': await db.add_message('fan', 'user', 'earlier additional detail', 'late')
        if change == 'native': db.queue['1']['state'] = 'cancelled'
        if change == 'account': db.nastavenia['ig_user_id'] = 'other'
        if change == 'takeover': db.users['fan']['human_takeover'] = True
        return ['im from cali, u?'], []
    agent._navrhy = generate
    assert await agent.regenerate('fan:1', brief='Ja som z Cali a ty? :)') == {}


async def test_expired_delivery_still_allows_private_brief_preview(monkeypatch):
    db, _, agent = await prepared()
    db.queue['1'].update(state='expired', reason='window_expired', source_at='2026-01-01T00:00:00Z')
    db.preview_source = lambda igsid: synced_source(db, igsid)
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: pytest.fail('expired private preview needs no delivery refresh'))
    agent._navrhy = AsyncMock(return_value=(['come see me on my page sometime'], []))
    result = await agent.regenerate('fan:1', brief='invite him to my page')
    assert result['suggestions'] == ['come see me on my page sometime']
    assert db.queue['1']['state'] == 'expired'


async def test_expired_preview_rejects_newer_source(monkeypatch):
    db, _, agent = await prepared()
    db.queue['1'].update(state='expired')
    db.preview_source = AsyncMock(return_value={'mid':'newer','role':'user'})
    monkeypatch.setattr(api, 'conversation', lambda *a, **kw: pytest.fail('no read'))
    agent._navrhy = AsyncMock()
    assert await agent.regenerate('fan:1', brief='invite him') == {}
    agent._navrhy.assert_not_awaited()
