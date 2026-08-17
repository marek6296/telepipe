"""Claim slučka — spúšťanie/zastavovanie runnerov podľa lease."""
import asyncio
from main import Pool

class FakeReg:
    def __init__(self):
        self.claims = []; self.released = []; self.hb = 0
        self.next_rows = []
        self.rows_by_id = {}
    async def claim(self, replica, capacity):
        self.claims.append(capacity); return self.next_rows
    async def heartbeat(self, replica): self.hb += 1
    async def release_all(self, replica): self.released.append("ALL")
    async def model_row(self, mid): return self.rows_by_id.get(mid)
    async def release(self, mid): self.released.append(mid)
    async def set_status(self, *a, **kw): pass

class FakeRunner:
    instances = []
    def __init__(self, *a, **kw):
        FakeRunner.instances.append(self); self.stopped = False
    async def run(self): await asyncio.sleep(3600)
    async def stop(self): self.stopped = True

ROW = {"id": "m-1", "account_id": "a-1", "name": "", "tg_api_id": 1,
       "tg_api_hash": "h", "tg_session_enc": "", "control_bot_token_enc": "",
       "owner_chat_id": 1, "status": "active"}

def _cfg():
    class C: max_tenants = 2; replica_name = "r-1"; claim_interval_s = 0
    return C()

def make_pool(reg):
    return Pool(registry=reg, transport=None, global_cfg=_cfg(),
                runner_factory=FakeRunner, tenant_factory=lambda row, g: row)

async def test_claims_up_to_capacity_and_starts_runner():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    assert reg.claims == [2]                     # capacity - 0 bežiacich
    assert len(FakeRunner.instances) == 1

async def test_second_tick_claims_remaining_capacity():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    await pool.tick()
    assert reg.claims == [2, 1]

async def test_paused_model_gets_stopped():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    reg.next_rows = []
    reg.rows_by_id["m-1"] = {**ROW, "status": "paused"}
    await pool.tick()
    assert FakeRunner.instances[0].stopped
    assert "m-1" in reg.released

async def test_dead_runner_leaves_registry(monkeypatch):
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    # runner skončí sám (error/out_of_credits) — task done
    mid, (runner, task) = next(iter(pool._running.items()))
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    await pool.tick()
    assert "m-1" not in pool._running            # von z evidencie

async def test_bad_config_row_goes_error():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    def bad_factory(row, g): raise ValueError("pokazený riadok")
    pool = Pool(registry=reg, transport=None, global_cfg=_cfg(),
                runner_factory=FakeRunner, tenant_factory=bad_factory)
    await pool.tick()
    assert not FakeRunner.instances
    assert "m-1" in reg.released

async def test_shutdown_releases_all():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    await pool.shutdown()
    assert FakeRunner.instances[0].stopped
    assert "ALL" in reg.released
