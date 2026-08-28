"""Prečo boli návrhy na Fanvue nepoužiteľné.

Marek: „vela krat su strasne zle navrhnute, fakt si malo kedy viem vybrat".
Príčina nebola v generovaní návrhov, ale v tom, čo model o situácii vedel.

NAMERANÉ 28. 8.: všetci TRAJA platiaci fanúšikovia (30,99 / 64,99 / 69,99 $,
tri nákupy každý) mali `stage = discovery`. Tá vetva promptu hovorí doslova
„Nevieš o ňom nič" a „TERAZ NIČ NEPONÚKAJ A NIČ NEPREDÁVAJ" — modelka teda
ponúkala zoznamovacie vety ľuďom, s ktorými bol majiteľ v predajnom rozhovore,
a `may_offer` im nesmela ponúknuť nič.

Fázu pritom držalo `msg_count`, ktoré sa zvyšuje LEN pri správach cez bota.
Kto píše priamo vo Fanvue — a v režime `semi` je to majiteľ — ho nechá takmer
na nule: 50 správ v chate a `msg_count` 6, 34 správ a 0.
"""
from __future__ import annotations

import fanvue_agent as fa
import fvflow
import fvsync


class TestKtoUzKupilNieJeCudzi:
    def test_kupujuci_je_known_aj_bez_sprav(self):
        """Toto je jadro chyby — 70 $ a stále «nevieš o ňom nič»."""
        assert fa.phase({"bought_count": 3, "msg_count": 0}, {}) == "known"

    def test_rozhoduju_aj_same_peniaze(self):
        assert fa.phase({"spent_cents": 3099, "msg_count": 0}, {}) == "known"

    def test_naozaj_novy_ostava_v_zoznamovani(self):
        assert fa.phase({"msg_count": 0}, {}) == "discovery"

    def test_dost_sprav_stale_staci(self):
        assert fa.phase({"msg_count": 6}, {}) == "known"

    def test_kupujucemu_uz_smie_ponuknut(self):
        """`may_offer` v `discovery` vracia False — kupujúcemu teda nesmela NIČ.

        Toto je priamy dôsledok chyby vo fáze: človek, ktorý u nej trikrát
        nakúpil, nemohol dostať ďalšiu ponuku, lebo systém ho stále považoval
        za cudzieho.
        """
        nastavenia = {"sell_content": True, "offer_after_msgs": 0}
        assert fa.may_offer(nastavenia, {"bought_count": 2, "msg_count": 0}) is True
        # Naozaj nový človek ponuku ďalej nedostane.
        assert fa.may_offer(nastavenia, {"msg_count": 0}) is False


class TestUhlyPodlaFazy:
    def test_cudziemu_sa_nepredava(self):
        uhly = fa.uhly_pre({"msg_count": 1}, {})
        assert uhly is fa.UHLY_ZOZNAMOVANIE
        assert not any("ponuk" in u for u in uhly)

    def test_kupujucemu_sa_predava(self):
        uhly = fa.uhly_pre({"bought_count": 1}, {})
        assert uhly is fa.UHLY_PREDAJ

    def test_su_to_tri_rozne_tahy(self):
        for uhly in (fa.UHLY_ZOZNAMOVANIE, fa.UHLY_PREDAJ):
            assert len(uhly) == 3
            assert len(set(uhly)) == 3

    def test_jeden_uhol_vzdy_nepredava(self):
        """Inak by boli všetky tri ponuky a majiteľ by nemal z čoho vyberať."""
        assert "bez akejkoľvek ponuky" in fa.UHLY_PREDAJ[0]

    def test_predajne_uhly_su_marekove_tahy(self):
        spolu = " ".join(fa.UHLY_PREDAJ)
        assert "zúž to na výber" in spolu, "«sitting or bent over?»"
        assert "zaváhaj" in spolu, "«i dont sure if i want share this one»"


class TestAkoSaPredava:
    def test_postup_je_v_prompte(self):
        out = fvflow.PREDAJ_AKO
        assert "nechaj POVEDAŤ, čo chce" in out
        assert "zaváhaj" in out.lower()
        assert "len preňho" in out

    def test_fotka_ma_mat_pribeh(self):
        assert "príbeh" in fvflow.PREDAJ_AKO

    def test_zakazuje_hole_nie(self):
        """«Odmietnutie zatvára chat, náznak ho drží otvorený.»"""
        assert "NIKDY nie holé nie" in fvflow.PREDAJ_AKO


class TestHistoriaBezDuplicit:
    """6 % správ bolo zdvojených — model videl svoju poslednú vetu dvakrát."""

    def _sprava(self, uuid, text, kto="fan-1"):
        return {"uuid": uuid, "text": text, "author": {"uuid": kto}}

    def test_co_sme_poslali_sa_nepridava_druhy_raz(self):
        fetched = [self._sprava("u1", "ahoj")]
        out = fvsync.missing(set(), fetched, "creator-1", bez_uuid=["ahoj"])
        assert out == []

    def test_bez_poistky_by_pribudla(self):
        """Kontrola, že test naozaj testuje tú poistku."""
        fetched = [self._sprava("u1", "ahoj")]
        assert len(fvsync.missing(set(), fetched, "creator-1")) == 1

    def test_naozaj_zopakovana_sprava_prejde(self):
        """Keď to isté napíše dvakrát, druhá je nová správa, nie duplicita."""
        fetched = [self._sprava("u1", "ahoj"), self._sprava("u2", "ahoj")]
        out = fvsync.missing(set(), fetched, "creator-1", bez_uuid=["ahoj"])
        assert len(out) == 1

    def test_ine_znenie_sa_nezahodi(self):
        fetched = [self._sprava("u1", "nieco ine")]
        out = fvsync.missing(set(), fetched, "creator-1", bez_uuid=["ahoj"])
        assert len(out) == 1

    def test_dedup_podla_uuid_funguje_dalej(self):
        fetched = [self._sprava("u1", "ahoj")]
        assert fvsync.missing({"u1"}, fetched, "creator-1") == []


class TestPocitadloSprav:
    def test_zosuladenie_ho_prepocita_zo_skutocneho_chatu(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "fanvue_agent.py").read_text(
            "utf-8"
        )
        i = src.index("async def _reconcile")
        blok = src[i : i + 3000]
        assert "skutocny_pocet = len(skutocne)" in blok
        assert '"msg_count": skutocny_pocet' in blok
