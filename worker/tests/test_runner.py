"""TenantRunner — životný cyklus, backoff, čistý stop."""
import asyncio, pytest
from runner import TenantRunner, BACKOFF_S

async def test_backoff_progression():
    assert BACKOFF_S == [30, 60, 300, 900]

async def test_five_failures_sets_error(monkeypatch):
    calls = {"n": 0}; statuses = []
    class Reg:
        async def set_status(self, mid, s, r=""): statuses.append((s, r))
        async def release(self, mid): pass
    async def boom(self): calls["n"] += 1; raise RuntimeError("pád")
    monkeypatch.setattr(TenantRunner, "_run_once", boom)
    async def nosleep(s): pass
    monkeypatch.setattr(TenantRunner, "_sleep", staticmethod(nosleep))
    r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=Reg(), transport=None)
    await r.run()
    assert calls["n"] == 5
    assert statuses[-1] == ("error", "crashed_repeatedly")

async def test_stop_cancels_cleanly(monkeypatch):
    started = asyncio.Event()
    async def forever(self): started.set(); await asyncio.sleep(3600)
    monkeypatch.setattr(TenantRunner, "_run_once", forever)
    class Reg:
        async def set_status(self, *a, **kw): pass
        async def release(self, mid): pass
    r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=Reg(), transport=None)
    task = asyncio.create_task(r.run())
    await started.wait()
    await r.stop()
    await asyncio.wait_for(task, 2)      # skončí bez výnimky

async def test_auth_revoked_no_retry(monkeypatch):
    from telethon.errors import AuthKeyUnregisteredError
    statuses = []
    class Reg:
        async def set_status(self, mid, s, r=""): statuses.append((s, r))
        async def release(self, mid): pass
    calls = {"n": 0}
    async def revoked(self):
        calls["n"] += 1
        raise AuthKeyUnregisteredError(request=None)
    monkeypatch.setattr(TenantRunner, "_run_once", revoked)
    r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=Reg(), transport=None)
    await r.run()
    assert calls["n"] == 1               # žiadny retry
    assert statuses[-1] == ("error", "session_revoked")

async def test_out_of_credits_stops_without_error_status(monkeypatch):
    from credits import OutOfCredits
    statuses = []; released = []
    class Reg:
        async def set_status(self, mid, s, r=""): statuses.append((s, r))
        async def release(self, mid): released.append(mid)
    async def broke(self): raise OutOfCredits("m-1")
    monkeypatch.setattr(TenantRunner, "_run_once", broke)
    r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=Reg(), transport=None)
    await r.run()
    assert statuses == []                # MeteredLlm už pauzol; runner nič nemení
    assert released                      # ale lease pustí
