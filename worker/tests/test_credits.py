"""Kreditový wrapper — check pred volaním, zápis po ňom, pauza pri nule."""
import logging

import pytest
import credits
from credits import MeteredLlm, OutOfCredits

class FakeLlm:
    def __init__(self):
        self.last_usage = {"input": 1000, "output": 500}
        self.calls = 0
    async def reply(self, *a, **kw):
        self.calls += 1
        return "ahoj"

class FakeRegistry:
    def __init__(self, balance=10.0, unlimited=False):
        self._balance = balance
        self._unlimited = unlimited
        self.usage_rows = []
        self.status_calls = []
    async def credit_balance(self, model_id): return self._balance
    async def credit_state(self, model_id): return self._balance, self._unlimited
    async def pricing(self, slug):
        return {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0, "multiplier": 2.0}
    async def record_usage(self, model_id, kind, i, o, u, atlas, charged):
        self.usage_rows.append((kind, i, o, atlas, charged))
        self._balance -= charged
        return self._balance
    async def set_status(self, model_id, status, reason=""):
        self.status_calls.append((status, reason))

async def test_charges_double_atlas_cost():
    reg = FakeRegistry(); llm = FakeLlm()
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="x-ai/grok-4.5")
    await m.reply("sys", [])
    kind, i, o, atlas, charged = reg.usage_rows[0]
    # 1000/1e6*3.0 + 500/1e6*15.0 = 0.003 + 0.0075 = 0.0105
    assert atlas == pytest.approx(0.0105)
    assert charged == pytest.approx(0.021)     # ×2
    assert kind == "chat" and i == 1000 and o == 500

async def test_zero_balance_blocks_and_pauses():
    reg = FakeRegistry(balance=0.0); llm = FakeLlm()
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s")
    with pytest.raises(OutOfCredits):
        await m.reply("sys", [])
    assert llm.calls == 0                       # LLM sa vôbec nezavolalo
    assert reg.status_calls == [("paused", "out_of_credits")]

async def test_zero_balance_notifies_owner_once():
    """Majiteľ dostane správu o vyčerpaných kreditoch raz, nie pri každej správe."""
    reg = FakeRegistry(balance=0.0); llm = FakeLlm()
    sent = []
    async def notify(text): sent.append(text)
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s", notify=notify)
    for _ in range(2):
        with pytest.raises(OutOfCredits):
            await m.reply("sys", [])
    assert len(sent) == 1                       # žiadny spam do control bota
    assert reg.status_calls == [("paused", "out_of_credits")]   # ani do DB


async def test_zero_balance_works_without_notify():
    """Bez kontrolného bota (notify=None) sa nič nerozbije."""
    reg = FakeRegistry(balance=0.0)
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="s", notify=None)
    with pytest.raises(OutOfCredits):
        await m.reply("sys", [])
    assert reg.status_calls == [("paused", "out_of_credits")]


async def test_notify_failure_does_not_swallow_out_of_credits():
    reg = FakeRegistry(balance=0.0)
    async def boom(text): raise RuntimeError("bot down")
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="s", notify=boom)
    with pytest.raises(OutOfCredits):
        await m.reply("sys", [])


async def test_unlimited_account_replies_at_zero_balance():
    """Neobmedzený účet pri nulovom kredite odpovedá ďalej — žiadny OutOfCredits."""
    reg = FakeRegistry(balance=0.0, unlimited=True); llm = FakeLlm()
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s")
    assert await m.reply("sys", []) == "ahoj"
    assert llm.calls == 1


async def test_unlimited_account_never_pauses_nor_notifies():
    reg = FakeRegistry(balance=-5.0, unlimited=True)     # aj do mínusu
    sent = []
    async def notify(text): sent.append(text)
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="s", notify=notify)
    for _ in range(3):
        await m.reply("sys", [])
    assert reg.status_calls == []                # stav modelu sa nedotkne
    assert sent == []                            # majiteľ nedostane nič


async def test_unlimited_account_still_records_usage():
    """Odpočet preskakuje DB (record_usage), ale udalosť v ledgeri musí byť —
    inak by vlastná prevádzka zmizla z admin čísel."""
    reg = FakeRegistry(balance=0.0, unlimited=True)
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="x-ai/grok-4.5")
    await m.reply("sys", [])
    kind, i, o, atlas, charged = reg.usage_rows[0]
    assert kind == "chat" and i == 1000 and o == 500
    assert atlas == pytest.approx(0.0105) and charged == pytest.approx(0.021)


async def test_summarize_uses_summary_kind():
    reg = FakeRegistry(); llm = FakeLlm()
    llm.summarize = llm.reply
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s")
    await m.summarize("facts", "transcript")
    assert reg.usage_rows[0][0] == "summary"

async def test_missing_pricing_uses_fallback():
    reg = FakeRegistry()
    async def no_price(slug): return {}
    reg.pricing = no_price
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="s",
                   fallback_per_mtok=5.0)
    await m.reply("sys", [])
    _, _, _, atlas, charged = reg.usage_rows[0]
    assert atlas == pytest.approx(1500 / 1e6 * 5.0)
    assert charged == pytest.approx(2 * atlas)  # multiplier default 2 pri fallbacku

async def test_missing_pricing_warns_once_per_slug(caplog):
    """Chýbajúci cenník je konfiguračná chyba — warning raz, nie pri každej správe."""
    credits._MISSING_PRICE_WARNED.discard("bez-ceny")
    reg = FakeRegistry()
    async def no_price(slug): return {}
    reg.pricing = no_price
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="bez-ceny")
    with caplog.at_level(logging.WARNING, logger="credits"):
        await m.reply("sys", [])
        await m.reply("sys", [])
    assert len([r for r in caplog.records if "Chýba cenník" in r.getMessage()]) == 1


async def test_record_usage_failure_does_not_break_reply():
    reg = FakeRegistry(); llm = FakeLlm()
    async def boom(*a, **kw): raise RuntimeError("db down")
    reg.record_usage = boom
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s")
    assert await m.reply("sys", []) == "ahoj"   # odpoveď prežije výpadok ledgeru


# ---------------------------------------------------------------------------
# Neúspešné volanie sa tiež účtuje
# ---------------------------------------------------------------------------
#
# `Llm._chat` opakuje pokus po 429/5xx a spotrebu zo VŠETKÝCH pokusov sčítava
# do `last_usage`. Keby sa účtovalo len po úspechu, tri pokusy zakončené pádom
# by nezaplatil nikto — a padajúci poskytovateľ je presne ten stav, keď sa to
# deje často.


class PadajuciLlm:
    """Spáli tokeny a potom padne — presne ako `_chat` po troch pokusoch."""

    def __init__(self, usage=None):
        self.last_usage = usage if usage is not None else {"input": 300, "output": 70}

    async def reply(self, *a, **kw):
        raise RuntimeError("LLM zlyhal po 3 pokusoch")


async def test_failed_call_still_bills_burned_tokens():
    reg = FakeRegistry()
    m = MeteredLlm(PadajuciLlm(), reg, model_id="m-1", model_slug="x-ai/grok-4.5")
    with pytest.raises(RuntimeError):
        await m.reply("sys", [])
    kind, i, o, atlas, charged = reg.usage_rows[0]
    assert kind == "chat" and i == 300 and o == 70
    assert atlas == pytest.approx(300 / 1e6 * 3.0 + 70 / 1e6 * 15.0)


async def test_failed_call_propagates_original_error():
    """Účtovanie nesmie prekryť dôvod pádu — runner sa podľa neho rozhoduje."""
    reg = FakeRegistry()
    m = MeteredLlm(PadajuciLlm(), reg, model_id="m-1", model_slug="s")
    with pytest.raises(RuntimeError, match="3 pokusoch"):
        await m.reply("sys", [])


async def test_failed_call_without_usage_writes_nothing():
    """Volanie, ktoré k modelu vôbec nedošlo (DNS, timeout) — nulový riadok by
    len zaplnil ledger bez informácie."""
    reg = FakeRegistry()
    m = MeteredLlm(PadajuciLlm({"input": 0, "output": 0}), reg, model_id="m-1", model_slug="s")
    with pytest.raises(RuntimeError):
        await m.reply("sys", [])
    assert reg.usage_rows == []


async def test_ledger_failure_on_error_path_keeps_original_error():
    reg = FakeRegistry()
    async def boom(*a, **kw): raise RuntimeError("db down")
    reg.record_usage = boom
    m = MeteredLlm(PadajuciLlm(), reg, model_id="m-1", model_slug="s")
    with pytest.raises(RuntimeError, match="3 pokusoch"):
        await m.reply("sys", [])


async def test_out_of_credits_bills_nothing():
    """Volanie sa vôbec nestalo, takže niet čo účtovať."""
    reg = FakeRegistry(balance=0.0)
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="s")
    with pytest.raises(OutOfCredits):
        await m.reply("sys", [])
    assert reg.usage_rows == []


async def test_accumulated_usage_bills_the_sum():
    """Dva neúspešné pokusy + úspech: do ledgeru ide súčet, nie posledný pokus."""
    reg = FakeRegistry()
    llm = FakeLlm()
    llm.last_usage = {"input": 300, "output": 70}   # 100+100+100 / 10+10+50
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="x-ai/grok-4.5")
    await m.reply("sys", [])
    _, i, o, _, _ = reg.usage_rows[0]
    assert (i, o) == (300, 70)
