"""Fakty — append-only pamäť, ktorá sa neprepisuje sama zo seba."""
import asyncio

import facts
import pytest

from test_reply_flow import build, user_row

pytestmark = pytest.mark.usefixtures("fast")

NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}


class TestMergePlan:
    def test_new_fact_is_inserted(self):
        plan = facts.merge_plan([], [{"key": "work", "value": "truck driver"}])
        assert [i["key"] for i in plan["inserts"]] == ["work"]
        assert plan["supersedes"] == []

    def test_same_value_only_confirms(self):
        existing = [{"id": 1, "key": "work", "value": "truck driver", "superseded_by": None}]
        plan = facts.merge_plan(existing, [{"key": "work", "value": "Truck  Driver"}])
        assert plan["confirms"] == [1]
        assert plan["inserts"] == []

    def test_changed_value_supersedes_instead_of_overwriting(self):
        """Rozchod nesmie zmazať, že mal priateľku — len to odložiť."""
        existing = [{"id": 2, "key": "relationship", "value": "girlfriend Sarah", "superseded_by": None}]
        plan = facts.merge_plan(existing, [{"key": "relationship", "value": "broke up with Sarah"}])
        assert plan["supersedes"] == [2]
        assert [i["value"] for i in plan["inserts"]] == ["broke up with Sarah"]

    def test_already_superseded_is_ignored(self):
        existing = [{"id": 3, "key": "work", "value": "old job", "superseded_by": 9}]
        plan = facts.merge_plan(existing, [{"key": "work", "value": "new job"}])
        assert plan["supersedes"] == []
        assert len(plan["inserts"]) == 1


class TestSheet:
    def test_lists_only_active_facts(self):
        rows = [
            {"key": "work", "value": "truck driver", "superseded_by": None},
            {"key": "relationship", "value": "girlfriend Sarah", "superseded_by": 9},
        ]
        sheet = facts.sheet(rows)
        assert "truck driver" in sheet
        assert "Predtým platilo" in sheet

    def test_empty_without_facts(self):
        assert facts.sheet([]) == ""

    def test_known_keys_only_from_active(self):
        rows = [
            {"key": "work", "value": "x", "superseded_by": None},
            {"key": "location", "value": "y", "superseded_by": 4},
        ]
        assert facts.known_keys(rows) == ["work"]

    def test_free_form_keys_are_not_topics(self):
        rows = [{"key": "boss_name", "value": "Dave", "superseded_by": None}]
        assert facts.known_keys(rows) == []


class TestParsing:
    def test_handles_code_fence(self):
        assert facts._coerce('```json\n[{"key":"work","value":"driver"}]\n```') == [
            {"key": "work", "value": "driver"}
        ]

    def test_handles_surrounding_text(self):
        assert facts._coerce('Here you go: [{"key":"pets","value":"a dog"}] hope it helps') == [
            {"key": "pets", "value": "a dog"}
        ]

    def test_broken_json_returns_nothing(self):
        assert facts._coerce("not json at all") == []

    def test_drops_incomplete_items(self):
        assert facts._coerce('[{"key":"","value":"x"},{"key":"work"}]') == []


class TestFactsInFlow:
    def test_fact_sheet_reaches_the_prompt(self):
        bot, db, llm, _, _ = build(
            user_row(msg_count=9),
            [{"role": "user", "content": "yeah"}],
            "i see",
            behavior=NO_WINDOW,
        )
        db.facts_rows = [{"key": "work", "value": "truck driver from Ohio", "superseded_by": None}]
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "ČO O ŇOM VIEŠ" in prompt
        assert "truck driver from Ohio" in prompt

    def test_known_facts_close_the_matching_topic(self):
        """Toto bola diera: known_facts dostávalo len ["name"]."""
        bot, db, llm, _, _ = build(
            user_row(msg_count=4, asked_topics={}),
            [{"role": "user", "content": "hey"}],
            "hi there",
            behavior={**NO_WINDOW, "question_chance": 1.0},
        )
        db.facts_rows = [
            {"key": "work", "value": "truck driver", "superseded_by": None},
            {"key": "location", "value": "Ohio", "superseded_by": None},
        ]
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        suggestions = prompt.split("Toto ste ešte neprebrali a teraz to sedí:")[-1].split(".")[0]
        assert "čo robí" not in suggestions
        assert "odkiaľ je" not in suggestions

    def test_no_section_without_facts(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=4),
            [{"role": "user", "content": "hey"}],
            "hi",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "ČO O ŇOM VIEŠ" not in llm.prompts[0]
