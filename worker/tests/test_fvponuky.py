"""Neodomknutá ponuka, ochota po nákupe a to, čo v zásobe nemáme."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fvflow

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
PRED = lambda h: (NOW - timedelta(hours=h)).isoformat()  # noqa: E731

S = {
    "sell_content": True, "offer_after_msgs": 6,
    "offer_cooldown_h": 12, "nudge_after_msgs": 25,
}


class TestNeodomknutaPonuka:
    def test_cerstva_visi(self):
        assert fvflow.offer_state({"pending_offer_at": PRED(0.2)}, NOW) == "visi"

    def test_starsia_uz_nevisi(self):
        assert fvflow.offer_state({"pending_offer_at": PRED(5)}, NOW) == "stara"

    def test_ziadna_ponuka(self):
        assert fvflow.offer_state({}, NOW) == ""

    def test_ked_visi_dalsiu_neposiela(self):
        """Dve neodomknuté vedľa seba vyzerajú ako otravný predavač."""
        row = {"msg_count": 30, "pending_offer_at": PRED(0.2)}
        assert fvflow.paid_moment(row, S, asked_spicy=True, now=NOW) == "visi"

    def test_pokyn_mu_pripomenie_ze_jedno_ma(self):
        out = fvflow.guidance({}, S, "visi", False, asked_photo=True)
        assert "už máš" in out
        assert "neposielaj" in out

    def test_po_hodine_uz_smie_dalsiu(self):
        row = {"msg_count": 30, "pending_offer_at": PRED(5)}
        assert fvflow.paid_moment(row, S, asked_spicy=True, now=NOW) == "asked"


class TestPoNakupe:
    def test_kto_prave_kupil_je_najochotnejsi(self):
        row = {"msg_count": 30, "last_bought_at": PRED(1)}
        assert fvflow.paid_moment(row, S, asked_spicy=False, now=NOW) == "after_buy"

    def test_starsi_nakup_uz_neplati(self):
        row = {"msg_count": 30, "last_bought_at": PRED(9)}
        assert fvflow.paid_moment(row, S, asked_spicy=False, now=NOW) != "after_buy"

    def test_pokyn_necha_jeho_povedat_co_chce(self):
        out = fvflow.guidance({}, S, "after_buy", False, False)
        assert "nechaj HO povedať" in out


class TestKedyNemameToCoChce:
    def test_pri_ziadosti_sa_pripomina_custom(self):
        out = fvflow.guidance({}, S, "asked", False, False)
        assert "custom" in out
        assert "nevymýšľaj" in out

    def test_nahrada_potichu_je_zakazana(self):
        assert "potichu" in fvflow.MISSING_HINT


class TestZadarmoMenej:
    def test_pri_bezneej_fotke_pripomina_ze_zadarmo_je_malo(self):
        row = {"free_photos": 0}
        out = fvflow.guidance(row, {**S, "free_photo_max": 2}, "", True, False)
        assert "Zadarmo posielaš málo" in out
