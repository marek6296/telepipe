"""Realistické chovanie — aktívne okno, pauzy, zdravenie, štýl."""
import random
from datetime import datetime, timedelta, timezone

import pytest

import behavior as bhv
import humanize
import memory
from behavior import Behavior

RNG = random.Random(7)

# Kalifornské okno, ktoré chce Marek: 12:12 – 02:30
CA = Behavior(active_start_min=732, active_end_min=150)


def at(hour, minute=0):
    return datetime(2026, 8, 11, hour, minute)


class TestActiveWindow:
    def test_afternoon_is_active(self):
        assert bhv.in_active_window(at(14, 0), CA.active_start_min, CA.active_end_min)

    def test_just_before_start_is_off(self):
        assert not bhv.in_active_window(at(12, 11), CA.active_start_min, CA.active_end_min)

    def test_start_minute_is_active(self):
        assert bhv.in_active_window(at(12, 12), CA.active_start_min, CA.active_end_min)

    def test_after_midnight_still_active(self):
        assert bhv.in_active_window(at(1, 30), CA.active_start_min, CA.active_end_min)

    def test_end_minute_is_off(self):
        assert not bhv.in_active_window(at(2, 30), CA.active_start_min, CA.active_end_min)

    def test_morning_is_off(self):
        assert not bhv.in_active_window(at(9, 0), CA.active_start_min, CA.active_end_min)

    def test_equal_bounds_means_always_on(self):
        assert bhv.in_active_window(at(4, 0), 0, 0)

    def test_minutes_until_active_is_zero_when_open(self):
        assert bhv.minutes_until_active(at(15, 0), 732, 150) == 0

    def test_minutes_until_active_counts_forward(self):
        assert bhv.minutes_until_active(at(9, 12), 732, 150) == 180

    def test_minutes_until_active_wraps_midnight(self):
        # 03:00, okno sa otvára o 12:12 ten istý deň
        assert bhv.minutes_until_active(at(3, 0), 732, 150) == 552

    def test_window_formatting(self):
        assert bhv.format_window(732, 150) == "12:12–02:30"
        assert bhv.format_window(0, 0) == "24/7"


class TestDeferredReply:
    """„Neodpíše“ neznamená nikdy — znamená až za 2–3 hodiny."""

    def test_never_defers_first_message(self):
        always = Behavior(defer_reply_chance=1.0)
        assert bhv.should_defer_reply(always, 1, "hey") == 0.0

    def test_never_defers_a_question(self):
        always = Behavior(defer_reply_chance=1.0)
        assert bhv.should_defer_reply(always, 9, "what are you doing?") == 0.0

    def test_defers_into_hours_when_certain(self):
        always = Behavior(defer_reply_chance=1.0, defer_min_s=7200, defer_max_s=10800)
        seconds = bhv.should_defer_reply(always, 9, "ok")
        assert 2 <= seconds / 3600 <= 3, "odloženie má byť 2–3 hodiny"

    def test_no_defer_when_disabled(self):
        never = Behavior(defer_reply_chance=0.0)
        assert bhv.should_defer_reply(never, 9, "ok") == 0.0

    def test_default_chance_is_one_percent(self):
        assert Behavior().defer_reply_chance == 0.01


class TestPauses:
    def test_seen_only_returns_zero_when_disabled(self):
        assert bhv.seen_only_delay(Behavior(seen_only_chance=0.0), RNG) == 0.0

    def test_seen_only_in_range_when_certain(self):
        b = Behavior(seen_only_chance=1.0, seen_only_min_s=240, seen_only_max_s=600)
        assert 240 <= bhv.seen_only_delay(b, RNG) <= 600

    def test_long_pause_in_range_when_certain(self):
        b = Behavior(long_pause_chance=1.0, long_pause_min_s=1200, long_pause_max_s=2400)
        delay = bhv.long_pause_delay(b, RNG)
        assert 20 <= delay / 60 <= 40, "dlhá pauza má byť 20–40 minút"

    def test_long_pause_zero_when_disabled(self):
        assert bhv.long_pause_delay(Behavior(long_pause_chance=0.0), RNG) == 0.0

    def test_read_and_reply_delays_in_range(self):
        b = Behavior()
        assert b.read_delay_min_s <= bhv.read_delay(b, RNG) <= b.read_delay_max_s
        assert b.reply_delay_min_s <= bhv.reply_delay(b, RNG) <= b.reply_delay_max_s

    def test_delays_are_randomised(self):
        b = Behavior()
        values = {bhv.read_delay(b) for _ in range(25)}
        assert len(values) > 15, "delaye musia byť náhodné, nie konštantné"


class TestGreetingGap:
    def test_greets_on_very_first_message(self):
        assert bhv.greeting_allowed(Behavior(greeting_gap_hours=6), None)

    def test_does_not_greet_five_minutes_later(self):
        assert not bhv.greeting_allowed(Behavior(greeting_gap_hours=6), 5 / 60)

    def test_does_not_greet_after_two_hours(self):
        assert not bhv.greeting_allowed(Behavior(greeting_gap_hours=6), 2.0)

    def test_greets_after_long_gap(self):
        assert bhv.greeting_allowed(Behavior(greeting_gap_hours=6), 9.0)

    def test_gap_hours_from_timestamps(self):
        now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
        assert bhv.gap_hours(now - timedelta(hours=3), now) == 3.0

    def test_gap_hours_none_without_previous(self):
        assert bhv.gap_hours(None, datetime.now(timezone.utc)) is None

    def test_describe_gap_wording(self):
        assert "prvá správa" in bhv.describe_gap(None)
        assert "minút" in bhv.describe_gap(0.5)
        assert "hodín" in bhv.describe_gap(5.0)
        assert "dní" in bhv.describe_gap(50.0)


class TestBehaviorRow:
    def test_defaults_when_row_missing(self):
        b = Behavior.from_row(None)
        assert b.mode == bhv.REAL
        assert b.active_tz == "America/Los_Angeles"

    def test_reads_row_and_casts_types(self):
        b = Behavior.from_row(
            {
                "mode": "ai",
                "active_start_min": "700",
                "seen_only_chance": "0.25",
                "no_diacritics": False,
                "slang": "medium",
            }
        )
        assert b.mode == bhv.AI
        assert b.active_start_min == 700
        assert b.seen_only_chance == 0.25
        assert b.no_diacritics is False
        assert b.slang == "medium"

    def test_ignores_nulls_and_keeps_defaults(self):
        b = Behavior.from_row({"mode": None, "slang": None})
        assert b.mode == bhv.REAL
        assert b.slang == "light"


class TestWritingLikeAGirl:
    def test_strips_slovak_diacritics(self):
        assert humanize.strip_diacritics("nevadí, ľúbim ťa") == "nevadi, lubim ta"

    def test_keeps_emoji_and_punctuation(self):
        assert humanize.strip_diacritics("čau 😘!") == "cau 😘!"

    def test_handles_empty(self):
        assert humanize.strip_diacritics("") == ""

    KNOWN = 25  # už sa poznajú

    def test_mirror_hint_scales_with_his_length(self):
        """Keď sa už poznajú, dĺžka sa riadi jeho správou."""
        assert "pol vety" in humanize.mirror_length_hint("hey", self.KNOWN)
        assert "JEDNOU" in humanize.mirror_length_hint("hey what are you up today", self.KNOWN)
        assert "do 16 slov" in humanize.mirror_length_hint(" ".join(["word"] * 60), self.KNOWN)

    def test_real_question_unlocks_a_longer_answer(self):
        hint = humanize.mirror_length_hint("why did you move to california?", self.KNOWN, True)
        assert "vetu navyše" in hint

    def test_long_answers_stay_occasional(self):
        """allow_long=False — inak by sa z výnimky stal štandard."""
        hint = humanize.mirror_length_hint("why did you move there?", self.KNOWN, False)
        assert "vetu navyše" not in hint
        assert "drž sa pri zemi" in hint

    def test_small_talk_does_not_unlock_it(self):
        assert "vetu navyše" not in humanize.mirror_length_hint("ok cool", self.KNOWN)

    def test_there_is_still_a_ceiling(self):
        """Strop bol 70 slov, čo je na mobile pol obrazovky — a tak to aj
        vyzeralo. Potom 35, a to bolo stále dvakrát viac, než sa reálne písalo:
        medián jej správy 68 znakov proti 35 u skutočných mužov v tých istých
        chatoch. Marek: „trocha kratsie tie spravy lebo pise strasne dlhe"."""
        for message in ("hey", "why did you move?", " ".join(["w"] * 80)):
            assert "22 slov" in humanize.mirror_length_hint(message, self.KNOWN)

    def test_detects_open_questions(self):
        assert humanize.wants_a_real_answer("what do you think about that")
        assert humanize.wants_a_real_answer("tell me about your day")
        assert not humanize.wants_a_real_answer("u up?")
        assert not humanize.wants_a_real_answer("nice")


class TestEarlyConversation:
    """Cudziemu človeku nikto nepíše dlhé správy."""

    def test_new_person_gets_short_replies(self):
        for message in ("hey", "hey whats up how are you doing today"):
            hint = humanize.mirror_length_hint(message, msg_count=3)
            assert "KRÁTKO" in hint
            assert "do 12 slov" in hint

    def test_even_a_real_question_stays_brief_early(self):
        hint = humanize.mirror_length_hint("tell me about california", msg_count=4)
        assert "do 18 slov" in hint
        assert "vetu navyše" not in hint

    def test_long_message_does_not_unlock_it_early(self):
        hint = humanize.mirror_length_hint(" ".join(["word"] * 60), msg_count=2)
        assert "KRÁTKO" in hint

    def test_opens_up_once_they_know_each_other(self):
        early = humanize.mirror_length_hint("tell me about california", msg_count=4)
        later = humanize.mirror_length_hint("tell me about california", msg_count=20, allow_long=True)
        assert "KRÁTKO" in early
        assert "KRÁTKO" not in later

    def test_boundary_is_the_tenth_message(self):
        assert "KRÁTKO" in humanize.mirror_length_hint("hey", humanize.EARLY_MESSAGES - 1)
        assert "KRÁTKO" not in humanize.mirror_length_hint("hey", humanize.EARLY_MESSAGES)


class TestStyleDetection:
    def test_detects_short_lowercase_no_punctuation(self):
        rows = [
            {"role": "user", "content": "hey"},
            {"role": "user", "content": "u up"},
        ]
        note = memory.describe_style(rows)
        assert "veľmi krátko" in note
        assert "malými písmenami" in note
        assert "neukončuje vety" in note

    def test_detects_emoji_user(self):
        rows = [{"role": "user", "content": "hey there 😍 how are you"}] * 3
        assert "používa emoji" in memory.describe_style(rows)

    def test_ignores_her_own_messages(self):
        rows = [{"role": "assistant", "content": "SOMETHING VERY LONG " * 10}]
        assert memory.describe_style(rows) == ""

    def test_empty_input(self):
        assert memory.describe_style([]) == ""


class TestCaliforniaDay:
    """Musí sa chovať ako dievča žijúce v Kalifornii, nie ako stroj."""

    def test_part_of_day_matches_hour(self):
        assert bhv.part_of_day(at(13)) == "poobede"
        assert bhv.part_of_day(at(18)) == "podvecer"
        assert bhv.part_of_day(at(22)) == "vecer"
        assert bhv.part_of_day(at(1)) == "noc"

    def test_situation_is_stable_within_the_hour(self):
        hints = {bhv.situation_hint(at(14, m)) for m in (0, 20, 45, 59)}
        assert len(hints) == 1, "v jednej hodine si nesmie protirečiť"

    def test_situation_changes_between_hours(self):
        hints = {bhv.situation_hint(at(h)) for h in (12, 13, 14, 15, 18, 19, 22, 23)}
        assert len(hints) > 3, "cez deň sa musí meniť"

    def test_situation_fits_time_of_day(self):
        assert bhv.situation_hint(at(1)) in bhv._SITUATIONS["noc"]

    def test_local_time_line_mentions_time_and_day(self):
        line = bhv.local_time_line(at(22, 30), "California, USA")
        assert "22:30" in line and "California" in line

    def test_local_time_line_pouzije_mesto_persony(self):
        """Ayko býva v New Yorku — natvrdo písaná Kalifornia by jej klamala."""
        assert "New York" in bhv.local_time_line(at(9, 0), "New York City, USA")

    def test_local_time_line_bez_mesta_nevymysla(self):
        line = bhv.local_time_line(at(9, 0))
        assert "09:00" in line and "Kalifor" not in line

    def test_minutes_to_window_end(self):
        assert bhv.minutes_to_window_end(at(2, 0), 732, 150) == 30
        assert bhv.minutes_to_window_end(at(13, 0), 732, 150) == 810

    def test_no_window_end_when_closed(self):
        assert bhv.minutes_to_window_end(at(9, 0), 732, 150) is None

    def test_winding_down_near_the_end(self):
        assert bhv.winding_down(at(2, 0), 732, 150)
        assert not bhv.winding_down(at(20, 0), 732, 150)

    def test_next_window_open(self):
        assert bhv.next_window_open(at(2, 0), 732, 150).strftime("%H:%M") == "12:12"


class TestGoodnightLock:
    def test_detects_goodnight_phrases(self):
        for text in ("gn babe", "goodnight 😴", "im going to bed", "sweet dreams", "gonna sleep"):
            assert bhv.says_goodnight(text), text

    def test_does_not_trigger_on_question_about_sleep(self):
        assert not bhv.says_goodnight("did you sleep well?")
        assert not bhv.says_goodnight("i had a good night out")

    def test_locks_until_next_window_at_night(self):
        until = bhv.should_sleep_until_morning(at(1, 50), CA, "ok gn babe")
        assert until is not None
        assert until.strftime("%H:%M") == "12:12"

    def test_does_not_lock_in_the_afternoon(self):
        assert bhv.should_sleep_until_morning(at(13, 0), CA, "sleep well") is None

    def test_does_not_lock_without_goodnight(self):
        assert bhv.should_sleep_until_morning(at(2, 0), CA, "what u doing") is None


class TestQuickReply:
    """30 % správ má dostať rýchlu, pozornú odpoveď (5–20 s podľa dĺžky)."""

    ALWAYS = Behavior(quick_reply_chance=1.0)

    def test_disabled_returns_none(self):
        assert bhv.quick_reply(Behavior(quick_reply_chance=0.0), "hey", RNG) is None

    def test_returns_read_and_reply_seconds(self):
        read_in, reply_in = bhv.quick_reply(self.ALWAYS, "hey", RNG)
        assert 1.0 <= read_in <= self.ALWAYS.quick_read_max_s
        assert 1.0 <= reply_in <= self.ALWAYS.quick_reply_max_s

    def test_longer_message_takes_longer(self):
        rng = random.Random(11)
        short = min(bhv.quick_reply(self.ALWAYS, "hey", rng)[1] for _ in range(30))
        rng = random.Random(11)
        long = max(bhv.quick_reply(self.ALWAYS, " ".join(["w"] * 45), rng)[1] for _ in range(30))
        assert long > short, "dlhšia správa má trvať dlhšie"

    def test_never_exceeds_configured_maximum(self):
        rng = random.Random(5)
        worst = max(
            bhv.quick_reply(self.ALWAYS, " ".join(["w"] * 200), rng)[1] for _ in range(200)
        )
        assert worst <= self.ALWAYS.quick_reply_max_s, "nesmie prekročiť nastavené maximum"

    def test_triggers_roughly_at_configured_rate(self):
        behavior = Behavior(quick_reply_chance=0.30)
        rng = random.Random(99)
        hits = sum(1 for _ in range(4000) if bhv.quick_reply(behavior, "hey", rng))
        assert 0.26 <= hits / 4000 <= 0.34, f"malo byť ~30 %, bolo {hits / 4000:.1%}"

    def test_default_is_thirty_percent(self):
        assert Behavior().quick_reply_chance == 0.30


class TestNoAiTypography:
    """Dlhá pomlčka a úvodzovky sú najväčší prezradzovač AI. Rieši to kód."""

    def test_em_dash_becomes_comma(self):
        assert humanize.plain_punctuation("i get that a lot — with the red") == (
            "i get that a lot, with the red"
        )

    def test_ellipsis_character_becomes_dots(self):
        assert humanize.plain_punctuation("hmm…") == "hmm..."

    def test_removes_straight_and_curly_quotes(self):
        assert humanize.plain_punctuation('she said "maybe" ok') == "she said maybe ok"
        assert humanize.plain_punctuation("he said “hello”") == "he said hello"

    def test_semicolon_becomes_comma(self):
        assert humanize.plain_punctuation("i dont know; weird") == "i dont know, weird"

    def test_keeps_apostrophes(self):
        assert "don't" in humanize.plain_punctuation("i don't know")

    def test_strips_markdown_and_odd_symbols(self):
        assert humanize.plain_punctuation("~cool~ | stuff # here") == "cool stuff here"

    def test_keeps_emoji(self):
        assert humanize.plain_punctuation("miss u 😘") == "miss u 😘"

    def test_bold_keeps_the_word(self):
        assert humanize.sanitize("thats **really** nice", keep_greeting=True) == (
            "thats really nice"
        )

    def test_roleplay_action_is_removed(self):
        assert humanize.sanitize("*smiles* hey you", keep_greeting=True) == "hey you"

    def test_collapses_long_dot_runs(self):
        assert humanize.plain_punctuation("ok....... fine") == "ok... fine"

    def test_removed_chars_do_not_glue_words(self):
        """Odstránenie znaku bez náhrady zlepilo slová: face"you -> faceyou."""
        assert humanize.plain_punctuation('bare face"you are gorgeous') == (
            "bare face you are gorgeous"
        )
        assert humanize.plain_punctuation("one|two") == "one two"


class TestSlangEnforcement:
    """Na promptové pravidlo sa nedá spoľahnúť — model naň občas zabudne."""

    def test_rn_is_rewritten_for_light(self):
        assert humanize.soften_slang("what made u think of that rn?", "light") == (
            "what made u think of that right now?"
        )

    def test_hard_slang_gone_for_none(self):
        out = humanize.soften_slang("ngl that is wild tbh", "none")
        assert "ngl" not in out and "tbh" not in out

    def test_medium_is_left_alone(self):
        assert humanize.soften_slang("ngl that is wild rn", "medium") == "ngl that is wild rn"

    def test_keeps_soft_slang(self):
        assert "lol" in humanize.soften_slang("lol ok", "light")
        assert "omg" in humanize.soften_slang("omg ok", "none")

    def test_does_not_touch_words_containing_slang(self):
        assert humanize.soften_slang("i was born in france", "none") == (
            "i was born in france"
        )


class TestGreetingRemnants:
    def test_hey_yourself_leaves_no_fragment(self):
        assert humanize.sanitize("hey yourself 😊 just got out", keep_greeting=False) == (
            "😊 just got out"
        )

    def test_hi_there_leaves_no_fragment(self):
        assert humanize.sanitize("hi there, hows it going", keep_greeting=False) == (
            "hows it going"
        )

    def test_greeting_kept_when_allowed(self):
        assert humanize.sanitize("hey you look nice", keep_greeting=True) == (
            "hey you look nice"
        )


class TestModelArtifacts:
    """Klientovi nesmie odísť riadiaci token modelu."""

    def test_strips_trailing_eos(self):
        assert humanize.sanitize("still warm out eos", keep_greeting=True) == "still warm out"

    def test_strips_chat_markers(self):
        assert humanize.sanitize("hey you <|im_end|>", keep_greeting=True) == "hey you"
        assert humanize.sanitize("ok</s>", keep_greeting=True) == "ok"
        assert humanize.sanitize("nice [/INST]", keep_greeting=True) == "nice"

    def test_keeps_the_word_when_it_is_real_text(self):
        text = "he sang the eos song and left"
        assert humanize.sanitize(text, keep_greeting=True) == text

    def test_early_hint_counts_words_not_just_sentences(self):
        assert "12 slov" in humanize.mirror_length_hint("hey", msg_count=3)
        assert "18 slov" in humanize.mirror_length_hint("tell me about it", msg_count=3)


class TestForeignLanguage:
    """Keď nerozumie, musí to milo povedať — nie predstierať, že rozumela."""

    @pytest.mark.parametrize(
        "text",
        [
            "ahoj ako sa mas dnes",
            "hola como estas amigo",
            "wie geht es dir heute",
            "bonjour comment allez vous",
            "привет как дела",
            "こんにちは元気ですか",
        ],
    )
    def test_spots_a_foreign_message(self, text):
        assert humanize.looks_foreign(text)

    @pytest.mark.parametrize(
        "text",
        [
            "hey how are you doing",
            "just got home from work",
            "i love hola tacos",
            "what are you up to tonight",
        ],
    )
    def test_leaves_english_alone(self, text):
        assert not humanize.looks_foreign(text)

    def test_too_short_to_judge(self):
        """Z „hola" sa nedá usúdiť nič — nemá vyzerať, že nechápe ani pozdrav."""
        assert not humanize.looks_foreign("hola")
        assert not humanize.looks_foreign("ok")
        assert not humanize.looks_foreign("")

    def test_non_latin_decides_even_when_short(self):
        assert humanize.looks_foreign("привет")

    def test_english_word_anywhere_rules_it_out(self):
        assert not humanize.looks_foreign("the hola como estas")


class TestPrepinacHlasoviek:
    """Vypnuté hlasovky znamenajú, že si bude len písať."""

    def test_default_je_zapnute(self):
        assert bhv.Behavior().voices_enabled is True

    def test_z_riadku_sa_nacita(self):
        assert bhv.Behavior.from_row({"voices_enabled": False}).voices_enabled is False
        assert bhv.Behavior.from_row({"voices_enabled": True}).voices_enabled is True

    def test_chybajuci_stlpec_neprepne(self):
        assert bhv.Behavior.from_row({}).voices_enabled is True


class TestZaciatokOkna:
    """Ranný beh musí vedieť, ako dávno sa cyklus začal."""

    def test_mimo_okna_nic(self):
        assert bhv.minutes_since_window_start(at(9, 0), 732, 150) is None

    def test_hned_po_starte(self):
        assert bhv.minutes_since_window_start(at(12, 12), 732, 150) == 0

    def test_hodinu_po_starte(self):
        assert bhv.minutes_since_window_start(at(13, 12), 732, 150) == 60

    def test_po_polnoci_sa_pocita_dalej(self):
        """Okno prechádza cez polnoc, takže 1:00 je 13 hodín po štarte."""
        assert bhv.minutes_since_window_start(at(1, 12), 732, 150) == 13 * 60
