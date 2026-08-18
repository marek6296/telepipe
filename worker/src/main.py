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
  4. pošle heartbeat a podľa jeho odpovede zastaví tenantov, ktorých už
     nevlastní (fencing — viď `Pool._fence`).

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
from datetime import datetime, timezone

log = logging.getLogger("main")

# Typy agentov, pre ktoré táto replika má beh (`TenantRunner` + Telethon).
#
# Prvou obranou je `claim_models` (migrácia 018) — RPC filtruje na
# `model_type = 'persona'` a iný typ replike vôbec nepridelí. Toto je druhá:
# keby sa filter niekedy stratil pri úprave RPC, riadok firemného agenta by tu
# naštartoval dievčenský runner a ten by odpisoval firemným zákazníkom
# personou. Radšej nech nebeží nič, než nesprávna vec.
#
# Keď pribudne firemný/osobný agent, dostane VLASTNÝ pool a vlastné napojenie
# na claim (parameter typu do RPC alebo vlastná claim funkcia) — nie ďalšiu
# vetvu tu. Jeden pool = jeden typ.
RUNNABLE_MODEL_TYPES = frozenset({"persona"})

# Riadok bez `model_type` je starý riadok, nie firemný agent. Chýbajúcu hodnotu
# preto berieme ako `persona`: keby sa replika nasadila skôr než migrácia,
# opačná voľba by zastavila všetko, čo beží.
DEFAULT_MODEL_TYPE = "persona"


def _model_type(row) -> str:
    return (row.get("model_type") or DEFAULT_MODEL_TYPE) if row else DEFAULT_MODEL_TYPE


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _reap(task: asyncio.Task) -> None:
    """Počká na zrušenú úlohu, nech nekričí „Task exception was never retrieved".

    Zrušenie samo o sebe nestačí — kým sa výsledok neprevezme, asyncio pri
    zbere pamäte vypíše varovanie o neprevzatej výnimke. Dôvod pádu tu už
    nikoho nezaujíma, runner si ho zalogoval sám.
    """
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


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
        # Monitoring repliky: čas štartu procesu sa posiela len pri prvom
        # úspešnom upserte (viď `Registry.upsert_replica`).
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._replica_registered = False

    async def tick(self) -> None:
        """Jeden cyklus claim slučky. Nikdy nehádže ďalej — chyby sa logujú."""
        # 1. modely, ktoré prestali byť active (alebo zmizli), sa zastavia
        for mid in list(self._running):
            row = await self._reg.model_row(mid)
            # Typ sa po založení nemení (DB naň nedáva update grant), ale ak by
            # sa raz zmenil pod bežiacim runnerom, platí to isté čo pri claime:
            # cudzí typ nesmie ďalej bežať na tomto poole.
            if (
                not row
                or row.get("status") != "active"
                or _model_type(row) not in RUNNABLE_MODEL_TYPES
            ):
                runner, task = self._running.pop(mid)
                log.info("model %s: lease/stav už nesedí — zastavujem", mid)
                await runner.stop()
                task.cancel()
                await _reap(task)
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
                typ = _model_type(row)
                if typ not in RUNNABLE_MODEL_TYPES:
                    # Sem sa to nemá ako dostať, kým `claim_models` filtruje.
                    # Ak sa dostalo, je rozbitá RPC — lease pustíme a runner
                    # NEštartujeme (žiadna Telethon session na cudzom type).
                    log.error(
                        "model %s: typ %r nemá v tejto replike beh — nespúšťam, "
                        "vraciam lease (claim_models by ho nemala dávať)", mid, typ,
                    )
                    await self._reg.release(mid)
                    continue
                try:
                    cfg = self._tenant_factory(row, self._g)
                except Exception as exc:
                    # `BadModelRow` nesie názov stĺpca — nech sa dá príčina
                    # prečítať z jedného riadku logu aj zo `status_reason`,
                    # bez chodenia do databázy. Bez toho sa 2026-08-18 hľadalo
                    # ručne, prečo klientov model padol na `int(None)`.
                    field = getattr(exc, "field", "")
                    reason = f"bad_config:{field}" if field else "bad_config"
                    log.exception(
                        "model %s: neplatný riadok (%s) — odstavujem", mid, reason,
                    )
                    try:
                        await self._reg.set_status(mid, "error", reason)
                    except Exception:  # noqa: BLE001 — nesmie zhodiť tick
                        log.exception("model %s: set_status zlyhal", mid)
                    await self._reg.release(mid)
                    continue
                runner = self._runner_factory(cfg, self._g, self._reg, self._transport)
                task = asyncio.create_task(runner.run())
                self._running[mid] = (runner, task)
                log.info("model %s: runner naštartovaný", mid)

        # 4. heartbeat — Supabase nech vie, že replika žije, a nech povie,
        #    ktorých tenantov ešte naozaj vlastní (fencing, viď nižšie)
        owned = await self._reg.heartbeat(self._g.replica_name)
        await self._fence(owned)

        # 5. stav repliky pre admin monitor (worker_replicas). Zlyhanie
        #    monitoringu nesmie zhodiť tick — replika beží aj bez neho, len ju
        #    admin uvidí ako stale.
        try:
            await self._reg.upsert_replica(
                self._g.replica_name,
                len(self._running),
                started_at=None if self._replica_registered else self._started_at,
            )
            self._replica_registered = True
        except Exception:  # noqa: BLE001 — monitoring nie je kritická cesta
            log.exception("upsert do worker_replicas zlyhal")

    async def _fence(self, owned) -> None:
        """Zastaví runnery tenantov, ktorých už replika nevlastní.

        PREČO TO TREBA
        Lease expiruje po 90 s bez heartbeatu, ale replika, ktorá heartbeat
        nestihla, nemusí byť mŕtva — stačí zaseknutá sieť alebo dlhé GC.
        `claim_models` medzitým tenanta pridelí inej replike a tá spustí
        vlastnú Telethon session. Dve sessions na jednom Telegram účte je
        presne ten scenár, pred ktorým sa všade inde chránime, len tu doteraz
        nikto nekontroloval, či heartbeat vôbec niečo obnovil.

        `heartbeat_models` (migrácia 016) preto vracia id riadkov, ktoré
        skutočne osviežila. Čo v nich nie je, patrí niekomu inému.

        `None` = RPC nič nepovedala (staršia verzia funkcie počas rolloutu) —
        vtedy sa nerobí nič, lebo „neviem" nesmie znamenať „zastav všetko".

        Lease sa tu ZÁMERNE nepúšťa (`release`): riadok už patrí inej replike
        a `claimed_by = null` by jej ho vzal spod rúk.
        """
        if owned is None:
            return
        for mid in list(self._running):
            if mid in owned:
                continue
            runner, task = self._running.pop(mid)
            log.warning(
                "model %s: lease prevzala iná replika — zastavujem, nech nebežia "
                "dve sessions na jednom účte", mid,
            )
            with contextlib.suppress(Exception):
                await runner.stop()
            task.cancel()
            await _reap(task)

    async def shutdown(self) -> None:
        """Zastaví všetky runnery a pustí celý lease repliky."""
        for mid, (runner, task) in list(self._running.items()):
            log.info("model %s: shutdown — zastavujem", mid)
            await runner.stop()
            task.cancel()
            await _reap(task)
        self._running.clear()
        await self._reg.release_all(self._g.replica_name)


async def _pricing_sync_loop(cfg, transport, registry, stop: asyncio.Event) -> None:
    """Background task: denný sync cien z Atlas Billing API + stráženie zostatku.

    Vypnuté (PRICING_SYNC_HOURS=0) alebo bez LLM kľúča → nič nerobí. Prvý beh
    je ~60s po štarte (nech nespomaľuje boot), ďalej v intervale
    `pricing_sync_hours`. Chyba v jednom cykle nesmie zhodiť pool — sync_pricing
    aj check_atlas_balance sú samy o sebe fail-open, ale cyklus je obalený
    ešte raz navyše pre istotu.
    """
    if cfg.pricing_sync_hours <= 0 or not cfg.llm_key:
        return

    from pricing_sync import check_atlas_balance, sync_pricing

    try:
        await asyncio.wait_for(stop.wait(), timeout=60)
        return  # stop prišiel skôr než prvý beh — koniec
    except asyncio.TimeoutError:
        pass

    while not stop.is_set():
        try:
            await sync_pricing(transport, registry, cfg.llm_key)
            await check_atlas_balance(cfg.llm_key, cfg.atlas_balance_alert_usd)
        except Exception:  # noqa: BLE001 — cyklus nesmie zhodiť pool
            log.exception("pricing sync cyklus zlyhal — skúšam nabudúce")
        try:
            await asyncio.wait_for(stop.wait(), timeout=cfg.pricing_sync_hours * 3600)
        except asyncio.TimeoutError:
            pass


async def _login_jobs_loop(cfg, transport, stop: asyncio.Event) -> None:
    """Background task: fronta Telegram loginov z webu (`tg_login_jobs`).

    Web (Next.js) MTProto nevie, takže wizard odloží prácu do DB a spraví ju
    tento poller. Interval je v sekundách — používateľ pri wizarde čaká na
    „kód odoslaný"/„prihlásené". LOGIN_JOBS_POLL_S=0 poller vypne.
    `poll_once` si chyby jednotlivých jobov rieši sama; obal je pre prípad, že
    padne samotný výber z fronty (výpadok Supabase) — pool to nesmie zhodiť.
    """
    if cfg.login_jobs_poll_s <= 0:
        return

    import login_jobs

    while not stop.is_set():
        try:
            await login_jobs.poll_once(transport, cfg.encryption_key)
        except Exception:  # noqa: BLE001 — cyklus nesmie zhodiť pool
            log.exception("login jobs poll zlyhal — skúšam nabudúce")
        try:
            await asyncio.wait_for(stop.wait(), timeout=cfg.login_jobs_poll_s)
        except asyncio.TimeoutError:
            pass


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
    pricing_task = asyncio.create_task(_pricing_sync_loop(cfg, transport, registry, stop))
    login_task = asyncio.create_task(_login_jobs_loop(cfg, transport, stop))
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
        pricing_task.cancel()
        login_task.cancel()
        await _reap(pricing_task)
        await _reap(login_task)
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
