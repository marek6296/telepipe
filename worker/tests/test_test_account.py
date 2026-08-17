"""Marekov vlastný účet: odpovedá vždy a hneď, aby sa dalo testovať.

Pre všetkých ostatných musia pravidlá platiť naďalej — to je to podstatné.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import behavior as bhv
import pytest

from test_reply_flow import build, make_config, user_row

pytestmark = pytest.mark.usefixtures("fast")

OWNER = 999
STRANGER = 555

CFG = make_config(owner_chat_id=OWNER, owner_as_client=True)
NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}


def owner_row(**kw):
    return user_row(tg_id=OWNER, **kw)


class TestOwnerAlwaysAnswered:
    def test_answers_outside_active_window(self, monkeypatch):
        monkeypatch.setattr(bhv, "in_active_window", lambda *a, **k: False)
        bot, _, _, client, _ = build(
            owner_row(msg_count=3), [{"role": "user", "content": "test"}], "hey", cfg=CFG
        )
        asyncio.run(bot.reply_to(OWNER))
        assert client.sent, "vlastníkovi má odpovedať aj mimo okna"

    def test_answers_despite_pending_defer(self):
        later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        bot, _, _, client, _ = build(
            owner_row(msg_count=3, reply_after=later),
            [{"role": "user", "content": "test"}],
            "hey",
            cfg=CFG,
        )
        asyncio.run(bot.reply_to(OWNER))
        assert client.sent, "naplánované odloženie sa má pri teste ignorovať"

    def test_answers_despite_hourly_cap(self):
        bot, db, _, client, _ = build(
            owner_row(msg_count=3),
            [{"role": "user", "content": "a"}],
            "sure thing",  # nie pozdrav — ten by greeting filter odstrelil
            cfg=CFG,
            behavior={**NO_WINDOW, "max_replies_per_hour": 1},
        )
        asyncio.run(bot.reply_to(OWNER))
        # nová správa od neho, inak by druhú odpoveď zablokovala ochrana
        # proti dvojitej odpovedi (a to je správne)
        db.messages.append({"role": "user", "content": "b"})
        asyncio.run(bot.reply_to(OWNER))
        assert len(client.sent) == 2, "strop sa pri teste neuplatňuje"

    def test_never_defers_owner(self, monkeypatch):
        monkeypatch.setattr(bhv, "should_defer_reply", lambda *a, **k: 9000)
        bot, db, _, client, _ = build(
            owner_row(msg_count=5), [{"role": "user", "content": "ok"}], "hey", cfg=CFG
        )
        asyncio.run(bot.reply_to(OWNER))
        assert client.sent, "vlastníkovi sa odpoveď neodkladá"
        assert db.users[OWNER]["reply_after"] is None

    def test_no_goodnight_lock_for_owner(self, monkeypatch):
        monkeypatch.setattr(bhv, "should_sleep_until_morning", lambda *a, **k: datetime.now())
        bot, db, _, client, _ = build(
            owner_row(msg_count=5), [{"role": "user", "content": "u up"}], "gn babe", cfg=CFG
        )
        asyncio.run(bot.reply_to(OWNER))
        assert client.sent
        assert db.users[OWNER]["reply_after"] is None, "test účet sa neuspáva"

    def test_delays_are_skipped(self, monkeypatch):
        """Nesmie čakať — inak sa chovanie nedá prakticky vyskúšať."""
        slept = []
        original = asyncio.sleep

        async def spy(seconds, *a, **k):
            slept.append(seconds)
            return await original(0)

        monkeypatch.setattr(asyncio, "sleep", spy)
        # naschvál NEpatchujem bhv delaye — pri teste sa nemajú ani zavolať
        monkeypatch.setattr(bhv, "read_delay", lambda *a, **k: 999)
        monkeypatch.setattr(bhv, "reply_delay", lambda *a, **k: 999)
        bot, _, _, client, _ = build(
            owner_row(msg_count=3), [{"role": "user", "content": "test"}], "hey", cfg=CFG
        )
        asyncio.run(bot.reply_to(OWNER))
        assert client.sent
        assert 999 not in slept, "pri teste sa nesmie čakať na read/reply delay"


class TestStrangersStillFollowRules:
    def test_stranger_defers_outside_window(self, monkeypatch):
        monkeypatch.setattr(bhv, "in_active_window", lambda *a, **k: False)
        bot, db, _, client, _ = build(
            user_row(tg_id=STRANGER, msg_count=3),
            [{"role": "user", "content": "hey"}],
            "hi",
            cfg=CFG,
        )
        asyncio.run(bot.reply_to(STRANGER))
        assert client.sent == [], "cudzím sa mimo okna neodpisuje"
        assert db.users[STRANGER]["pending_reply"] is True

    def test_stranger_respects_scheduled_defer(self):
        later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        bot, _, _, client, _ = build(
            user_row(tg_id=STRANGER, msg_count=3, reply_after=later),
            [{"role": "user", "content": "hey"}],
            "hi",
            cfg=CFG,
        )
        asyncio.run(bot.reply_to(STRANGER))
        assert client.sent == [], "cudzím odloženie platí"

    def test_owner_not_test_account_when_flag_off(self, monkeypatch):
        """OWNER_AS_CLIENT=false → vlastník sa vôbec neobsluhuje."""
        monkeypatch.setattr(bhv, "in_active_window", lambda *a, **k: False)
        cfg = make_config(owner_chat_id=OWNER, owner_as_client=False)
        bot, _, _, client, _ = build(
            owner_row(msg_count=3), [{"role": "user", "content": "test"}], "hey", cfg=cfg
        )
        asyncio.run(bot.reply_to(OWNER))
        assert client.sent == []
