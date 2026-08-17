"""Denný auto-sync cien z Atlas Billing API (public/v1) + stráženie zostatku.

Schéma Atlas /model-usage a /model-costs bola overená empiricky (throwaway
probe proti reálnemu účtu, viď report) — /model-usage vracia `data[].results[]`
s `model.name` (slug), `model_type` ("text"/"image"/"video") a
`usage.tokens.{input,output}`; /model-costs má rovnaký tvar buckets, ale
`amount.value` je JEDNA blendovaná suma za deň/model (input+output spolu,
Atlas cenu na vstup/výstup nerozdeľuje). /balance vracia `available.value`.
"""
import httpx
import pytest

import pricing_sync
from pricing_sync import (
    check_atlas_balance,
    compute_prices,
    fetch_atlas_daily,
    sync_pricing,
)


def _mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler),
                              base_url="https://api.atlascloud.ai/public/v1")


def _usage_body(date_, rows):
    return {
        "object": "usage.list", "scope": "account",
        "data": [{
            "object": "usage.bucket", "date": date_,
            "start_at": f"{date_}T00:00:00Z", "end_at": f"{date_}T23:59:59Z",
            "covered_until": f"{date_}T23:59:59Z", "partial": False,
            "results": rows,
        }],
        "has_more": False, "next_page": None, "request_id": "req-1",
    }


def _usage_row(slug, in_tok, out_tok, model_type="text"):
    return {
        "object": "usage.result", "model_type": model_type,
        "model": {"id": f"ms-{slug}", "name": slug, "type": model_type, "status": "active"},
        "usage": {"requests": 1, "tokens": {
            "input": in_tok, "input_audio": 0, "output": out_tok, "total": 0,
            "cache_creation": 0, "cache_creation_1h": 0, "cache_read": 0,
            "cache_audio": 0, "input_image": 0, "output_image": 0,
        }, "images": None, "video": None},
    }


def _costs_body(date_, rows):
    return {
        "object": "model_cost.list", "scope": "account",
        "data": [{
            "object": "model_cost.bucket", "date": date_,
            "start_at": f"{date_}T00:00:00Z", "end_at": f"{date_}T23:59:59Z",
            "covered_until": f"{date_}T23:59:59Z", "partial": False,
            "results": rows,
        }],
        "has_more": False, "next_page": None, "request_id": "req-2",
    }


def _cost_row(slug, value, model_type="text"):
    return {
        "object": "model_cost.result", "model_type": model_type,
        "model": {"id": f"ms-{slug}", "name": slug, "type": model_type, "status": "active"},
        "amount": {"value": f"{value:.6f}", "currency": "usd"},
    }


# ---------- fetch_atlas_daily ----------

async def test_fetch_merges_usage_and_costs(monkeypatch):
    def handler(req):
        if "/model-usage" in str(req.url):
            return httpx.Response(200, json=_usage_body("2026-08-14", [
                _usage_row("xai/grok-4.5", 275088, 3500),
            ]))
        if "/model-costs" in str(req.url):
            return httpx.Response(200, json=_costs_body("2026-08-14", [
                _cost_row("xai/grok-4.5", 0.627688),
            ]))
        raise AssertionError(f"neočakávaná URL {req.url}")

    monkeypatch.setattr(pricing_sync, "_client", lambda: _mock_client(handler))
    rows = await fetch_atlas_daily("apikey-x", "2026-08-14", "2026-08-14")
    assert rows == [{
        "model_slug": "xai/grok-4.5", "date": "2026-08-14",
        "input_tokens": 275088, "output_tokens": 3500,
        "cost_usd": pytest.approx(0.627688),
    }]


async def test_fetch_skips_non_text_models(monkeypatch):
    """Image/video modely nemajú tokenovú cenu — pricing tabuľka ich nerieši."""
    def handler(req):
        if "/model-usage" in str(req.url):
            return httpx.Response(200, json=_usage_body("2026-08-14", [
                _usage_row("alibaba/wan-2.7-pro/image-edit", 0, 0, model_type="image"),
                _usage_row("xai/grok-4.5", 100, 50),
            ]))
        return httpx.Response(200, json=_costs_body("2026-08-14", [
            _cost_row("alibaba/wan-2.7-pro/image-edit", 0.3, model_type="image"),
            _cost_row("xai/grok-4.5", 0.01),
        ]))

    monkeypatch.setattr(pricing_sync, "_client", lambda: _mock_client(handler))
    rows = await fetch_atlas_daily("apikey-x", "2026-08-14", "2026-08-14")
    assert [r["model_slug"] for r in rows] == ["xai/grok-4.5"]


async def test_fetch_tolerates_missing_cost_row(monkeypatch):
    """Model má usage, ale chýba mu cost bucket (napr. free tier) — cost_usd=0, nespadne."""
    def handler(req):
        if "/model-usage" in str(req.url):
            return httpx.Response(200, json=_usage_body("2026-08-14", [
                _usage_row("new/model", 10, 5),
            ]))
        return httpx.Response(200, json=_costs_body("2026-08-14", []))

    monkeypatch.setattr(pricing_sync, "_client", lambda: _mock_client(handler))
    rows = await fetch_atlas_daily("apikey-x", "2026-08-14", "2026-08-14")
    assert rows[0]["cost_usd"] == 0


async def test_fetch_tolerates_missing_token_split():
    """Defenzívny parser — ak by usage.tokens chýbal/mal iný tvar, nespadne, len 0 tokeny."""
    row = {
        "object": "usage.result", "model_type": "text",
        "model": {"id": "ms-x", "name": "weird/model", "type": "text", "status": "active"},
        "usage": {"requests": 1, "tokens": None, "images": None, "video": None},
    }

    def handler(req):
        if "/model-usage" in str(req.url):
            return httpx.Response(200, json=_usage_body("2026-08-14", [row]))
        return httpx.Response(200, json=_costs_body("2026-08-14", []))

    import pricing_sync as ps
    orig = ps._client
    ps._client = lambda: _mock_client(handler)
    try:
        rows = await fetch_atlas_daily("apikey-x", "2026-08-14", "2026-08-14")
    finally:
        ps._client = orig
    assert rows[0]["input_tokens"] == 0 and rows[0]["output_tokens"] == 0


# ---------- compute_prices ----------

async def test_compute_prices_no_ledger_ratio_uses_blended():
    rows = [
        {"model_slug": "m", "date": "d1", "input_tokens": 900_000, "output_tokens": 100_000,
         "cost_usd": 1.0},
    ]
    prices = await compute_prices(rows)
    # blended = 1.0 / (1_000_000/1e6) = 1.0 $/Mtok, žiadny ledger pomer -> obe rovnaké
    assert prices == {"m": {"input_usd_per_mtok": pytest.approx(1.0),
                             "output_usd_per_mtok": pytest.approx(1.0)}}


async def test_compute_prices_aggregates_across_days():
    rows = [
        {"model_slug": "m", "date": "d1", "input_tokens": 500_000, "output_tokens": 0,
         "cost_usd": 0.5},
        {"model_slug": "m", "date": "d2", "input_tokens": 500_000, "output_tokens": 0,
         "cost_usd": 0.5},
    ]
    prices = await compute_prices(rows)
    assert prices["m"]["input_usd_per_mtok"] == pytest.approx(1.0)


async def test_compute_prices_splits_via_ledger_ratio():
    """Ledger hovorí, že output tokeny stoja 4x toľko čo input (pomer 4).
    Blendovaná cena sa musí rozdeliť tak, aby spätne sedela na celkovú sumu."""
    rows = [
        {"model_slug": "m", "date": "d1", "input_tokens": 900_000, "output_tokens": 100_000,
         "cost_usd": 5.2},
    ]
    prices = await compute_prices(rows, ledger_ratios={"m": 4.0})
    p_in = prices["m"]["input_usd_per_mtok"]
    p_out = prices["m"]["output_usd_per_mtok"]
    assert p_out == pytest.approx(p_in * 4.0)
    # spätná kontrola: musí dať presne pôvodnú celkovú sumu
    total = 900_000 / 1e6 * p_in + 100_000 / 1e6 * p_out
    assert total == pytest.approx(5.2)


async def test_compute_prices_no_ledger_data_for_model_falls_back_blended():
    rows = [
        {"model_slug": "a", "date": "d1", "input_tokens": 100, "output_tokens": 100, "cost_usd": 0.2},
        {"model_slug": "b", "date": "d1", "input_tokens": 100, "output_tokens": 100, "cost_usd": 0.4},
    ]
    prices = await compute_prices(rows, ledger_ratios={"a": 3.0})   # chýba pre "b"
    assert prices["a"]["output_usd_per_mtok"] == pytest.approx(prices["a"]["input_usd_per_mtok"] * 3.0)
    assert prices["b"]["input_usd_per_mtok"] == prices["b"]["output_usd_per_mtok"]


async def test_compute_prices_skips_zero_token_rows():
    rows = [{"model_slug": "m", "date": "d1", "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}]
    prices = await compute_prices(rows)
    assert prices == {}


# ---------- sync_pricing ----------

class FakeRegistry:
    pass  # sync_pricing v tejto fáze cez registry nič nečíta, len upsertuje cez transport


async def test_sync_pricing_upserts_and_preserves_multiplier(monkeypatch):
    async def fake_fetch(api_key, start, end):
        return [{"model_slug": "xai/grok-4.5", "date": "d", "input_tokens": 900_000,
                  "output_tokens": 100_000, "cost_usd": 2.0}]

    posted = {}

    def handler(req):
        if req.method == "POST" and "/pricing" in str(req.url):
            import json
            posted["body"] = json.loads(req.content)
            posted["headers"] = dict(req.headers)
            return httpx.Response(200, json=posted["body"])
        raise AssertionError(f"neočakávaný request {req.method} {req.url}")

    monkeypatch.setattr(pricing_sync, "fetch_atlas_daily", fake_fetch)

    from transport import SupabaseTransport
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   base_url="https://x.supabase.co/rest/v1")

    await sync_pricing(t, FakeRegistry(), "apikey-x")

    assert len(posted["body"]) == 1
    row = posted["body"][0]
    assert row["model_slug"] == "xai/grok-4.5"
    assert "multiplier" not in row          # nedotýkame sa multiplikátora
    assert row["input_usd_per_mtok"] == pytest.approx(2.0)  # blended, žiadny ledger
    assert "merge-duplicates" in posted["headers"]["prefer"]


async def test_sync_pricing_skips_default_slug(monkeypatch):
    async def fake_fetch(api_key, start, end):
        return [
            {"model_slug": "_default", "date": "d", "input_tokens": 100, "output_tokens": 100,
             "cost_usd": 0.1},
            {"model_slug": "real/model", "date": "d", "input_tokens": 100, "output_tokens": 100,
             "cost_usd": 0.2},
        ]

    posted = {}

    def handler(req):
        import json
        posted["body"] = json.loads(req.content)
        return httpx.Response(200, json=posted["body"])

    monkeypatch.setattr(pricing_sync, "fetch_atlas_daily", fake_fetch)
    from transport import SupabaseTransport
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   base_url="https://x.supabase.co/rest/v1")

    await sync_pricing(t, FakeRegistry(), "apikey-x")
    assert [r["model_slug"] for r in posted["body"]] == ["real/model"]


async def test_sync_pricing_no_rows_does_not_post(monkeypatch):
    async def fake_fetch(api_key, start, end):
        return []

    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return httpx.Response(200, json=[])

    monkeypatch.setattr(pricing_sync, "fetch_atlas_daily", fake_fetch)
    from transport import SupabaseTransport
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   base_url="https://x.supabase.co/rest/v1")

    await sync_pricing(t, FakeRegistry(), "apikey-x")
    assert called["n"] == 0


async def test_sync_pricing_fetch_exception_does_not_raise(monkeypatch):
    async def boom(api_key, start, end):
        raise RuntimeError("Atlas API padla")

    monkeypatch.setattr(pricing_sync, "fetch_atlas_daily", boom)
    from transport import SupabaseTransport
    t = SupabaseTransport("https://x.supabase.co", "sk")
    await sync_pricing(t, FakeRegistry(), "apikey-x")  # nesmie hodiť výnimku


async def test_sync_pricing_upsert_exception_does_not_raise(monkeypatch):
    async def fake_fetch(api_key, start, end):
        return [{"model_slug": "m", "date": "d", "input_tokens": 100, "output_tokens": 100,
                  "cost_usd": 0.1}]

    def handler(req):
        return httpx.Response(500, json={"error": "db down"})

    monkeypatch.setattr(pricing_sync, "fetch_atlas_daily", fake_fetch)
    from transport import SupabaseTransport
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   base_url="https://x.supabase.co/rest/v1")

    await sync_pricing(t, FakeRegistry(), "apikey-x")  # nesmie hodiť výnimku


# ---------- check_atlas_balance ----------

async def test_check_atlas_balance_parses_available_value(monkeypatch):
    def handler(req):
        assert "/balance" in str(req.url)
        assert req.headers["authorization"] == "Bearer apikey-x"
        return httpx.Response(200, json={
            "object": "balance", "scope": "account",
            "account": {"id": "a", "name": "n", "type": "t"},
            "available": {"value": "123.45", "currency": "usd"},
            "cash": {"value": "100", "currency": "usd"},
            "bonus": {"value": "23.45", "currency": "usd"},
            "subscription_bonus": {"value": "0", "currency": "usd"},
            "frozen": {"value": "0", "currency": "usd"},
            "credit_grant": {"status": "none", "granted": {"value": "0", "currency": "usd"},
                              "used": {"value": "0", "currency": "usd"},
                              "remaining_overdraft": {"value": "0", "currency": "usd"},
                              "overdrawn": {"value": "0", "currency": "usd"}},
            "request_id": "r-1",
        })

    monkeypatch.setattr(pricing_sync, "_client", lambda: _mock_client(handler))
    balance = await check_atlas_balance("apikey-x", threshold_usd=50.0)
    assert balance == pytest.approx(123.45)


async def test_check_atlas_balance_logs_error_below_threshold(monkeypatch, caplog):
    def handler(req):
        return httpx.Response(200, json={"available": {"value": "10.0", "currency": "usd"}})

    monkeypatch.setattr(pricing_sync, "_client", lambda: _mock_client(handler))
    import logging
    with caplog.at_level(logging.ERROR, logger="pricing_sync"):
        balance = await check_atlas_balance("apikey-x", threshold_usd=50.0)
    assert balance == pytest.approx(10.0)
    assert any("10" in r.getMessage() for r in caplog.records)


async def test_check_atlas_balance_above_threshold_no_error_log(monkeypatch, caplog):
    def handler(req):
        return httpx.Response(200, json={"available": {"value": "999.0", "currency": "usd"}})

    monkeypatch.setattr(pricing_sync, "_client", lambda: _mock_client(handler))
    import logging
    with caplog.at_level(logging.ERROR, logger="pricing_sync"):
        await check_atlas_balance("apikey-x", threshold_usd=50.0)
    assert not any(r.levelno == logging.ERROR for r in caplog.records)


async def test_check_atlas_balance_fails_open_on_exception(monkeypatch, caplog):
    def handler(req):
        return httpx.Response(401, json={"error": "unauthorized"})

    monkeypatch.setattr(pricing_sync, "_client", lambda: _mock_client(handler))
    import logging
    with caplog.at_level(logging.WARNING, logger="pricing_sync"):
        balance = await check_atlas_balance("apikey-x", threshold_usd=50.0)
    assert balance is None
