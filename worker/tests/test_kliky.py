"""Meranie klikov na odkaz — čím sa rozlíši „nikto neklikol" od „klikli a nekúpili"."""
import asyncio
from datetime import datetime, timedelta, timezone

import db as db_mod
import odkazy
import tyzdenny


class TestKratkyOdkaz:
    def test_token_je_dost_dlhy_a_nahodny(self):
        tokeny = {odkazy.novy_token() for _ in range(200)}
        assert len(tokeny) == 200, "tokeny sa nesmú opakovať"
        assert all(len(t) == odkazy.DLZKA for t in tokeny)

    def test_bez_zamenitelnych_znakov(self):
        """Odkaz môže niekto prepisovať z obrazovky."""
        for zly in "0O1lI":
            assert zly not in odkazy.ABECEDA

    def test_zlozenie_adresy(self):
        assert odkazy.zloz("https://telepipe.me", "abc") == "https://telepipe.me/r/abc"
        assert odkazy.zloz("https://telepipe.me/", "abc") == "https://telepipe.me/r/abc"

    def test_bez_domeny_ziadny_odkaz(self):
        """Prázdny výsledok znamená „pošli pôvodný Fanvue odkaz"."""
        assert odkazy.zloz("", "abc") == ""
        assert odkazy.zloz("https://telepipe.me", "") == ""


class TestPadyNezhodiaOdkaz:
    """Meranie je bonus. Keby výpadok databázy znamenal, že modelka nepošle nič,
    vymenili by sme informáciu za tržbu."""

    def test_pad_databazy_vrati_prazdno(self):
        class RozbitaDb:
            async def ensure_short_link(self, tg_id):
                raise RuntimeError("databáza je preč")

        out = asyncio.run(odkazy.pre_konverzaciu(RozbitaDb(), 1, "https://telepipe.me"))
        assert out == ""

    def test_bez_domeny_sa_ani_nepyta(self):
        class DbKtoraNesmieByt:
            async def ensure_short_link(self, tg_id):
                raise AssertionError("toto sa nemalo volať")

        assert asyncio.run(odkazy.pre_konverzaciu(DbKtoraNesmieByt(), 1, "")) == ""


class FakeTransport(db_mod.TenantDb):
    def __init__(self, rows=None):
        self.rows = rows or []
        self.posty = []
        self.model_id = "m-1"

    async def _get(self, path, params):
        return list(self.rows)

    async def _post(self, path, body, upsert=False):
        self.posty.append(body)
        self.rows = [body]
        return [body]


class TestTokenJeStaly:
    def test_druhy_odkaz_ma_ten_isty_token(self):
        """Inak by sa kliky rozsypali do dvoch riadkov."""
        t = FakeTransport([{"token": "abc123"}])
        assert asyncio.run(t.ensure_short_link(42)) == "abc123"
        assert t.posty == [], "existujúci token sa nemá prepisovať"

    def test_prvy_raz_sa_vyrobi(self):
        t = FakeTransport([])
        token = asyncio.run(t.ensure_short_link(42))
        assert token and t.posty[0]["tg_id"] == 42
        assert t.posty[0]["model_id"] == "m-1"


class TestCerstveKliky:
    def _row(self, klik_pred_h, hlasene_pred_h=None):
        teraz = datetime.now(timezone.utc)
        return {
            "tg_id": 5,
            "link_clicked_at": (teraz - timedelta(hours=klik_pred_h)).isoformat(),
            "click_notified_at": None
            if hlasene_pred_h is None
            else (teraz - timedelta(hours=hlasene_pred_h)).isoformat(),
        }

    def test_neohlaseny_klik_sa_vrati(self):
        t = FakeTransport([self._row(1)])
        assert len(asyncio.run(t.fresh_clicks())) == 1

    def test_uz_ohlaseny_sa_nevrati(self):
        t = FakeTransport([self._row(klik_pred_h=5, hlasene_pred_h=4)])
        assert asyncio.run(t.fresh_clicks()) == []

    def test_novy_klik_po_ohlaseni_sa_vrati(self):
        """Klik o týždeň neskôr je nová udalosť, nie duplicita."""
        t = FakeTransport([self._row(klik_pred_h=1, hlasene_pred_h=200)])
        assert len(asyncio.run(t.fresh_clicks())) == 1


class TestTyzdenneCisla:
    def test_kliky_su_v_sprave(self):
        text = tyzdenny.zostav({"novi": 10, "odkazy": 8, "kliky": 3, "zavrete": 2}, 100)
        assert "Opened your page: *3*" in text
        assert "38%" in text

    def test_nula_klikov_ukaze_kde_hladat(self):
        text = tyzdenny.zostav({"novi": 10, "odkazy": 6, "kliky": 0, "zavrete": 1}, 100)
        assert "nobody opened it" in text
        assert "points at the chat" in text

    def test_jeden_odkaz_bez_kliku_sa_nekomentuje(self):
        """Pri jednom-dvoch odkazoch to nič neznamená."""
        text = tyzdenny.zostav({"novi": 3, "odkazy": 1, "kliky": 0, "zavrete": 0}, 100)
        assert "points at the chat" not in text

    def test_stara_sprava_bez_klikov_nespadne(self):
        tyzdenny.zostav({"novi": 1, "odkazy": 1, "zavrete": 0}, 100)
