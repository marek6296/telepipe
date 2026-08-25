"""Message generator — napíšeš, čo má odznieť, a dostaneš jej vetu na skopírovanie.

Je to samostatná dielňa v menu bota, nie odpoveď v chate: majiteľ si vyrobí
uvítaciu správu alebo vetu, ktorú pošle sám, a skopíruje ju. Zadanie píše po
slovensky, výstup musí byť v jazyku a štýle modelky.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import generator
from behavior import Behavior

PERSONA = {
    "name": "Simona",
    "backstory": "23, býva v LA",
    "msg_style": "krátke správy, malé písmená",
    "tone": "hravý",
    "language": "English",
    "cta_link": "https://www.fanvue.com/sima.sima",
    "boundaries": "žiadne stretnutia",
}
BEHAVIOR = Behavior.from_row({})


class FakeLlm:
    """Zachytí prompt a vráti tri verzie."""

    def __init__(self, odpoved: List[str] | None = None) -> None:
        self.system = ""
        self.angles: List[str] = []
        self.seed = ""
        self.n = 0
        self._odpoved = odpoved if odpoved is not None else ["jedna", "dva", "tri"]

    async def suggest(self, system, history, n=3, angles=None, seed=""):
        self.system = system
        self.angles = angles or []
        self.seed = seed
        self.n = n
        return list(self._odpoved)


def _napis(brief="napis spravu ze jooj konecne si ma nasiel", pokus=1, llm=None):
    llm = llm or FakeLlm()
    out = asyncio.run(generator.napis(llm, PERSONA, BEHAVIOR, brief, pokus))
    return out, llm


class TestZadanie:
    def test_vrati_tri_verzie(self):
        out, _ = _napis()
        assert out == ["jedna", "dva", "tri"]

    def test_zadanie_ide_do_promptu(self):
        _, llm = _napis("napis spravu ze jooj konecne si ma nasiel")
        assert "jooj konecne si ma nasiel" in llm.system

    def test_prazdne_zadanie_nevolá_model(self):
        llm = FakeLlm()
        assert asyncio.run(generator.napis(llm, PERSONA, BEHAVIOR, "   ")) == []
        assert llm.system == "", "model sa nemal volať vôbec"

    def test_dlhe_zadanie_sa_skrati(self):
        _, llm = _napis("a" * 900)
        assert "a" * generator.MAX_ZADANIE in llm.system
        assert "a" * (generator.MAX_ZADANIE + 1) not in llm.system

    def test_uhly_menia_len_podanie_nie_temu(self):
        _, llm = _napis()
        assert llm.angles == generator.UHLY
        assert all("povedz to" in u for u in llm.angles)


class TestJejHlas:
    """Vygenerovaná veta musí byť na nerozoznanie od tej, čo píše modelka."""

    def test_prompt_stoji_na_persone(self):
        _, llm = _napis()
        assert "Simona" in llm.system
        assert "krátke správy, malé písmená" in llm.system

    def test_plati_jej_jazyk(self):
        """Zadanie je po slovensky, správa musí byť v jej jazyku."""
        _, llm = _napis()
        assert "JAZYK ODPOVEDÍ" in llm.system
        assert "v inom jazyku" in llm.system, "chýba pravidlo o jazyku zadania"

    def test_platia_jej_hranice(self):
        _, llm = _napis()
        assert "žiadne stretnutia" in llm.system

    def test_zadanie_sa_neprepisuje_doslova(self):
        _, llm = _napis()
        assert "NIE text na odoslanie" in llm.system

    def test_nesluby_fotku_ktoru_nema_kto_poslat(self):
        """Z generátora neodchádza žiadne médium — sľub by nemal kto splniť."""
        _, llm = _napis()
        assert "FOTKY NEPOSIELAŠ VÔBEC" in llm.system

    def test_negeneruje_odkaz(self):
        """Majiteľ chce vetu na skopírovanie, nie pozvánku, ktorú potom pošle
        aj tam, kde nemá čo robiť."""
        _, llm = _napis()
        assert "https://www.fanvue.com/sima.sima" not in llm.system


class TestSamostatnaSprava:
    """Generátor nemá chat, takže nie je na čo nadväzovať."""

    def test_zakazuje_nadvazovanie_na_nic(self):
        _, llm = _napis()
        assert "SAMOSTATNÁ SPRÁVA" in llm.system
        assert "aww thats sweet" in llm.system

    def test_fanusik_nie_je_uplne_novy(self):
        """Pri nule by platili pravidlá prvej správy a generátor by odmietal
        napísať čokoľvek smelšie."""
        assert generator.fanusik()["msg_count"] >= 4


class TestPregenerovanie:
    def test_prvy_pokus_je_bez_seedu(self):
        _, llm = _napis(pokus=1)
        assert llm.seed == ""

    def test_dalsi_pokus_ziada_ine_vety(self):
        """Bez toho by model vrátil to isté a tlačidlo by vyzeralo pokazené."""
        _, llm = _napis(pokus=3)
        assert llm.seed == "3"

    def test_prazdne_odpovede_sa_zahodia(self):
        out, _ = _napis(llm=FakeLlm(["", "  ", "toto ostane"]))
        assert out == ["toto ostane"]


class TestNapojenieVBote:
    def test_tlacidlo_je_v_menu(self):
        import re
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")
        assert 'Button.inline("✍️ Message generator", b"mg")' in src
        assert 'b"mgr"' in src, "chýba Regenerate"

    def test_vety_sa_daju_skopirovat_tuknutim(self):
        """V Telegrame sa `code` blok kopíruje jedným ťuknutím — a skopírovať
        a poslať je celý zmysel tohto tlačidla."""
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "control_bot.py").read_text("utf-8")
        assert "Tap a message to copy it" in src
