"""Kým píše zadanie, môže prísť nová správa — jeho text sa nesmie zahodiť.

NAOSTRO (27. 8., Fanvue chat 9b202cc7). Marek klikol „Say this", začal
písať zadanie, a o minútu prišla fanúšikova ďalšia správa. Nová karta tú
starú prebila (`supersede_open` → `cancel_card` → `_forget_card`), takže keď
text odoslal, `_cards` už staré `mid` nepoznalo a odpoveď znela „That card is
gone". Zadanie sa stratilo a nevygenerovalo sa nič.

Pritom išlo o TOHO ISTÉHO človeka a v jeho chate práve čakala nová karta.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import control_bot as cb


class FakeDb:
    """Stará karta je preč, nová na ten istý chat čaká."""

    def __init__(self, fresh: Optional[Dict[str, Any]]) -> None:
        self.fresh = fresh
        self.ziadane: List[str] = []

    async def get_pending(self, pid):
        return None                      # starú už nikto nenájde

    async def get_pending_for(self, conv_key):
        self.ziadane.append(conv_key)
        return self.fresh


class FakeEvent:
    def __init__(self) -> None:
        self.chat_id = 1
        self.odpovede: List[str] = []

    async def reply(self, text="", **kw):
        self.odpovede.append(text)


def _bot(fresh):
    bot = cb.ControlBot.__new__(cb.ControlBot)
    bot._db = FakeDb(fresh)
    bot._cards = {}
    bot._wizard = {}
    bot._chat_ctx = {10: {"channel": "fanvue", "conv_key": "9b202cc7", "name": "fan"}}
    bot._awaiting = {}

    class FakeSender:
        async def regenerate(self, conv_key, seed="", brief=""):
            return {"suggestions": ["a"]}

        async def deliver_text(self, conv_key, text):
            return True

    bot._senders = {"fanvue": FakeSender()}
    bot.volane: List[tuple] = []

    async def fake_new(mid, pid, row, brief="", nova_sprava=False):
        bot.volane.append((mid, pid, row.get("conv_key"), brief, nova_sprava))
        return ""

    bot._new_suggestions = fake_new
    return bot


NOVA_KARTA = {
    "id": "pid-2",
    "conv_key": "9b202cc7",
    "channel": "fanvue",
    "status": "awaiting",
    "control_msg_id": 20,
    "prompt": "PERSONA",
    "hint": "",
    "incoming_preview": "hey",
}


class TestZadanieSaNestrati:
    def test_prebita_karta_presmeruje_na_aktualnu(self):
        bot = _bot(NOVA_KARTA)
        event = FakeEvent()
        asyncio.run(bot._apply_semi(event, "semi_brief", "10", "podakuj mu"))
        assert bot.volane, "zadanie sa vôbec nespracovalo"
        mid, pid, conv, brief, nova = bot.volane[0]
        assert nova is True, "napísané zadanie musí ukázať výsledok dole"
        assert pid == "pid-2", "malo sa použiť aktuálne čakajúce"
        assert mid == 20, "karta na prepísanie je tá nová"
        assert conv == "9b202cc7" and brief == "podakuj mu"

    def test_hlada_podla_toho_isteho_cloveka(self):
        bot = _bot(NOVA_KARTA)
        asyncio.run(bot._apply_semi(FakeEvent(), "semi_brief", "10", "x"))
        assert bot._db.ziadane == ["9b202cc7"]

    def test_nova_karta_sa_zapamata(self):
        """Ďalší klik na ňu musí fungovať bez ďalšieho hľadania."""
        bot = _bot(NOVA_KARTA)
        asyncio.run(bot._apply_semi(FakeEvent(), "semi_brief", "10", "x"))
        assert bot._cards[20] == "pid-2"

    def test_ked_uz_nic_neceka_povie_to(self):
        """Bez čakajúcej karty sa zadanie naozaj nemá kam poslať."""
        bot = _bot(None)
        event = FakeEvent()
        asyncio.run(bot._apply_semi(event, "semi_brief", "10", "x"))
        assert not bot.volane
        assert any("Message generator" in t for t in event.odpovede)

    def test_bez_kontextu_chatu_sa_nehlada(self):
        """Nepoznáme chat — nie je koho hľadať a nesmie sa hádať."""
        bot = _bot(NOVA_KARTA)
        bot._chat_ctx = {}
        event = FakeEvent()
        asyncio.run(bot._apply_semi(event, "semi_brief", "10", "x"))
        assert bot._db.ziadane == []
        assert any("no longer current" in t for t in event.odpovede)


class TestNavrhySaUctuju:
    """`suggest` chvíľu chýbalo v meranom obale — tokeny sa míňali, klientovi
    sa neúčtovali."""

    def test_suggest_je_medzi_meranymi(self):
        import inspect

        import credits

        zdroj = inspect.getsource(credits.MeteredLlm)
        assert 'self._metered("suggest"' in zdroj

    def test_kazda_llm_metoda_je_meraná(self):
        """Poistka do budúcna: čo Llm vie, musí obal merať."""
        import credits
        import llm as llm_mod

        # Metódy, ktoré naozaj míňajú tokeny.
        platene = {"reply", "suggest", "structured", "summarize",
                   "describe_image", "transcribe_voice"}
        ma_llm = {m for m in dir(llm_mod.Llm) if not m.startswith("_")}
        chyba = platene - ma_llm
        assert not chyba, f"Llm už nemá: {sorted(chyba)}"
        neobalene = {m for m in platene if m not in vars(credits.MeteredLlm)}
        assert not neobalene, f"neúčtuje sa: {sorted(neobalene)}"
