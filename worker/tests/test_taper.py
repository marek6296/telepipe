"""Útlm konverzácie — po dňoch, nie po pol hodine."""
from datetime import datetime, timedelta, timezone

import taper

TERAZ = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def clovek(dni_od_odkazu=None, pripomenuti=0, **kw):
    row = {"link_push_count": pripomenuti, "paid": False, "funnel_stage": "link_sent"}
    if dni_od_odkazu is not None:
        row["link_sent_at"] = (TERAZ - timedelta(days=dni_od_odkazu)).isoformat()
    row.update(kw)
    return row


class TestUroven:
    def test_bez_odkazu_ziadny_utlm(self):
        assert taper.level(clovek(), TERAZ) == 0

    def test_hned_po_odkaze_ziadny_utlm(self):
        """Pol hodiny po odkaze sa nesmie nič meniť."""
        assert taper.level(clovek(0, 1), TERAZ) == 0

    def test_po_dni_a_pripomenuti_mierny_utlm(self):
        assert taper.level(clovek(1, 1), TERAZ) == 1

    def test_po_dvoch_dnoch_kratsie(self):
        assert taper.level(clovek(2, 2), TERAZ) == 2

    def test_po_troch_dnoch_povie_mu_to(self):
        assert taper.level(clovek(3, 3), TERAZ) == 3

    def test_po_piatich_dnoch_uz_len_minimum(self):
        assert taper.level(clovek(6, 4), TERAZ) == 4

    def test_bez_pripomenuti_sa_neutlmi(self):
        """Samotný čas nestačí — musel dostať aj pripomenutia."""
        assert taper.level(clovek(5, 0), TERAZ) == 0

    def test_kto_zaplatil_nikdy_neutlmi(self):
        assert taper.level(clovek(9, 5, paid=True), TERAZ) == 0
        assert taper.level(clovek(9, 5, funnel_stage="converted"), TERAZ) == 0

    def test_rozbity_datum_neutlmi(self):
        assert taper.level({"link_sent_at": "nezmysel", "link_push_count": 5}, TERAZ) == 0


class TestPokyny:
    def test_kazda_uroven_ma_pokyn(self):
        for uroven in (1, 2, 3, 4):
            assert taper.guidance(uroven)

    def test_uroven_tri_pozyva_na_stranku(self):
        assert "príde tam" in taper.guidance(3)

    def test_ziadna_uroven_ho_neodpaluje(self):
        """Útlm je stíšenie, nie vyhodenie — nikde nesmie byť pokyn byť chladná."""
        for uroven in (1, 2, 3, 4):
            pokyn = taper.guidance(uroven)
            assert "chladná" not in pokyn or "nikdy nie chladná" in pokyn
            assert "ignoruj" not in pokyn.lower() or "ignoruješ" in pokyn

    def test_uroven_tri_zakazuje_rozlucku(self):
        """Má to znieť ako pozvánka, nie ako 'už ti nebudem odpisovať'."""
        assert "Žiadne „už ti nebudem odpisovať" in taper.guidance(3)
