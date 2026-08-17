"""Claim slučka — spúšťanie/zastavovanie runnerov podľa lease."""
import asyncio
import json
import pathlib
from main import Pool

class FakeReg:
    def __init__(self):
        self.claims = []; self.released = []; self.hb = 0
        self.next_rows = []
        self.rows_by_id = {}
        self.replicas = []
    # `owned` = čo vráti heartbeat (fencing token). None = staršia RPC, ktorá
    # nič nepovie — vtedy sa nesmie diať nič.
    owned = None
    async def claim(self, replica, capacity):
        self.claims.append(capacity); return self.next_rows
    async def heartbeat(self, replica):
        self.hb += 1
        return self.owned
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

# ---------------------------------------------------------------------------
# Fencing — heartbeat povie, koho replika ešte naozaj vlastní
# ---------------------------------------------------------------------------
#
# Lease vyprší po 90 s bez heartbeatu, ale replika, ktorá ho nestihla, nemusí
# byť mŕtva — stačí zaseknutá sieť. Iná replika si tenanta medzitým prevezme
# a spustí vlastnú Telethon session. Dve sessions na jednom Telegram účte je
# najrýchlejšia cesta k banu, takže sa runner musí zastaviť sám.


async def test_stolen_tenant_is_stopped_within_one_tick():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    reg.owned = {"m-1"}
    await pool.tick()
    assert "m-1" in pool._running

    # Iná replika si ho prevzala — náš heartbeat už jeho riadok neobnovil.
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    reg.owned = set()
    await pool.tick()
    assert "m-1" not in pool._running
    assert FakeRunner.instances[0].stopped


async def test_stolen_tenant_lease_is_not_released():
    """`release` by novému majiteľovi vynulovalo `claimed_by` — riadok už
    nie je náš a siahať naň by znamenalo vziať mu ho spod rúk."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    reg.owned = {"m-1"}
    await pool.tick()
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    reg.owned = set()
    reg.released.clear()
    await pool.tick()
    assert reg.released == []


async def test_owned_tenant_keeps_running():
    """Bežný stav sa nesmie zmeniť — heartbeat potvrdí, čo beží."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    reg.owned = {"m-1"}
    await pool.tick()
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    await pool.tick()
    assert "m-1" in pool._running
    assert not FakeRunner.instances[0].stopped


async def test_silent_heartbeat_stops_nothing():
    """Staršia verzia RPC nevráti nič. „Neviem" nesmie znamenať „zastav
    všetko" — inak by rollout zhodil všetky modelky naraz."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    reg.owned = None
    await pool.tick()
    reg.rows_by_id["m-1"] = ROW
    reg.next_rows = []
    await pool.tick()
    assert "m-1" in pool._running


async def test_shutdown_releases_all():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    await pool.shutdown()
    assert FakeRunner.instances[0].stopped
    assert "ALL" in reg.released


def test_railway_spusta_main():
    """Railway štartuje jediný entrypoint — `src/main.py` s claim slučkou.

    Fanvue agent beží in-process cez runner (TenantRunner._start_fanvue), nie
    ako samostatná služba, takže žiadna iná predloha štartovacieho príkazu
    neexistuje.
    """
    root = pathlib.Path(__file__).resolve().parent.parent
    config = json.loads((root / "railway.json").read_text(encoding="utf-8"))
    assert config["deploy"]["startCommand"] == "python src/main.py"


# ---------------------------------------------------------------------------
# Typ agenta — pool spúšťa len to, pre čo má beh
# ---------------------------------------------------------------------------
#
# Prvou obranou je `claim_models` (migrácia 018), ktorá filtruje na
# `model_type = 'persona'`. Tieto testy sú o druhej: keby ten filter niekto pri
# úprave RPC stratil, riadok firemného agenta sa dostane až sem — a tu sa musí
# zastaviť, kým sa naň nespustí Telethon session s dievčenskou personou.

PERSONA_ROW = {**ROW, "model_type": "persona"}
BUSINESS_ROW = {**ROW, "model_type": "business"}
PRIVATE_ROW = {**ROW, "model_type": "private"}


async def test_persona_row_starts_runner():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [PERSONA_ROW]
    pool = make_pool(reg)
    await pool.tick()
    assert len(FakeRunner.instances) == 1
    assert "m-1" in pool._running


async def test_business_row_never_starts_runner():
    """Žiadny runner, žiadna session — a lease sa vráti, nech ho pool nedrží."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [BUSINESS_ROW]
    pool = make_pool(reg)
    await pool.tick()
    assert FakeRunner.instances == []
    assert pool._running == {}
    assert "m-1" in reg.released


async def test_private_row_never_starts_runner():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [PRIVATE_ROW]
    pool = make_pool(reg)
    await pool.tick()
    assert FakeRunner.instances == []
    assert pool._running == {}


async def test_unknown_type_never_starts_runner():
    """Neznámy typ je tá istá situácia ako firemný — beh preň neexistuje."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [{**ROW, "model_type": "kocur"}]
    pool = make_pool(reg)
    await pool.tick()
    assert FakeRunner.instances == []


async def test_row_without_model_type_still_runs():
    """Riadok bez stĺpca je starý riadok, nie firemný agent.

    Keby sa replika nasadila skôr než migrácia 018, opačná voľba by zastavila
    všetko, čo práve beží — vrátane produkčných modeliek.
    """
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]        # ROW `model_type` nemá
    pool = make_pool(reg)
    await pool.tick()
    assert len(FakeRunner.instances) == 1


async def test_bad_type_does_not_eat_capacity():
    """Odmietnutý riadok nesmie zabrať miesto — ďalší tick pýta plnú kapacitu."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [BUSINESS_ROW]
    pool = make_pool(reg)
    await pool.tick()
    reg.next_rows = []
    await pool.tick()
    assert reg.claims == [2, 2]


async def test_running_tenant_stopped_when_type_stops_being_runnable():
    """Typ sa nemá ako zmeniť (DB naň nedáva update grant), ale keby áno,
    bežiaci runner nesmie prežiť jeden tick."""
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [PERSONA_ROW]
    pool = make_pool(reg)
    await pool.tick()
    assert "m-1" in pool._running

    reg.next_rows = []
    reg.rows_by_id["m-1"] = BUSINESS_ROW
    await pool.tick()
    assert "m-1" not in pool._running
    assert FakeRunner.instances[0].stopped


def test_runnable_types_are_only_persona():
    """Kanárik: kým `claim_models` filtruje na `persona`, tento zoznam sa mu
    musí rovnať. Rozšíriť ho bez migrácie znamená pustiť sem typ, ktorý DB
    replike nikdy nepridelí — alebo horšie, spustiť naň dievčenský runner."""
    from main import RUNNABLE_MODEL_TYPES

    assert RUNNABLE_MODEL_TYPES == frozenset({"persona"})
