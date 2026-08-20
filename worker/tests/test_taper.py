"""Útlm konverzácie — okno v dňoch, ktoré si nastaví klient.

ZMENA ZMYSLU OPROTI PÔVODNÉMU NÁVRHU
------------------------------------
Predtým sa útlm počítal od chvíle, keď odišiel odkaz, a vyžadoval aj
pripomenutia. Malo to dve chyby: kto odkaz nikdy nedostal, neutlmil sa NIKDY,
a klient nevedel dopredu povedať, ako dlho sa má s človekom baviť.

Teraz je to okno v dňoch od PRVÉHO kontaktu (`behavior.chat_days`).
"""
from datetime import datetime, timedelta, timezone

import taper

TERAZ = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def clovek(hodin_od_zaciatku=0, **kw):
    row = {
        "created_at": (TERAZ - timedelta(hours=hodin_od_zaciatku)).isoformat(),
        "paid": False,
        "funnel_stage": "warm",
    }
    row.update(kw)
    return row


class TestKrivka:
    def test_zaciatok_je_normalna_konverzacia(self):
        assert taper.level(clovek(0), 3, TERAZ) == 0

    def test_utlm_rastie_s_casom(self):
        urovne = [taper.level(clovek(h), 3, TERAZ) for h in (0, 20, 40, 60)]
        assert urovne == sorted(urovne), urovne
        assert urovne[0] == 0 and urovne[-1] >= 2

    def test_po_okne_je_ticho(self):
        assert taper.level(clovek(73), 3, TERAZ) == taper.TICHO
        assert taper.ticho(clovek(73), 3, TERAZ)

    def test_v_okne_ticho_nie_je(self):
        assert not taper.ticho(clovek(40), 3, TERAZ)


class TestJednodnoveOkno:
    """Najtesnejší prípad: všetko sa musí zmestiť do jedného dňa."""

    def test_prvy_den_este_hovori(self):
        assert taper.level(clovek(2), 1, TERAZ) < taper.TICHO

    def test_po_dni_uz_nie(self):
        assert taper.ticho(clovek(25), 1, TERAZ)

    def test_odkaz_sa_pusti_este_v_prvy_den(self):
        """Bez toho by človek odišiel bez toho, aby stránku vôbec videl."""
        assert taper.closing(clovek(19), 1, TERAZ)

    def test_na_zaciatku_sa_este_neponahla(self):
        assert not taper.closing(clovek(1), 1, TERAZ)


class TestPlatiaciSaNeutlmi:
    def test_paid_nikdy(self):
        assert taper.level(clovek(300, paid=True), 1, TERAZ) == 0
        assert not taper.ticho(clovek(300, paid=True), 1, TERAZ)

    def test_converted_nikdy(self):
        u = clovek(300, funnel_stage="converted")
        assert taper.level(u, 1, TERAZ) == 0


class TestOdolnost:
    def test_bez_datumu_sa_neutlmi(self):
        """Radšej sa baviť ďalej než stíchnuť kvôli chýbajúcemu poľu."""
        assert taper.level({"paid": False}, 3, TERAZ) == 0

    def test_rozbity_datum_sa_neutlmi(self):
        assert taper.level({"created_at": "toto nie je datum"}, 3, TERAZ) == 0

    def test_nula_dni_sa_berie_ako_jeden(self):
        """Nula by znamenala okno dĺžky nula a ticho od prvej správy."""
        assert taper.level(clovek(1), 0, TERAZ) < taper.TICHO

    def test_dlhe_okno_sa_utlmuje_pomaly(self):
        assert taper.level(clovek(48), 14, TERAZ) == 0
