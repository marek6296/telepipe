"""Hlasovky na Fanvue — kedy, aké a čo si z nich pamätá."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fvflow
import fvvoice

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


class TestKedySaOzve:
    ZAP = {"voices_enabled": True, "sell_content": True}

    def test_vypnute_znamena_nikdy(self):
        s = {"voices_enabled": False, "sell_content": True}
        assert fvvoice.should_speak({}, s, asked=True, hot=True, now=NOW) == ""

    def test_ked_je_horuco_ide_platena(self):
        assert fvvoice.should_speak({}, self.ZAP, False, True, NOW) == "paid"

    def test_ked_si_pyta_ide_zadarmo(self):
        assert fvvoice.should_speak({}, self.ZAP, True, False, NOW) == "free"

    def test_bez_dovodu_nic(self):
        assert fvvoice.should_speak({}, self.ZAP, False, False, NOW) == ""

    def test_hned_po_predchadzajucej_nic(self):
        """Keď chodia stále, prestanú byť udalosťou."""
        row = {"last_voice_at": (NOW - timedelta(hours=1)).isoformat()}
        assert fvvoice.should_speak(row, self.ZAP, True, True, NOW) == ""

    def test_po_odstupe_znova(self):
        row = {"last_voice_at": (NOW - timedelta(hours=9)).isoformat()}
        assert fvvoice.should_speak(row, self.ZAP, True, False, NOW) == "free"


class TestPytanie:
    def test_pozna_ziadost_o_hlas(self):
        assert fvvoice.asked_for_voice("can i hear your voice") is True
        assert fvvoice.asked_for_voice("send me a voice note") is True

    def test_bezna_sprava_nie(self):
        assert fvvoice.asked_for_voice("how was your day") is False


class TestPokyn:
    def test_platena_ide_naplno_aj_so_znackami(self):
        out = fvvoice.script_hint("paid", 800)
        assert "$8.00" in out
        assert "[moans softly]" in out
        assert "pomaly" in out

    def test_zadarmo_je_ochutnavka(self):
        out = fvvoice.script_hint("free")
        assert "ochutnávka" in out
        assert "[whispers]" in out


class TestPrepis:
    def test_znacky_sa_do_pamate_nedostanu(self):
        """Keby ostali v prepise, model by ich o týždeň písal do správ."""
        out = fvvoice.spoken_only("[whispers] chcem ta [moans softly] tak moc")
        assert "[" not in out
        assert "chcem ta" in out
        assert "tak moc" in out

    def test_bez_znaciek_sa_nic_nezmeni(self):
        assert fvvoice.spoken_only("ahoj ako sa mas") == "ahoj ako sa mas"


class TestCitanieCloveka:
    def test_kto_uz_kupil(self):
        assert fvflow.reads_as({"bought_count": 2}) == "kupuje"

    def test_kto_chce_ostre(self):
        assert fvflow.reads_as({"wants": "sex chat and nudes"}) == "chce_sex"

    def test_kto_sa_chce_len_bavit(self):
        assert fvflow.reads_as({"wants": "someone to talk to"}) == "chce_sa_bavit"

    def test_na_povidajuceho_sa_netlaci(self):
        assert "NETLAČ" in fvflow.CITANIE["chce_sa_bavit"]


class TestVyhovorka:
    def test_po_nakupe_dlho_nie(self):
        """Použiť ju na toho, kto práve zaplatil, z neho spraví bankomat."""
        row = {"last_bought_at": (NOW - timedelta(days=2)).isoformat()}
        assert fvflow.may_use_story(row, NOW) is False

    def test_po_case_zase_ano(self):
        row = {"last_bought_at": (NOW - timedelta(days=9)).isoformat()}
        assert fvflow.may_use_story(row, NOW) is True

    def test_bez_historie_ano(self):
        assert fvflow.may_use_story({}, NOW) is True


class TestLudskePisanie:
    def test_zakazuje_odborne_slova(self):
        assert "IT slová" in fvflow.STYLE or "IT slov" in fvflow.STYLE

    def test_smie_sa_pytat_co_to_je(self):
        assert "SPÝTAJ" in fvflow.STYLE

    def test_zakazuje_opakovanie_frazi(self):
        assert "NEOPAKUJ SA" in fvflow.STYLE
