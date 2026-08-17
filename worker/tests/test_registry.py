"""Registry — claim/heartbeat/release/usage cez Supabase RPC."""
import httpx, json, pytest
from transport import SupabaseTransport
from registry import Registry

def _mock(handler):
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")
    return t

async def test_claim_calls_rpc():
    seen = {}
    def handler(req):
        seen["url"] = str(req.url); seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=[{"id": "m-1", "account_id": "a-1"}])
    reg = Registry(_mock(handler))
    rows = await reg.claim("replika-a", 25)
    assert "/rpc/claim_models" in seen["url"]
    assert seen["body"] == {"p_replica": "replika-a", "p_capacity": 25}
    assert rows[0]["id"] == "m-1"

async def test_record_usage_returns_balance():
    def handler(req):
        return httpx.Response(200, json=9.98)
    reg = Registry(_mock(handler))
    balance = await reg.record_usage("m-1", "chat", 100, 50, 0, 0.01, 0.02)
    assert balance == 9.98

async def test_credit_balance_null_is_zero():
    """Chýbajúci účet → RPC vráti null. Musí z toho byť 0.0, nie TypeError
    v MeteredLlm (`None <= 0`)."""
    def handler(req):
        return httpx.Response(200, json=None)
    reg = Registry(_mock(handler))
    assert await reg.credit_balance("m-1") == 0.0


async def test_credit_balance_returns_float():
    def handler(req):
        return httpx.Response(200, json="12.5")
    reg = Registry(_mock(handler))
    assert await reg.credit_balance("m-1") == 12.5


async def test_credit_state_parses_row():
    """Table-returning RPC chodí ako zoznam riadkov; numeric ako string."""
    seen = {}
    def handler(req):
        seen["url"] = str(req.url); seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=[{"balance": "12.5", "unlimited": True}])
    reg = Registry(_mock(handler))
    assert await reg.credit_state("m-1") == (12.5, True)
    assert "/rpc/credit_state" in seen["url"]
    assert seen["body"] == {"p_model": "m-1"}


async def test_credit_state_missing_row_is_zero_and_limited():
    """Neexistujúci účet → prázdny zoznam. Von (0.0, False), nie pád."""
    def handler(req):
        return httpx.Response(200, json=[])
    reg = Registry(_mock(handler))
    assert await reg.credit_state("m-1") == (0.0, False)


async def test_credit_state_tolerates_null_and_missing_keys():
    def handler(req):
        return httpx.Response(200, json={"balance": None})
    reg = Registry(_mock(handler))
    assert await reg.credit_state("m-1") == (0.0, False)


async def test_pricing_cached():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=[
            {"model_slug": "_default", "input_usd_per_mtok": 0, "output_usd_per_mtok": 0, "multiplier": 2.0},
            {"model_slug": "x-ai/grok-4.5", "input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0, "multiplier": 2.0},
        ])
    reg = Registry(_mock(handler))
    p1 = await reg.pricing("x-ai/grok-4.5")
    p2 = await reg.pricing("x-ai/grok-4.5")
    assert p1["input_usd_per_mtok"] == 3.0 and calls["n"] == 1  # cache 5 min

async def test_pricing_unknown_slug_falls_back_to_default():
    def handler(req):
        return httpx.Response(200, json=[
            {"model_slug": "_default", "input_usd_per_mtok": 1.0, "output_usd_per_mtok": 2.0, "multiplier": 2.0},
        ])
    reg = Registry(_mock(handler))
    p = await reg.pricing("neznamy/model")
    assert p["input_usd_per_mtok"] == 1.0

async def test_set_model_status():
    seen = {}
    def handler(req):
        seen["method"] = req.method; seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(204)
    reg = Registry(_mock(handler))
    await reg.set_status("m-1", "paused", "out_of_credits")
    assert seen["method"] == "PATCH" and "models" in seen["url"]
    assert seen["body"] == {"status": "paused", "status_reason": "out_of_credits"}
