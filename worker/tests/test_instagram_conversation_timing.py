from datetime import datetime, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

import instagram_agent
import prehlad
from instagram_tenant import TenantInstagramDb
from test_instagram_kolo import FakeDb
from test_conversation_timing import reopened, NOW


@pytest.mark.parametrize('path', ['auto', 'semi', 'regenerate', 'brief'])
async def test_current_greeting_survives_every_instagram_generation_path(path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz or timezone.utc)
    monkeypatch.setattr(instagram_agent, 'datetime', Clock)
    db = FakeDb()
    db.history = AsyncMock(return_value=reopened())
    user = await db.ensure_user('fan', 'visitor')
    user['msg_count'] = 8
    llm = AsyncMock()
    llm.reply.return_value = 'hey honey im here'
    llm.suggest.return_value = ['hey honey im here', 'hi you im here']
    agent = instagram_agent.InstagramAgent(db, llm)
    # This test isolates prompt chronology; provider freshness has dedicated
    # native-reply race regressions with actual snapshots and state changes.
    agent._delivery.refresh_regeneration = AsyncMock(return_value=True)
    if path == 'auto':
        out = await agent._napis(user, 'fan', db.nastavenia)
        call = llm.reply.call_args
    elif path == 'semi':
        proposals, history = await agent._navrhy(user, 'fan', db.nastavenia)
        out, call = proposals[0], llm.suggest.call_args
        assert history == reopened()
    else:
        result = await agent.regenerate('fan', brief='tell him you are here' if path == 'brief' else '')
        out, call = result['suggestions'][0], llm.suggest.call_args
    assert out.startswith('hey'), 'sanitizer must not remove a greeting from the current inbound block'
    system, messages = call.args[:2]
    assert 'CURRENT TURN contains the latest 2' in system
    assert 'reopened conversation' in system
    assert 'ÚPLNE PRVÁ' not in system, 'an established chat must not be described as a stranger'
    assert 'BACKGROUND' in messages[1]['content']
    assert '09:40 PST' in messages[2]['content']
    assert all(set(m) == {'role', 'content'} for m in messages)


async def test_instagram_history_retains_source_time_not_ingestion_time():
    transport = AsyncMock()
    transport._get.return_value = [{'role': 'user', 'content': 'Hi', 'occurred_at': '2026-11-16T17:40:52Z', 'created_at': '2026-11-17T01:00:00Z'}]
    db = TenantInstagramDb(transport, 'model', '')
    history = await db.history('fan')
    assert 'occurred_at' in transport._get.call_args.args[1]['select']
    assert history[0]['occurred_at'] == '2026-11-16T17:40:52Z'


def test_owner_card_shows_local_dates_and_preserves_speaker_prefix():
    card = prehlad.blok_rozhovoru(reopened(), now_local=NOW)
    lines = card.splitlines()
    assert lines[0].startswith(prehlad.JEJ)
    assert '11-15 15:33 PST' in lines[0]
    assert '11-16 09:40 PST' in lines[2]


def test_multi_message_instruction_counts_only_the_current_turn():
    assert '2 správy' in prehlad.pokyn_pre_model(reopened())
    assert '3 správy' not in prehlad.pokyn_pre_model(reopened())


async def test_one_previous_outbound_means_established_chat_even_outside_history_window():
    db = FakeDb()
    db.history = AsyncMock(return_value=[{'role': 'user', 'content': 'hi again'}])
    user = await db.ensure_user('fan', 'visitor')
    user['msg_count'] = 1  # Instagram counts sent replies, not inbound messages.
    system, *_ = await instagram_agent.InstagramAgent(db, None)._prompt(user, 'fan', db.nastavenia)
    assert 'ÚPLNE PRVÁ' not in system
