"""Rámec „zadarmo to nie je" — a chyby z ostrých chatov, ktoré ho vynútili.

Všetky prípady nižšie sú NAMERANÉ na Simoniných chatoch z 24.–27. 8. 2026,
nie vymyslené. Preto sú tu aj citáty: keď to niekto o rok prepíše, má vidieť,
čo presne sa naživo stalo.
"""
from __future__ import annotations

from datetime import datetime

import funnel
import ramec
from behavior import Behavior
from persona import build_system_prompt


def _user(**kw):
    zaklad = {
        "tg_id": 1,
        "msg_count": 40,
        "link_sent_at": "2026-08-26T04:00:00+00:00",
        "link_push_count": 1,
        "paid": False,
    }
    zaklad.update(kw)
    return zaklad


def _nahych(kolko: int):
    return [
        {"role": "user", "content": "[poslal EXPLICITNÚ fotku: x]",
         "created_at": "2026-08-26T21:00:00+00:00"}
        for _ in range(kolko)
    ]


class TestKedyDrzatRamec:
    def test_ma_odkaz_nezaplatil_a_pyta_fotku(self):
        assert ramec.drzat(_user(), [], wants_photo=True) is True

    def test_posiela_nahe_po_odkaze(self):
        assert ramec.drzat(_user(), _nahych(1), explicit_now=True) is True

    def test_bez_odkazu_sa_nema_na_co_odvolat(self):
        """Kto odkaz ešte nedostal, nemá kam ísť — rámec by bol len odmietnutie."""
        assert ramec.drzat(_user(link_sent_at=None), [], wants_photo=True) is False

    def test_kto_zaplatil_je_zakaznik(self):
        assert ramec.drzat(_user(paid=True), [], wants_photo=True) is False

    def test_ked_prave_netlaci_mlci(self):
        """Bez tejto podmienky by to bola výčitka do ticha."""
        assert ramec.drzat(_user(), [], wants_photo=False, explicit_now=False) is False

    def test_rozlucka_ma_prednost(self):
        """Inak by v jednej správe aj presúval, aj lúčil sa."""
        user = _user(link_push_count=2)
        rows = _nahych(funnel.NUDE_PUSH_LIMIT)
        assert funnel.pushing_after_link(user, rows) is True
        assert ramec.drzat(user, rows, explicit_now=True) is False


class TestZneniaRamca:
    def test_zakazuje_povzbudzovanie(self):
        """Naživo: „damn thats thick 🥵 nice grip too keep showing off"."""
        assert "keep showing off" in ramec.blok()
        assert "NEPOVZBUDZUJ" in ramec.blok()

    def test_neposiela_odkaz_znova(self):
        assert "NEPOSIELAJ" in ramec.blok()

    def test_nie_je_to_odmietnutie(self):
        out = ramec.blok()
        assert "samozrejmosť" in out
        assert "neurážaš" in out

    def test_pokracuje_v_rozhovore(self):
        """Rámec chat nezatvára — to robí rozlúčka."""
        assert "pokračuj v rozhovore" in ramec.blok()


class TestBezSlubov:
    def test_zakazuje_slub_na_neskor(self):
        """Naživo: „maybe i flash something cute later if u ask nice"."""
        out = ramec.bez_slubov()
        assert "NIKDY NESĽUBUJ NIČ ZADARMO" in out
        assert "neskôr" in out

    def test_flirtovat_sa_stale_smie(self):
        """Zákaz je na KONKRÉTNY obsah, nie na náladu — inak by vyschla."""
        assert "smieš naplno" in ramec.bez_slubov()


class TestNapojenieDoPromptu:
    def _p(self, **kw):
        return build_system_prompt(
            persona={"name": "S", "backstory": "x", "msg_style": "krátko"},
            user=_user(), allow_link=False, asked_if_ai=False,
            behavior=Behavior.from_row({}), **kw,
        )

    def test_ramec_je_v_prompte_len_ked_ma_byt(self):
        assert "ZADARMO TO NIE JE" in self._p(hold_frame=True)
        assert "ZADARMO TO NIE JE" not in self._p(hold_frame=False)

    def test_zakaz_slubov_ide_vzdy(self):
        """Sľuby padali aj tam, kde nikto netlačil."""
        assert "NIKDY NESĽUBUJ NIČ ZADARMO" in self._p()

    def test_pri_ramci_nedostane_pokyn_mlcat_o_stranke(self):
        """Práve ten pokyn vyrobil „keep showing off"."""
        out = self._p(
            hold_frame=True, remind_link=False,
            last_incoming="[poslal EXPLICITNÚ fotku: x]",
        )
        assert "Stránku ani odkaz TERAZ vôbec nespomínaj" not in out


class TestOtazkaKdeToNajde:
    """Naživo: „Once you do your shoots where do all the photos go?" →
    „most go on my page after i sort them" — stránku pomenovala, odkaz nedala."""

    def test_chyti_namerane_znenie(self):
        assert funnel.asks_where_content(
            "Once you do your shoots where do all the photos go?"
        )

    def test_chyti_obe_poradia_slov(self):
        assert funnel.asks_where_content("where can i see your pics")
        assert funnel.asks_where_content("where do all the photos go")

    def test_nechyti_bezne_otazky(self):
        for text in (
            "where are you from", "where do you live", "i love your photos",
            "where were the photos taken", "where did you get that shirt",
        ):
            assert not funnel.asks_where_content(text), text

    def test_sekcia_pri_poslanom_odkaze_ukaze_hore(self):
        out = build_system_prompt(
            persona={"name": "S", "backstory": "x", "msg_style": "k"},
            user=_user(), allow_link=False, asked_if_ai=False,
            behavior=Behavior.from_row({}),
            page_question=True, link_already_sent=True,
        )
        assert "PÝTA SA, KDE TVOJ OBSAH NÁJDE" in out
        assert "pozrie hore" in out


class TestMenoZTelegramu:
    def test_namerane_zle_mena_uz_neprejdu(self):
        """„Im feeling horny thinking about you" dalo meno „Feeling" Jasonovi."""
        assert funnel.extract_name("Im feeling horny thinking about you") == ""
        assert funnel.extract_name("im shorter than you") == ""

    def test_skutocne_predstavenia_fungujú_dalej(self):
        assert funnel.extract_name("my name is Gerard") == "Gerard"
        assert funnel.extract_name("im Marek") == "Marek"
        assert funnel.extract_name("call me Colin") == "Colin"

    def test_telegramove_meno_ma_prednost(self):
        assert funnel.z_telegramu("Jason") == "Jason"
        assert funnel.z_telegramu("  don  ") == "Don"

    def test_prezyvka_neprejde(self):
        """Radšej žiadne meno než oslovovať človeka prezývkou."""
        assert funnel.z_telegramu("ailqk_1") == ""
        assert funnel.z_telegramu("") == ""

    def test_kratke_ing_mena_ostavaju(self):
        """Ming a Jing sú mená, „feeling" nie."""
        assert funnel.z_telegramu("Ming") == "Ming"
        assert funnel.extract_name("im Ming") == "Ming"

    def test_userbot_berie_telegram_ako_prvy(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "userbot.py").read_text("utf-8")
        i = src.index("if not (user.get(\"partner_name\") or \"\").strip():")
        blok = src[i : i + 700]
        assert blok.index("z_telegramu") < blok.index("extract_name")


class TestVyhovorkaLenRaz:
    def test_zaneprazdnena_sa_neopakuje(self):
        """Naživo 10× z 80 správ, z toho 8× za dve hodiny."""
        out = build_system_prompt(
            persona={"name": "S", "backstory": "x", "msg_style": "k"},
            user=_user(), allow_link=False, asked_if_ai=False,
            behavior=Behavior.from_row({}), busy=True,
            now_local=datetime(2026, 8, 27, 14, 0),
        )
        assert "POVEDZ TO NAJVIAC RAZ" in out
