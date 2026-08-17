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


async def _make_account(t) -> str:
    """Účet už nevzniká priamo — `accounts.id` je FK na `auth.users.id`
    (migrácia 007). Používateľa založíme cez GoTrue admin API (rovnaký service
    kľúč, aký transport už nesie v hlavičkách), trigger `handle_new_user`
    synchronne doplní `accounts` riadok. Vraciame id používateľa == id účtu.
    """
    base = os.environ["SUPABASE_URL"]
    r = await t._client.post(
        f"{base}/auth/v1/admin/users",
        json={
            "email": f"it-{uuid.uuid4()}@test.dev",
            "password": uuid.uuid4().hex,
            "email_confirm": True,
        },
    )
    r.raise_for_status()
    return r.json()["id"]


async def _delete_account(t, uid: str) -> None:
    """Zmazanie auth.users kaskádne zhodí accounts → models → všetko ostatné."""
    base = os.environ["SUPABASE_URL"]
    r = await t._client.delete(f"{base}/auth/v1/admin/users/{uid}")
    r.raise_for_status()


async def test_lease_lifecycle(real):
    reg, t = real
    uid = await _make_account(t)
    # Trigger zakladá účet s nulovým kreditom — test potrebuje 5 USD.
    await t._patch("accounts", {"id": f"eq.{uid}"}, {"credit_balance_usd": 5})
    row = (await t._post("models", {"account_id": uid, "status": "active",
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
        await _delete_account(t, uid)


async def test_provision_trigger_seeds_singletons(real):
    reg, t = real
    uid = await _make_account(t)
    row = (await t._post("models", {"account_id": uid}))[0]
    try:
        for table in ("persona", "behavior", "settings"):
            rows = await t._get(table, {"model_id": f"eq.{row['id']}", "select": "*"})
            assert len(rows) == 1, table
        bhv = (await t._get("behavior", {"model_id": f"eq.{row['id']}", "select": "voice_chance"}))[0]
        assert float(bhv["voice_chance"]) == pytest.approx(0.18)
    finally:
        await _delete_account(t, uid)
