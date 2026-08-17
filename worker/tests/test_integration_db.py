"""Proti reálnej telepipe DB (kľúče z ../.env). Spúšťa sa ručne:
   .venv/bin/pytest -m integration
"""
import os, uuid, pytest

pytestmark = pytest.mark.integration


@pytest.fixture
async def real():
    from dotenv import load_dotenv
    load_dotenv("/Users/marek/telepipe/.env")
    from transport import SupabaseTransport
    from registry import Registry
    t = SupabaseTransport(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    yield Registry(t), t
    await t.close()


async def test_lease_lifecycle(real):
    reg, t = real
    acc = (await t._post("accounts", {"email": f"it-{uuid.uuid4()}@test.dev",
                                      "credit_balance_usd": 5}))[0]
    row = (await t._post("models", {"account_id": acc["id"], "status": "active",
                                    "tg_api_id": 1, "owner_chat_id": 1}))[0]
    try:
        claimed = await reg.claim("it-replika", 5)
        assert any(r["id"] == row["id"] for r in claimed)
        again = await reg.claim("it-replika-2", 5)
        assert not any(r["id"] == row["id"] for r in again)   # čerstvý heartbeat drží
        balance = await reg.record_usage(row["id"], "chat", 10, 5, 0, 0.001, 0.002)
        assert balance == pytest.approx(4.998)
        assert await reg.credit_balance(row["id"]) == pytest.approx(4.998)
        await reg.release_all("it-replika")
        freed = await reg.model_row(row["id"])
        assert freed["claimed_by"] is None
    finally:
        r = await t._client.delete(f"/accounts?id=eq.{acc['id']}")
        r.raise_for_status()


async def test_provision_trigger_seeds_singletons(real):
    reg, t = real
    acc = (await t._post("accounts", {"email": f"it-{uuid.uuid4()}@test.dev"}))[0]
    row = (await t._post("models", {"account_id": acc["id"]}))[0]
    try:
        for table in ("persona", "behavior", "settings"):
            rows = await t._get(table, {"model_id": f"eq.{row['id']}", "select": "*"})
            assert len(rows) == 1, table
        bhv = (await t._get("behavior", {"model_id": f"eq.{row['id']}", "select": "voice_chance"}))[0]
        assert float(bhv["voice_chance"]) == pytest.approx(0.18)
    finally:
        r = await t._client.delete(f"/accounts?id=eq.{acc['id']}")
        r.raise_for_status()
