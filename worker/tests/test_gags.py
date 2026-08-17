"""Drzé vtipy — zriedka a nikdy tomu istému dvakrát do týždňa."""
import asyncio
import random
from datetime import datetime, timedelta, timezone

import gags
import pytest

from test_reply_flow import build, user_row

pytestmark = pytest.mark.usefixtures("fast")

RNG = random.Random(11)
NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}


def ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class TestWeekCooldown:
    def test_fresh_gag_is_available(self):
        assert gags.is_available(gags.BY_KEY["poop"], {}, "vecer")

    def test_blocked_right_after_use(self):
        used = gags.record({}, "poop", datetime.now(timezone.utc))
        assert not gags.is_available(gags.BY_KEY["poop"], used, "vecer")

    def test_still_blocked_after_six_days(self):
        """Šesť dní nie je dosť — vtip by ešte pamätal."""
        used = {"poop": ago(24 * 6)}
        assert not gags.is_available(gags.BY_KEY["poop"], used, "vecer")

    def test_free_after_eight_days(self):
        used = {"poop": ago(24 * 8)}
        assert gags.is_available(gags.BY_KEY["poop"], used, "vecer")

    def test_minimum_cooldown_cannot_be_undercut(self):
        cheeky = gags.Gag("x", "test", cooldown_h=1)
        used = {"x": ago(5)}
        assert not gags.is_available(cheeky, used, "vecer"), "minimum je týždeň"


class TestRarity:
    def test_never_when_chance_is_zero(self):
        assert gags.maybe_pick({}, "vecer", 0.0, RNG) is None

    def test_always_when_chance_is_one(self):
        assert gags.maybe_pick({}, "vecer", 1.0, RNG) is not None

    def test_rate_matches_configuration(self):
        rng = random.Random(7)
        hits = sum(1 for _ in range(4000) if gags.maybe_pick({}, "vecer", 0.07, rng))
        assert 0.05 <= hits / 4000 <= 0.09, f"malo byť ~7 %, bolo {hits / 4000:.1%}"

    def test_nothing_left_returns_none(self):
        used = {g.key: datetime.now(timezone.utc).isoformat() for g in gags.CATALOG}
        assert gags.maybe_pick(used, "vecer", 1.0, RNG) is None

    def test_never_picks_a_used_one(self):
        used = {g.key: datetime.now(timezone.utc).isoformat() for g in gags.CATALOG if g.key != "poop"}
        for _ in range(60):
            picked = gags.maybe_pick(used, "vecer", 1.0, random.Random())
            assert picked is None or picked.key == "poop"


class TestTimeOfDay:
    def test_underwear_game_only_in_the_evening(self):
        assert not gags.is_available(gags.BY_KEY["guess_colour"], {}, "poobede")
        assert gags.is_available(gags.BY_KEY["guess_colour"], {}, "vecer")

    def test_poop_joke_fits_any_hour(self):
        for part in gags.ALL:
            assert gags.is_available(gags.BY_KEY["poop"], {}, part)


class TestRecord:
    def test_does_not_mutate_input(self):
        original = {"poop": ago(1)}
        gags.record(original, "no_pants", datetime.now(timezone.utc))
        assert "no_pants" not in original


class TestGagInFlow:
    def test_prompt_carries_the_gag(self, monkeypatch):
        monkeypatch.setattr(gags, "maybe_pick", lambda *a, **k: gags.BY_KEY["poop"])
        bot, _, llm, _, _ = build(
            user_row(msg_count=5),
            [{"role": "user", "content": "what are you doing"}],
            "on the toilet lol",
            behavior={**NO_WINDOW, "gag_chance": 1.0},
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "DRZÝ VTIP" in prompt
        assert "záchode" in prompt

    def test_gag_is_recorded_so_it_cannot_repeat(self, monkeypatch):
        monkeypatch.setattr(gags, "maybe_pick", lambda *a, **k: gags.BY_KEY["poop"])
        bot, db, _, _, _ = build(
            user_row(msg_count=5),
            [{"role": "user", "content": "what are you doing"}],
            "on the toilet lol",
            behavior={**NO_WINDOW, "gag_chance": 1.0},
        )
        asyncio.run(bot.reply_to(555))
        assert "poop" in (db.users[555].get("used_gags") or {})

    def test_no_gag_section_when_none_picked(self, monkeypatch):
        monkeypatch.setattr(gags, "maybe_pick", lambda *a, **k: None)
        bot, db, llm, _, _ = build(
            user_row(msg_count=5),
            [{"role": "user", "content": "what are you doing"}],
            "just relaxing",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "DRZÝ VTIP" not in llm.prompts[0]
        assert not (db.users[555].get("used_gags") or {})
