"""Odkaz, ktorý si nesie, komu bol poslaný."""
from __future__ import annotations

import checkout


class TestReferencia:
    def test_z_id_spravi_hodnotu(self):
        assert checkout.reference(566608217) == "tg-566608217"

    def test_retazec_prejde_tiez(self):
        assert checkout.reference("566608217") == "tg-566608217"

    def test_bez_id_nic(self):
        assert checkout.reference(None) == ""
        assert checkout.reference("") == ""
        assert checkout.reference("nezmysel") == ""

    def test_tam_a_spat(self):
        assert checkout.telegram_id(checkout.reference(42)) == 42

    def test_cudziu_hodnotu_neprecita(self):
        """Ručne vyplnené client_reference_id nesmieme čítať ako Telegram id."""
        assert checkout.telegram_id("crm-123") is None
        assert checkout.telegram_id("") is None
        assert checkout.telegram_id(None) is None
        assert checkout.telegram_id("tg-nieco") is None


class TestOdkaz:
    def test_prida_sa_na_ciste_url(self):
        out = checkout.attributed("https://www.fanvue.com/checkout/abc", 7)
        assert out == "https://www.fanvue.com/checkout/abc?client_reference_id=tg-7"

    def test_existujuci_parameter_sa_nezmaze(self):
        out = checkout.attributed("https://www.fanvue.com/checkout/abc?utm=tg", 7)
        assert out == "https://www.fanvue.com/checkout/abc?utm=tg&client_reference_id=tg-7"

    def test_kotva_ostane_na_konci(self):
        """Keby parameter išiel za kotvu, stal by sa jej súčasťou."""
        out = checkout.attributed("https://www.fanvue.com/simona#o-mne", 7)
        assert out == "https://www.fanvue.com/simona?client_reference_id=tg-7#o-mne"

    def test_druhy_raz_sa_nepridava(self):
        raz = checkout.attributed("https://www.fanvue.com/checkout/abc", 7)
        assert checkout.attributed(raz, 7) == raz

    def test_cudzi_odkaz_ostava_nedotknuty(self):
        """Čo si Marek nastaví mimo Fanvue, do toho nesiahame."""
        assert checkout.attributed("https://onlyfans.com/x", 7) == "https://onlyfans.com/x"

    def test_bez_id_ostava_povodny(self):
        link = "https://www.fanvue.com/checkout/abc"
        assert checkout.attributed(link, None) == link

    def test_prazdny_odkaz(self):
        assert checkout.attributed("", 7) == ""
        assert checkout.attributed(None, 7) == ""


class TestVPrompte:
    def test_modelka_dostane_odkaz_s_id(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "cta_link": "https://www.fanvue.com/checkout/abc"},
            {"tg_id": 566608217, "funnel_stage": "warm", "msg_count": 8},
            True,
            False,
        )
        assert "client_reference_id=tg-566608217" in out

    def test_bez_povolenia_odkaz_nikde(self):
        from persona import build_system_prompt

        out = build_system_prompt(
            {"name": "Simona", "cta_link": "https://www.fanvue.com/checkout/abc"},
            {"tg_id": 566608217, "funnel_stage": "warm", "msg_count": 2},
            False,
            False,
        )
        assert "client_reference_id" not in out
