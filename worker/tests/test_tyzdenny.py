"""Týždenný súhrn s číslami."""
from datetime import datetime, timedelta, timezone

import tyzdenny


def _pondelok(hodina=3, minuta=0):
    """2026-08-17 je pondelok."""
    return datetime(2026, 8, 17, hodina, minuta, tzinfo=timezone.utc)


# Okno 10:00–02:30, ako ho má bežiaca modelka.
START, KONIEC = 600, 150


class TestKedy:
    def test_v_pondelok_po_konci_okna(self):
        assert tyzdenny.treba_poslat(_pondelok(3), START, KONIEC, None)

    def test_v_utorok_nie(self):
        utorok = _pondelok(3) + timedelta(days=1)
        assert not tyzdenny.treba_poslat(utorok, START, KONIEC, None)

    def test_uprostred_jej_dna_nie(self):
        assert not tyzdenny.treba_poslat(_pondelok(14), START, KONIEC, None)

    def test_druhykrat_v_ten_isty_pondelok_nie(self):
        pred_chvilou = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert not tyzdenny.treba_poslat(_pondelok(3), START, KONIEC, pred_chvilou)

    def test_o_tyzden_znova_ano(self):
        davno = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        assert tyzdenny.treba_poslat(_pondelok(3), START, KONIEC, davno)

    def test_rozbity_vodoznak_report_nezablokuje(self):
        assert tyzdenny.treba_poslat(_pondelok(3), START, KONIEC, "minuly tyzden")

    def test_modelka_bez_okna_dostane_o_polnoci(self):
        assert tyzdenny.treba_poslat(_pondelok(0, 10), 0, 0, None)
        assert not tyzdenny.treba_poslat(_pondelok(13), 0, 0, None)


class TestText:
    CISLA = {"novi": 12, "odkazy": 7, "zavrete": 5}

    def test_obsahuje_cisla(self):
        text = tyzdenny.zostav(self.CISLA, 4200)
        assert "*12*" in text and "*7*" in text and "*5*" in text

    def test_podiel_odkazov(self):
        assert "58%" in tyzdenny.zostav(self.CISLA, 4200)

    def test_zostatok_coinov(self):
        assert "4 200" in tyzdenny.zostav(self.CISLA, 4200.4)

    def test_prazdny_tyzden_sa_hlasi_tiez(self):
        """Ticho je informácia: klient chce vedieť, že sa nedialo nič."""
        text = tyzdenny.zostav({"novi": 0, "odkazy": 0, "zavrete": 0}, 100)
        assert "Nobody new wrote" in text
        assert "still connected" in text, "a má vedieť, čo si má overiť"

    def test_porovnanie_s_minulym(self):
        hore = tyzdenny.zostav(self.CISLA, 100, minuly={"novi": 8})
        assert "4 up" in hore
        dole = tyzdenny.zostav(self.CISLA, 100, minuly={"novi": 20})
        assert "8 down" in dole

    def test_rovnaky_tyzden_sa_nekomentuje(self):
        assert "up on last week" not in tyzdenny.zostav(self.CISLA, 100, minuly={"novi": 12})

    def test_ziadne_html_znacky(self):
        """Control bot ide cez Telethon, teda markdown. `<b>` by bolo vidieť."""
        assert "<" not in tyzdenny.zostav(self.CISLA, 100)

    def test_nedelenie_nulou(self):
        tyzdenny.zostav({"novi": 0, "odkazy": 0, "zavrete": 0}, 0)
