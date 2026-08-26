"""Odkaz dostal a aj tak posiela nahé fotky ďalej.

Človek, ktorý odkaz má, pripomenutý mu bol, a namiesto toho posiela do
Telegramu ďalšie a ďalšie nahé fotky, si kúpil bezplatnú zábavu. Chatovať
s ním donekonečna nič nezmení — ale odstrihnúť ho bez slova tiež nie je
správne. Dostane jednu jasnú vetu („odkaz máš, tam mi také posielaj a ja
tebe tiež") a potom je ticho.

Cena omylu je vysoká: takto sa chat zatvára NAVŽDY. Preto musia platiť tri
podmienky naraz a testy tu strážia hlavne to, kedy sa to spustiť NESMIE.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import funnel
from behavior import Behavior
from persona import build_system_prompt

ODKAZ = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)


def _nude(minuty: int) -> dict:
    return {
        "role": "user",
        "content": "[poslal EXPLICITNÚ fotku: close up]",
        "created_at": (ODKAZ + timedelta(minutes=minuty)).isoformat(),
    }


def _user(**kw) -> dict:
    zaklad = {"link_sent_at": ODKAZ.isoformat(), "link_push_count": 2}
    zaklad.update(kw)
    return zaklad


class TestKedySaKonci:
    def test_tri_nahe_po_odkaze_a_po_pripomenuti(self):
        rows = [_nude(5), _nude(20), _nude(40)]
        assert funnel.pushing_after_link(_user(), rows) is True

    def test_dve_este_nestacia(self):
        """Dve sú vzplanutie, tri sú „posiela ich ďalej"."""
        assert funnel.pushing_after_link(_user(), [_nude(5), _nude(20)]) is False


class TestKedySaNESMIEKoncit:
    def test_bez_odkazu_nikdy(self):
        """Kto odkaz ešte nedostal, nemá kam ísť — zatvoriť mu chat by bolo
        len odohnanie človeka."""
        rows = [_nude(5), _nude(20), _nude(40)]
        assert funnel.pushing_after_link(_user(link_sent_at=None), rows) is False

    def test_bez_pripomenutia_nikdy(self):
        """Odkaz raz preletel v konverzácii — najprv dostane pripomenutie."""
        rows = [_nude(5), _nude(20), _nude(40)]
        assert funnel.pushing_after_link(_user(link_push_count=1), rows) is False

    def test_fotky_spred_odkazu_sa_neratajú(self):
        """Presne za tie ho odkaz dostal — nemôžu byť dôvodom skončiť."""
        stare = [
            {
                "role": "user",
                "content": "[poslal EXPLICITNÚ fotku: x]",
                "created_at": (ODKAZ - timedelta(hours=i)).isoformat(),
            }
            for i in (1, 2, 3)
        ]
        assert funnel.pushing_after_link(_user(), stare) is False

    def test_jej_vlastne_spravy_sa_neratajú(self):
        rows = [
            {"role": "assistant", "content": "[poslal EXPLICITNÚ fotku: x]",
             "created_at": (ODKAZ + timedelta(minutes=i)).isoformat()}
            for i in (5, 10, 15)
        ]
        assert funnel.pushing_after_link(_user(), rows) is False

    def test_bezne_fotky_sa_neratajú(self):
        rows = [
            {"role": "user", "content": "[poslal fotku: smiling man]",
             "created_at": (ODKAZ + timedelta(minutes=i)).isoformat()}
            for i in (5, 10, 15)
        ]
        assert funnel.pushing_after_link(_user(), rows) is False

    def test_pokazeny_cas_odkazu_nespusti_koniec(self):
        rows = [_nude(5), _nude(20), _nude(40)]
        assert funnel.pushing_after_link(_user(link_sent_at="neplatný"), rows) is False


class TestPoslednaSprava:
    """Znenie sa musí líšiť od bežnej rozlúčky — odkaz už má."""

    def _prompt(self, reason: str) -> str:
        return build_system_prompt(
            persona={"name": "Simona", "backstory": "x", "msg_style": "krátko",
                     "cta_link": "https://www.fanvue.com/sima.sima"},
            user={"tg_id": 1, "msg_count": 30, "funnel_stage": "link_sent"},
            allow_link=True,
            asked_if_ai=False,
            behavior=Behavior.from_row({}),
            farewell=True,
            farewell_reason=reason,
        )

    def test_pri_tlaceni_sa_odkaz_neposiela_znova(self):
        """Odkaz už má vyššie — poslať ho tretíkrát je otravné."""
        out = self._prompt("pushing")
        assert "ODKAZ MUSÍ BYŤ V TEJTO SPRÁVE" not in out
        assert "odkaz už má vyššie" in out.lower() or "má vyššie" in out

    def test_pri_tlaceni_este_raz_zareaguje_hot(self):
        """Skončiť chladne na jeho fotke by bolo horšie než neskončiť."""
        assert "zareaguj hot" in self._prompt("pushing")

    def test_pri_tlaceni_povie_kam_to_patri(self):
        out = self._prompt("pushing")
        assert "ill send u mine" in out

    def test_pri_tlaceni_ziadna_vycitka(self):
        out = self._prompt("pushing")
        assert "Žiadna výčitka" in out

    def test_bezna_rozlucka_ostala_nedotknuta(self):
        out = self._prompt("window")
        assert "strašne veľa správ" in out
        assert "ill send u mine" not in out

    def test_bez_dovodu_plati_bezna_rozlucka(self):
        """Volajúci, ktorý dôvod neposiela, dostane to, čo dostával doteraz."""
        out = build_system_prompt(
            persona={"name": "Simona", "backstory": "x", "msg_style": "krátko"},
            user={"tg_id": 1, "msg_count": 30},
            allow_link=False,
            asked_if_ai=False,
            farewell=True,
        )
        assert "strašne veľa správ" in out
