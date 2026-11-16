"""Native Telegram messages stay in context without echoing worker sends."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.tl.types import Message, PeerUser, User

from userbot import UserBot, Reconciler
from test_reply_flow import FakeDb, FakeClient, FakeLlm, make_config, user_row
from test_reconcile import FakeDialog, FakeTgClient

STAMP = datetime.now(timezone.utc) - timedelta(minutes=2)


def message(mid, text, *, out=True, seconds=0):
    return Message(id=mid, peer_id=PeerUser(555), message=text, out=out,
                   date=STAMP + timedelta(seconds=seconds))


class NativeDb(FakeDb):
    def __init__(self):
        super().__init__(user_row(tg_id=555, last_msg_id=100, pending_reply=True))
        self.ingested = []
        self.pending = True

    async def ingest_tg_message(self, tg_id, message_id, role, content, *, account_scope, created_at, origin):
        key = (tg_id, account_scope, message_id)
        if any(row['key'] == key for row in self.ingested):
            return {'inserted': False, 'id': message_id}
        self.ingested.append({'key': key, 'role': role, 'content': content, 'created_at': created_at, 'origin': origin})
        self.messages.append({'role': role, 'content': content, 'created_at': created_at, 'id': message_id})
        if role == 'assistant' and origin == 'native':
            self.pending = False
            self.users[tg_id]['pending_reply'] = False
        return {'inserted': True, 'id': message_id}

    async def source_snapshot(self, channel, external):
        return max((row.get('id', 0) for row in self.messages), default=0)

    async def supersede_open(self, channel, external):
        self.pending = False
        return []


class NativeClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.messages = []
        self.handlers = []

    def add_event_handler(self, handler, builder):
        self.handlers.append((handler, builder))

    def iter_messages(self, entity, **kwargs):
        async def rows():
            for row in sorted(self.messages, key=lambda row: row.id, reverse=True)[:kwargs.get('limit', 30)]:
                yield row
        return rows()


class Outgoing:
    def __init__(self, msg, peer=None, private=True):
        self.message = msg
        self.is_private = private
        self.chat_id = 555
        self._peer = peer or User(id=555, first_name='Alex', username='alex')

    async def get_chat(self):
        return self._peer


def setup():
    db, client = NativeDb(), NativeClient()
    bot = UserBot(make_config(tg_account_scope='telegram:account-one'), db, FakeLlm('unused'), client, AsyncMock())
    return bot, db, client


def test_registers_native_outgoing_observer():
    bot, _, client = setup()
    bot.register()
    assert any(builder.outgoing for _, builder in client.handlers), 'Native outgoing updates must have an observer'


async def test_native_reply_keeps_recipient_source_time_and_cancels_old_draft_once():
    bot, db, client = setup()
    event = Outgoing(message(101, 'I meant next Friday.'))
    await bot._on_outgoing(event)
    await bot._on_outgoing(event)
    assert [(row['role'], row['content']) for row in db.messages] == [('assistant', 'I meant next Friday.')]
    assert db.ingested[0]['key'] == (555, 'telegram:account-one', 101)
    assert db.ingested[0]['created_at'] == STAMP.isoformat()
    assert db.pending is False
    assert not db.users[555].get('human_takeover'), 'Native replies do not permanently switch off Auto'
    assert client.sent == []


@pytest.mark.parametrize('peer,private', [
    (User(id=555, is_self=True), True), (User(id=555, bot=True), True),
    (User(id=555, contact=True), True), (User(id=999), True), (User(id=777000), True),
    (User(id=555), False),
])
async def test_native_observer_respects_private_contact_filters(peer, private):
    bot, db, _ = setup()
    await bot._on_outgoing(Outgoing(message(101, 'private'), peer=peer, private=private))
    assert db.messages == []


async def test_worker_echo_waits_for_provider_id_record_and_is_not_native():
    bot, db, client = setup()
    echo = None
    async def send(peer, text, **kwargs):
        nonlocal echo
        msg = message(101, text)
        echo = asyncio.create_task(bot._on_outgoing(Outgoing(msg)))
        await asyncio.sleep(0)
        return msg
    client.send_message = send
    await bot._send_tracked(555, 'exact worker reply')
    await echo
    assert len(db.messages) == 1
    assert db.ingested[0]['origin'] == 'telepipe'
    assert db.pending is True, 'Own echo cannot cancel a valid draft as a native takeover'


async def test_recovery_imports_both_sides_once_and_does_not_reply_after_native_answer():
    bot, db, _ = setup()
    peer = User(id=555, first_name='Alex')
    rows = [message(101, 'Are you free?', out=False), message(102, 'Friday works.', seconds=5)]
    client = FakeTgClient([FakeDialog(peer, rows[-1])], {555: rows})
    reconciler = Reconciler(bot, bot._cfg, db, client)
    await reconciler.run()
    await reconciler.run()
    assert [(row['role'], row['content']) for row in db.messages] == [('user', 'Are you free?'), ('assistant', 'Friday works.')]
    assert not db.users[555]['pending_reply']
    assert not db.pending


async def test_next_inbound_retains_native_reply_in_future_context():
    bot, db, _ = setup()
    peer = User(id=555, first_name='Alex')
    rows = [message(101, 'Are you free?', out=False), message(102, 'Friday works.', seconds=5), message(103, 'What time Friday?', out=False, seconds=10)]
    client = FakeTgClient([FakeDialog(peer, rows[-1])], {555: rows})
    await Reconciler(bot, bot._cfg, db, client).run()
    import conversation_timing
    turn = conversation_timing.analyze(await db.recent_messages(555, 12))
    assert turn.latest_text == 'What time Friday?'
    assert any(row['role'] == 'assistant' and 'Friday works.' in row['content'] for row in turn.messages)
    assert db.users[555]['pending_reply'] is True


async def test_native_reply_during_suggestion_generation_prevents_old_card():
    bot, db, _ = setup()
    db.messages = [{'id': 100, 'role': 'user', 'content': 'Are you free?', 'created_at': (STAMP - timedelta(seconds=5)).isoformat()}]
    bot._control = SimpleNamespace(post_approval=AsyncMock(return_value=True))
    async def suggest(*args, **kwargs):
        await bot._on_outgoing(Outgoing(message(101, 'I already replied.')))
        return ['stale suggestion']
    bot._llm.suggest = suggest
    await bot._handoff_semi(555, await db.get_user(555), 'persona', list(db.messages), 'Are you free?')
    bot._control.post_approval.assert_not_awaited()
    assert db.pending is False


async def test_auto_preflight_catches_native_reply_without_an_update_event():
    bot, db, client = setup()
    bot._generation_versions[555] = 0
    client.messages = [message(101, 'Already answered in the app.')]
    assert await bot._auto_send_time_ok(555) is False
    assert db.messages[-1]['content'] == 'Already answered in the app.'
    assert client.sent == [] and client.read == []


async def test_operator_final_preflight_catches_native_reply_during_read_ack():
    bot, db, client = setup()
    async def read_ack(peer):
        client.messages = [message(101, 'Answered while the approval was loading.')]
    client.send_read_acknowledge = read_ack
    async def before_send():
        return await db.source_snapshot('telegram', '555') == 0
    result = await bot.deliver_operator(dict(account_scope='telegram:account-one', external_id='555',
                                            operation='approve', text='Obsolete preview'), before_send)
    assert result.status == 'blocked' and result.reason == 'stale_context'
    assert client.sent == []


async def test_sent_reply_does_not_retry_when_history_write_temporarily_fails():
    bot, db, client = setup()
    original = db.ingest_tg_message
    failures = 0
    async def ingest(*args, **kwargs):
        nonlocal failures
        failures += 1
        if failures == 1:
            raise RuntimeError('Temporary storage failure')
        return await original(*args, **kwargs)
    db.ingest_tg_message = ingest
    sent = message(101, 'Already delivered')
    client.send_message = AsyncMock(return_value=sent)
    assert await bot._send_tracked(555, 'Already delivered') is sent
    await bot._on_outgoing(Outgoing(sent))
    assert client.send_message.await_count == 1
    assert len(db.messages) == 1 and db.ingested[0]['origin'] == 'telepipe'
    assert db.pending is True


async def test_reconnect_scan_skips_unchanged_dialog_heads_and_recovers_later_reply():
    bot, db, _ = setup()
    peer = User(id=555, first_name='Alex')
    rows = [message(101, 'Initial native answer')]
    dialog = FakeDialog(peer, rows[-1])
    client = FakeTgClient([dialog], {555: rows})
    actual = client.iter_messages
    reads = []
    def iter_messages(*args, **kwargs):
        reads.append(args[0].id)
        return actual(*args, **kwargs)
    client.iter_messages = iter_messages
    reconciler = Reconciler(bot, bot._cfg, db, client)
    await reconciler.run()
    await reconciler.run()
    assert reads == [555]
    later = message(102, 'Another native answer', seconds=5)
    rows.append(later)
    dialog.message = later
    await reconciler.run()
    assert reads == [555, 555]
    assert [row['content'] for row in db.messages] == ['Initial native answer', 'Another native answer']


async def test_auto_generation_checks_durable_version_when_other_worker_imported_native_reply():
    bot, db, client = setup()
    bot._generation_sources = {555: 0}
    # Another live replica persisted the native update before this one sees it.
    await db.ingest_tg_message(555, 101, 'assistant', 'Already answered elsewhere',
                              account_scope='telegram:account-one', created_at=STAMP.isoformat(), origin='native')
    client.messages = [message(101, 'Already answered elsewhere')]
    assert await bot._auto_send_time_ok(555) is False
    assert client.sent == []


async def test_recovery_pages_through_a_native_reply_gap_larger_than_latest_window():
    bot, db, _ = setup()
    peer = User(id=555, first_name='Alex')
    rows = [message(mid, f'Native reply {mid}', seconds=mid - 101) for mid in range(101, 171)]
    client = FakeTgClient([FakeDialog(peer, rows[-1])], {555: rows})
    await Reconciler(bot, bot._cfg, db, client).run()
    assert len(db.messages) == 70
    assert db.messages[0]['content'] == 'Native reply 101'
    assert db.messages[-1]['content'] == 'Native reply 170'
