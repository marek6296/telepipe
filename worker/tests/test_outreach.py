"""Pozdrav na druhý deň — jediná chvíľa, keď píše prvá. Preto prísne pravidlá."""
from datetime import datetime, timedelta, timezone

import outreach

# now_local musí byť tz-aware v pásme modelky. V testoch berieme UTC ako lokál.
TERAZ = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)


def clovek(prvy_kontakt_dni=1, ticho_hodin=12, **kw):
    """Predvolene: prvý kontakt VČERA, ešte neoslovený → pozdrav sa patrí."""
    prvy = TERAZ - timedelta(days=prvy_kontakt_dni)
    posledny = TERAZ - timedelta(hours=ticho_hodin)
    row = {
        "tg_id": 555, "msg_count": 20, "paid": False, "funnel_stage": "warm",
        "human_takeover": False, "ai_enabled": True,
        "last_outreach_at": None,
        "created_at": prvy.isoformat(),
        "last_incoming_at": posledny.isoformat(),
        "last_reply_at": posledny.isoformat(),
    }
    row.update(kw)
    return row


class TestKohoOslovit:
    def test_druhy_den_po_prvom_kontakte_ano(self):
        assert outreach.deserves(clovek(prvy_kontakt_dni=1), TERAZ)

    def test_v_ten_isty_den_nie(self):
        """Prvý kontakt dnes → ešte nie je druhý deň."""
        dnes = clovek(created_at=(TERAZ - timedelta(hours=2)).isoformat())
        assert not outreach.deserves(dnes, TERAZ)

    def test_uz_raz_oslovila_nikdy_viac(self):
        """Vodoznak: keď pozdrav odišiel, druhýkrát nikdy."""
        po = clovek(last_outreach_at=(TERAZ - timedelta(days=5)).isoformat())
        assert not outreach.deserves(po, TERAZ)

    def test_kratka_konverzacia_nie(self):
        assert not outreach.deserves(clovek(msg_count=2), TERAZ)

    def test_kto_zaplatil_sa_nerusi(self):
        assert not outreach.deserves(clovek(paid=True), TERAZ)
        assert not outreach.deserves(clovek(funnel_stage="converted"), TERAZ)

    def test_rucne_prevzaty_nie(self):
        assert not outreach.deserves(clovek(human_takeover=True), TERAZ)
        assert not outreach.deserves(clovek(ai_enabled=False), TERAZ)

    def test_kto_zmizol_na_tyzden_uz_nie(self):
        """Prvý kontakt pred 9 dňami, odvtedy ticho → pozdrav do prázdna."""
        davno = clovek(prvy_kontakt_dni=9, ticho_hodin=24 * 9)
        assert not outreach.deserves(davno, TERAZ)

    def test_pasmo_rozhoduje_druhy_den(self):
        """Prvý kontakt bol v jej lokálnom pásme ešte včera → pozdrav áno."""
        # now_local je v pásme UTC-8; prvý kontakt 20 h dozadu je v tomto
        # pásme na predošlom dni.
        pasmo = timezone(timedelta(hours=-8))
        teraz_local = datetime(2026, 8, 15, 6, 0, tzinfo=pasmo)
        u = clovek(created_at=(teraz_local - timedelta(hours=20)).isoformat(),
                   last_incoming_at=(teraz_local - timedelta(hours=10)).isoformat(),
                   last_reply_at=(teraz_local - timedelta(hours=10)).isoformat())
        assert outreach.deserves(u, teraz_local)

    def test_rozbity_datum_neposiela(self):
        assert not outreach.deserves(clovek(created_at="nezmysel"), TERAZ)


class TestDue:
    def test_strop_plati(self):
        ludia = [clovek(tg_id=i) for i in range(40)]
        assert len(outreach.due(ludia, TERAZ, limit=25)) == 25

    def test_nevhodnych_preskoci(self):
        ludia = [
            clovek(tg_id=1),
            clovek(tg_id=2, paid=True),
            clovek(tg_id=3),
        ]
        assert [u["tg_id"] for u in outreach.due(ludia, TERAZ)] == [1, 3]


class TestRozlozenie:
    def test_stabilne_pre_den(self):
        a = outreach.delay_for(555, "2026-08-15")
        b = outreach.delay_for(555, "2026-08-15")
        assert a == b

    def test_iny_den_ine_poradie(self):
        a = outreach.delay_for(555, "2026-08-15")
        b = outreach.delay_for(555, "2026-08-16")
        assert a != b

    def test_v_ramci_okna(self):
        for tg in range(50):
            assert 0 <= outreach.delay_for(tg, "2026-08-15") <= outreach.SPREAD_HOURS * 3600


class TestGuidance:
    def test_jednoduchy_pozdrav(self):
        pokyn = outreach.guidance(clovek())
        assert "SIMPLE NEXT-DAY HELLO" in pokyn
        assert "'hey'" in pokyn

    def test_zakazuje_temy_a_otazky(self):
        pokyn = outreach.guidance(clovek())
        assert "do NOT ask a real" in pokyn
        assert "bring up anything you talked about" in pokyn

    def test_obsahuje_meno(self):
        assert "Peter" in outreach.guidance(clovek(partner_name="Peter"))
