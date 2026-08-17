"""Fanvue — fázy rozhovoru, kedy sa predáva a čo je v prompte."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import fanvue_agent as fa

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _event(typ="creator.message.received", **data):
    payload = {"data": {"object": "message", "sender": "fan", "text": "hey", **data}}
    return {"type": typ, "payload": payload}


class TestNaCoOdpisuje:
    def test_bezna_sprava_od_fanusika(self):
        assert fa.wants_reply(_event()) is True

    def test_vlastnu_spravu_nekomentuje(self):
        assert fa.wants_reply(_event(sender="creator")) is False

    def test_na_automat_neodpisuje(self):
        """Automat odpovedajúci automatu je nekonečná slučka."""
        assert fa.wants_reply(_event(is_automated=True)) is False

    def test_prazdna_sprava(self):
        assert fa.wants_reply(_event(text="   ")) is False

    def test_novy_odberatel_sa_pozna(self):
        assert fa.is_new_subscriber(_event("creator.subscription.activated")) is True
        assert fa.is_new_subscriber(_event()) is False

    def test_platba_sa_pozna_aj_so_sumou(self):
        e = _event("creator.payment.succeeded", amount=1500)
        assert fa.is_payment(e) is True
        assert fa.paid_cents(e) == 1500


class TestFazy:
    def test_na_zaciatku_sa_zoznamuje(self):
        assert fa.phase({"msg_count": 0}, {"discovery_msgs": 4}) == "discovery"
        assert fa.phase({"msg_count": 3}, {"discovery_msgs": 4}) == "discovery"

    def test_po_par_spravach_uz_vedie(self):
        assert fa.phase({"msg_count": 4}, {"discovery_msgs": 4}) == "known"

    def test_ked_povie_co_hlada_prejde_hned(self):
        """Toto je celý zmysel zoznamovania — nečakať zbytočne."""
        row = {"msg_count": 1, "wants": "sex chat"}
        assert fa.phase(row, {"discovery_msgs": 4}) == "known"


class TestKedySaPreda:
    ZAPNUTE = {"sell_content": True, "discovery_msgs": 0, "offer_after_msgs": 6, "offer_cooldown_h": 12}

    def test_vypnute_znamena_nikdy(self):
        assert fa.may_offer({"sell_content": False}, {"msg_count": 99}) is False

    def test_pocas_zoznamovania_nikdy(self):
        """Ponuka skôr, než vieme čo chce, je strela naslepo."""
        settings = {**self.ZAPNUTE, "discovery_msgs": 4}
        assert fa.may_offer(settings, {"msg_count": 2}) is False

    def test_prilis_skoro_nie(self):
        assert fa.may_offer(self.ZAPNUTE, {"msg_count": 3}) is False

    def test_po_dostatku_sprav_ano(self):
        assert fa.may_offer(self.ZAPNUTE, {"msg_count": 6}, NOW) is True

    def test_hned_po_ponuke_znova_nie(self):
        row = {"msg_count": 20, "last_offer_at": (NOW - timedelta(hours=2)).isoformat()}
        assert fa.may_offer(self.ZAPNUTE, row, NOW) is False

    def test_po_odstupe_znova_ano(self):
        row = {"msg_count": 20, "last_offer_at": (NOW - timedelta(hours=20)).isoformat()}
        assert fa.may_offer(self.ZAPNUTE, row, NOW) is True


class TestCasy:
    def test_rovnake_hranice_znamenaju_vzdy(self):
        assert fa.within_hours({"active_start_min": 0, "active_end_min": 0}, NOW) is True

    def test_v_okne_ano_mimo_nie(self):
        s = {"active_start_min": 9 * 60, "active_end_min": 22 * 60}
        assert fa.within_hours(s, NOW.replace(hour=12)) is True
        assert fa.within_hours(s, NOW.replace(hour=3)) is False

    def test_okno_cez_polnoc(self):
        """20:00–02:00 sa musí čítať naopak, inak by nebolo nikdy."""
        s = {"active_start_min": 20 * 60, "active_end_min": 2 * 60}
        assert fa.within_hours(s, NOW.replace(hour=23)) is True
        assert fa.within_hours(s, NOW.replace(hour=1)) is True
        assert fa.within_hours(s, NOW.replace(hour=12)) is False


class TestPamat:
    def test_fakty_sa_zlucia_a_novsie_prepisu(self):
        out = fa.merge_facts("praca: vodic\nmesto: berlin", [{"key": "praca", "value": "kuchar"}])
        assert "praca: kuchar" in out
        assert "mesto: berlin" in out

    def test_nezmysly_sa_preskocia(self):
        assert fa.parse_facts("bez dvojbodky\n: bez kluca\nok: hodnota") == {"ok": "hodnota"}

    def test_prazdna_pamat_nepadne(self):
        assert fa.merge_facts(None, []) == ""


PERSONA = {
    "name": "Simona",
    "backstory": "23, Los Angeles, fitness",
    "msg_style": "krátko, malé písmená",
    "tone": "drzá",
    "language": "English",
    "boundaries": "žiadne stretnutia",
}


class TestPrompt:
    def test_odkaz_na_fanvue_sa_zakazuje(self):
        out = fa.build_prompt(PERSONA, {}, {}, {}, None)
        assert "NIKDY neposielaj odkaz na Fanvue" in out

    def test_pri_zoznamovani_sa_pyta_co_tu_hlada(self):
        out = fa.build_prompt(PERSONA, {"discovery_msgs": 4}, {}, {"msg_count": 0}, None)
        assert "ZOZNAMUJETE" in out
        assert "what brings you here" in out
        assert "NIČ NEPONÚKAJ" in out

    def test_ked_vie_co_chce_vedie_tym_smerom(self):
        row = {"msg_count": 9, "wants": "sex chat"}
        out = fa.build_prompt(PERSONA, {"discovery_msgs": 4}, {}, row, None)
        assert "UŽ HO POZNÁŠ" in out
        assert "sex chat" in out

    def test_horuca_nastavenie_pusti_do_promptu_pravidla_sexu(self):
        out = fa.build_prompt(PERSONA, {"heat": "hot"}, {}, {}, None)
        assert "KEĎ TO IDE DO SEXU" in out
        assert "prvej osobe" in out

    def test_jemna_ostre_pravidla_nepusti(self):
        out = fa.build_prompt(PERSONA, {"heat": "mild"}, {}, {}, None)
        assert "KEĎ TO IDE DO SEXU" not in out

    def test_zakazuje_knizne_pisanie_vzdy(self):
        """Opisné vety na tri riadky prezradia automat rýchlejšie než čokoľvek."""
        out = fa.build_prompt(PERSONA, {}, {}, {}, None)
        assert "román" in out

    def test_pokyn_o_obsahu_sa_dostane_dnu(self):
        """O tom, či niečo odíde, rozhoduje kód — prompt to len dostane."""
        out = fa.build_prompt(
            PERSONA, {}, {}, {}, None, pokyn_obsah="- Pýta si fotku, ale si vo fitku."
        )
        assert "ČO TERAZ S OBSAHOM" in out
        assert "vo fitku" in out

    def test_pamat_sa_dostane_do_promptu(self):
        row = {"msg_count": 9, "facts": "praca: vodic", "summary": "flirtujú"}
        out = fa.build_prompt(PERSONA, {}, {}, row, None)
        assert "praca: vodic" in out
        assert "flirtujú" in out

    def test_miestny_cas_je_v_prompte(self):
        out = fa.build_prompt(PERSONA, {}, {}, {}, None, NOW.replace(hour=21, minute=5))
        assert "21:05" in out

    def test_kontext_z_telegramu(self):
        tg = {
            "user": {"first_name": "Joe", "summary": "flirtovali tri dni"},
            "facts": [{"key": "práca", "value": "vodič"}],
            "recent": [{"role": "user", "content": "miss you"}],
        }
        out = fa.build_prompt(PERSONA, {}, {}, {"msg_count": 9}, tg)
        assert "volá sa Joe" in out
        assert "flirtovali tri dni" in out
        assert "miss you" in out

    def test_hranice_persony_platia_aj_tu(self):
        out = fa.build_prompt(PERSONA, {}, {}, {}, None)
        assert "žiadne stretnutia" in out


class TestFanUdalosti:
    def test_vytiahne_fanusika_aj_text(self):
        event = _event(text="  ahoj  ", fan={"uuid": "u-1", "handle": "joe", "display_name": "Joe"})
        fan = fa.fan_of(event)
        assert fan["uuid"] == "u-1"
        assert fan["text"] == "ahoj"

    def test_chybajuci_fanusik_nepadne(self):
        assert fa.fan_of(_event())["uuid"] == ""
