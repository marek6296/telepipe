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
        assert "*fan:* prva" in text and "*fan:* druha" in text
        assert "*fan:* tretia" in text


class TestKtoToPovedal:
    """Marek (29. 8., s fotkou karty): „vidim aj modelkyne spravy aj klientove
    ale vobec neviem ktora je moja a ktora jeho … (Jeho meno): sprava
    (Modelkyne meno): sprava".

    Úvodzovky a odsadená šípka boli príliš tiché. Meno pred vetou nie je.
    """

    def _card(self, preview, jeho="Fashionable Snipe", jej="Simona"):
        import control_bot

        return "\n".join(control_bot._card_lines(  # noqa: SLF001
            "fanvue", jeho, preview, ["a"], her_name=jej,
        ))

    def test_meno_pred_kazdou_vetou(self):
        text = self._card(f"hej\n{prehlad.JEJ}ahoj\nesteraz")
        assert "*Fashionable Snipe:* hej" in text
        assert "*Simona:* ahoj" in text
        assert "*Fashionable Snipe:* esteraz" in text

    def test_pocet_skrytych_nedostane_meno(self):
        """„(+6 earlier)" nie je ničia veta, je to poznámka o rozsahu."""
        text = self._card("(+6 earlier)\nhej")
        assert "_(+6 earlier)_" in text
        assert "Snipe:* (+6" not in text

    def test_dlhe_meno_sa_oreze(self):
        """Dvojslovné prezývky z Fanvue by inak zjedli pol riadku."""
        text = self._card("hej", jeho="Extraordinarily Fashionable Snipe")
        assert "*Extraordinarily F…:* hej" in text

    def test_podtrznik_v_mene_nerozbije_pismo(self):
        """Meno ide do `*…*`; osamotené `_` by Telethonu rozhodilo riadok."""
        text = self._card("hej", jeho="ailqk_1")
        assert "*ailqk 1:* hej" in text

    def test_bez_mena_modelky_ostane_zastupny_text(self):
        text = self._card(f"{prehlad.JEJ}ahoj", jej="")
        assert "*Her:* ahoj" in text


class TestBlokRozhovoru:
    """Karta ukazuje CHAT, nie zoznam jeho správ.

    Marek (29. 8., s fotkou karty): „vidim iba jeho spravy … proste 10
    poslednych sprav v chate dokopy jeho aj moje na fanvue aby som videl, a ak
    napise on zasebou 10 tak bude iba jeho spravy vidno."
    """

    def test_obe_strany_v_poradi(self):
        h = _h(("user", "1"), ("assistant", "a"), ("user", "2"))
        assert prehlad.blok_rozhovoru(h) == f"1\n{prehlad.JEJ}a\n2"

    def test_jej_riadky_su_oznacene(self):
        """Bez značky by sa po ceste cez `incoming_preview` stratilo, kto je kto."""
        h = _h(("assistant", "ahoj"))
        assert prehlad.blok_rozhovoru(h) == f"{prehlad.JEJ}ahoj"

    def test_desat_dokopy_nie_desat_jeho(self):
        """Šesť jeho a šesť jej = dvanásť. Na kartu patrí posledných desať."""
        h = _h(*[(("user" if i % 2 else "assistant"), f"s{i}") for i in range(12)])
        out = prehlad.blok_rozhovoru(h).splitlines()
        assert out[0] == "(+2 earlier)"
        assert len(out) == prehlad.SPOLU + 1
        assert out[-1].endswith("s11")
        assert not any(r.endswith("s1") for r in out), "prvé dve sa už nezmestili"

    def test_ked_napise_desat_za_sebou_su_tam_len_jeho(self):
        h = _h(("assistant", "stara"), *[("user", f"s{i}") for i in range(10)])
        out = prehlad.blok_rozhovoru(h).splitlines()
        assert out[0] == "(+1 earlier)"
        assert all(prehlad.JEJ not in r for r in out[1:])

    def test_prazdna_historia(self):
        assert prehlad.blok_rozhovoru([]) == ""
        assert prehlad.blok_rozhovoru(None) == ""

    def test_prazdne_spravy_sa_nepocitaju(self):
        h = _h(("user", "   "), ("user", "ozaj"))
        assert prehlad.blok_rozhovoru(h) == "ozaj"
