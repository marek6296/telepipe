"""Ranné oslovenie — jediná chvíľa, keď píše prvá. Preto prísne pravidlá."""
from datetime import datetime, timedelta, timezone

import outreach

TERAZ = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)


def clovek(hodin_ticha=12, **kw):
    row = {
        "tg_id": 555, "msg_count": 20, "paid": False, "funnel_stage": "warm",
        "human_takeover": False, "ai_enabled": True, "outreach_silent": 0,
        "last_outreach_at": None,
        "last_incoming_at": (TERAZ - timedelta(hours=hodin_ticha)).isoformat(),
        "last_reply_at": (TERAZ - timedelta(hours=hodin_ticha)).isoformat(),
    }
    row.update(kw)
    return row


class TestKohoOslovit:
    def test_beznemu_po_nocnom_tichu_ano(self):
        assert outreach.deserves(clovek(), TERAZ)

    def test_kto_pisal_pred_hodinou_nie(self):
        """Ozvať sa niekomu, s kým si píše, je nezmysel."""
        assert not outreach.deserves(clovek(hodin_ticha=1), TERAZ)

    def test_po_tyzdni_ticha_uz_nie(self):
        assert not outreach.deserves(clovek(hodin_ticha=24 * 9), TERAZ)

    def test_kratka_konverzacia_nie(self):
        assert not outreach.deserves(clovek(msg_count=2), TERAZ)

    def test_kto_zaplatil_sa_nerusi(self):
        assert not outreach.deserves(clovek(paid=True), TERAZ)
        assert not outreach.deserves(clovek(funnel_stage="converted"), TERAZ)

    def test_rucne_prevzaty_nie(self):
        assert not outreach.deserves(clovek(human_takeover=True), TERAZ)
        assert not outreach.deserves(clovek(ai_enabled=False), TERAZ)

    def test_po_dvoch_tichych_ranach_koniec(self):
        assert outreach.deserves(clovek(outreach_silent=1), TERAZ)
        assert not outreach.deserves(clovek(outreach_silent=2), TERAZ)

    def test_dvakrat_za_den_nie(self):
        dnes = clovek(last_outreach_at=(TERAZ - timedelta(hours=3)).isoformat())
        assert not outreach.deserves(dnes, TERAZ)

    def test_vcerajsie_oslovenie_brani(self):
        """Nepíše prvá každý deň — aj keby medzitým odpovedal."""
        vcera = clovek(last_outreach_at=(TERAZ - timedelta(hours=23)).isoformat())
        assert not outreach.deserves(vcera, TERAZ)

    def test_po_styroch_dnoch_sa_moze_ozvat(self):
        davno = clovek(last_outreach_at=(TERAZ - timedelta(days=5)).isoformat())
        assert outreach.deserves(davno, TERAZ)

    def test_rozbity_datum_neposiela(self):
        assert not outreach.deserves(clovek(last_incoming_at="nezmysel", last_reply_at=None), TERAZ)


class TestVyber:
    def test_strop_plati(self):
        ludia = [clovek(tg_id=i) for i in range(40)]
        assert len(outreach.due(ludia, TERAZ, limit=25)) == 25

    def test_nevhodnych_preskoci(self):
        ludia = [clovek(tg_id=1), clovek(tg_id=2, paid=True), clovek(tg_id=3)]
        assert [u["tg_id"] for u in outreach.due(ludia, TERAZ)] == [1, 3]


class TestRozprestretie:
    def test_v_ramci_okna(self):
        for tg_id in range(50):
            assert 0 <= outreach.delay_for(tg_id, "2026-08-15") <= outreach.SPREAD_HOURS * 3600

    def test_stabilne_pre_den(self):
        assert outreach.delay_for(555, "2026-08-15") == outreach.delay_for(555, "2026-08-15")

    def test_iny_den_ine_poradie(self):
        assert outreach.delay_for(555, "2026-08-15") != outreach.delay_for(555, "2026-08-16")

    def test_ludia_nejdu_naraz(self):
        casy = {round(outreach.delay_for(i, "2026-08-15")) for i in range(30)}
        assert len(casy) > 25, "správy sa musia rozložiť, nie odísť v jednej minúte"


class TestPokyn:
    def test_obsahuje_meno(self):
        assert "Peter" in outreach.guidance(clovek(partner_name="Peter"))

    def test_pri_tichu_ziadna_vycitka(self):
        pokyn = outreach.guidance(clovek(outreach_silent=1))
        assert "žiadna výčitka" in pokyn

    def test_zakazuje_genericke_good_morning(self):
        assert "good morning" in outreach.guidance(clovek())
