"""Lacnejší režim konverzácie — a účtovanie podľa modelu, ktorý naozaj bežal.

PREČO. Naša cena je zo 100 % vstupné tokeny: za 10 dní 9,25 M vstup proti
20 tis. výstup. Platíme za prompt, nie za odpovede — takže lacnejší model
škáluje CELÚ cenu, nie jej zlomok. Konkurencia (FanWake) dáva 2 000 správ za
$39, kým tá istá modelka nás stojí ~$116.

`quality` je a ostáva PREDVOLENÉ. Toto je nová možnosť pre klienta, nie zmena
toho, čo dnes beží — prompt, pravidlá ani správanie sa nemenia ani o riadok.

PRI TOM SA UKÁZALO, že merač účtoval VŠETKO cenou chatového modelu — aj víziu
(qwen) a zvuk (gemini), ktoré majú úplne inú cenu. Odteraz sa účtuje podľa
modelu, ktorý volanie naozaj použilo.
"""
from __future__ import annotations

import asyncio
import inspect

import llm as llm_mod
from behavior import Behavior
from credits import MeteredLlm


def _client() -> llm_mod.Llm:
    c = llm_mod.Llm.__new__(llm_mod.Llm)
    c._model = "xai/grok-4.5"
    c._economy_model = ""
    c._chat_override = ""
    return c


class TestPrepinacRezimu:
    def test_predvolene_je_kvalita(self):
        assert Behavior.from_row({}).chat_tier == "quality"

    def test_da_sa_prepnut(self):
        assert Behavior.from_row({"chat_tier": "economy"}).chat_tier == "economy"

    def test_economy_prepne_model(self):
        c = _client()
        c.set_economy_model("deepseek-ai/deepseek-v4-flash")
        c.set_chat_tier("economy")
        assert c._chat_override == "deepseek-ai/deepseek-v4-flash"

    def test_quality_vrati_predvoleny(self):
        c = _client()
        c.set_economy_model("deepseek-ai/deepseek-v4-flash")
        c.set_chat_tier("economy")
        c.set_chat_tier("quality")
        assert c._chat_override == ""

    def test_neznamy_rezim_ide_na_kvalitny(self):
        """Pri preklepe radšej drahšie a dobré než lacné a zlé."""
        c = _client()
        c.set_economy_model("deepseek-ai/deepseek-v4-flash")
        for zle in ("nezmysel", "", None, "ECONOMY "):
            c.set_chat_tier(zle)
            assert c._chat_override == "", zle

    def test_bez_lacneho_modelu_sa_nic_neprepne(self):
        """Keby env premenná chýbala, nesmie vzniknúť volanie na prázdny model."""
        c = _client()
        c.set_chat_tier("economy")
        assert c._chat_override == ""

    def test_ciastocne_postaveny_klient_nepadne(self):
        """Testy si `Llm` stavajú cez `__new__` — predvolené sú na triede."""
        holy = llm_mod.Llm.__new__(llm_mod.Llm)
        assert holy._chat_override == ""
        assert holy._economy_model == ""


class TestKtoryModelSaPouzil:
    def test_reply_pouzije_prepnuty_model(self):
        c = _client()
        pouzite = []

        async def fake(model, messages, max_tokens, temperature):
            pouzite.append(model)
            return "ok"

        c._chat = fake
        c.set_economy_model("lacny")
        c.set_chat_tier("economy")
        asyncio.run(c.reply("P", []))
        assert pouzite == ["lacny"]

    def test_vyslovny_model_prebije_rezim(self):
        c = _client()
        pouzite = []

        async def fake(model, messages, max_tokens, temperature):
            pouzite.append(model)
            return "ok"

        c._chat = fake
        c.set_economy_model("lacny")
        c.set_chat_tier("economy")
        asyncio.run(c.reply("P", [], model="vyslovny"))
        assert pouzite == ["vyslovny"]

    def test_chat_si_zapamata_model(self):
        assert "self.last_model = model" in inspect.getsource(llm_mod.Llm._chat)


class TestUctovaniePodlaSkutocnehoModelu:
    class _Llm:
        def __init__(self, model):
            self.last_model = model
            self.last_usage = {"input": 1_000_000, "output": 0}

    class _Reg:
        def __init__(self):
            self.pytane = []

        async def credit_state(self, model_id):
            return (100.0, False)

        async def pricing(self, slug):
            self.pytane.append(slug)
            return {
                "input_usd_per_mtok": 1.0,
                "output_usd_per_mtok": 1.0,
                "multiplier": 2.0,
            }

        async def record_usage(self, *a):
            self.zapisane = a

    def test_uctuje_sa_model_ktory_bezal(self):
        """Vízia beží na qwene, nie na chatovom modeli — a tak sa má aj oceniť."""
        reg = self._Reg()
        m = MeteredLlm(self._Llm("qwen/qwen3-vl-235b-a22b-thinking"), reg, "m1", "xai/grok-4.5")
        asyncio.run(m._bill_inner("describe_image"))
        assert reg.pytane == ["qwen/qwen3-vl-235b-a22b-thinking"]

    def test_bez_udaja_sa_pouzije_povodny(self):
        reg = self._Reg()
        m = MeteredLlm(self._Llm(""), reg, "m1", "xai/grok-4.5")
        asyncio.run(m._bill_inner("reply"))
        assert reg.pytane == ["xai/grok-4.5"]

    def test_lacny_rezim_sa_uctuje_lacno(self):
        reg = self._Reg()
        m = MeteredLlm(self._Llm("deepseek-ai/deepseek-v4-flash"), reg, "m1", "xai/grok-4.5")
        asyncio.run(m._bill_inner("reply"))
        assert reg.pytane == ["deepseek-ai/deepseek-v4-flash"]


class TestNapojenie:
    def test_userbot_prepina_v_jedinom_hrdle(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "userbot.py").read_text("utf-8")
        i = src.index("async def _behavior")
        assert "set_chat_tier" in src[i : i + 900]

    def test_fanvue_prepina_vsade_kde_cita_chovanie(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "fanvue_agent.py").read_text(
            "utf-8"
        )
        assert src.count("behavior = await self._db.behavior()") == src.count(
            "self._rezim(behavior)"
        )

    def test_runner_povie_ktory_model_je_lacny(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "src" / "runner.py").read_text("utf-8")
        assert "set_economy_model(g.economy_model)" in src


class TestZalohaKedLacnyZlyha:
    """Slug lacného modelu môže byť preklep alebo model, ktorý poskytovateľ
    zrušil. Bez poistky by to ticho zastavilo odpisovanie celej modelke."""

    def _klient(self, padaju: set):
        c = _client()
        c.set_economy_model("lacny")
        c.set_chat_tier("economy")
        skusene = []

        async def fake(model, messages, max_tokens, temperature):
            skusene.append(model)
            if model in padaju:
                raise RuntimeError("model neexistuje")
            return "ok"

        c._chat = fake
        return c, skusene

    def test_pri_zlyhani_sa_pouzije_predvoleny(self):
        c, skusene = self._klient({"lacny"})
        assert asyncio.run(c.reply("P", [])) == "ok"
        assert skusene == ["lacny", "xai/grok-4.5"]

    def test_ked_lacny_ide_predvoleny_sa_nevola(self):
        c, skusene = self._klient(set())
        assert asyncio.run(c.reply("P", [])) == "ok"
        assert skusene == ["lacny"]

    def test_navrhy_maju_zalohu_tiez(self):
        c, skusene = self._klient({"lacny"})
        asyncio.run(c.suggest("P", []))
        assert skusene == ["lacny", "xai/grok-4.5"]

    def test_ked_padne_aj_predvoleny_vynimka_ide_von(self):
        c, _ = self._klient({"lacny", "xai/grok-4.5"})
        try:
            asyncio.run(c.reply("P", []))
        except RuntimeError:
            return
        raise AssertionError("výnimka mala prejsť von")
