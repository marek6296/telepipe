"""Entrypoint — replika workera: claim slučka, heartbeat, graceful shutdown.

V predlohe (`/Users/marek/telegram/src/main.py`) bol jeden proces = jeden
model. Tu je proces replika, ktorá si cez Registry claimuje až `max_tenants`
modelov naraz a pre každý beží `TenantRunner` (Task 10) ako `asyncio.Task`.
`Pool` drží evidenciu bežiacich runnerov a v pravidelnej slučke (`tick`):

  1. zastaví runnery modelov, ktorým lease/stav už nedáva zmysel (odobraný
     lease, alebo status v `models` prestal byť `active`),
  2. vyčistí evidenciu runnerov, ktoré skončili samé (`TenantRunner.run()`
     sa vždy vráti čisto — pád na inom mieste je bug, nie dôvod padnúť pool),
  3. doklaimuje voľnú kapacitu a naštartuje nové runnery,
  4. pošle heartbeat, nech Supabase vie, že replika ešte žije.

Fáza fanvue rola (`SERVICE_ROLE=fanvue` vetva z predlohy) sa v tejto fáze
zámerne NEPORTUJE — fanvue agent sa aktivuje až vo Fáze 3.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys

log = logging.getLogger("main")


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class Pool:
    """Drží bežiace `TenantRunner` úlohy jednej repliky a stará sa o lease."""

    def __init__(
        self,
        registry,
        transport,
        global_cfg,
        runner_factory=None,
        tenant_factory=None,
    ) -> None:
        self._reg = registry
        self._transport = transport
        self._g = global_cfg
        # Lazy importy — default factories nech nevyžadujú Telethon a pod. pri
        # čisto jednotkovom testovaní poolu (testy si ich podvrhnú).
        if runner_factory is None:
            from runner import TenantRunner

            runner_factory = TenantRunner
        if tenant_factory is None:
            from config import TenantConfig

            tenant_factory = TenantConfig.from_row
        self._runner_factory = runner_factory
        self._tenant_factory = tenant_factory
        # model_id -> (runner, task)
        self._running: dict = {}

    async def tick(self) -> None:
        """Jeden cyklus claim slučky. Nikdy nehádže ďalej — chyby sa logujú."""
        # 1. modely, ktoré prestali byť active (alebo zmizli), sa zastavia
        for mid in list(self._running):
            row = await self._reg.model_row(mid)
            if not row or row.get("status") != "active":
                runner, task = self._running.pop(mid)
                log.info("model %s: lease/stav už nesedí — zastavujem", mid)
                await runner.stop()
                task.cancel()
                await self._reg.release(mid)

        # 2. runnery, ktoré skončili samé, vypadnú z evidencie a ich lease sa
        #    pustí. Čistý návrat z `TenantRunner.run()` (disconnect) lease
        #    NEPÚŠŤA — robí to len chybová/out_of_credits vetva. Keby ho pool
        #    nepustil, heartbeat repliky by `claimed_until` ďalej obnovoval a
        #    model by už nikto nedoklaimoval. Opakovaný release je neškodný,
        #    RPC je idempotentné.
        for mid in list(self._running):
            _runner, task = self._running[mid]
            if task.done():
                log.info("model %s: runner skončil sám — mažem z evidencie", mid)
                self._running.pop(mid)
                try:
                    await self._reg.release(mid)
                except Exception:  # noqa: BLE001 — zlyhaný release nesmie zhodiť tick
                    log.exception("model %s: release po skončení runnera zlyhal", mid)

        # 3. doklaimni voľnú kapacitu a naštartuj nové runnery
        free = self._g.max_tenants - len(self._running)
        if free > 0:
            rows = await self._reg.claim(self._g.replica_name, free)
            for row in rows:
                mid = row["id"]
                try:
                    cfg = self._tenant_factory(row, self._g)
                except Exception:
                    log.exception("model %s: neplatný riadok — odstavujem", mid)
                    try:
                        await self._reg.set_status(mid, "error", "bad_config")
                    except Exception:  # noqa: BLE001 — nesmie zhodiť tick
                        log.exception("model %s: set_status zlyhal", mid)
                    await self._reg.release(mid)
                    continue
                runner = self._runner_factory(cfg, self._g, self._reg, self._transport)
                task = asyncio.create_task(runner.run())
                self._running[mid] = (runner, task)
                log.info("model %s: runner naštartovaný", mid)

        # 4. heartbeat — Supabase nech vie, že replika žije
        await self._reg.heartbeat(self._g.replica_name)

    async def shutdown(self) -> None:
        """Zastaví všetky runnery a pustí celý lease repliky."""
        for mid, (runner, task) in list(self._running.items()):
            log.info("model %s: shutdown — zastavujem", mid)
            await runner.stop()
            task.cancel()
        self._running.clear()
        await self._reg.release_all(self._g.replica_name)


async def run() -> None:
    from config import Config
    from registry import Registry
    from transport import SupabaseTransport

    cfg = Config.from_env()
    transport = SupabaseTransport(cfg.supabase_url, cfg.supabase_key)
    registry = Registry(transport)
    pool = Pool(registry=registry, transport=transport, global_cfg=cfg)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # `add_signal_handler` nie je podporovaný všade (Windows) — v produkcii
        # (Linux/Railway) vždy funguje, nech testovacie/iné prostredia nepadajú.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    log.info(
        "replika %s: štart, max_tenants=%d, claim_interval_s=%d",
        cfg.replica_name, cfg.max_tenants, cfg.claim_interval_s,
    )
    try:
        while not stop.is_set():
            try:
                await pool.tick()
            except Exception:  # noqa: BLE001 — výpadok Supabase nesmie zhodiť proces
                log.exception("tick zlyhal — skúšam ďalej")
            try:
                await asyncio.wait_for(stop.wait(), timeout=cfg.claim_interval_s)
            except asyncio.TimeoutError:
                pass
    finally:
        log.info("replika %s: shutdown", cfg.replica_name)
        await pool.shutdown()


def main() -> None:
    _setup_logging()
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Ukončené používateľom")


if __name__ == "__main__":
    main()
