"""Rytmus predaja na Fanvue — kedy čo pošle a kedy sa ozve sama."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fvflow

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
PRED = lambda h: (NOW - timedelta(hours=h)).isoformat()  # noqa: E731


class TestKdeJe:
    def test_doma_sa_fotit_da(self):
        assert fvflow.can_take_photo("home") is True
        assert fvflow.can_take_photo("bedroom") is True

    def test_vo_fitku_nie(self):
        """Fotka z fitka by prezradila viac než akákoľvek veta."""
        assert fvflow.can_take_photo("gym") is False
        assert fvflow.can_take_photo("car") is False
        assert fvflow.can_take_photo("outside") is False

    def test_neznáme_miesto_sa_berie_ako_doma(self):
        assert fvflow.can_take_photo("") is True


class TestFotkaZadarmo:
    S = {"free_photo_max": 2}

    def test_na_zaciatku_aj_bez_pytania(self):
        assert fvflow.free_photo_ok({"free_photos": 0}, self.S, asked=False) is True
        assert fvflow.free_photo_ok({"free_photos": 1}, self.S, asked=False) is True

    def test_po_strope_uz_len_na_vyziadanie(self):
        assert fvflow.free_photo_ok({"free_photos": 2}, self.S, asked=False) is False
        assert fvflow.free_photo_ok({"free_photos": 2}, self.S, asked=True) is True

    def test_odkial_sa_neda_tak_nikdy(self):
        assert fvflow.free_photo_ok({"free_photos": 0}, self.S, True, "gym") is False


class TestSlub:
    def test_cerstvy_slub_plati(self):
        assert fvflow.owes_photo({"promised_at": PRED(2)}, NOW) is True

    def test_stary_slub_uz_nie(self):
        """Nikto sa po dvoch dňoch nevráti k „pošlem ti to doma“."""
        assert fvflow.owes_photo({"promised_at": PRED(40)}, NOW) is False

    def test_ziadny_slub(self):
        assert fvflow.owes_photo({}, NOW) is False


class TestKedyPlatene:
    S = {
        "sell_content": True, "offer_after_msgs": 6,
        "offer_cooldown_h": 12, "nudge_after_msgs": 25,
    }

    def test_vypnute_nikdy(self):
        assert fvflow.paid_moment({"msg_count": 99}, {"sell_content": False}, True, NOW) == ""

    def test_prilis_skoro_nie(self):
        assert fvflow.paid_moment({"msg_count": 3}, self.S, True, NOW) == ""

    def test_ked_si_pyta_je_to_ten_moment(self):
        assert fvflow.paid_moment({"msg_count": 10}, self.S, True, NOW) == "asked"

    def test_hned_po_ponuke_znova_nie(self):
        row = {"msg_count": 30, "last_offer_at": PRED(2)}
        assert fvflow.paid_moment(row, self.S, True, NOW) == ""

    def test_ked_dlho_nepyta_ozve_sa_sama(self):
        """Nie každý si vypýta, aj keď by kúpil."""
        assert fvflow.paid_moment({"msg_count": 30}, self.S, False, NOW) == "nudge"

    def test_este_nie_dost_sprav_na_vlastnu_ponuku(self):
        assert fvflow.paid_moment({"msg_count": 10}, self.S, False, NOW) == ""

    def test_vlastna_ponuka_sa_neopakuje_stale(self):
        row = {"msg_count": 30, "last_paid_ask_at": PRED(3)}
        assert fvflow.paid_moment(row, self.S, False, NOW) == ""

    def test_po_dvoch_dnoch_sa_smie_znova(self):
        row = {"msg_count": 30, "last_paid_ask_at": PRED(60)}
        assert fvflow.paid_moment(row, self.S, False, NOW) == "nudge"


class TestPokyn:
    S = {"free_photo_max": 2, "sell_content": True}

    def test_pri_ziadosti_z_fitka_slubi_na_doma(self):
        out = fvflow.guidance({}, self.S, "", False, asked_photo=True, where="gym")
        assert "sľúb" in out.lower()
        assert "gym" in out

    def test_ked_si_pyta_ostre_ide_naplno(self):
        out = fvflow.guidance({}, self.S, "asked", False, False)
        assert "neuhýbaj" in out
        assert "cenu" in out

    def test_vlastna_ponuka_len_raz(self):
        out = fvflow.guidance({}, self.S, "nudge", False, False)
        assert "Raz." in out

    def test_nesplneny_slub_sa_pripomenie(self):
        out = fvflow.guidance({}, self.S, "", False, False, owed=True)
        assert "SĽÚBILA" in out

    def test_po_strope_uz_nedava_zadarmo(self):
        row = {"free_photos": 5}
        out = fvflow.guidance(row, self.S, "", False, asked_photo=True)
        assert "zadarmo už" in out


class TestStyl:
    def test_zakazuje_knizne_pisanie(self):
        assert "román" in fvflow.STYLE
        assert "preklep" in fvflow.STYLE

    def test_hot_zakazuje_opisy_zvonku(self):
        assert "prvej osobe" in fvflow.HOT
