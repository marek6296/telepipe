"""Zamknutá fotka (unlock.me) — druhá cesta k peniazom popri Fanvue funneli.

ČO SA NESMIE POKAZIŤ. Toto je doplnok, nie náhrada: bežný funnel (odkaz na
platformu, pripomenutie, rozlúčka) musí fungovať presne ako doteraz. Preto
väčšina testov tu kontroluje, kedy sa odkaz poslať NESMIE.

Ide to v dvoch krokoch — najprv otázka („chceš to vidieť?"), odkaz až po
jeho súhlase. Odkaz do ticha je reklama, otázka je rozhovor.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import funnel

TERAZ = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
PERSONA = {"unlock_enabled": True, "unlock_link": "https://unlock.me/abc"}


def _user(**kw):
    zaklad = {
        "funnel_stage": "link_sent",
        "paid": False,
        "link_sent_at": (TERAZ - timedelta(days=1)).isoformat(),
        "unlock_count": 0,
        "unlock_offered_at": None,
    }
    zaklad.update(kw)
    return zaklad


class TestKedySaPyta:
    def test_pyta_fotku_a_odkaz_uz_ma(self):
        assert funnel.unlock_offer(_user(), PERSONA, True, False, TERAZ) is True

    def test_aj_ked_tlaci_na_ostre_veci(self):
        assert funnel.unlock_offer(_user(), PERSONA, False, True, TERAZ) is True

    def test_ked_nic_nechce_tak_nie(self):
        """Ponuka do prázdna je reklama."""
        assert funnel.unlock_offer(_user(), PERSONA, False, False, TERAZ) is False


class TestKedySaNESMIEPytat:
    def test_vypnute(self):
        p = {**PERSONA, "unlock_enabled": False}
        assert funnel.unlock_offer(_user(), p, True, True, TERAZ) is False

    def test_bez_odkazu_v_nastaveniach(self):
        p = {**PERSONA, "unlock_link": "  "}
        assert funnel.unlock_offer(_user(), p, True, True, TERAZ) is False

    def test_este_nedostal_odkaz_na_platformu(self):
        """Toto je to najdôležitejšie: unlock nesmie predbehnúť vlastný funnel."""
        u = _user(link_sent_at=None, funnel_stage="warm")
        assert funnel.unlock_offer(u, PERSONA, True, True, TERAZ) is False

    def test_platiacemu_nikdy(self):
        assert funnel.unlock_offer(_user(paid=True), PERSONA, True, True, TERAZ) is False
        u = _user(funnel_stage="converted")
        assert funnel.unlock_offer(u, PERSONA, True, True, TERAZ) is False

    def test_uz_ho_dostal(self):
        """Raz za chat. Druhá ponuka už nie je ponuka."""
        assert funnel.unlock_offer(_user(unlock_count=1), PERSONA, True, True, TERAZ) is False

    def test_nepyta_sa_dvakrat_kym_ponuka_plati(self):
        u = _user(unlock_offered_at=(TERAZ - timedelta(hours=1)).isoformat())
        assert funnel.unlock_offer(u, PERSONA, True, True, TERAZ) is False

    def test_po_vyprsani_ponuky_sa_smie_spytat_znova(self):
        u = _user(unlock_offered_at=(TERAZ - timedelta(hours=30)).isoformat())
        assert funnel.unlock_offer(u, PERSONA, True, True, TERAZ) is True


class TestKedySaPosiela:
    PONUKA = {"unlock_offered_at": (TERAZ - timedelta(minutes=5)).isoformat()}

    def test_povedal_ano(self):
        u = _user(**self.PONUKA)
        assert funnel.unlock_send(u, PERSONA, "yes please", TERAZ) is True

    def test_bez_ponuky_nikdy(self):
        """Aj keby napísal „yes" na niečo úplne iné."""
        assert funnel.unlock_send(_user(), PERSONA, "yes", TERAZ) is False

    def test_stara_ponuka_uz_neplati(self):
        u = _user(unlock_offered_at=(TERAZ - timedelta(hours=9)).isoformat())
        assert funnel.unlock_send(u, PERSONA, "yes", TERAZ) is False

    def test_odmietol(self):
        u = _user(**self.PONUKA)
        for odpoved in ("no", "nah", "no thanks", "maybe later"):
            assert funnel.unlock_send(u, PERSONA, odpoved, TERAZ) is False, odpoved

    def test_odpovedal_nieco_ine(self):
        u = _user(**self.PONUKA)
        assert funnel.unlock_send(u, PERSONA, "what did u do today", TERAZ) is False

    def test_platiacemu_ani_po_ano(self):
        u = _user(paid=True, **self.PONUKA)
        assert funnel.unlock_send(u, PERSONA, "yes", TERAZ) is False


class TestSuhlas:
    def test_bezne_tvary(self):
        for t in ("yes", "yeah", "yep", "sure", "ok", "ofc", "of course",
                  "please", "pls", "show me", "send it", "fuck yes", "i want"):
            assert funnel.said_yes(t), t

    def test_odmietnutie_neprejde(self):
        for t in ("no", "nope", "nah", "never", "no thanks", "stop", "later"):
            assert not funnel.said_yes(t), t

    def test_dlha_veta_nie_je_suhlas(self):
        assert not funnel.said_yes("i was gonna say something else entirely")

    def test_prazdne(self):
        assert not funnel.said_yes("") and not funnel.said_yes("   ")


class TestPromptMaDvaKroky:
    def _p(self, **kw):
        from behavior import Behavior
        from persona import build_system_prompt

        zaklad = dict(
            persona={"name": "S", "backstory": "x", "msg_style": "krátko"},
            user={"tg_id": 1, "msg_count": 20, "funnel_stage": "link_sent"},
            allow_link=False, asked_if_ai=False, behavior=Behavior.from_row({}),
        )
        zaklad.update(kw)
        return build_system_prompt(**zaklad)

    def test_ponuka_nema_odkaz(self):
        """Prvý krok je otázka. Odkaz v nej by celý dvojkrok zrušil."""
        out = self._p(unlock_offer=True)
        assert "SPÝTAJ SA HO" in out
        assert "unlock.me" not in out
        assert "ŽIADNY ODKAZ" in out

    def test_odoslanie_ma_odkaz(self):
        out = self._p(unlock_link="https://unlock.me/abc")
        assert "POVEDAL ÁNO" in out
        assert "https://unlock.me/abc" in out

    def test_nesmie_spochybnit_stranku(self):
        """Je to doplnok — nie správa, že sa presťahovala inam."""
        for out in (self._p(unlock_offer=True), self._p(unlock_link="https://unlock.me/abc")):
            assert "NIE JE náhrada" in out or "nepýtaj sa nasilu" in out

    def test_bez_neho_sa_nic_nepridava(self):
        out = self._p()
        assert "SPÝTAJ SA HO" not in out and "POVEDAL ÁNO" not in out


class TestOdkazPrezijeCistenie:
    def test_povoleny_odkaz_ostane_ostatne_zmiznu(self):
        """Keď je odkaz na platformu na cooldowne, čistenie zmaže VŠETKY URL —
        aj ten unlock, ktorý práve poslať smie."""
        from userbot import _strip_urls

        text = "tu to mas https://unlock.me/abc a toto nie https://inde.com/x"
        out = _strip_urls(text, keep="https://unlock.me/abc")
        assert "https://unlock.me/abc" in out
        assert "inde.com" not in out

    def test_bez_povolenia_zmizne_vsetko(self):
        from userbot import _strip_urls

        assert "unlock.me" not in _strip_urls("hej https://unlock.me/abc")
