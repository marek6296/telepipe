"""Kým majiteľ nerozhodne, fanúšik píše ďalej — karta sa má dopĺňať.

PREDTÝM: každá nová správa nahradila kartu novou, ktorá ukazovala LEN tú
poslednú. Prvé dve zmizli aj s tým, na čo sa pýtal, a majiteľ odpovedal na
tretiu vetu bez kontextu predošlých dvoch.

TERAZ: karta ukazuje celý neodpovedaný blok (1, potom 1+2, potom 1+2+3) a
model dostane pokyn odpovedať na všetky naraz.
"""
from __future__ import annotations

import prehlad


def _h(*páry):
    return [{"role": r, "content": c} for r, c in páry]


class TestCoEsteNeodpovedala:
    def test_jedna_sprava(self):
        assert prehlad.neodpovedane(_h(("user", "hey"))) == ["hey"]

    def test_tri_za_sebou_v_poradi(self):
        h = _h(("user", "1"), ("user", "2"), ("user", "3"))
        assert prehlad.neodpovedane(h) == ["1", "2", "3"]

    def test_konci_pri_jej_poslednej_odpovedi(self):
        """Čokoľvek pred jej odpoveďou už zodpovedané bolo."""
        h = _h(("user", "stare"), ("assistant", "odpisala"), ("user", "nove"))
        assert prehlad.neodpovedane(h) == ["nove"]

    def test_ked_ma_posledne_slovo_ona(self):
        h = _h(("user", "hey"), ("assistant", "hi"))
        assert prehlad.neodpovedane(h) == []

    def test_prazdna_historia(self):
        assert prehlad.neodpovedane([]) == []
        assert prehlad.neodpovedane(None) == []

    def test_prazdne_spravy_sa_preskocia(self):
        h = _h(("user", "   "), ("user", "ozaj"))
        assert prehlad.neodpovedane(h) == ["ozaj"]


class TestBlokNaKartu:
    def test_kazda_na_vlastny_riadok(self):
        h = _h(("user", "prva"), ("user", "druha"))
        assert prehlad.blok_neodpovedanych(h) == "prva\ndruha"

    def test_viacriadkova_sprava_sa_zloži(self):
        """Inak by jedna správa rozbila počítanie riadkov na karte."""
        h = _h(("user", "prvy\nriadok"))
        assert prehlad.blok_neodpovedanych(h) == "prvy riadok"

    def test_vela_sprav_sa_oreze_a_povie_kolko(self):
        h = _h(*[("user", f"s{i}") for i in range(9)])
        out = prehlad.blok_neodpovedanych(h)
        assert out.startswith("(+4 earlier)")
        assert out.count("\n") == prehlad.MAX_NEODPOVEDANYCH
        assert "s8" in out, "posledná musí byť vidieť vždy"
        assert "s0" not in out

    def test_ked_neceka_nic(self):
        assert prehlad.blok_neodpovedanych(_h(("assistant", "hi"))) == ""


class TestPokynPreModel:
    def test_pri_jednej_sprave_ziadny(self):
        """Bez potreby nepridávame do promptu nič — je to len šum."""
        assert prehlad.pokyn_pre_model(_h(("user", "hey"))) == ""

    def test_pri_dvoch_uz_ano(self):
        out = prehlad.pokyn_pre_model(_h(("user", "1"), ("user", "2")))
        assert "ČAKÁ VIAC SPRÁV" in out
        assert "2 správy" in out

    def test_ziada_jednu_odpoved_na_vsetky(self):
        """Tri odpovede za sebou vyzerajú ako automat, nie ako človek."""
        out = prehlad.pokyn_pre_model(_h(("user", "1"), ("user", "2")))
        assert "AKO NA CELOK" in out
        assert "nie len na tú poslednú" in out

    def test_pocet_sedi_na_skutocnost(self):
        h = _h(("assistant", "hi"), ("user", "1"), ("user", "2"), ("user", "3"))
        assert "3 správy" in prehlad.pokyn_pre_model(h)


class TestObaKanalyToPouzivaju:
    def test_karta_dostane_cely_rozhovor(self):
        """Od 29. 8. karta ukazuje ROZHOVOR, nie len jeho neodpovedané správy —
        bez jej odpovedí sa Marek nemal na čo napojiť a musel si otvárať chat
        vedľa. Oba kanály to musia stavať rovnako, inak sa rozídu."""
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "src"
        for subor in ("userbot.py", "fanvue_agent.py"):
            text = (src / subor).read_text("utf-8")
            assert "blok_rozhovoru" in text, subor
            assert "pokyn_pre_model" in text, subor

    def test_karta_vypise_kazdu_na_vlastny_riadok(self):
        import control_bot

        lines = control_bot._card_lines(  # noqa: SLF001
            "fanvue", "fan", "prva\ndruha\ntretia", ["a"],
        )
        text = "\n".join(lines)
        assert "„prva“" in text and "„druha“" in text and "„tretia“" in text
