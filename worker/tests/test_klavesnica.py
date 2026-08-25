"""Trvalá klávesnica nad vstupom — a to, čo pri nej môže ticho vybuchnúť.

Inline tlačidlá žijú na správe: keď sa správa stratí v histórii, stratí sa
s ňou aj ovládanie. Klávesnica sedí nad vstupom stále.

NAJDÔLEŽITEJŠIA VEC V CELOM SÚBORE: ťuknutie na ňu pošle OBYČAJNÝ TEXT.
Bot ho musí rozpoznať skôr, než ho spracuje čokoľvek iné — inak sa
„👤 Persona" uloží ako nová persona alebo odíde modelke do skúšobného chatu
a človek netuší, prečo tlačidlo nefunguje.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, List

import control_bot as cb

SRC = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")


class FakeEvent:
    def __init__(self, text: str, chat_id: int = 1) -> None:
        self.raw_text = text
        self.chat_id = chat_id
        self.id = 42
        self.odpovede: List[str] = []

    async def respond(self, text="", **kw):
        self.odpovede.append(text)

    async def reply(self, text="", **kw):
        self.odpovede.append(text)


class FakeSkuska:
    def __init__(self) -> None:
        self.bezi_kde = set()
        self.vypnute: List[int] = []

    def bezi(self, chat_id): return chat_id in self.bezi_kde
    def vypni(self, chat_id): self.vypnute.append(chat_id); self.bezi_kde.discard(chat_id)


def _bot():
    bot = cb.ControlBot.__new__(cb.ControlBot)
    bot._awaiting = {}
    bot._skuska = FakeSkuska()
    bot.routed: List[str] = []

    async def fake_route(event, data):
        bot.routed.append(data)

    bot._route = fake_route
    return bot


class TestKlikNaKlavesnicu:
    def test_kazde_tlacidlo_ma_akciu(self):
        """Popisok bez akcie je tlačidlo, ktoré nič nerobí."""
        popisky = {text for riadok in cb.KLAVESNICA for text in riadok}
        assert popisky == set(cb.KLAVESNICA_AKCIE)

    def test_akcie_vedu_na_existujuce_obrazovky(self):
        """Klávesnica nemá vlastnú logiku — stláča to, čo už existuje."""
        obsluhovane = set(re.findall(r'head == "([a-z]+)"', SRC))
        for akcia in cb.KLAVESNICA_AKCIE.values():
            assert akcia in obsluhovane, akcia

    def test_klik_otvori_obrazovku(self):
        bot = _bot()
        event = FakeEvent("👤 Persona")
        assert asyncio.run(bot._klavesnica_klik(event)) is True
        assert bot.routed == ["pm"]

    def test_bezny_text_klavesnica_neberie(self):
        bot = _bot()
        assert asyncio.run(bot._klavesnica_klik(FakeEvent("ahoj ako sa mas"))) is False
        assert bot.routed == []

    def test_rozpisana_hodnota_sa_zahodi(self):
        """Uložiť „🎭 Behaviour" ako hodnotu poľa by bolo horšie než ju stratiť."""
        bot = _bot()
        bot._awaiting[1] = ("persona", "backstory")
        asyncio.run(bot._klavesnica_klik(FakeEvent("🎭 Behaviour")))
        assert 1 not in bot._awaiting

    def test_menu_je_cesta_von_zo_skusky(self):
        """Inak by ďalšia správa išla modelke namiesto nastavení."""
        bot = _bot()
        bot._skuska.bezi_kde.add(1)
        asyncio.run(bot._klavesnica_klik(FakeEvent("⌂ Menu")))
        assert bot._skuska.vypnute == [1]

    def test_iné_tlacidlo_skusku_nezhasina(self):
        """Pozrieť si štatistiky počas skúšky ju nemá ukončiť."""
        bot = _bot()
        bot._skuska.bezi_kde.add(1)
        asyncio.run(bot._klavesnica_klik(FakeEvent("📊 Stats")))
        assert bot._skuska.vypnute == []

    def test_zlyhanie_obrazovky_nezhodi_bota(self):
        bot = _bot()

        async def zle(event, data):
            raise RuntimeError("rozbité")

        bot._route = zle
        event = FakeEvent("📊 Stats")
        assert asyncio.run(bot._klavesnica_klik(event)) is True
        assert any("⚠️" in t for t in event.odpovede)


class TestPoradieSpracovania:
    """Klávesnica musí ísť PRED nastavením aj pred skúškou."""

    def test_klavesnica_je_prva_v_on_value(self):
        telo = SRC[SRC.index("async def _on_value"):]
        telo = telo[: telo.index("async def ", 40)]
        klavesnica = telo.index("_klavesnica_klik")
        skuska = telo.index("self._skuska.bezi")
        awaiting = telo.index("self._awaiting[chat_id]")
        assert klavesnica < skuska, "skúšobný chat by zjedol ťuknutie"
        assert klavesnica < awaiting, "rozpísaná hodnota by zjedla ťuknutie"

    def test_parovanie_ostava_uplne_prve(self):
        """Neznámy chat sa musí vedieť ohlásiť aj bez klávesnice."""
        telo = SRC[SRC.index("async def _on_value"):]
        assert telo.index("_try_pair") < telo.index("_klavesnica_klik")


class TestPrezlekZaKlik:
    """Obrazovky sú písané pre callback udalosť; ťuknutie ju nemá."""

    def test_edit_posle_novu_spravu(self):
        event = FakeEvent("x")
        klik = cb._KlavesovyKlik(event)
        asyncio.run(klik.edit("nová obrazovka"))
        assert event.odpovede == ["nová obrazovka"]

    def test_answer_je_ticho(self):
        event = FakeEvent("x")
        asyncio.run(cb._KlavesovyKlik(event).answer("čokoľvek"))
        assert event.odpovede == []

    def test_nesie_chat_a_spravu(self):
        klik = cb._KlavesovyKlik(FakeEvent("x", chat_id=77))
        assert klik.chat_id == 77 and klik.message_id == 42


class TestTvarKlavesnice:
    def test_je_v_dvojiciach(self):
        """Telegram robí tlačidlá v riadku rovnako široké — nepárny riadok
        vyzerá ako zvyšok."""
        for riadok in cb.KLAVESNICA:
            assert len(riadok) == 2, riadok

    def test_vstup_ma_vlastny_popis(self):
        """Bez neho je vo vstupe „Write a message" a vyzerá to, akoby sa
        čakalo na text."""
        assert cb.VSTUP_PLACEHOLDER

    def test_klavesnica_sa_neposiela_s_kazdym_menu(self):
        """Telegram ju musí niesť správa — inak by pri každom /menu pribudla
        druhá správa navyše."""
        assert 'if command == "/start":' in SRC
