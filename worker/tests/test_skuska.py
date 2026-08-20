"""Skúšobný chat — modelka odpovie majiteľovi, bez dotyku so skutočnými chatmi."""
import asyncio

import behavior as bhv
import skuska


PERSONA = {
    "name": "Lucia",
    "age": 23,
    "city": "Bratislava",
    "backstory": "Studuje dizajn.",
    "tone": "hrava",
    "msg_style": "kratke spravy",
    "boundaries": "",
    "funnel_rules": "",
    "cta_link": "https://fanvue.com/lucia",
    "extra_rules": "",
    "examples": "",
}


class FakeLlm:
    def __init__(self, odpoved="hey you 😄 whats up"):
        self.odpoved = odpoved
        self.prompty = []
        self.historie = []

    async def reply(self, system, history):
        self.prompty.append(system)
        self.historie.append(list(history))
        return self.odpoved


def _behavior():
    return bhv.Behavior.from_row({})


def _odpoved(s, llm, text="hey", chat=1):
    return asyncio.run(s.odpoved(chat, text, PERSONA, _behavior(), llm))


class TestBeh:
    def test_odpovie(self):
        s = skuska.Skuska()
        s.zapni(1)
        assert _odpoved(s, FakeLlm()), "musí prísť aspoň jedna bublina"

    def test_pamata_si_v_ramci_skusky(self):
        s = skuska.Skuska()
        s.zapni(1)
        llm = FakeLlm()
        _odpoved(s, llm, "hey")
        _odpoved(s, llm, "what are u doing")
        posledna = llm.historie[-1]
        assert [m["role"] for m in posledna] == ["user", "assistant", "user"]
        assert posledna[0]["content"] == "hey"

    def test_dva_majitelia_sa_nemiesaju(self):
        s = skuska.Skuska()
        s.zapni(1)
        s.zapni(2)
        llm = FakeLlm()
        _odpoved(s, llm, "prvy", chat=1)
        _odpoved(s, llm, "druhy", chat=2)
        assert len(s.historia(1)) == 2 and len(s.historia(2)) == 2
        assert s.historia(2)[0]["content"] == "druhy"

    def test_reset_zacne_odznova(self):
        s = skuska.Skuska()
        s.zapni(1)
        _odpoved(s, FakeLlm())
        s.vycisti(1)
        assert s.historia(1) == []
        assert s.bezi(1), "reset skúšku neukončuje"

    def test_vypnutie_zmaze_vsetko(self):
        s = skuska.Skuska()
        s.zapni(1)
        _odpoved(s, FakeLlm())
        s.vypni(1)
        assert not s.bezi(1) and s.historia(1) == []


class TestNepokaziOstruPrevadzku:
    def test_odkaz_sa_v_skuske_neposiela(self):
        """Nie je komu — a klient by posudzoval vetu, ktorá naživo príde inak."""
        s = skuska.Skuska()
        s.zapni(1)
        llm = FakeLlm("pozri sa na https://fanvue.com/lucia babe")
        kusy = _odpoved(s, llm)
        assert "fanvue.com" not in " ".join(kusy)

    def test_prompt_nedovoli_odkaz(self):
        s = skuska.Skuska()
        s.zapni(1)
        llm = FakeLlm()
        _odpoved(s, llm)
        assert "ODKAZ JE TERAZ ZAKÁZANÝ" in llm.prompty[-1]

    def test_pouziva_skutocnu_personu(self):
        s = skuska.Skuska()
        s.zapni(1)
        llm = FakeLlm()
        _odpoved(s, llm)
        assert "Lucia" in llm.prompty[-1]

    def test_pamat_je_ohranicena(self):
        """Skúška beží v procese — nesmie rásť donekonečna."""
        s = skuska.Skuska()
        s.zapni(1)
        llm = FakeLlm()
        for i in range(30):
            _odpoved(s, llm, f"sprava {i}")
        assert len(s.historia(1)) <= skuska.PAMAT

    def test_prazdna_odpoved_nezhodi_skusku(self):
        s = skuska.Skuska()
        s.zapni(1)
        assert _odpoved(s, FakeLlm("")) == []
        assert s.bezi(1)


class TestPremazanie:
    """Klient zmenil personu → skúška musí ísť začať odznova.

    Toto nie je kozmetika. Kým v histórii visia staré odpovede, model sa nimi
    riadi — klient zmení tón, ona odpisuje po starom a vyzerá to, že zmena
    nezabrala.
    """

    def test_po_premazani_model_stare_odpovede_nevidi(self):
        s = skuska.Skuska()
        s.zapni(1)
        llm = FakeLlm("stara odpoved v starom style")
        _odpoved(s, llm, "hey")
        _odpoved(s, llm, "a co teraz")
        s.vycisti(1)
        _odpoved(s, llm, "znova hey")
        posledna = llm.historie[-1]
        assert len(posledna) == 1, "po premazaní ide modelu len nová správa"
        assert posledna[0]["content"] == "znova hey"

    def test_premazanie_nevypne_skusku(self):
        s = skuska.Skuska()
        s.zapni(1)
        _odpoved(s, FakeLlm())
        s.vycisti(1)
        assert s.bezi(1)

    def test_premazanie_nezapne_skusku_ktora_nebezi(self):
        s = skuska.Skuska()
        s.vycisti(1)
        assert not s.bezi(1)

    def test_premazanie_sa_tyka_len_mojho_chatu(self):
        s = skuska.Skuska()
        s.zapni(1)
        s.zapni(2)
        llm = FakeLlm()
        _odpoved(s, llm, "moje", chat=1)
        _odpoved(s, llm, "cudzie", chat=2)
        s.vycisti(1)
        assert s.historia(1) == []
        assert len(s.historia(2)) == 2, "cudziu skúšku sa to nesmie dotknúť"

    def test_po_premazani_pokracuje_ako_rozbehnuta_konverzacia(self):
        """Nesmie spadnúť na prvú opatrnú vetu — skúša sa bežný chat."""
        s = skuska.Skuska()
        s.zapni(1)
        llm = FakeLlm()
        _odpoved(s, llm)
        s.vycisti(1)
        _odpoved(s, llm)
        assert "PRVÉ DVE SPRÁVY" not in llm.prompty[-1]
