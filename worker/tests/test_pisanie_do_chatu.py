"""Písanie do chatu bez čakajúcej karty.

DVE VECI, KTORÉ CHÝBALI:

1. Na jednu správu od fanúšika sa dalo odpovedať práve raz. Kto chcel napísať
   vetu a hneď za ňou poslať fotku, musel čakať, kým fanúšik napíše znova —
   a to je presne to, čo skutočný človek nerobí.
2. Do chatu sa vôbec nedalo napísať prvému. Kým fanúšik nenapísal, karta
   neexistovala a bot nemal kam poslať ani slovo.

Oboje rieši ten istý rozvod: rozhodovanie sa oddelilo od PÍSANIA. Karta
(`pending_replies`) uzatvára jednu odpoveď; kontext chatu (`_chat_ctx`) žije
ďalej a stačí na to, aby sa dalo poslať čokoľvek ďalšie.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")


class TestPosielanieBezKarty:
    def test_odoslanie_nekonci_slepou_ulickou(self):
        """Po odoslaní musí prísť otázka, či ide ešte niečo — inak sa druhá
        vec tomu istému človeku poslať nedá."""
        assert "Anything else for" in SRC
        assert 'Button.inline("➕ Send more", b"an")' in SRC

    def test_kontext_chatu_prezije_rozhodnutie(self):
        """`_forget_card` zabúda kartu. Keby zabudol aj chat, „Send more" by
        nemalo komu poslať."""
        zaciatok = SRC.index("async def _forget_card")
        koniec = SRC.index("async def _pin_card")
        telo = SRC[zaciatok:koniec]
        assert "_chat_ctx" not in telo

    def test_pid_je_volitelny_pri_kazdom_odoslani(self):
        """Text, fotka aj hlasovka sa musia dať poslať bez čakajúceho riadku.

        Výnimka je časový fallback: ten vzniká Z RIADKU, takže `pid` tam vždy
        je a podmienka by len zakrývala, že sa niečo pokazilo.
        """
        nechranene = [
            riadok.strip()
            for riadok in SRC.splitlines()
            if "claim_pending(pid)" in riadok and "pid and" not in riadok
        ]
        assert len(nechranene) == 1, nechranene
        fallback = SRC.index("async def _auto_send")
        koniec = SRC.index("async def recover_cards")
        assert nechranene[0] in SRC[fallback:koniec], "nechránené je inde než vo fallbacku"

    def test_zapisy_do_pending_su_podmienene(self):
        """`mark_pending(None, …)` by spadlo na strane databázy."""
        for riadok in SRC.splitlines():
            if "mark_pending(pid" in riadok:
                assert riadok.strip().startswith("await self._db.mark_pending"), riadok

    def test_done_kontext_zahodi(self):
        """Bez toho by sa dalo písať do chatu, ktorý majiteľ zavrel."""
        assert 'elif head == "ad":' in SRC
        assert "self._chat_ctx.pop(mid, None)" in SRC


class TestOtvorenieChatuZMenu:
    def test_menu_ma_oba_kanaly(self):
        assert 'Button.inline("💬 Fanvue chats", b"fc")' in SRC
        assert 'Button.inline("💬 Telegram chats", b"tc")' in SRC

    def test_tlacidlo_nesie_index_nie_kluc(self):
        """Callback dáta majú strop 64 bajtov a fanvue uuid má 36 znakov —
        s dvoma takými kľúčmi by tlačidlo prestalo fungovať."""
        assert 'f"oc:{i}".encode()' in SRC

    def test_stary_zoznam_nespadne(self):
        assert "That list is stale" in SRC

    def test_composer_ponuka_vsetky_tri_veci(self):
        zaciatok = SRC.index("async def _composer")
        telo = SRC[zaciatok:zaciatok + 1400]
        assert 'b"ac"' in telo and 'b"af"' in telo and 'b"av"' in telo

    def test_z_menu_sa_neponukaju_navrhy(self):
        """Bez karty žiadne návrhy neexistujú — čísla by nemali čo poslať."""
        assert "Use ✍️ Message generator in the menu" in SRC


class TestPamatNerastieDonekonecna:
    def test_kontexty_maju_strop(self):
        import control_bot

        assert control_bot._MAX_CHAT_CTX <= 200

    def test_strop_sa_naozaj_uplatnuje(self):
        import control_bot

        bot = control_bot.ControlBot.__new__(control_bot.ControlBot)
        bot._chat_ctx = {}
        for i in range(control_bot._MAX_CHAT_CTX + 25):
            bot._zapamataj_chat(i, channel="fanvue", conv_key=str(i), name="x")
        assert len(bot._chat_ctx) == control_bot._MAX_CHAT_CTX
        # Najnovší zostáva, najstarší odchádza.
        assert (control_bot._MAX_CHAT_CTX + 24) in bot._chat_ctx
        assert 0 not in bot._chat_ctx


class TestObaKanalyVediaVypisatChaty:
    def test_agenty_maju_recent_chats(self):
        import fanvue_agent
        import userbot

        for trieda in (fanvue_agent.FanvueAgent, userbot.UserBot):
            assert hasattr(trieda, "recent_chats"), trieda.__name__

    def test_tvar_je_rovnaky_pre_oba(self):
        """Control bot ich vypisuje tým istým kódom, takže sa tvar nesmie líšiť."""
        import inspect

        import fanvue_agent
        import userbot

        for trieda in (fanvue_agent.FanvueAgent, userbot.UserBot):
            zdroj = inspect.getsource(trieda.recent_chats)
            assert '"conv_key"' in zdroj and '"name"' in zdroj and '"hint"' in zdroj
