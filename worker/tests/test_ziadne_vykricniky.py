"""Výkričníky — jeden vie správu prezradiť rýchlejšie než celá zlá veta."""
from __future__ import annotations

import humanize


class TestOdstranenie:
    def test_na_konci_ide_bez_nahrady(self):
        """Bodku by tam človek do mobilu ani nedal."""
        assert humanize.no_shouting("ty si poklad!") == "ty si poklad"

    def test_seria_tiez(self):
        assert humanize.no_shouting("ty si poklad!!!") == "ty si poklad"

    def test_v_strede_ostane_bodka(self):
        assert humanize.no_shouting("hey! ako sa mas") == "hey. ako sa mas"

    def test_viac_viet(self):
        out = humanize.no_shouting("wow! to je super! dik")
        assert "!" not in out
        assert out == "wow. to je super. dik"

    def test_za_emoji_sa_bodka_nedopisuje(self):
        out = humanize.no_shouting("made my night 🥰!")
        assert out == "made my night 🥰"

    def test_kombinacia_s_otaznikom(self):
        assert humanize.no_shouting("naozaj?!") == "naozaj?"
        assert humanize.no_shouting("naozaj!?") == "naozaj?"

    def test_viac_otaznikov_je_ten_isty_krik(self):
        assert humanize.no_shouting("naozaj???") == "naozaj?"

    def test_bez_vykricnikov_sa_nic_nezmeni(self):
        text = "hey ako sa mas dnes"
        assert humanize.no_shouting(text) == text

    def test_prazdny_vstup(self):
        assert humanize.no_shouting("") == ""
        assert humanize.no_shouting(None) == ""

    def test_emoji_ostava(self):
        assert "🥰" in humanize.no_shouting("dik 🥰!")

    def test_nezdvojuje_bodky(self):
        out = humanize.no_shouting("no.! dobre")
        assert ".." not in out

    def test_tri_bodky_ostanu(self):
        """Trojbodka je ľudská, tú netreba brať."""
        assert "..." in humanize.no_shouting("no neviem... asi hej")


class TestPravidloVPrompte:
    def test_fanvue_ma_zakaz_v_pravidlach(self):
        import fvflow

        assert "ŽIADNE VÝKRIČNÍKY" in fvflow.STYLE

    def test_na_zaciatku_pise_malo(self):
        import fvflow

        assert "začiatku rozhovoru píš málo" in fvflow.STYLE
