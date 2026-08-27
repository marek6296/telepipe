"""Kontext od majiteľa — „toto je Jason z Instagramu, už si píšeme".

PREČO. Marek si s niekým píše inde a dotiahne ho na Telegram. Modelka o tom
nevie nič, takže ho privíta ako úplne cudzieho — a pre človeka, ktorý si
„s ňou" týždeň písal, je to prvá vec, ktorá nesedí.

Poznámka sa píše ľubovoľným jazykom a ukladá po ANGLICKY: ide do promptu
medzi ostatné fakty a slovenčina v ňom ťahá k slovenčine celú odpoveď.
"""
from __future__ import annotations

import asyncio

import kontext


class FakeLlm:
    def __init__(self, out: str = "He is Jason from Instagram.") -> None:
        self.out = out
        self.system = ""
        self.content = ""

    async def structured(self, system, content, max_tokens=0, temperature=0.0):
        self.system, self.content = system, content
        return self.out


class TestUlozenieDoAnglictiny:
    def test_slovenska_poznamka_sa_prelozi(self):
        llm = FakeLlm()
        out = asyncio.run(
            kontext.do_anglictiny(llm, "toto je Jason z instagramu, píšeme si tam týždeň")
        )
        assert out == "He is Jason from Instagram."
        assert "Jason z instagramu" in llm.content, "model musí dostať pôvodné znenie"

    def test_zadanie_pyta_anglictinu_a_tretiu_osobu(self):
        llm = FakeLlm()
        asyncio.run(kontext.do_anglictiny(llm, "je to jason"))
        assert "ENGLISH" in llm.system
        assert "Third person" in llm.system
        assert "invent nothing" in llm.system

    def test_ked_preklad_zlyha_ostane_povodne(self):
        """Poznámka v slovenčine je stále lepšia než privítať známeho ako cudzieho."""

        class Zly(FakeLlm):
            async def structured(self, *a, **kw):
                raise RuntimeError("model spadol")

        out = asyncio.run(kontext.do_anglictiny(Zly(), "toto je Jason"))
        assert out == "toto je Jason"

    def test_prazdna_odpoved_modelu_nezahodi_vstup(self):
        out = asyncio.run(kontext.do_anglictiny(FakeLlm("   "), "toto je Jason"))
        assert out == "toto je Jason"

    def test_prazdny_vstup_model_ani_nevola(self):
        llm = FakeLlm()
        assert asyncio.run(kontext.do_anglictiny(llm, "   ")) == ""
        assert llm.content == "", "model sa nemal volať vôbec"

    def test_dlha_poznamka_sa_oreze(self):
        """Dlhšie už nie je kontext, ale scenár."""
        out = kontext.orez("a" * 900)
        assert len(out) == kontext.MAX_ZNAKOV

    def test_viacriadkova_poznamka_sa_zlozi(self):
        assert kontext.orez("prvy\n\n  druhy") == "prvy druhy"


class TestBlokDoPromptu:
    def test_prazdna_poznamka_nic_nepridava(self):
        assert kontext.blok("") == ""
        assert kontext.blok("   ") == ""

    def test_poznamka_je_v_bloku(self):
        out = kontext.blok("He is Jason from Instagram.")
        assert "He is Jason from Instagram." in out
        assert "UŽ POZNÁŠ" in out

    def test_zakazuje_pytat_sa_na_to_co_uz_vie(self):
        """Inak sa spýta „how did u find me" niekoho, s kým si píše týždeň."""
        assert "nepýtaj sa na to" in kontext.blok("He is Jason.")

    def test_zakazuje_vysypat_to_hned(self):
        """„Viem že si Jason z Instagramu a píšeme si týždeň" je horšie než nič."""
        out = kontext.blok("He is Jason.")
        assert "NEVYSYP" in out
        assert "nevymenúvaj" in out


class TestNapojenie:
    def test_poznamka_ide_do_promptu(self):
        from behavior import Behavior
        from persona import build_system_prompt

        def _p(note):
            return build_system_prompt(
                persona={"name": "S", "backstory": "x", "msg_style": "krátko"},
                user={"tg_id": 1, "msg_count": 1, "owner_note": note},
                allow_link=False, asked_if_ai=False, behavior=Behavior.from_row({}),
            )

        assert "He is Jason from Instagram." in _p("He is Jason from Instagram.")
        assert "UŽ POZNÁŠ" not in _p("")

    def test_upozornenie_ma_tlacidlo(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "userbot.py").read_text("utf-8")
        i = src.index("New conversation")
        assert "_kontext_button" in src[i : i + 400]

    def test_bot_klik_obsluhuje(self):
        import control_bot

        assert "nc" in {
            *__import__("re").findall(r'head == "([a-z]+)"',
                                      __import__("inspect").getsource(control_bot))
        }
