"""Kreditový wrapper — check pred volaním, zápis po ňom, pauza pri nule."""
import pytest
from credits import MeteredLlm, OutOfCredits

class FakeLlm:
    def __init__(self):
        self.last_usage = {"input": 1000, "output": 500}
        self.calls = 0
    async def reply(self, *a, **kw):
        self.calls += 1
        return "ahoj"

class FakeRegistry:
    def __init__(self, balance=10.0):
        self._balance = balance
        self.usage_rows = []
        self.status_calls = []
    async def credit_balance(self, model_id): return self._balance
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

async def test_record_usage_failure_does_not_break_reply():
    reg = FakeRegistry(); llm = FakeLlm()
    async def boom(*a, **kw): raise RuntimeError("db down")
    reg.record_usage = boom
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s")
    assert await m.reply("sys", []) == "ahoj"   # odpoveď prežije výpadok ledgeru
