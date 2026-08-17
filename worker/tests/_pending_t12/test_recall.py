"""Epizódy, sľuby a archív — pamäť, ktorá si pamätá dej, nie len stav."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import recall

from test_reply_flow import build, user_row

pytestmark = pytest.mark.usefixtures("fast")

NOW = datetime(2026, 8, 11, 20, tzinfo=timezone.utc)
NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}


def at(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).isoformat()


class TestSessions:
    def test_open_session_is_not_closed(self):
        rows = [{"created_at": at(2)}, {"created_at": at(1)}]
        assert not recall.session_closed(rows, NOW)

    def test_long_silence_closes_it(self):
        rows = [{"created_at": at(30)}, {"created_at": at(28)}]
        assert recall.session_closed(rows, NOW)

    def test_single_message_is_not_a_session(self):
        assert not recall.session_closed([{"created_at": at(30)}], NOW)

    def test_last_session_stops_at_the_gap(self):
        rows = [
            {"content": "a", "created_at": at(50)},
            {"content": "b", "created_at": at(49)},
            {"content": "c", "created_at": at(3)},
            {"content": "d", "created_at": at(2)},
        ]
        assert [r["content"] for r in recall.last_session(rows)] == ["c", "d"]

    def test_one_continuous_run_is_all_of_it(self):
        rows = [{"content": "a", "created_at": at(3)}, {"content": "b", "created_at": at(2)}]
        assert len(recall.last_session(rows)) == 2


class TestBlocks:
    def test_episodes_use_human_dating(self):
        block = recall.episodes_block(
            [{"ended_at": at(24 * 5), "body": "bol na dne z rozchodu", "mood": "na dne"}], NOW
        )
        assert "pred 5 dňami" in block
        assert "na dne" in block

    def test_yesterday_and_today(self):
        assert "včera" in recall.episodes_block([{"ended_at": at(30), "body": "x"}], NOW)
        assert "dnes" in recall.episodes_block([{"ended_at": at(3), "body": "x"}], NOW)

    def test_empty_inputs_give_empty_blocks(self):
        assert recall.episodes_block([]) == ""
        assert recall.loops_block([]) == ""
        assert recall.archive_block([], "Ona") == ""

    def test_loops_lists_only_open_ones(self):
        rows = [{"what": "sľúbila poslať odkaz", "closed_at": None},
                {"what": "stará vec", "closed_at": at(1)}]
        block = recall.loops_block(rows)
        assert "sľúbila poslať odkaz" in block
        assert "stará vec" not in block


class TestSearchTerms:
    def test_keeps_meaningful_words(self):
        terms = recall.search_terms("i was thinking about that trip to colorado with my brother")
        assert "colorado" in terms
        assert "brother" in terms

    def test_drops_filler(self):
        terms = recall.search_terms("yeah that would be really good i think")
        assert "would" not in terms and "really" not in terms

    def test_short_message_gives_little(self):
        assert recall.search_terms("ok cool") == ""


class TestMemoryInPrompt:
    def _memory_db(self, db, episodes=(), loops=(), hits=()):
        async def episodes_for(_tg_id, limit=4):
            return list(episodes)

        async def open_loops(_tg_id):
            return list(loops)

        async def search_archive(_tg_id, _query, limit=5):
            return list(hits)

        db.episodes_for = episodes_for
        db.open_loops = open_loops
        db.search_archive = search_archive

    def test_episodes_reach_the_prompt(self):
        bot, db, llm, _, _ = build(
            user_row(msg_count=12),
            [{"role": "user", "content": "hey again"}],
            "hey you",
            behavior=NO_WINDOW,
        )
        self._memory_db(db, episodes=[{"ended_at": at(24 * 4), "body": "bol na dne z rozchodu"}])
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "ČO STE SPOLU ZAŽILI" in prompt
        assert "rozchodu" in prompt

    def test_open_promises_reach_the_prompt(self):
        bot, db, llm, _, _ = build(
            user_row(msg_count=12),
            [{"role": "user", "content": "so?"}],
            "right",
            behavior=NO_WINDOW,
        )
        self._memory_db(db, loops=[{"what": "sľúbila mu povedať kde ju nájde", "closed_at": None}])
        asyncio.run(bot.reply_to(555))
        assert "NESPLNILA" in llm.prompts[0]

    def test_archive_hits_reach_the_prompt(self):
        bot, db, llm, _, _ = build(
            user_row(msg_count=20),
            [{"role": "user", "content": "remember that colorado trip i mentioned"}],
            "of course",
            behavior=NO_WINDOW,
        )
        self._memory_db(
            db, hits=[{"role": "user", "content": "i went to colorado last summer", "created_at": at(24 * 40)}]
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "STARŠIE ÚRYVKY" in prompt
        assert "colorado" in prompt

    def test_nothing_extra_when_memory_is_empty(self):
        bot, db, llm, _, _ = build(
            user_row(msg_count=3),
            [{"role": "user", "content": "hey"}],
            "hi",
            behavior=NO_WINDOW,
        )
        self._memory_db(db)
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "ČO STE SPOLU ZAŽILI" not in prompt
        assert "STARŠIE ÚRYVKY" not in prompt

    def test_memory_failure_does_not_block_the_reply(self):
        bot, db, _, client, _ = build(
            user_row(msg_count=9),
            [{"role": "user", "content": "hey"}],
            "hi there",
            behavior=NO_WINDOW,
        )

        async def boom(*_a, **_k):
            raise RuntimeError("db down")

        db.episodes_for = boom
        db.open_loops = boom
        db.search_archive = boom
        asyncio.run(bot.reply_to(555))
        assert client.sent, "pamäť navyše nesmie zhodiť odpoveď"
