"""Dobehnutie po výpadku Railway.

Kľúčové: po štarte NIKOMU nepíše sama od seba. Len dotiahne, čo prišlo počas
výpadku, doplní kontext a rozhodne, na čo sa ešte oplatí odpovedať.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from telethon.tl.types import User
from userbot import Reconciler, UserBot

from test_reply_flow import FakeClient, FakeDb, FakeLlm, make_config, user_row

pytestmark = pytest.mark.usefixtures("fast")

CFG = make_config(owner_chat_id=999, owner_as_client=False, skip_contacts=True)


def person(user_id=555, bot=False, contact=False, is_self=False):
    return User(id=user_id, bot=bot, contact=contact, is_self=is_self,
                username="peter", first_name="Peter", lang_code="en")


class FakeMessage:
    def __init__(self, msg_id, text, hours_ago=1.0, out=False):
        self.id = msg_id
        self.message = text
        self.out = out
        self.date = datetime.now(timezone.utc) - timedelta(hours=hours_ago)


class FakeDialog:
    def __init__(self, entity, message):
        self.entity = entity
        self.message = message


class FakeTgClient:
    """Minimálny Telethon: dialógy a správy po danom id."""

    def __init__(self, dialogs, messages):
        self._dialogs = dialogs
        self._messages = messages  # {user_id: [FakeMessage]}

    def iter_dialogs(self, limit=None):
        dialogs = self._dialogs

        class _It:
            def __aiter__(self):
                async def gen():
                    for d in dialogs:
                        yield d
                return gen()

        return _It()

    def iter_messages(self, entity, min_id=0, limit=None):
        rows = [m for m in self._messages.get(entity.id, []) if m.id > min_id]
        rows = sorted(rows, key=lambda m: m.id, reverse=True)[: limit or 100]

        class _It:
            def __aiter__(self):
                async def gen():
                    for m in rows:
                        yield m
                return gen()

        return _It()


def make(dialogs, messages, db_user=None, cfg=CFG):
    db = FakeDb(db_user or user_row(tg_id=555, msg_count=2, last_msg_id=100))
    client = FakeTgClient(dialogs, messages)
    sent = []

    async def notify(text):
        sent.append(text)

    bot = UserBot(cfg, db, FakeLlm("x"), FakeClient(), notify)
    return Reconciler(bot, cfg, db, client), db


class TestCatchUp:
    def test_pulls_messages_that_arrived_during_downtime(self):
        p = person()
        msgs = [FakeMessage(101, "you there?", 2.0), FakeMessage(102, "hello?", 1.5)]
        rec, db = make([FakeDialog(p, msgs[-1])], {555: msgs})
        stats = asyncio.run(rec.run())
        assert stats["dotiahnutych"] == 2
        assert [m["content"] for m in db.messages] == ["you there?", "hello?"]

    def test_queues_them_for_a_reply(self):
        p = person()
        msgs = [FakeMessage(101, "you there?", 2.0)]
        rec, db = make([FakeDialog(p, msgs[0])], {555: msgs})
        stats = asyncio.run(rec.run())
        assert stats["na_odpoved"] == 1
        assert db.users[555]["pending_reply"] is True

    def test_advances_last_msg_id(self):
        p = person()
        msgs = [FakeMessage(101, "a", 2.0), FakeMessage(140, "b", 1.0)]
        rec, db = make([FakeDialog(p, msgs[-1])], {555: msgs})
        asyncio.run(rec.run())
        assert db.users[555]["last_msg_id"] == 140

    def test_ignores_messages_already_processed(self):
        """Bez toho by sa po každom reštarte história zdvojila."""
        p = person()
        msgs = [FakeMessage(50, "stara", 5.0), FakeMessage(100, "tiez stara", 4.0)]
        rec, db = make([FakeDialog(p, msgs[-1])], {555: msgs})
        stats = asyncio.run(rec.run())
        assert stats["dotiahnutych"] == 0
        assert db.messages == []

    def test_skips_her_own_outgoing_messages(self):
        p = person()
        msgs = [FakeMessage(101, "moja odpoved", 1.0, out=True)]
        rec, db = make([FakeDialog(p, msgs[0])], {555: msgs})
        assert asyncio.run(rec.run())["dotiahnutych"] == 0

    def test_counts_messages_into_msg_count(self):
        p = person()
        msgs = [FakeMessage(101, "a", 2.0), FakeMessage(102, "b", 1.0)]
        rec, db = make([FakeDialog(p, msgs[-1])], {555: msgs},
                       db_user=user_row(tg_id=555, msg_count=7, last_msg_id=100))
        asyncio.run(rec.run())
        assert db.users[555]["msg_count"] == 9


class TestStaleMessages:
    def test_does_not_reply_to_very_old_messages(self):
        """Odpísať na 3 dni starú správu, akoby sa nič nedialo, je horšie než mlčať."""
        p = person()
        msgs = [FakeMessage(101, "hey", 80.0)]
        rec, db = make([FakeDialog(p, msgs[0])], {555: msgs})
        stats = asyncio.run(rec.run())
        assert stats["prestarnutych"] == 1
        assert stats["na_odpoved"] == 0
        assert db.users[555]["pending_reply"] is False

    def test_but_still_stores_them_for_context(self):
        p = person()
        msgs = [FakeMessage(101, "hey from three days ago", 80.0)]
        rec, db = make([FakeDialog(p, msgs[0])], {555: msgs})
        asyncio.run(rec.run())
        assert db.messages[0]["content"] == "hey from three days ago"

    def test_recent_messages_are_answered(self):
        p = person()
        msgs = [FakeMessage(101, "hey", 3.0)]
        rec, db = make([FakeDialog(p, msgs[0])], {555: msgs})
        assert asyncio.run(rec.run())["na_odpoved"] == 1


class TestNeverSpams:
    def test_sends_nothing_by_itself(self):
        """Po štarte nesmie odísť ani jedna správa."""
        p = person()
        msgs = [FakeMessage(101, "hey", 1.0)]
        rec, db = make([FakeDialog(p, msgs[0])], {555: msgs})
        asyncio.run(rec.run())
        assert rec._bot._client.sent == [], "reconciler nesmie sám nič poslať"

    def test_dialog_with_no_new_messages_is_untouched(self):
        p = person()
        rec, db = make([FakeDialog(p, FakeMessage(100, "stara", 5.0))], {555: []})
        stats = asyncio.run(rec.run())
        assert stats["dotiahnutych"] == 0
        assert db.users[555]["pending_reply"] is False

    def test_skips_bots(self):
        b = person(777, bot=True)
        msgs = [FakeMessage(101, "spam", 1.0)]
        rec, _ = make([FakeDialog(b, msgs[0])], {777: msgs})
        assert asyncio.run(rec.run())["dialogov"] == 0

    def test_skips_contacts(self):
        c = person(556, contact=True)
        msgs = [FakeMessage(101, "ahoj", 1.0)]
        rec, _ = make([FakeDialog(c, msgs[0])], {556: msgs})
        assert asyncio.run(rec.run())["dialogov"] == 0

    def test_skips_owner_when_not_testing(self):
        owner = person(999)
        msgs = [FakeMessage(101, "test", 1.0)]
        rec, _ = make([FakeDialog(owner, msgs[0])], {999: msgs})
        assert asyncio.run(rec.run())["dialogov"] == 0

    def test_includes_owner_when_testing(self):
        cfg = make_config(owner_chat_id=999, owner_as_client=True, skip_contacts=True)
        owner = person(999, contact=True)
        msgs = [FakeMessage(101, "test", 1.0)]
        rec, _ = make([FakeDialog(owner, msgs[0])], {999: msgs},
                      db_user=user_row(tg_id=999, msg_count=1, last_msg_id=100), cfg=cfg)
        assert asyncio.run(rec.run())["dialogov"] == 1


class TestRobustness:
    def test_survives_a_broken_dialog(self):
        class Boom:
            @property
            def entity(self):
                raise RuntimeError("rozbity dialog")

        rec, _ = make([Boom()], {})
        stats = asyncio.run(rec.run())
        assert stats["dotiahnutych"] == 0, "štart nesmie padnúť"


class TestSystemAccounts:
    """777000 je oficiálny Telegram (prihlasovacie kódy) — nie je označený ako bot."""

    def test_reconciler_skips_telegram_service(self):
        svc = person(777000)
        msgs = [FakeMessage(101, "Login code: 12345", 1.0)]
        rec, db = make([FakeDialog(svc, msgs[0])], {777000: msgs})
        stats = asyncio.run(rec.run())
        assert stats["dialogov"] == 0
        assert stats["na_odpoved"] == 0

    def test_reconciler_skips_support_flagged(self):
        svc = person(12345)
        svc.support = True
        msgs = [FakeMessage(101, "hi", 1.0)]
        rec, _ = make([FakeDialog(svc, msgs[0])], {12345: msgs})
        assert asyncio.run(rec.run())["dialogov"] == 0
