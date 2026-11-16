"""Instagram karta v control bote — názov, tlačidlá, prevzatie, fallback."""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta, timezone

import control_bot as cb


def _bot():
    return cb.ControlBot.__new__(cb.ControlBot)


def _data(riadky):
    return {b.data for riadok in riadky for b in riadok}


class TestNazovKanala:
    def test_instagram_ma_vlastny_nazov(self):
        assert cb._plat("instagram") == "Instagram"
        assert cb._plat("fanvue") == "Fanvue"
        assert cb._plat("telegram") == "Telegram"

    def test_karta_hovori_instagram(self):
        riadky = cb._card_lines("instagram", "fan", "ahoj", ["a", "b"])
        assert riadky[0].startswith("💬 *Instagram · fan*")


class TestTlacidla:
    def test_instagram_nema_fotku_ani_hlasovku(self):
        data = _data(_bot()._approval_buttons(3, "instagram"))
        assert b"af" not in data and b"av" not in data
        # Všetko ostatné ostáva.
        for nutne in (b"ap:0", b"ap:2", b"ar", b"ab", b"ai", b"ac", b"as", b"ax"):
            assert nutne in data

    def test_telegram_a_fanvue_maju_media_ako_doteraz(self):
        for kanal in ("telegram", "fanvue", ""):
            data = _data(_bot()._approval_buttons(3, kanal))
            assert b"af" in data and b"av" in data


class _Event:
    def __init__(self, mid=10):
        self.message_id = mid
        self.chat_id = 1
        self.edity = []

    async def edit(self, text, buttons=None):
        self.edity.append(text)

    async def answer(self, *a, **k):
        pass


class _Db:
    def __init__(self, row):
        self.row = row
        self.mark = []

    async def get_pending(self, pid):
        return self.row

    async def mark_pending(self, pid, status, **k):
        self.mark.append(status)


class _Sender:
    def __init__(self):
        self.prevzate = []

    async def take_over(self, conv):
        self.prevzate.append(conv)


class TestPrevzatie:
    def test_take_over_na_instagram_karte_vypne_ai(self):
        bot = _bot()
        row = {"id": "p1", "status": "awaiting", "channel": "instagram",
               "conv_key": "999", "suggestions": ["x"]}
        bot._db = _Db(row)
        sender = _Sender()
        bot._senders = {"instagram": sender}
        bot._cards = {10: "p1"}
        bot._chat_ctx = {}
        bot._wizard = {}
        bot._pinned = set()

        async def pending_for(event):
            return "p1", row

        bot._pending_for = pending_for
        asyncio.run(bot._route_approval(_Event(), "ax", ""))
        assert sender.prevzate == ["999"]
        assert bot._db.mark == ["skipped"]


class TestFallback:
    @pytest.mark.parametrize('channel',['telegram','fanvue','instagram'])
    def test_semi_karta_neodide_sama(self,channel):
        """Žiadny Semi kanál nesmie odoslať návrh bez majiteľa."""
        bot = _bot()
        stara = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        odoslane = []

        class Db:
            async def awaiting_pending(self):
                return [{"id": "p1", "channel": channel, "conv_key": "999",
                         "suggestions": ["x"], "created_at": stara}]

            async def tg_reply_mode(self):
                return {"fallback_minutes": 1}

            async def fanvue_reply_mode(self):
                return {"fallback_minutes": 1}

        bot._db = Db()

        async def auto_send(row):
            odoslane.append(row)

        bot._auto_send = auto_send
        asyncio.run(bot._fallback_tick())
        assert odoslane == []
