"""Tú istú taktiku nemožno používať na toho istého človeka dookola.

Marek: „ono nemozeme rovnaku taktyku pouzivat na toho isteho cloveka dookola
… ked tam ostanu dlhsie treba aj sex chat a podobne a ked su nadrzany a chcu
daco potom posielat hlavne."

Tri veci naraz:
  1. REGISTER ŤAHOV — postup, ktorý raz predal, sa nesmie opakovať. Formulku
     človek spozná rýchlejšie než čokoľvek iné. (`fvtah`)
  2. SEX CHAT JE PRODUKT — kto tu ostáva dlhšie, platí aj za rozhovor. Keď
     beží, ponuka doňho neskáče. (`fvmedia.rozohriaty` + `paid_moment`)
  3. PREDÁVA SA NA VRCHOLE — keď si o niečo povie, to je ten moment. (`asked`)
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import fvflow
import fvmedia
import fvtah

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class TestRegisterTahov:
    def test_nepouzity_tah_je_volny(self):
        assert fvtah.vyber({}, fvtah.NUDGE, now=NOW) is not None

    def test_pouzity_sa_hned_nezopakuje(self):
        tah = fvtah.CATALOG[0]
        pouzite = {tah.key: NOW.isoformat()}
        assert fvtah.je_volny(tah, pouzite, tah.momenty[0], NOW) is False

    def test_po_odstupe_sa_smie_znova(self):
        tah = fvtah.CATALOG[0]
        davno = (NOW - timedelta(hours=tah.cooldown_h + 1)).isoformat()
        assert fvtah.je_volny(tah, {tah.key: davno}, tah.momenty[0], NOW) is True

    def test_ked_su_vsetky_pouzite_nevrati_nic(self):
        """Lepšie bez pokynu než zopakovať ten, ktorý si pamätá."""
        vsetky = {t.key: NOW.isoformat() for t in fvtah.CATALOG}
        assert fvtah.vyber(vsetky, fvtah.NUDGE, now=NOW) is None

    def test_tah_sedi_na_moment(self):
        for _ in range(20):
            tah = fvtah.vyber({}, fvtah.AFTER_BUY, now=NOW)
            assert tah is None or fvtah.AFTER_BUY in tah.momenty

    def test_bez_momentu_ziadny_tah(self):
        assert fvtah.vyber({}, "", now=NOW) is None

    def test_striedaju_sa(self):
        """Dvadsať ťahov za sebou nesmie byť dvadsaťkrát ten istý."""
        pouzite: dict = {}
        videne = set()
        for _ in range(20):
            tah = fvtah.vyber(pouzite, fvtah.NUDGE, rng=random.Random(1), now=NOW)
            if tah is None:
                break
            videne.add(tah.key)
            pouzite = fvtah.zapis(pouzite, tah.key, NOW)
        assert len(videne) > 1

    def test_minimalny_odstup_plati_aj_pri_nizsom_nastaveni(self):
        tah = fvtah.Tah("x", "hint", (fvtah.NUDGE,), cooldown_h=1)
        kedy = (NOW - timedelta(hours=2)).isoformat()
        assert fvtah.je_volny(tah, {"x": kedy}, fvtah.NUDGE, NOW) is False

    def test_nezmyselna_znacka_neblokuje(self):
        tah = fvtah.CATALOG[0]
        assert fvtah.je_volny(tah, {tah.key: "nezmysel"}, tah.momenty[0], NOW) is True

    def test_register_z_riadku(self):
        assert fvtah.pouzite_z({"used_moves": {"a": "x"}}) == {"a": "x"}
        assert fvtah.pouzite_z({}) == {}
        assert fvtah.pouzite_z({"used_moves": None}) == {}

    def test_blok_bez_tahu_je_prazdny(self):
        assert fvtah.blok(None) == ""

    def test_kluce_su_jedinecne(self):
        assert len({t.key for t in fvtah.CATALOG}) == len(fvtah.CATALOG)

    def test_marekove_tahy_su_v_katalogu(self):
        """Ktoré naozaj predali — nechaj vybrať, zaváhaj, exkluzivita, príbeh."""
        for kluc in ("vyber_z_dvoch", "zavahanie", "exkluzivita", "pribeh"):
            assert kluc in fvtah.BY_KEY


class TestRozohriatyChat:
    def test_sex_chat_sa_pozna(self):
        h = [
            {"content": "hey"},
            {"content": "im so horny"},
            {"content": "mmm"},
            {"content": "i wanna fuck u"},
        ]
        assert fvmedia.rozohriaty(h) is True

    def test_bezny_rozhovor_nie(self):
        h = [{"content": "hey"}, {"content": "how are u"}, {"content": "good day?"}]
        assert fvmedia.rozohriaty(h) is False

    def test_jedna_narazka_nestaci(self):
        assert fvmedia.rozohriaty([{"content": "hey"}, {"content": "im horny"}]) is False

    def test_stara_naladenost_uz_neplati(self):
        """Okno je krátke zámerne — pred hodinou to bolo, teraz je reč o inom."""
        h = [{"content": "im horny"}, {"content": "fuck"}] + [{"content": "ok"}] * 6
        assert fvmedia.rozohriaty(h) is False

    def test_prazdna_historia_nepadne(self):
        assert fvmedia.rozohriaty([]) is False
        assert fvmedia.rozohriaty(None) is False


class TestKedySaPredava:
    NASTAVENIA = {"sell_content": True, "nudge_after_msgs": 5}
    RIADOK = {"msg_count": 20}

    def test_v_beznom_chate_pride_s_tym_sama(self):
        assert fvflow.paid_moment(self.RIADOK, self.NASTAVENIA, False) == "nudge"

    def test_do_sex_chatu_neskace(self):
        """Toto je jadro: rozhovor sám je to, za čo platí."""
        assert (
            fvflow.paid_moment(self.RIADOK, self.NASTAVENIA, False, rozohriaty=True)
            == ""
        )

    def test_ked_si_povie_predava_sa_aj_v_sex_chate(self):
        """«ked su nadrzany a chcu daco potom posielat hlavne»"""
        assert (
            fvflow.paid_moment(self.RIADOK, self.NASTAVENIA, True, rozohriaty=True)
            == "asked"
        )


class TestPokynyVPrompte:
    def test_sex_chat_ma_vlastny_pokyn(self):
        out = fvflow.guidance({}, {}, "", False, False, rozohriaty=True)
        assert "BEŽÍ SEX CHAT" in out
        assert "nekaz to" in out

    def test_bez_sex_chatu_ten_pokyn_nie_je(self):
        out = fvflow.guidance({}, {}, "nudge", False, False)
        assert "BEŽÍ SEX CHAT" not in out

    def test_tah_sa_pripoji_k_pokynom(self):
        tah = fvtah.BY_KEY["zavahanie"]
        out = fvflow.guidance(
            {}, {"sell_content": True}, "nudge", False, False,
            tah_hint=fvtah.blok(tah),
        )
        assert "inak než minule" in out

    def test_tah_sam_o_sebe_nic_nespusti(self):
        """Bez ostatných pokynov by visel vo vzduchu bez rozhodnutia."""
        out = fvflow.guidance({}, {}, "", False, False, tah_hint="NIECO")
        assert "NIECO" not in out


class TestNapojenie:
    def test_agent_zapisuje_pouzity_tah(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "fanvue_agent.py").read_text(
            "utf-8"
        )
        assert src.count("fvtah.zapis(") == 2, "auto aj semi vetva musia zapisovať"
        assert "rozohriaty=horuco" in src
