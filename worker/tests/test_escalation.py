"""Eskalácia na platformu a strop odkazov — jadro funnelu."""
import asyncio

import pytest
from datetime import datetime, timedelta, timezone

import funnel

from test_reply_flow import build, user_row

# celý tok odpovede — bez tejto fixture by testy reálne spali minúty
pytestmark = pytest.mark.usefixtures("fast")

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


class TestLinkRequest:
    def test_asks_for_link(self):
        assert funnel.detect_link_request("send me your link")

    def test_asks_where_to_find_her(self):
        assert funnel.detect_link_request("where can i find more of you")

    def test_names_the_platform(self):
        assert funnel.detect_link_request("are you on fanvue?")

    def test_asks_how_to_subscribe(self):
        assert funnel.detect_link_request("how do i subscribe")

    def test_small_talk_is_not_a_request(self):
        assert not funnel.detect_link_request("what did you do today")


class TestExplicitInterest:
    def test_asks_for_nudes(self):
        assert funnel.detect_explicit_interest("send nudes")

    def test_wants_to_see_more(self):
        assert funnel.detect_explicit_interest("i wanna see more of you")

    def test_sexual_talk(self):
        assert funnel.detect_explicit_interest("im so horny right now")

    def test_asks_for_exclusive(self):
        assert funnel.detect_explicit_interest("do you have exclusive content")

    def test_normal_chat_is_not_explicit(self):
        assert not funnel.detect_explicit_interest("i went hiking yesterday")

    def test_compliment_is_not_explicit(self):
        assert not funnel.detect_explicit_interest("you look really nice today")


class TestFastTrack:
    def test_cold_user_normally_blocked(self):
        u = user_row(funnel_stage="cold", msg_count=2)
        assert not funnel.can_send_link(u, NOW, 6, 48, 3)

    def test_fast_track_bypasses_stage_and_count(self):
        u = user_row(funnel_stage="cold", msg_count=2)
        assert funnel.can_send_link(u, NOW, 6, 48, 3, fast_track=True)

    def test_fast_track_still_respects_cooldown(self):
        u = user_row(
            funnel_stage="warm",
            msg_count=20,
            link_push_count=1,
            link_sent_at=(NOW - timedelta(hours=2)).isoformat(),
        )
        assert not funnel.can_send_link(u, NOW, 6, 48, 3, fast_track=True)

    def test_fast_track_still_respects_max_pushes(self):
        u = user_row(
            funnel_stage="warm",
            msg_count=40,
            link_push_count=3,
            link_sent_at=(NOW - timedelta(days=10)).isoformat(),
        )
        assert not funnel.can_send_link(u, NOW, 6, 48, 3, fast_track=True)

    def test_fast_track_never_for_paying_user(self):
        u = user_row(paid=True, funnel_stage="converted", msg_count=30)
        assert not funnel.can_send_link(u, NOW, 6, 48, 3, fast_track=True)


class TestLinkQuota:
    def test_link_allowed_when_quota_free(self):
        bot, db, llm, client, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "where can i see more"}],
            "check my page https://www.fanvue.com/sima.sima",
            behavior={"active_start_min": 0, "active_end_min": 0, "max_links_per_hour": 2},
        )
        db.links_last_hour = 1
        asyncio.run(bot.reply_to(555))
        assert "fanvue" in client.sent[0][1]
        assert "ODKAZ JE TERAZ POVOLENÝ" in llm.prompts[0]

    def test_link_blocked_when_quota_used_up(self):
        bot, db, llm, client, _ = build(
            user_row(msg_count=8),
            [{"role": "user", "content": "where can i see more"}],
            "check my page https://www.fanvue.com/sima.sima",
            behavior={"active_start_min": 0, "active_end_min": 0, "max_links_per_hour": 2},
        )
        db.links_last_hour = 2
        asyncio.run(bot.reply_to(555))
        assert "fanvue" not in client.sent[0][1], "odkaz sa musí vystrihnúť"
        assert "ODKAZ JE TERAZ ZAKÁZANÝ" in llm.prompts[0]

    def test_explicit_request_from_cold_user_gets_escalation_prompt(self):
        bot, db, llm, _, _ = build(
            user_row(funnel_stage="cold", msg_count=2),
            [{"role": "user", "content": "send me some nudes"}],
            "not here babe",
            behavior={"active_start_min": 0, "active_end_min": 0, "max_links_per_hour": 2},
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "KEĎ CHCE VIAC" in prompt, "musí dostať pokyny na eskaláciu"
        assert "ODKAZ JE TERAZ POVOLENÝ" in prompt, "fast track má odkaz povoliť"

    def test_normal_chat_from_cold_user_has_no_link(self):
        bot, _, llm, _, _ = build(
            user_row(funnel_stage="cold", msg_count=2),
            [{"role": "user", "content": "i went hiking yesterday"}],
            "sounds nice",
            behavior={"active_start_min": 0, "active_end_min": 0},
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "ODKAZ JE TERAZ ZAKÁZANÝ" in prompt
        assert "KEĎ CHCE VIAC" not in prompt


class TestDeferredReplyFlow:
    def test_defers_instead_of_replying(self, monkeypatch):
        """1 % šanca: neodpíše teraz, ale naplánuje sa na 2–3 h."""
        import behavior as bhv

        monkeypatch.setattr(bhv, "should_defer_reply", lambda *a, **k: 9000)
        bot, db, _, client, _ = build(
            user_row(msg_count=5),
            [{"role": "user", "content": "ok cool"}],
            "odpoved",
            behavior={"active_start_min": 0, "active_end_min": 0},
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == [], "teraz nesmie odpovedať"
        assert db.users[555]["pending_reply"] is True
        assert db.users[555]["reply_after"] is not None

    def test_waits_until_scheduled_time(self):
        later = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        bot, _, _, client, _ = build(
            user_row(msg_count=5, reply_after=later),
            [{"role": "user", "content": "ok cool"}],
            "odpoved",
            behavior={"active_start_min": 0, "active_end_min": 0},
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == [], "pred naplánovaným časom nesmie odpovedať"

    def test_replies_once_time_has_passed(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        bot, db, _, client, _ = build(
            user_row(msg_count=5, reply_after=past),
            [{"role": "user", "content": "ok cool"}],
            "sorry was busy",
            behavior={"active_start_min": 0, "active_end_min": 0},
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent, "po uplynutí času musí odpovedať"
        assert db.users[555]["reply_after"] is None, "čas sa má vynulovať"


class TestQuickReplyFlow:
    def test_quick_mode_skips_seen_only_and_long_pause(self, monkeypatch):
        """Keď je pri telefóne, žiadne minútové pauzy sa neuplatnia."""
        import behavior as bhv_mod

        monkeypatch.setattr(bhv_mod, "quick_reply", lambda *a, **k: (1.0, 2.0))
        monkeypatch.setattr(bhv_mod, "seen_only_delay", lambda *a, **k: 999)
        monkeypatch.setattr(bhv_mod, "long_pause_delay", lambda *a, **k: 999)
        slept = []
        original = asyncio.sleep

        async def spy(seconds, *a, **k):
            slept.append(seconds)
            return await original(0)

        monkeypatch.setattr(asyncio, "sleep", spy)
        bot, _, _, client, _ = build(
            user_row(msg_count=4),
            [{"role": "user", "content": "u there"}],
            "yeah whats up",
            behavior={"active_start_min": 0, "active_end_min": 0},
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent, "musí odpovedať"
        assert 999 not in slept, "v pozornom režime sa nesmie čakať minúty"
        assert 1.0 in slept and 2.0 in slept, "má použiť rýchle časy"
