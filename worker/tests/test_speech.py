"""Hlasovka na mieru — pokyn od modelu, miestnosť z rozhovoru, hovorená podoba."""
import asyncio

import speech


class TestPokynOdModelu:
    """`[HLAS: ...]` je súhlas modelu. Do chatu sa nesmie dostať nikdy."""

    def test_vytiahne_pokyny_a_ocisti_text(self):
        pokyny, text = speech.parse_directive(
            "[HLAS: pozadie=auto, emocia=unavena]\nhey im driving right now"
        )
        assert pokyny == {"pozadie": "auto", "emocia": "unavena"}
        assert text == "hey im driving right now"

    def test_bez_pokynu_vrati_none(self):
        pokyny, text = speech.parse_directive("hey whats up")
        assert pokyny is None
        assert text == "hey whats up"

    def test_pokazeny_riadok_sa_aj_tak_odstrani(self):
        """Aj keď sa pokyn nedá prečítať, do chatu odísť nesmie."""
        pokyny, text = speech.parse_directive("[HLAS: uplny nezmysel]\nhey")
        assert text == "hey"
        assert "HLAS" not in text
        assert pokyny == {}

    def test_znacka_zprostred_textu_vypadne(self):
        _, text = speech.parse_directive("hey [HLAS: pozadie=doma] whats up")
        assert "HLAS" not in text and "hey" in text and "whats up" in text

    def test_wants_voice(self):
        assert speech.wants_voice({"pozadie": "doma"})
        assert not speech.wants_voice(None)
        assert not speech.wants_voice({"posli": "nie"})

    def test_tempo_z_pokynu(self):
        assert speech.tempo_from({"tempo": "1.2"}, 1.12) == 1.2
        assert speech.tempo_from({"tempo": "9"}, 1.12) == 1.12, "nezmysel → nastavenie"
        assert speech.tempo_from({"tempo": "cosi"}, 1.12) == 1.12
        assert speech.tempo_from(None, 1.12) == 1.12


class TestOdkialZnie:
    """Keď pred chvíľou napísala, že je v aute, nesmie znieť z kuchyne."""

    def test_pokyn_modelu_vyhrava(self):
        assert speech.ambience_from({"pozadie": "auto"}, ["im on the couch"]) == "car"

    def test_inak_rozhoduje_co_o_sebe_povedala(self):
        assert speech.ambience_from(None, ["just got to the gym"]) == "gym"
        assert speech.ambience_from(None, ["im laying in bed"]) == "bedroom"
        assert speech.ambience_from(None, ["stuck in traffic ugh"]) == "car"

    def test_novsia_sprava_prebije_starsiu(self):
        recent = ["i was at home all day", "im outside now on a walk"]
        assert speech.ambience_from(None, recent) == "outside"

    def test_ked_nic_nevyplyva_plati_nastavenie(self):
        assert speech.ambience_from(None, ["haha ok"], fallback="cafe") == "cafe"

    def test_slovenske_aj_anglicke_pomenovanie(self):
        assert speech.ambience_from({"pozadie": "kuchyna"}) == "kitchen"
        assert speech.ambience_from({"pozadie": "kitchen"}) == "kitchen"

    def test_neznamu_miestnost_ignoruje(self):
        assert speech.ambience_from({"pozadie": "vesmir"}, ["im in bed"]) == "bedroom"


class TestHovorenaPodoba:
    def test_emoji_a_skratky_sa_nehovoria(self):
        out = speech.fallback_spoken("haha u ok? 😄 btw idk")
        assert "😄" not in out
        assert "you ok" in out and "by the way" in out and "i dont know" in out

    def test_odkaz_sa_necita_nahlas(self):
        assert "http" not in speech.fallback_spoken("tu mas https://fanvue.com/x")

    def test_prepis_cez_model(self):
        class Llm:
            async def structured(self, *_a, **_k):
                return "hmm no proste [laughs] dneska to bolo dlhe"

        out = asyncio.run(speech.to_spoken(Llm(), "today was long"))
        assert "[laughs]" in out

    def test_zlyhanie_modelu_vrati_ocisteny_text(self):
        class Boom:
            async def structured(self, *_a, **_k):
                raise RuntimeError("model down")

        out = asyncio.run(speech.to_spoken(Boom(), "haha u ok 😄"))
        assert out and "😄" not in out and "you ok" in out

    def test_ukecany_model_sa_zahodi(self):
        """Model občas vráti vysvetlenie namiesto textu — to sa prehovoriť nesmie."""
        class Ukecany:
            async def structured(self, *_a, **_k):
                return "Tu je prepis vašej správy do hovorenej podoby: " + "blabla " * 40

        out = asyncio.run(speech.to_spoken(Ukecany(), "today was long"))
        assert out == "today was long"


class TestNikdyDvakratToIste:
    """Naživo z jednej vety vyšla nahrávka, kde to isté zaznelo trikrát.

    Strop na dĺžku bol `+160 znakov`, čo pri krátkej vete znamená
    štvornásobok — a do toho sa zopakovanie pohodlne zmestilo.
    """

    def test_najde_zopakovanu_frazu(self):
        assert speech.says_twice(
            "hey stranger was wondering when ud pop up again. hey stranger "
            "was wondering when ud pop up"
        )

    def test_bezna_veta_nie_je_opakovanie(self):
        assert not speech.says_twice(
            "like fifteen more minutes then im out, my legs are toast"
        )

    def test_kratke_texty_sa_nehodnotia(self):
        assert not speech.says_twice("hey hey")

    def test_opakovany_prepis_sa_zahodi(self):
        class Opakuje:
            async def structured(self, *_a, **_k):
                return ("hey stranger was wondering when ud pop up again. "
                        "hey stranger was wondering when ud pop up again.")

        out = asyncio.run(
            speech.to_spoken(Opakuje(), "hey stranger was wondering when ud pop up again")
        )
        assert not speech.says_twice(out)
        assert out == "hey stranger was wondering when ud pop up again"

    def test_strop_na_dlzku_je_tesnejsi(self):
        """Krátka veta sa nesmie prepísať na štvornásobok."""
        class Natahuje:
            async def structured(self, *_a, **_k):
                return "no tak proste " * 12

        zaklad = "hey whats up"
        out = asyncio.run(speech.to_spoken(Natahuje(), zaklad))
        assert out == zaklad

    def test_prirodzeny_prepis_s_tagom_prejde(self):
        class Dobry:
            async def structured(self, *_a, **_k):
                return "like fifteen more minutes then im out. [sighs] legs are toast"

        out = asyncio.run(
            speech.to_spoken(Dobry(), "like fifteen more minutes then im out, legs are toast")
        )
        assert "[sighs]" in out


class TestKedNepocul:
    """Hlasovka mu zanikla. Ďalšia by dopadla rovnako."""

    def test_pozna_ze_nerozumel(self):
        import humanize

        for text in [
            "what did you say?", "what was that", "couldnt hear you",
            "i didnt catch that", "say that again", "can u repeat that",
            "sorry it was muffled", "u broke up there",
        ]:
            assert humanize.asks_what_she_said(text), text

    def test_bezna_sprava_to_nespusti(self):
        import humanize

        for text in ["haha ok", "what are you doing", "that sounds good",
                     "say something nice to me"]:
            assert not humanize.asks_what_she_said(text), text

    def test_prompt_kaze_zopakovat_textom(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 9, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False, misheard=True,
        )
        assert "NEPOČUL" in out
        assert "TEXTOM a JEDNODUCHŠIE" in out
        assert "Ďalšiu hlasovku neposielaj" in out

    def test_bez_toho_sekcia_nie_je(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "language": "", "languages": "", "backstory": "",
             "tone": "", "msg_style": "", "boundaries": "", "funnel_rules": "",
             "cta_link": "", "extra_rules": ""},
            {"tg_id": 1, "msg_count": 9, "funnel_stage": "warm"},
            allow_link=False, asked_if_ai=False,
        )
        assert "NEPOČUL" not in out


class TestRozvrhPrebijaStareSpravy:
    """Veta spred dvoch hodín nesmie posielať hlasovku z fitka aj z gauča."""

    def test_rozvrh_vyhrava_nad_starsou_spravou(self):
        assert speech.ambience_from(
            None, her_recent=["im at the gym"], schedule="home"
        ) == "home"

    def test_pokyn_modelu_je_stale_prvy(self):
        assert speech.ambience_from(
            {"pozadie": "auto"}, her_recent=["im at the gym"], schedule="home"
        ) == "car"

    def test_bez_rozvrhu_rozhoduju_jej_spravy(self):
        assert speech.ambience_from(
            None, her_recent=["im at the gym"], schedule=""
        ) == "gym"


class TestVynimkyPreHlasovku:
    """Bežne sa hlasovkou nezačína. Toto sú chvíle, keď je hlas najsilnejší."""

    @staticmethod
    def _b(**kw):
        from behavior import Behavior
        return Behavior(**kw)

    def test_vypytal_si_ju(self):
        assert speech.exception_reason(self._b(), asked_for_voice=True)
        assert not speech.exception_reason(
            self._b(voice_when_asked=False), asked_for_voice=True
        )

    def test_neveri_ze_je_skutocna(self):
        assert speech.exception_reason(self._b(), doubts_her=True)
        assert not speech.exception_reason(
            self._b(voice_when_doubted=False), doubts_her=True
        )

    def test_sam_posiela_hlasovky(self):
        assert speech.exception_reason(self._b(), he_voiced=True)
        assert not speech.exception_reason(
            self._b(voice_when_he_voices=False), he_voiced=True
        )

    def test_vonku_a_dobru_noc_su_vychodiskovo_vypnute(self):
        assert not speech.exception_reason(self._b(), away=True)
        assert not speech.exception_reason(self._b(), winding_down=True)
        assert speech.exception_reason(self._b(voice_when_away=True), away=True)
        assert speech.exception_reason(
            self._b(voice_on_goodnight=True), winding_down=True
        )

    def test_bez_dovodu_ziadna_vynimka(self):
        assert speech.exception_reason(self._b()) == ""

    def test_dovod_je_citatelny_lebo_ide_do_logu(self):
        dovod = speech.exception_reason(self._b(), doubts_her=True)
        assert isinstance(dovod, str) and len(dovod) > 5


class TestPoznaJehoHlasovku:
    def test_pozna_znacky_z_archivu(self):
        assert speech.he_sent_voice("[poslal hlasovku]")
        assert speech.he_sent_voice("[poslal hlasovku, nebolo jej rozumieť]")
        assert speech.he_sent_voice("[v hlasovke povedal] hey whats up")

    def test_bezny_text_nie(self):
        assert not speech.he_sent_voice("send me a voice")
        assert not speech.he_sent_voice("")


class TestPikantnaHlasovkaKedTlaci:
    """Odkaz má, tlačí a nepohol sa. Ďalšia zmienka o stránke ho už otravuje."""

    @staticmethod
    def _b(**kw):
        from behavior import Behavior
        return Behavior(**kw)

    def test_je_to_vynimka(self):
        assert speech.exception_reason(self._b(), hot_stuck=True)

    def test_da_sa_vypnut(self):
        assert not speech.exception_reason(
            self._b(voice_when_hot=False), hot_stuck=True
        )


class TestKedyJeHotAZaseknuty:
    import_funnel = True

    def test_potrebuje_odkaz_aj_tlak(self):
        import funnel

        assert funnel.hot_and_stuck({"link_push_count": 1}, explicit_now=True)
        assert not funnel.hot_and_stuck({"link_push_count": 0}, explicit_now=True)
        assert not funnel.hot_and_stuck({"link_push_count": 2}, explicit_now=False)

    def test_kto_zaplatil_sa_neriesi(self):
        import funnel

        assert not funnel.hot_and_stuck(
            {"link_push_count": 2, "paid": True}, explicit_now=True
        )
        assert not funnel.hot_and_stuck(
            {"link_push_count": 2, "funnel_stage": "converted"}, explicit_now=True
        )
