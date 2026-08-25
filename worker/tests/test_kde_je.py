"""Kde je, musí vedieť od PRVEJ správy — inak si to vymyslí.

ODKIAĽ TO PRIŠLO (25. 8. 2026, chat s Koliom). Simonin rozvrh o 16:36 hovoril
„sedí v kaviarni po fotení". Ona napísala:

    16:36  „just chillin after gym pretty lazy day 😄"
    16:43  „im 27. just sat down in a cafe after some photos 😄"

Dve rôzne miesta v jednom rozhovore, osem minút od seba. Príčina nebola
v modeli: situácia sa do promptu pridávala až od ŠTVRTEJ správy od fanúšika,
aby model na prvý kontakt nevysypal, čo robí. Lenže keď mu to nepovieme,
nemlčí — vymyslí si. A potom si protirečí, len čo sa brána otvorí.
"""
from __future__ import annotations

from datetime import datetime

from behavior import Behavior
from persona import build_system_prompt

PERSONA = {"name": "Simona", "backstory": "23, LA", "msg_style": "krátko", "city": "Los Angeles"}
TERAZ = datetime(2026, 8, 25, 16, 36)
KAVIAREN = "sedí v kaviarni po fotení a nikam sa neponáhľa"


def _prompt(msg_count: int, **kw) -> str:
    zaklad = dict(
        persona=PERSONA,
        user={"tg_id": 1, "msg_count": msg_count, "funnel_stage": "warm"},
        allow_link=False,
        asked_if_ai=False,
        behavior=Behavior.from_row({}),
        now_local=TERAZ,
        situation=KAVIAREN,
    )
    zaklad.update(kw)
    return build_system_prompt(**zaklad)


class TestSituaciaJeVzdy:
    def test_prva_sprava_uz_vie_kde_je(self):
        """Toto je celý ten bug: pri prvej správe o kaviarni nevedela."""
        assert KAVIAREN in _prompt(1)

    def test_druha_sprava_tiez(self):
        """Práve pri druhej správe napísala „after gym"."""
        assert KAVIAREN in _prompt(2)

    def test_aj_neskor(self):
        assert KAVIAREN in _prompt(9)

    def test_vzdy_s_pravidlom_nevysypat(self):
        """Zamlčanie nebolo riešenie — riešením je pravidlo. Bez neho by model
        v prvej odpovedi vysypal, kde je a čo robí."""
        for count in (1, 2, 5, 20):
            out = _prompt(count)
            assert "NEHOVOR sama od seba" in out, count
            assert "nikdy si neprotireč" in out, count


class TestOznameniePresunuOstavaNeskor:
    """Jediná časť, ktorá modelku nabáda povedať to SAMA, patrí až niekomu,
    s kým si už chvíľu píše — cudziemu človeku by to bolo divné."""

    PRESUN = "práve sa usadila v kaviarni"

    def test_cudziemu_sa_presun_neoznamuje(self):
        assert "PRÁVE SA TO ZMENILO" not in _prompt(1, arrival=self.PRESUN)
        assert "PRÁVE SA TO ZMENILO" not in _prompt(3, arrival=self.PRESUN)

    def test_znamemu_ano(self):
        assert "PRÁVE SA TO ZMENILO" in _prompt(4, arrival=self.PRESUN)

    def test_kde_je_vie_aj_tak(self):
        """Aj keď sa presun neoznamuje, miesto v prompte byť MUSÍ."""
        assert KAVIAREN in _prompt(1, arrival=self.PRESUN)


class TestMediumSaPomenuje:
    """„[poslal médium bez textu]" nedáva šancu reagovať.

    Naostro: fanúšik poslal médium ako prvú správu a dostal „hey u 😄 whats up",
    akoby neprišlo nič. Človek na video alebo nálepku odpovie inak než na nič.
    """

    def test_pozna_druhy_media(self):
        import userbot

        class E:
            sticker = None
            video_note = None
            gif = None
            video = None
            document = None

        video = E()
        video.video = object()
        assert userbot._co_to_prislo(video) == "[poslal video]"

        subor = E()
        subor.document = object()
        assert userbot._co_to_prislo(subor) == "[poslal súbor]"

        nic = E()
        assert "médium" in userbot._co_to_prislo(nic)

    def test_fotka_ako_subor_ide_na_vision(self):
        """Fotka poslaná „bez kompresie" nie je `event.photo` — bez tejto
        vetvy by sa na ňu nikdy nepozrela."""
        import userbot

        class Dok:
            mime_type = "image/jpeg"

        class E:
            document = Dok()

        assert userbot._je_obrazok_subor(E()) is True

    def test_gif_nejde_na_vision(self):
        """GIF chodí ako `image/gif`, ale popis prvého snímku by klamal."""
        import userbot

        class Dok:
            mime_type = "image/gif"

        class E:
            document = Dok()

        assert userbot._je_obrazok_subor(E()) is False

    def test_bez_dokumentu_nespadne(self):
        import userbot

        class E:
            document = None

        assert userbot._je_obrazok_subor(E()) is False
