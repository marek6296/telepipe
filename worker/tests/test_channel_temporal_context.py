"""Adapters retain message time and answer the current inbound turn."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import fanvue_agent as fa
import fvsync
import userbot
from test_reply_flow import build, user_row
from test_channel_read_timing import telegram_semi
from test_fvsemi_brana import _agent as fv_agent, FAN

pytestmark = pytest.mark.usefixtures('fast')


def history_rows():
    now = datetime.now(timezone.utc)
    return [
        {'role': 'assistant', 'content': 'Hope your hike goes well', 'created_at': (now-timedelta(days=1,minutes=5)).isoformat()},
        {'role': 'user', 'content': 'What did you do after lunch?', 'created_at': (now-timedelta(days=1)).isoformat()},
        {'role': 'user', 'content': 'Hey honey', 'created_at': (now-timedelta(minutes=2)).isoformat()},
        {'role': 'user', 'content': 'You there honey', 'created_at': (now-timedelta(minutes=1)).isoformat()},
    ]


async def test_tg_semi_keeps_new_greeting_separate_from_old_unanswered_topic():
    bot, db, llm, client, cards = telegram_semi()
    db.messages = history_rows()
    await bot.reply_to(555)
    prompt, history = llm.suggest.await_args.args[:2]
    greeting = next(r['content'] for r in history if 'Hey honey' in r['content'])
    assert 'What did you do after lunch?' not in greeting
    assert 'He greets you in the CURRENT TURN' in prompt
    assert 'latest 2 unanswered' in prompt
    assert client.sent == [] and client.read == [] and cards
    assert all(set(r) == {'role', 'content'} for r in history)


async def test_tg_auto_preserves_greeting_when_followed_by_nudge():
    rows = history_rows()[2:]
    bot, db, _, client, _ = build(user_row(last_reply_at=datetime.now(timezone.utc).isoformat()),
        rows, 'Hey honey, yes I am here')
    await bot.reply_to(555)
    assert client.sent[0][1].lower().startswith('hey honey')


@pytest.mark.parametrize('brief', ['', 'ask how his day is going'])
async def test_tg_regenerate_replaces_stale_time_and_greeting_snapshot(brief):
    bot, db, llm, client, _ = telegram_semi()
    db.messages = history_rows()
    db.get_pending_for = AsyncMock(return_value={'prompt':
        'PERSONA\nkept facts\n\nČAS\nU teba je 01:00.\nNEZDRAV SA. Konverzácia beží.\n\nVEDENIE KONVERZÁCIE\nBe kind'})
    await bot.regenerate('555', brief=brief)
    prompt, history = llm.suggest.await_args.args[:2]
    assert 'U teba je 01:00' not in prompt and 'NEZDRAV SA' not in prompt
    assert 'kept facts' in prompt
    assert 'He greets you in the CURRENT TURN' in prompt
    assert 'latest 2 unanswered' in prompt
    assert all(set(r) == {'role', 'content'} for r in history)
    assert client.read == [] and client.sent == []


@pytest.mark.parametrize('brief', ['', 'ask how his day is going'])
async def test_fv_regenerate_uses_current_inbound_bundle_and_timestamps(brief):
    a = fv_agent()
    a._db.behavior = AsyncMock(return_value={'active_tz': 'America/Los_Angeles'})
    a._db.history_rows = AsyncMock(return_value=history_rows())
    a._db.history = AsyncMock(return_value=history_rows())
    a._api.chat_messages = AsyncMock(return_value=[])
    a._situacia = AsyncMock(return_value=SimpleNamespace(prompt='persona',tip=''))
    a._llm.suggest = AsyncMock(return_value=['hello'])
    await a.regenerate(FAN['uuid'], brief=brief)
    fan = a._situacia.await_args.args[0]
    assert fan['text'] == 'Hey honey\nYou there honey'
    prompt, history = a._llm.suggest.await_args.args[:2]
    assert 'He greets you in the CURRENT TURN' in prompt
    assert 'latest 2 unanswered' in prompt
    assert all(set(r) == {'role', 'content'} for r in history)
    assert a._api.sent == []


def test_fv_import_keeps_provider_sent_at():
    rows = fvsync.missing(set(), [{'uuid':'message-1','text':'Hey honey',
        'sender':{'uuid':FAN['uuid']},'sentAt':'2026-11-15T20:00:00Z'}], 'creator-1')
    assert rows[0]['occurred_at'] == '2026-11-15T20:00:00+00:00'


def test_fv_import_does_not_invent_time_for_invalid_provider_value():
    rows = fvsync.missing(set(), [{'uuid':'message-1','text':'hello',
        'sender':{'uuid':FAN['uuid']},'sentAt':'yesterday'}], 'creator-1')
    assert rows[0].get('occurred_at') is None


async def test_fv_regenerate_refreshes_source_times_without_seen_and_stops_after_owner_reply():
    a = fv_agent()
    a._db.settings = AsyncMock(return_value={'creator_uuid':'creator-1','reply_mode':'semi'})
    a._db.behavior = AsyncMock(return_value={'active_tz':'America/Los_Angeles'})
    a._db.known_message_uuids = AsyncMock(return_value={'latest-owner'})
    a._db.texty_bez_uuid = AsyncMock(return_value=set())
    a._db.backfill_message_times = AsyncMock()
    a._api.chat_messages = AsyncMock(return_value=[{'uuid':'latest-owner','text':'Already here',
        'sender':{'uuid':'creator-1'},'sentAt':'2026-11-16T20:00:00Z'}])
    a._llm.suggest = AsyncMock(return_value=['should not generate'])
    result = await a.regenerate(FAN['uuid'])
    assert result == {}
    a._api.chat_messages.assert_awaited_once_with(FAN['uuid'], mark_read=False)
    a._db.backfill_message_times.assert_awaited_once_with(FAN['uuid'],
        {'latest-owner':'2026-11-16T20:00:00+00:00'})
    a._llm.suggest.assert_not_awaited()
    assert a._api.sent == []


@pytest.mark.parametrize('heading', ['NA TOTO SA PÝTAL', 'LEN PRIKÝVOL',
    'NEPOČUL, ČO SI POVEDALA V HLASOVKE', 'PRÁVE BOL NA TEBA DRZÝ',
    'PÍŠETE SI UŽ DLHO', 'PRÁVE MU POSIELAŠ FOTKU'])
async def test_tg_regenerate_drops_stale_current_turn_directives(heading):
    bot, db, llm, _, _ = telegram_semi()
    db.messages = history_rows()
    db.get_pending_for = AsyncMock(return_value={'prompt':
        f'PERSONA\nkept facts\n\n{heading}\nOld picnic question has priority over everything.\n\nOTHER RULES\nBe kind'})
    await bot.regenerate('555')
    prompt = llm.suggest.await_args.args[0]
    assert 'Old picnic question has priority' not in prompt
    assert 'kept facts' in prompt and 'He greets you in the CURRENT TURN' in prompt


async def test_telegram_storage_keeps_source_time_when_supplied():
    from db import TenantDb
    db = object.__new__(TenantDb)
    db.model_id = 'model-A'
    db._post = AsyncMock()
    await db.add_message(555, 'user', 'hello', created_at='2026-11-15T20:00:00+00:00')
    assert db._post.await_args.args[1] == {'model_id':'model-A', 'tg_id':555,
        'role':'user','content':'hello','created_at':'2026-11-15T20:00:00+00:00'}


async def test_telegram_recovery_keeps_original_message_time():
    from test_reconcile import person, FakeMessage, FakeDialog, make
    p = person()
    message = FakeMessage(101, 'Hey honey', hours_ago=8)
    recovery, db = make([FakeDialog(p,message)], {555:[message]})
    await recovery.run()
    assert db.messages[0]['created_at'] == message.date.isoformat()


async def test_fv_regenerate_sync_does_not_send_a_purchase_thank_you():
    a = fv_agent()
    a._db.behavior = AsyncMock(return_value={'active_tz':'America/Los_Angeles'})
    a._db.history_rows = AsyncMock(return_value=history_rows())
    a._db.known_message_uuids = AsyncMock(return_value={'m1'})
    a._db.texty_bez_uuid = AsyncMock(return_value=set())
    a._api.chat_messages = AsyncMock(return_value=[{'uuid':'m1','text':'Hey honey',
        'sender':{'uuid':FAN['uuid']},'sentAt':'2026-11-16T20:00:00Z',
        'purchasedAt':'2026-11-16T19:00:00Z'}])
    a._thank = AsyncMock()
    a._situacia = AsyncMock(return_value=SimpleNamespace(prompt='persona',tip=''))
    await a.regenerate(FAN['uuid'])
    a._thank.assert_not_awaited()
    assert a._api.sent == []
