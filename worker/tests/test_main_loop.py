"""Claim slučka — spúšťanie/zastavovanie runnerov podľa lease."""
import asyncio
from main import Pool

class FakeReg:
    def __init__(self):
        self.claims = []; self.released = []; self.hb = 0
        self.next_rows = []
        self.rows_by_id = {}
        self.replicas = []
    async def claim(self, replica, capacity):
        self.claims.append(capacity); return self.next_rows
    async def heartbeat(self, replica): self.hb += 1
    async def release_all(self, replica): self.released.append("ALL")
    async def model_row(self, mid): return self.rows_by_id.get(mid)
    async def release(self, mid): self.released.append(mid)
    async def set_status(self, *a, **kw): pass
    async def upsert_replica(self, replica, tenant_count, started_at=None):
        self.replicas.append((replica, tenant_count, started_at))

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

async def test_finished_runner_releases_lease():
    """Runner, ktorý sa vráti čisto, lease nepúšťa — musí to spraviť pool.

    Inak by heartbeat repliky ďalej obnovoval `claimed_until` a model by už
    nikto nikdy nedoklaimoval (osirený lease).
    """
    class DoneRunner(FakeRunner):
        async def run(self): return          # skončí hneď, lease nepúšťa

    reg = FakeReg(); reg.next_rows = [ROW]
    pool = Pool(registry=reg, transport=None, global_cfg=_cfg(),
                runner_factory=DoneRunner, tenant_factory=lambda row, g: row)
    await pool.tick()
    _mid, (_runner, task) = next(iter(pool._running.items()))
    await asyncio.sleep(0)                   # nech runner dobehne
    assert task.done()
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    await pool.tick()
    assert "m-1" not in pool._running
    assert "m-1" in reg.released


async def test_bad_config_row_goes_error():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    def bad_factory(row, g): raise ValueError("pokazený riadok")
    pool = Pool(registry=reg, transport=None, global_cfg=_cfg(),
                runner_factory=FakeRunner, tenant_factory=bad_factory)
    await pool.tick()
    assert not FakeRunner.instances
    assert "m-1" in reg.released

async def test_tick_upserts_replica_state():
    """Admin monitor: každý tick zapíše stav repliky, štart len raz.

    `started_at` sa posiela iba pri prvom ticku — inak by upsert pri každom
    cykle prepísal čas štartu na „teraz" a reštart repliky by nebolo vidieť.
    """
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    await pool.tick()
    assert [r[:2] for r in reg.replicas] == [("r-1", 1), ("r-1", 1)]
    assert reg.replicas[0][2] == pool._started_at   # prvý tick: čas štartu
    assert reg.replicas[1][2] is None               # ďalšie ticky ho neposielajú

async def test_replica_upsert_failure_does_not_break_tick():
    """Monitoring je vedľajšia cesta — jeho výpadok nesmie zastaviť claim slučku."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    async def boom(*a, **kw): raise RuntimeError("supabase down")
    reg.upsert_replica = boom
    pool = make_pool(reg)
    await pool.tick()                                # nesmie vyhodiť
    assert reg.hb == 1
    assert len(FakeRunner.instances) == 1
    assert not pool._replica_registered              # pri ďalšom pokuse zopakuje started_at

async def test_shutdown_releases_all():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    await pool.shutdown()
    assert FakeRunner.instances[0].stopped
    assert "ALL" in reg.released
