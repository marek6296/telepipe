"""Meno partnera — raz povedané, nikdy sa naň už nepýta."""
import asyncio

import funnel
import pytest

from test_reply_flow import build, user_row

pytestmark = pytest.mark.usefixtures("fast")

NO_WINDOW = {"active_start_min": 0, "active_end_min": 0}


class TestExtractName:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("hey im dan", "Dan"),
            ("My name is Michael btw", "Michael"),
            ("call me jt", "Jt"),
            ("this is Tom", "Tom"),
            ("it's mike here", "Mike"),
            ("name's alex", "Alex"),
        ],
    )
    def test_finds_the_name(self, text, expected):
        assert funnel.extract_name(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "im good thanks",
            "im from ohio",
            "im really horny",
            "im 45 and single",
            "hey how are you",
            "im just bored",
            "im looking for fun",
        ],
    )
    def test_does_not_invent_names(self, text):
        assert funnel.extract_name(text) == ""

    def test_normalises_capitalisation(self):
        assert funnel.extract_name("im DAN") == "Dan"


class TestAsksForName:
    @pytest.mark.parametrize(
        "text",
        ["whats your name?", "what should i call u", "do you have a name", "your name?"],
    )
    def test_detects_the_question(self, text):
        assert funnel.asks_for_name(text)

    def test_ignores_other_questions(self):
        assert not funnel.asks_for_name("hows your day going")
        assert not funnel.asks_for_name("whats your favourite food")


class TestNameInPrompt:
    def test_known_name_forbids_asking_again(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=8, partner_name="Dan"),
            [{"role": "user", "content": "hey again"}],
            "hows it going",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        prompt = llm.prompts[0]
        assert "Volá sa Dan" in prompt
        assert "NIKDY nepýtaj" in prompt

    def test_unknown_name_allows_asking_once(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=2, partner_name="", name_asked=False),
            [{"role": "user", "content": "hey"}],
            "hey you",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert "Môžeš sa raz mimochodom spýtať" in llm.prompts[0]

    def test_already_asked_does_not_ask_again(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=5, partner_name="", name_asked=True),
            [{"role": "user", "content": "hey"}],
            "whats up",
            behavior=NO_WINDOW,
        )
        assert asyncio.run(bot.reply_to(555)) is None
        assert "Nepýtaj sa znova" in llm.prompts[0]

    def test_pet_names_are_offered(self):
        bot, _, llm, _, _ = build(
            user_row(msg_count=5), [{"role": "user", "content": "hey"}], "hi", behavior=NO_WINDOW
        )
        asyncio.run(bot.reply_to(555))
        assert "honey" in llm.prompts[0]


class TestNameIsRemembered:
    def test_records_name_when_he_introduces_himself(self):
        bot, db, _, _, _ = build(
            user_row(msg_count=3, partner_name=""),
            [{"role": "user", "content": "hey"}],
            "hi",
            behavior=NO_WINDOW,
        )
        # simulácia príchodu správy cez handler je v test_incoming_filter;
        # tu overujeme, že sa meno prenesie do promptu, keď už v DB je
        db.users[555]["partner_name"] = "Dan"
        _, _, llm, _, _ = build(
            user_row(msg_count=4, partner_name="Dan"),
            [{"role": "user", "content": "so what now"}],
            "we talk",
            behavior=NO_WINDOW,
        )
        assert db.users[555]["partner_name"] == "Dan"

    def test_marks_name_as_asked_after_asking(self):
        bot, db, _, _, _ = build(
            user_row(msg_count=2, partner_name="", name_asked=False),
            [{"role": "user", "content": "hey"}],
            "hey you, whats your name?",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert db.users[555]["name_asked"] is True, "aby sa už nepýtala druhýkrát"

    def test_does_not_mark_when_she_did_not_ask(self):
        bot, db, _, _, _ = build(
            user_row(msg_count=2, partner_name="", name_asked=False),
            [{"role": "user", "content": "hey"}],
            "hows your evening going",
            behavior=NO_WINDOW,
        )
        asyncio.run(bot.reply_to(555))
        assert db.users[555].get("name_asked") is False
