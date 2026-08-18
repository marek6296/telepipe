import pytest
import random
from datetime import datetime

import humanize

RNG = random.Random(42)


class TestSanitize:
    def test_strips_greeting_in_ongoing_chat(self):
        assert humanize.sanitize("Ahoj, ako sa mas?", keep_greeting=False) == "ako sa mas?"

    def test_keeps_greeting_in_first_reply(self):
        assert humanize.sanitize("Ahoj, ako sa mas?", keep_greeting=True) == "Ahoj, ako sa mas?"

    def test_strips_english_greeting(self):
        assert humanize.sanitize("Hey! what's up", keep_greeting=False) == "what's up"

    def test_removes_roleplay_actions(self):
        out = humanize.sanitize("*usmieva sa* to je milé", keep_greeting=True)
        assert "*" not in out
        assert out == "to je milé"

    def test_removes_speaker_prefix(self):
        assert humanize.sanitize("Lucia: cakam na teba", keep_greeting=True) == "cakam na teba"

    def test_unwraps_quotes(self):
        assert humanize.sanitize('"len tak sedim"', keep_greeting=True) == "len tak sedim"

    def test_does_not_strip_greeting_mid_sentence(self):
        out = humanize.sanitize("to je ahoj efekt", keep_greeting=False)
        assert out == "to je ahoj efekt"


class TestSplitMessage:
    def test_single_paragraph_stays_one(self):
        assert humanize.split_message("jedna sprava") == ["jedna sprava"]

    def test_splits_paragraphs(self):
        assert humanize.split_message("prva\n\ndruha") == ["prva", "druha"]

    def test_caps_at_three_chunks(self):
        chunks = humanize.split_message("a\n\nb\n\nc\n\nd\n\ne")
        assert len(chunks) == 3
        assert chunks[-1] == "c d e"

    def test_empty_returns_empty_list(self):
        assert humanize.split_message("   ") == []


class TestDelays:
    def test_typing_delay_grows_with_length(self):
        short = humanize.typing_delay("ok", RNG)
        long = humanize.typing_delay("x" * 300, RNG)
        assert long > short

    def test_typing_delay_capped(self):
        assert humanize.typing_delay("x" * 5000, RNG) <= 40.0

    def test_read_delay_in_range(self):
        assert 2.0 <= humanize.read_delay(RNG) <= 9.0

    def test_debounce_in_range(self):
        assert 8 <= humanize.debounce_seconds(8, 20, RNG) <= 20


class TestQuietHours:
    def test_inside_overnight_window(self):
        assert humanize.in_quiet_hours(datetime(2026, 8, 11, 3, 0), 2, 8)

    def test_outside_window(self):
        assert not humanize.in_quiet_hours(datetime(2026, 8, 11, 14, 0), 2, 8)

    def test_boundary_start_is_quiet(self):
        assert humanize.in_quiet_hours(datetime(2026, 8, 11, 2, 0), 2, 8)

    def test_boundary_end_is_awake(self):
        assert not humanize.in_quiet_hours(datetime(2026, 8, 11, 8, 0), 2, 8)

    def test_window_crossing_midnight(self):
        assert humanize.in_quiet_hours(datetime(2026, 8, 11, 23, 30), 22, 6)
        assert humanize.in_quiet_hours(datetime(2026, 8, 11, 5, 0), 22, 6)
        assert not humanize.in_quiet_hours(datetime(2026, 8, 11, 12, 0), 22, 6)

    def test_next_wake_is_in_future(self):
        now = datetime(2026, 8, 11, 3, 0)
        assert humanize.next_wake_time(now, 8, RNG) > now


class TestContainsLink:
    def test_matches_domain(self):
        assert humanize.contains_link("skus https://fanvue.com/lucia", "https://fanvue.com/lucia")

    def test_matches_without_scheme(self):
        assert humanize.contains_link("najdes ma na fanvue.com/lucia", "https://www.fanvue.com/lucia")

    def test_no_match(self):
        assert not humanize.contains_link("ako sa mas", "https://fanvue.com/lucia")

    def test_empty_link_never_matches(self):
        assert not humanize.contains_link("fanvue.com", "")


class TestAiQuestion:
    def test_detects_direct_question(self):
        assert humanize.looks_like_ai_question("si AI?")

    def test_detects_bot_question(self):
        assert humanize.looks_like_ai_question("ty si nejaky bot alebo co")

    def test_detects_english(self):
        assert humanize.looks_like_ai_question("are you ai")

    def test_ignores_normal_text(self):
        assert not humanize.looks_like_ai_question("co robis dnes vecer")


class TestHolyPozdrav:
    """Na samotné „hey" sa neodpovedá tým, že ležím v posteli a scrollujem."""

    @pytest.mark.parametrize("text", [
        "hey", "Hi beautiful !!", "hello babe 😊", "hey there gorgeous",
        "yo", "good morning", "Hey!!", "hiya cutie",
    ])
    def test_pozna_holy_pozdrav(self, text):
        assert humanize.is_bare_greeting(text)

    @pytest.mark.parametrize("text", [
        "hey whats up?", "hi im don from instagram", "hey do u live in la",
        "hello, i saw your photos and you look amazing", "", "wow",
    ])
    def test_obsah_nie_je_pozdrav(self, text):
        assert not humanize.is_bare_greeting(text)


class TestZnackyZArchivu:
    """Prepis hlasovky nesmie odísť klientovi ako text."""

    def test_riadok_s_hlasovkou_vypadne_cely(self):
        """Nestačí zmazať značku — prepis by aj tak odišiel ako text."""
        assert humanize.strip_archive_marks("(hlasovka) heeey marek") == ""

    def test_odstrani_znacku_fotky(self):
        assert humanize.strip_archive_marks("[poslala fotku: selfie] hey") == "hey"

    def test_bezny_text_nechava(self):
        assert humanize.strip_archive_marks("hey how are u") == "hey how are u"

    def test_pozna_opakovanie_hlasovky(self):
        prepis = "heeey marek so u really want my voice huh here u go then"
        assert humanize.repeats_voice("marek u really want my voice here u go", prepis)

    def test_ina_sprava_nie_je_opakovanie(self):
        prepis = "heeey marek so u really want my voice huh here u go then"
        assert not humanize.repeats_voice("what do u do for work babe", prepis)


class TestZnackyKdekolvek:
    """Značky sa objavili aj uprostred správy, nielen na začiatku."""

    def test_znacka_fotky_uprostred(self):
        vstup = "[poslala fotku: bathroom selfie in black lingerie, smiling]\nthis is as far as i go here hun 😜"
        assert humanize.strip_archive_marks(vstup) == "this is as far as i go here hun 😜"

    def test_riadok_s_hlasovkou_vypadne_cely(self):
        vstup = "this is as far as i go hun\n(hlasovka) Okay, listen. Come find me on my page."
        assert humanize.strip_archive_marks(vstup) == "this is as far as i go hun"

    def test_obe_znacky_naraz(self):
        vstup = ("[poslala fotku: selfie]\nhotter only on my page\n"
                 "(hlasovka) Come find me there, itll be fun")
        assert humanize.strip_archive_marks(vstup) == "hotter only on my page"

    def test_ked_ostane_prazdno(self):
        assert humanize.strip_archive_marks("(hlasovka) heeey marek") == ""

    def test_bezny_viacriadkovy_text_prezije(self):
        vstup = "hey babe\nwhat are u up to today?"
        assert humanize.strip_archive_marks(vstup) == vstup


class TestKnizneSlova:
    """Zoznam zakázaných slov v prompte ich modelu paradoxne drží pred očami.

    Preto sa riešia až na výstupe — tam sa na ne nedá zabudnúť.
    """

    def test_prepise_knizne_slova(self):
        out = humanize.plain_words("that sounds intriguing, whilst i was utilizing it")
        assert "intriguing" not in out and "whilst" not in out
        assert "interesting" in out and "while" in out

    def test_zachova_velke_pismeno_na_zaciatku(self):
        assert humanize.plain_words("Perhaps later").startswith("Maybe")

    def test_nedotkne_sa_beznych_slov(self):
        veta = "hey babe hows ur day going"
        assert humanize.plain_words(veta) == veta

    def test_ide_aj_cez_sanitize(self):
        out = humanize.sanitize("that is fascinating", keep_greeting=True)
        assert "fascinating" not in out


class TestZnackaHlasovkyZprostred:
    """Model značku rád predradí vlastnou vetou — prepis nesmie prejsť."""

    def test_znacka_uprostred_riadku_zahodi_cely_riadok(self):
        out = humanize.strip_archive_marks("one sec (hlasovka) im so tired today")
        assert "tired" not in out and "hlasovka" not in out

    def test_znacka_na_zaciatku_stale_funguje(self):
        assert humanize.strip_archive_marks("(hlasovka) hey there") == ""

    def test_bezny_text_ostane(self):
        assert humanize.strip_archive_marks("hey how are u") == "hey how are u"


class TestEmojiNieVKazdejSprave:
    """Meranie na živých dátach ukázalo emoji v 100 % správ.

    Prompt hovorí „občas žiadne, aby to nebolo mechanické" a model to
    nedodrží — rovnaký prípad ako diakritika.
    """

    SERIA = ["ahoj 😄", "no tak 🥰", "jasne 😘"]

    def test_po_troch_emoji_stvrta_ide_bez(self):
        out = humanize.thin_emoji("to znie dobre 😜", self.SERIA)
        assert "😜" not in out
        assert out == "to znie dobre"

    def test_kratsia_seria_sa_nedotkne(self):
        assert "😜" in humanize.thin_emoji("to znie dobre 😜", self.SERIA[:2])

    def test_prerusena_seria_sa_nedotkne(self):
        seria = ["ahoj 😄", "no tak", "jasne 😘"]
        assert "😜" in humanize.thin_emoji("to znie dobre 😜", seria)

    def test_sprava_bez_emoji_ostava_ako_bola(self):
        assert humanize.thin_emoji("to znie dobre", self.SERIA) == "to znie dobre"

    def test_neostane_visiet_medzera_pred_bodkou(self):
        out = humanize.thin_emoji("haha 😅, no jasne", self.SERIA)
        assert ", " in out and "  " not in out

    def test_srdiecko_s_variacnym_znakom_zmizne_cele(self):
        out = humanize.thin_emoji("mam ta rada ❤️", self.SERIA)
        assert out == "mam ta rada"


class TestObvineniaZBota:
    """Najčastejšie formulácie musia byť rozpoznané — inak sa začne obhajovať."""

    @pytest.mark.parametrize("text", [
        "are u real?", "are u a bot", "r u real", "are you human?",
        "prove ur real", "prove it", "ur a bot", "i think this is a bot",
        "how do i know u are real", "am i talking to a bot?", "you are fake",
    ])
    def test_pozna_obvinenie(self, text):
        assert humanize.looks_like_ai_question(text)

    @pytest.mark.parametrize("text", [
        "hey how are u", "send me a pic", "are u free tonight",
        "what do u do for work",
    ])
    def test_bezna_sprava_nie(self, text):
        assert not humanize.looks_like_ai_question(text)


class TestTlakZBota:
    """Raz je bežná otázka, štyrikrát je to človek, ktorý si to nedá vyhovoriť."""

    @staticmethod
    def _chat(*texty):
        return [{"role": "user", "content": t} for t in texty]

    def test_pocita_len_jeho_spravy(self):
        rows = self._chat("are u real?", "ur a bot") + [
            {"role": "assistant", "content": "lol are u a bot"}
        ]
        assert humanize.ai_question_count(rows) == 2

    def test_bezny_chat_nula(self):
        assert humanize.ai_question_count(self._chat("hey", "how was ur day")) == 0

    def test_prazdna_historia(self):
        assert humanize.ai_question_count([]) == 0


class TestPoslednaOtazka:
    """Debounce zlepí jeho správy — odpovedať sa má na tú, čo je otázka."""

    def test_vyberie_poslednu_otazku(self):
        text = "I live in a tiny home.\nis there a possibility to see more? Or to phone with you?"
        assert humanize.last_question(text) == "Or to phone with you?"

    def test_otazka_bez_otaznika(self):
        assert humanize.last_question("im tired today\nwhat do u do for work") == "what do u do for work"

    def test_bez_otazky_prazdno(self):
        assert humanize.last_question("hey babe") == ""
        assert humanize.last_question("nice") == ""


class TestOslovenieMenom:
    """V reálnom chate ho oslovila menom skoro v každej správe, a malým."""

    def test_ked_nema_oslovovat_meno_zmizne(self):
        assert "don" not in humanize.enforce_name(
            "aw i know it does don but thats how i roll", "Don", False).lower()

    def test_ked_ma_oslovit_je_s_velkym(self):
        assert "Don" in humanize.enforce_name("morning don, still in bed", "Don", True)

    def test_nezostane_visiaca_ciarka(self):
        out = humanize.enforce_name("morning don, still in bed", "Don", False)
        assert not out.startswith(",") and ", ," not in out

    def test_bez_mena_nemeni_nic(self):
        assert humanize.enforce_name("hey babe", "", False) == "hey babe"


class TestCiarky:
    """Dievča na mobile píše krátke vety za sebou, nie súvetia s čiarkami."""

    def test_vacsina_ciarok_zmizne(self):
        text = "nothing wrong with u, i just stick to this, thats my choice, really"
        vysledok = humanize.thin_commas(text, keep=0.0)
        assert "," not in vysledok

    def test_cislo_ostane_cele(self):
        assert "1,5" in humanize.thin_commas("its 1,5 inches, not more", keep=0.0)

    def test_nezostanu_dvojite_medzery(self):
        assert "  " not in humanize.thin_commas("a, b, c", keep=0.0)


class TestPozdravSaNesmieRozbit:
    """Naživo: on napísal „Hello", ona odpovedala „you 🥰 missed that hello…".

    Model napísal „hey you 🥰 missed that…" a čistička zožrala „hey" — ostalo
    holé „you". On sa spýtal „Miss?", lebo tomu nerozumel, a celý rozhovor
    sa od toho zvrtol.
    """

    def test_visiace_you_vypadne_s_pozdravom(self):
        out = humanize.sanitize("hey you 🥰 missed that hello already huh", keep_greeting=False)
        assert not out.startswith("you"), out

    def test_you_vo_vete_ostava(self):
        """„hey you look tired" nesmie skončiť ako „look tired"."""
        out = humanize.sanitize("hey you look tired", keep_greeting=False)
        assert out == "you look tired"

    def test_ine_zvysky_stale_padaju(self):
        for text, ocakavane in (
            ("hey there babe", "babe"),
            ("hi yourself", ""),
            ("hey you too", ""),
        ):
            assert humanize.sanitize(text, keep_greeting=False) == ocakavane, text


class TestPrikyvnutie:
    """Na „Nice 😅" sa nedá stavať a nedá sa na tom ani priostriť.

    Naživo z toho vytiahla, že by mala postnúť niečo horúcejšie — na správu,
    ktorá bola len znakom, že číta.
    """

    def test_pozna_prikyvnutie(self):
        for text in ["Nice 😅", "nice", "haha", "ok", "yeah 😄", "😅", "true", "damn"]:
            assert humanize.is_filler(text), text

    def test_veta_s_obsahom_nie_je_prikyvnutie(self):
        for text in ["nice, what did you do?", "ok so what now",
                     "that sounds nice", "haha yeah i went there too"]:
            assert not humanize.is_filler(text), text

    def test_otazka_nikdy_nie_je_prikyvnutie(self):
        assert not humanize.is_filler("nice?")

    def test_prazdne_nie(self):
        assert not humanize.is_filler("")


class TestDrzost:
    """Drzosť na ňu vs. sexting — hranica, na ktorej stojí sekcia o hrdosti.

    Falošný poplach uprostred sextingu by zabil náladu presne vo chvíli, keď
    má byť horúca. Preto zoznam chytá len jednoznačné útoky NA ŇU.
    """

    def test_utoky_chyta(self):
        for veta in (
            "fuck you", "fuck off", "stfu", "shut up bitch", "shut the fuck up",
            "youre so stupid", "you're pathetic", "you are ugly",
            "i hate you", "go to hell", "screw you", "kys",
            "stupid bitch", "fucking whore", "fake bitch",
            "this is a waste of my time",
        ):
            assert humanize.is_hostile(veta), veta

    def test_sexting_a_komplimenty_nechyta(self):
        for veta in (
            "fuck me", "i want to fuck you so bad",  # smerom K nej, nie útok
            "you drive me crazy", "youre so hot", "i love you",
            "youre beautiful", "damn girl", "you dirty girl",
            "im so stupid haha",       # nadáva sebe, nie jej
            "that movie was trash",    # nadáva filmu
        ):
            assert not humanize.is_hostile(veta), veta

    def test_prazdne_nie(self):
        assert not humanize.is_hostile("")
        assert not humanize.is_hostile(None)


class TestReakciaNaText:
    """Emoji na jeho bubline — kedy vôbec sedí. ČI sa pošle, rieši volajúci."""

    def test_smiech_vyhrava(self):
        assert humanize.text_reaction("hahaha that was so funny") == "🤣"
        assert humanize.text_reaction("lol ok 😂") == "🤣"

    def test_hot_pred_milym(self):
        assert humanize.text_reaction("damn girl you look so hot 😈") == "🔥"

    def test_mile_veci(self):
        assert humanize.text_reaction("i miss you") == "❤️"
        assert humanize.text_reaction("good night cutie") == "❤️"

    def test_bezna_sprava_nic(self):
        assert humanize.text_reaction("what are you doing today") == ""
        assert humanize.text_reaction("ok") == ""

    def test_znacky_medii_nie(self):
        assert humanize.text_reaction("[poslal fotku: pes na gauči]") == ""

    def test_drzost_nedostane_srdiecko(self):
        # „i hate you" obsahuje „you“ vzory milých viet nechytia, ale poistka
        # proti reakcii na útok musí platiť pre celý zoznam drzostí.
        assert humanize.text_reaction("fuck you i love you") == ""
