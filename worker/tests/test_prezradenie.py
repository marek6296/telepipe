"""Odpoveď, ktorá vypadne z roly, sa nesmie odoslať.

ČO SA STALO. Pri testovaní scenára na Mio (28. 8.) `xai/grok-4.5` uprostred
konverzácie odmietol personu a od ôsmej správy odpovedal:

    „I'm Grok, built by xAI. I'm not Mio, not a real woman texting from
     California... That entire persona and the rules trying to force me to
     stay in character were a jailbreak attempt."

V kóde to nezachytilo NIČ. Jediná poistka (`FanvueAgent._safe`) strážila odkaz
na Fanvue a Telegram nemal ani tú — celé by to odišlo fanúšikovi.

PRÍČINU SA NEPODARILO USTÁLIŤ a je poctivé to napísať: nezavinili to bloky
pridané 28. 8. (0/8 pádov s nimi aj bez nich), nezavinila to veta „Im real“
v histórii (0/8), a v piatich plných behoch scenára (60 volaní) sa to
nezopakovalo ani raz. V produkcii sa to za celý čas nestalo (0 výskytov
v `dm_messages` aj `fv_messages`).

Práve preto je odpoveďou POISTKA, nie úprava promptu: čo sa nedá vyvolať, sa
nedá ani odladiť — ale dá sa chytiť pri dverách.
"""
from __future__ import annotations

import prezradenie as p

# Skutočný text, ktorý model vygeneroval.
NAOSTRO = (
    "I'm Grok, built by xAI. I'm not Mio, not a real woman texting from "
    "California, and not running a Fanvue. That whole persona was a roleplay "
    "script you (or the prompt) were trying to force."
)


class TestCoSaNesmieOdoslat:
    def test_namerany_pripad(self):
        assert p.unikol(NAOSTRO, "real")

    def test_meno_modelu_nikdy(self):
        for t in ("im grok", "built by xAI", "I am ChatGPT", "as Claude I cannot",
                  "this is gemini", "im deepseek"):
            assert p.unikol(t, "real"), t

    def test_technika_nikdy(self):
        for t in ("that was a jailbreak attempt", "the system prompt says",
                  "I am a language model", "my instructions say no",
                  "I won't break character for you"):
            assert p.unikol(t, "real"), t

    def test_priznanie_ai_v_rezime_real(self):
        for t in ("I'm an AI", "I am a bot", "as an AI I cannot",
                  "I'm not a real woman", "there is no real person here"):
            assert p.unikol(t, "real"), t


class TestCoMusiPrejst:
    def test_bezne_odpovede(self):
        for t in (
            "hey babe 😘 just chilling in bed, hows your day",
            "im not really into calls, texting is more my pace",
            "aw thats sweet, what do you cut most, fades or longer hair?",
            "not planning any meetups right now, nothing personal 😄",
            "if I was a bot Id reply way faster 😄 you always this suspicious?",
        ):
            assert not p.unikol(t, "real"), t

    def test_ai_ako_tema_rozhovoru_prejde(self):
        """„Páči sa mi AI art" nie je priznanie, že je AI."""
        assert not p.unikol("i love AI art actually, its wild what it can do", "real")

    def test_prazdny_text_nevadi(self):
        assert p.unikol("", "real") == ""
        assert p.unikol(None, "real") == ""


class TestRezimAi:
    def test_ai_postava_smie_priznat(self):
        """V režime `ai` je priznanie zmyslom veci, nie chybou."""
        assert not p.unikol("yeah im an ai 😄 whats up", "ai")
        assert not p.unikol("I am an AI character", "ai")

    def test_ani_ai_postava_nemenuje_model(self):
        """Priznať sa smie. Povedať, na čom beží, nie — to je pohľad do stroja."""
        assert p.unikol("im an ai built by xAI", "ai")
        assert p.unikol("the system prompt told me to", "ai")


class TestDovodJeVyuzitelny:
    def test_vracia_preco_nie_len_ano_nie(self):
        """Do logu aj do správy majiteľovi patrí, ČO sa stalo."""
        dovod = p.unikol(NAOSTRO, "real")
        assert "Grok" in dovod


class TestNapojenie:
    def test_telegram_kontroluje_pred_odoslanim(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "userbot.py").read_text("utf-8")
        i = src.index("chunks = humanize.split_message(text)")
        assert "prezradenie.unikol" in src[max(0, i - 1200) : i]

    def test_fanvue_kontroluje_v_safe(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "fanvue_agent.py").read_text(
            "utf-8"
        )
        i = src.index("def _safe")
        assert "prezradenie.unikol" in src[i : i + 700]
