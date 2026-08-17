"""Register tém — aby sa nepýtala to isté dvakrát a v nesprávny čas."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import topics as T

from test_reply_flow import build, user_row

pytestmark = pytest.mark.usefixtures("fast")

NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}


def hours_ago(n):
    return (datetime.now(timezone.utc) - timedelta(hours=n)).isoformat()


class TestDetectAsked:
    @pytest.mark.parametrize(
        "text,key",
        [
            ("so how was your day?", "day_was"),
            ("hows your day going?", "day_going"),
            ("where are you from?", "location"),
            ("whats your name?", "name"),
            ("what do you do for a living?", "work"),
            ("are you single?", "relationship"),
            ("how did you find me?", "how_found"),
            ("any plans for tonight?", "evening_plans"),
            ("do you have pets?", "pets"),
        ],
    )
    def test_recognises_the_topic(self, text, key):
        assert key in T.detect_asked(text)

    def test_statement_is_not_a_question(self):
        assert T.detect_asked("my day was long") == []

    def test_unrelated_question_records_nothing(self):
        assert T.detect_asked("you still there?") == []


class TestTimeAppropriateness:
    def test_how_was_your_day_not_in_the_afternoon(self):
        assert not T.is_available(T.BY_KEY["day_was"], {}, datetime(2026, 8, 11, 14), T.POOBEDE)

    def test_how_was_your_day_in_the_evening(self):
        assert T.is_available(T.BY_KEY["day_was"], {}, datetime(2026, 8, 11, 21), T.VECER)

    def test_how_is_your_day_only_in_the_afternoon(self):
        assert T.is_available(T.BY_KEY["day_going"], {}, datetime(2026, 8, 11, 14), T.POOBEDE)
        assert not T.is_available(T.BY_KEY["day_going"], {}, datetime(2026, 8, 11, 21), T.VECER)

    def test_sleep_question_only_at_night(self):
        assert T.is_available(T.BY_KEY["sleep"], {}, datetime(2026, 8, 11, 1), T.NOC)
        assert not T.is_available(T.BY_KEY["sleep"], {}, datetime(2026, 8, 11, 14), T.POOBEDE)

    def test_weekend_only_late_in_the_week(self):
        friday = datetime(2026, 8, 14, 21)
        tuesday = datetime(2026, 8, 11, 21)
        assert T.is_available(T.BY_KEY["weekend_plans"], {}, friday, T.VECER)
        assert not T.is_available(T.BY_KEY["weekend_plans"], {}, tuesday, T.VECER)


class TestNoRepeats:
    def test_fact_is_never_asked_twice(self):
        asked = {"location": hours_ago(500)}
        assert not T.is_available(
            T.BY_KEY["location"], asked, datetime(2026, 8, 11, 14), T.POOBEDE
        )

    def test_day_question_blocked_inside_cooldown(self):
        asked = {"day_was": hours_ago(5)}
        assert not T.is_available(T.BY_KEY["day_was"], asked, datetime(2026, 8, 11, 21), T.VECER)

    def test_day_question_free_after_cooldown(self):
        asked = {"day_was": hours_ago(25)}
        assert T.is_available(T.BY_KEY["day_was"], asked, datetime(2026, 8, 11, 21), T.VECER)

    def test_suggest_skips_known_facts(self):
        fresh = T.suggest({}, datetime(2026, 8, 11, 14), T.POOBEDE, known_facts=["name"])
        assert "name" not in [t.key for t in fresh]

    def test_suggest_returns_only_available(self):
        asked = T.record({}, ["name", "how_found", "work", "location"], datetime.now(timezone.utc))
        fresh = T.suggest(asked, datetime(2026, 8, 11, 14), T.POOBEDE)
        keys = [t.key for t in fresh]
        assert not {"name", "how_found", "work", "location"} & set(keys)

    def test_recently_asked_lists_facts_forever(self):
        asked = {"location": hours_ago(1000)}
        assert "location" in [t.key for t in T.recently_asked(asked)]

    def test_recently_asked_drops_old_situational(self):
        asked = {"day_was": hours_ago(200)}
        assert "day_was" not in [t.key for t in T.recently_asked(asked)]

    def test_record_does_not_mutate_input(self):
        original = {"name": hours_ago(1)}
        T.record(original, ["work"], datetime.now(timezone.utc))
        assert "work" not in original


class TestTopicsInFlow:
    def test_prompt_lists_fresh_topics(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=4, asked_topics={}),
            [{"role": "user", "content": "hey"}],
            "hows things",
            behavior={**NO_WINDOW, "question_chance": 1.0},
        )
        asyncio.run(bot.reply_to(555))
        assert "Toto ste ešte neprebrali" in llm.prompts[0]

    def test_prompt_forbids_repeats(self):
        asked = T.record({}, ["location", "work"], datetime.now(timezone.utc))
        bot, _, llm, _, _ = build(
            user_row(msg_count=8, asked_topics=asked),
            [{"role": "user", "content": "yeah"}],
            "i see",
            behavior={**NO_WINDOW, "question_chance": 1.0},
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "už NEPÝTAJ" in prompt
        assert "odkiaľ je" in prompt

    def test_no_question_when_chance_is_zero(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=6),
            [{"role": "user", "content": "cool"}],
            "yeah",
            behavior={**NO_WINDOW, "question_chance": 0.0},
        )
        asyncio.run(bot.reply_to(555))
        assert "NEPÝTAJ" in llm.prompts[0]

    def test_asked_topic_is_recorded_after_sending(self):
        bot, db, _, _, _ = build(
            user_row(msg_count=4, asked_topics={}),
            [{"role": "user", "content": "hey"}],
            "im ok, where are you from?",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "location" in (db.users[555].get("asked_topics") or {})

    def test_nothing_recorded_without_a_question(self):
        bot, db, _, _, _ = build(
            user_row(msg_count=4, asked_topics={}),
            [{"role": "user", "content": "hey"}],
            "im just relaxing at home",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert not (db.users[555].get("asked_topics") or {})


class TestReliability:
    def test_llm_failure_leaves_it_for_the_sweeper(self):
        bot, db, llm, client, _ = build(
            user_row(msg_count=4),
            [{"role": "user", "content": "hey"}],
            "whatever",
            behavior=NO_WINDOW,
        )

        async def boom(*_a, **_k):
            raise RuntimeError("model down")

        llm.reply = boom
        asyncio.run(bot.reply_to(555))
        assert client.sent == []
        assert db.users[555]["pending_reply"] is True, "správa nesmie zapadnúť"

    def test_empty_reply_is_retried_too(self):
        bot, db, _, client, _ = build(
            user_row(msg_count=4),
            [{"role": "user", "content": "hey"}],
            "   ",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert client.sent == []
        assert db.users[555]["pending_reply"] is True


class TestChatShorthand:
    """V chate sa píše „u" a otázniky sa vynechávajú — detekcia to musí zniesť."""

    @pytest.mark.parametrize(
        "text,key",
        [
            ("how did u find me here?", "how_found"),
            ("hows ur day going?", "day_going"),
            ("where r u from?", "location"),
            ("wat do u do for work?", "work"),
        ],
    )
    def test_shorthand_still_matches(self, text, key):
        assert key in T.detect_asked(text)

    @pytest.mark.parametrize(
        "text,key",
        [
            ("what u ordering for dinner", "food"),
            ("what do u usually do after a long day", "hobbies"),
            ("do u work tomorrow", "work_tomorrow"),
        ],
    )
    def test_question_without_question_mark(self, text, key):
        assert key in T.detect_asked(text), "otázka bez otáznika sa musí zapísať"

    @pytest.mark.parametrize(
        "text",
        ["my day was long and boring", "i love metal music", "im just laying in bed"],
    )
    def test_statements_record_nothing(self, text):
        assert T.detect_asked(text) == []

    def test_normalise_expands_shorthand(self):
        assert "you" in T.normalise("how did u find me")
        assert "your" in T.normalise("hows ur day")
