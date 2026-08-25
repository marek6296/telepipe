"""Vzhľad menu — a poistka, že sa pri jeho úprave nezmenila funkcia.

Menu bolo funkčné, ale vyzeralo ako zoznam prepínačov: každá obrazovka mala
vlastný tvar nadpisu, šípka späť sa písala tromi spôsobmi („←", „«", „← Menu")
a stav sa miešal do vety. Zmena bola ČISTO vizuálna, takže najdôležitejší test
v tomto súbore je ten posledný: callback hodnoty tlačidiel sa nesmeli hnúť ani
o bajt. Práve tam sa dá pri „len prekreslení" ticho odlomiť polovica bota.
"""
from __future__ import annotations

import re
from pathlib import Path

import control_bot

SRC = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")

# Callback dáta, ktoré musia existovať. Zoznam je napísaný RUČNE podľa toho,
# čo bot vedel pred prekreslením — nie vygenerovaný zo zdroja, inak by
# potvrdzoval sám seba.
KLIKY = {
    "m", "rm", "rmf", "pz", "wake", "nap", "pm", "bm", "tm", "st", "cv", "cd",
    "to", "pd", "tu", "nt", "nx", "mg", "mgr", "fc", "tc", "oc", "try", "tryr",
    "ap", "ac", "as", "ax", "af", "afd", "afi", "afree", "apaid", "acap",
    "acapn", "acapw", "av", "avc", "avok", "avno", "aback", "ar", "ab", "ai",
    "an", "ad", "t", "b", "vx", "ti", "ra", "sf", "wq",
}


def _callbacky() -> set:
    """Hlavy callbackov, ktoré zdroj naozaj posiela do tlačidiel.

    Hľadajú sa BAJTOVÉ literály a `…encode()`, nie celé volania `Button.inline`:
    tie sa lámu cez viac riadkov a vnorená zátvorka v f-reťazci rozbije každý
    rozumný regex. Toto o kúsok preberá (nájde aj bajty mimo tlačidla), ale na
    otázku „nezmizol niektorý callback?" je to presne to, čo treba.
    """
    out = set(re.findall(r'\bb"([a-z]+)(?::[^"]*)?"', SRC))
    out |= set(re.findall(r'f"([a-z]+):\{[^}]+\}"\.encode\(\)', SRC))
    return out


class TestFunkciaOstalaNedotknuta:
    def test_ziadne_tlacidlo_sa_nestratilo(self):
        """Toto je celý zmysel súboru: prekreslenie nesmie odpojiť akciu."""
        chyba = KLIKY - _callbacky()
        assert not chyba, f"tieto tlačidlá zmizli zo zdroja: {sorted(chyba)}"

    def test_smerovac_pozna_vsetko_co_menu_posiela(self):
        """Tlačidlo s callbackom, ktorý nikto nespracuje, je mŕtve tlačidlo."""
        posielane = _callbacky()
        obsluhovane = set(re.findall(r'head == "([a-z]+)"', SRC)) | control_bot.ControlBot._APPROVAL_HEADS
        mrtve = posielane - obsluhovane
        assert not mrtve, f"nikto neobsluhuje: {sorted(mrtve)}"

    def test_test_naozaj_nieco_meria(self):
        """Keby regex prestal sedieť, prvé dva testy by prešli s prázdnou množinou."""
        assert len(_callbacky()) >= 40


class TestJednotnyVzhlad:
    def test_spat_sa_pise_jedným_sposobom(self):
        """Tri rôzne šípky pôsobili, akoby každú obrazovku písal niekto iný."""
        assert '"← Back"' not in SRC and '"« Back"' not in SRC
        assert control_bot.SPAT.startswith("‹")

    def test_obrazovky_maju_rovnaku_hlavicku(self):
        out = control_bot._hlavicka("Times", "when she is awake")
        assert out.startswith("*Times*")
        assert control_bot.CIARA in out

    def test_hlavicka_znesie_aj_holy_nadpis(self):
        assert control_bot._hlavicka("Funnel") == f"*Funnel*\n{control_bot.CIARA}"

    def test_stav_je_zoznam_nie_veta(self):
        riadok = control_bot._polozka("🕘", "Active", "9:00 AM – 2:00 AM")
        assert riadok == "🕘 *Active* · 9:00 AM – 2:00 AM"


class TestCasyMajuAmPm:
    """Z 24-hodinového tvaru sa nedá poznať ráno od večera — naostro sa na tom
    raz pomýlilo nastavenie aktívneho okna a modelka mlčala celý deň."""

    def test_rano_a_vecer_sa_rozliszia(self):
        assert control_bot._hhmm12(9 * 60) == "9:00 AM"
        assert control_bot._hhmm12(21 * 60) == "9:00 PM"

    def test_polnoc_a_poludnie(self):
        assert control_bot._hhmm12(0) == "12:00 AM"
        assert control_bot._hhmm12(12 * 60) == "12:00 PM"

    def test_okno_cez_polnoc(self):
        assert control_bot._okno12(606, 150) == "10:06 AM – 2:30 AM"

    def test_nonstop_sa_nepise_ako_cas(self):
        assert control_bot._okno12(0, 0) == "24/7"


class TestZiadnaSlovencinaVAnglickomBote:
    """Bot je celý anglicky; slovenské slovo v ňom vyzerá ako nedorobok."""

    ZAKAZANE = ("bez obmedzenia", '"*Chovanie*', "⏰ Od ", "🌙 Do ", "naraz\"")

    def test_texty_pre_klienta_su_anglicky(self):
        for slovo in self.ZAKAZANE:
            assert slovo not in SRC, slovo
