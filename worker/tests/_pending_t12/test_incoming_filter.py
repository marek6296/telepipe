"""Kto sa vôbec dostane k odpovedi — filtre na prichádzajúce správy."""
import asyncio
from datetime import datetime, timezone

import pytest
from telethon.tl.types import User
from userbot import UserBot

from test_reply_flow import FakeClient, FakeDb, FakeLlm, build, make_config, user_row

# celý tok odpovede — bez tejto fixture by testy reálne spali minúty
pytestmark = pytest.mark.usefixtures("fast")


def FakeSender(user_id, bot=False, contact=False, is_self=False, username="peter"):
    """Skutočný Telethon User — nech sa otestuje aj isinstance kontrola v handleri."""
    return User(
        id=user_id,
        bot=bot,
        contact=contact,
        is_self=is_self,
        username=username,
        first_name="Peter",
        lang_code="en",
    )


class _FakeMessage:
    def __init__(self, msg_id=1001):
        self.id = msg_id


class FakeEvent:
    def __init__(self, sender, text="ahoj", is_private=True, media=None, msg_id=1001):
        self._sender = sender
        self.raw_text = text
        self.is_private = is_private
        self.media = media
        self.photo = None
        self.message = _FakeMessage(msg_id)

    async def get_sender(self):
        return self._sender


def run(sender, text="ahoj", is_private=True, cfg=None):
    """Spustí handler a vráti (db, ci_bola_naplanovana_odpoved)."""
    db = FakeDb(user_row(tg_id=sender.id))
    bot = UserBot(cfg or make_config(), db, FakeLlm("odpoved"), FakeClient(), _noop)
    scheduled = []
    bot._schedule_reply = lambda tg_id: scheduled.append(tg_id)  # type: ignore[method-assign]
    asyncio.run(bot._handle(FakeEvent(sender, text, is_private)))
    return db, scheduled


async def _noop(_text):
    return None


class TestIncomingFilter:
    def test_normal_stranger_gets_scheduled(self):
        _, scheduled = run(FakeSender(555))
        assert scheduled == [555]

    def test_owner_is_ignored(self):
        cfg = make_config(owner_chat_id=999)
        db, scheduled = run(FakeSender(999), cfg=cfg)
        assert scheduled == []
        assert db.messages == []

    def test_bot_is_ignored(self):
        _, scheduled = run(FakeSender(777, bot=True))
        assert scheduled == []

    def test_own_message_is_ignored(self):
        _, scheduled = run(FakeSender(555, is_self=True))
        assert scheduled == []

    def test_contact_is_ignored_by_default(self):
        _, scheduled = run(FakeSender(555, contact=True))
        assert scheduled == []

    def test_contact_is_answered_when_allowed(self):
        cfg = make_config(skip_contacts=False)
        _, scheduled = run(FakeSender(555, contact=True), cfg=cfg)
        assert scheduled == [555]

    def test_group_message_is_ignored(self):
        _, scheduled = run(FakeSender(555), is_private=False)
        assert scheduled == []

    def test_empty_text_is_ignored(self):
        _, scheduled = run(FakeSender(555), text="   ")
        assert scheduled == []

    def test_media_without_text_is_recorded(self):
        db = FakeDb(user_row(tg_id=555))
        bot = UserBot(make_config(), db, FakeLlm("x"), FakeClient(), _noop)
        scheduled = []
        bot._schedule_reply = lambda tg_id: scheduled.append(tg_id)  # type: ignore[method-assign]
        asyncio.run(bot._handle(FakeEvent(FakeSender(555), text="", media=object())))
        assert scheduled == [555]
        assert "médium" in db.messages[-1]["content"]

    def test_message_count_increments(self):
        db, _ = run(FakeSender(555))
        assert db.users[555]["msg_count"] == user_row()["msg_count"] + 1


@pytest.mark.parametrize("text,expected_stage", [("posli mi fotky", "warm"), ("ok", "warm")])
def test_stage_recalculated_on_incoming(text, expected_stage):
    db, _ = run(FakeSender(555), text=text)
    assert db.users[555]["funnel_stage"] == expected_stage


def test_owner_answered_when_flag_enabled():
    """OWNER_AS_CLIENT=true — na testovanie z vlastného účtu."""
    cfg = make_config(owner_chat_id=999, owner_as_client=True)
    _, scheduled = run(FakeSender(999), cfg=cfg)
    assert scheduled == [999]


def test_owner_answered_even_when_in_contacts():
    """Vlastník ako kontakt: OWNER_AS_CLIENT musí prebiť SKIP_CONTACTS.

    Presne na tomto spadol prvý živý test — Marekov účet je v jej kontaktoch.
    """
    cfg = make_config(owner_chat_id=999, owner_as_client=True, skip_contacts=True)
    _, scheduled = run(FakeSender(999, contact=True), cfg=cfg)
    assert scheduled == [999]


def test_telegram_service_account_is_ignored():
    """Správa s prihlasovacím kódom nesmie spustiť odpoveď."""
    _, scheduled = run(FakeSender(777000), text="Login code: 12345")
    assert scheduled == []


def test_contact_exception_is_answered():
    """Kamoš v kontaktoch, ktorého chceme obslúžiť — kvôli testovaniu."""
    cfg = make_config(skip_contacts=True, contact_exceptions=frozenset({693039915}))
    _, scheduled = run(FakeSender(693039915, contact=True), cfg=cfg)
    assert scheduled == [693039915]


def test_other_contacts_still_skipped():
    """Výnimka platí len pre uvedené id — mama zostáva chránená."""
    cfg = make_config(skip_contacts=True, contact_exceptions=frozenset({693039915}))
    _, scheduled = run(FakeSender(5427365965, contact=True), cfg=cfg)
    assert scheduled == []


class TestZablokovany:
    """Koho Marek zablokuje, tomu sa neodpisuje ani po tom, čo už napísal."""

    def test_zablokovanemu_sa_neodpisuje(self):
        bot, db, _llm, client, _notes = build(
            user_row(), [{"role": "user", "content": "hey"}], "nemalo odísť",
        )
        bot._blocked = frozenset({555})
        bot._blocked_at = datetime.now(timezone.utc)
        asyncio.run(bot.reply_to(555))
        assert not client.sent

    def test_zablokovanemu_sa_vypne_ai(self):
        bot, db, _llm, client, _notes = build(
            user_row(pending_reply=True), [{"role": "user", "content": "hey"}], "x",
        )
        bot._blocked = frozenset({555})
        bot._blocked_at = datetime.now(timezone.utc)
        asyncio.run(bot.reply_to(555))
        assert db.users[555]["ai_enabled"] is False
        assert db.users[555]["pending_reply"] is False

    def test_nezablokovanemu_odpisuje(self):
        bot, db, _llm, client, _notes = build(
            user_row(), [{"role": "user", "content": "hey"}], "hey you",
        )
        bot._blocked = frozenset({999})
        bot._blocked_at = datetime.now(timezone.utc)
        asyncio.run(bot.reply_to(555))
        assert client.sent
