"""Poďakovanie za nákup — kedy áno, kedy nie a čo v ňom má byť."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fvflow

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
ZAP = {"thank_purchases": True}


class TestKedySaPodakuje:
    def test_prvy_nakup_vzdy(self):
        assert fvflow.may_thank({}, ZAP, NOW) is True

    def test_vypnute_znamena_nikdy(self):
        assert fvflow.may_thank({}, {"thank_purchases": False}, NOW) is False

    def test_druhy_nakup_dostane_vdaku_tiez(self):
        """Za každý nákup patrí vďaka — druhá má len znieť inak."""
        row = {"last_thanks_at": (NOW - timedelta(minutes=3)).isoformat()}
        assert fvflow.may_thank(row, ZAP, NOW) is True

    def test_ta_ista_platba_dvakrat_nie(self):
        """O jednej platbe sa dozvieme aj z webhooku, aj z purchasedAt."""
        row = {"last_thanks_at": (NOW - timedelta(seconds=20)).isoformat()}
        assert fvflow.may_thank(row, ZAP, NOW) is False

    def test_po_odstupe_znova_ano(self):
        row = {"last_thanks_at": (NOW - timedelta(hours=5)).isoformat()}
        assert fvflow.may_thank(row, ZAP, NOW) is True

    def test_nezmyselna_znacka_neblokuje(self):
        assert fvflow.may_thank({"last_thanks_at": "nezmysel"}, ZAP, NOW) is True


class TestAkoPodakuje:
    def test_je_to_vdaka_a_nic_ine(self):
        out = fvflow.thanks_hint(800, 1)
        assert "POĎAKOVANIE" in out
        assert "nepredávaj" in out

    def test_sumu_nespomina(self):
        """Suma v správe znie ako účtenka."""
        out = fvflow.thanks_hint(800, 1)
        assert "nespomínaj" in out

    def test_zakazuje_firemnu_frazu(self):
        assert "ďakujem za podporu" in fvflow.thanks_hint(500, 1)

    def test_druhy_nakup_je_mile_prekvapenie(self):
        """Nie druhé zdvorilé poďakovanie, ale „joj a ďalšie, ty si poklad“."""
        out = fvflow.thanks_hint(500, 2)
        assert "poklad" in out
        assert "prekvapenie" in out

    def test_pri_dalsich_nakupoch_to_pripomenie(self):
        out = fvflow.thanks_hint(500, 4)
        assert "4. nákup" in out
        assert "samozrejmosť" in out

    def test_pri_prvom_nakupe_o_opakovani_nehovori(self):
        out = fvflow.thanks_hint(500, 1)
        assert "nákup" not in out
        assert "poklad" not in out

    def test_zakazuje_rovnaku_vetu_druhy_raz(self):
        assert "INAK" in fvflow.thanks_hint(500, 2)

    def test_bez_sumy_nepadne(self):
        out = fvflow.thanks_hint(0, 1)
        assert "POĎAKOVANIE" in out
        assert "$" not in out
