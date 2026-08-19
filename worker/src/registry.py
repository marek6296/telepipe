"""Globálne operácie nad Supabase — lease, ledger, cenník, stav modelov."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from transport import SupabaseTransport

MODELS = "/models"
PRICING = "/pricing"
APP_CONFIG = "/app_config"
WORKER_REPLICAS = "/worker_replicas"

log = logging.getLogger(__name__)

PRICING_TTL_SECONDS = 300
CONFIG_TTL_SECONDS = 300


class Registry:
    """Globálne operácie — lease, ledger, cenník, stav modelov."""

    def __init__(self, transport: SupabaseTransport) -> None:
        self._t = transport
        self._pricing_cache: Dict[str, Dict[str, Any]] = {}
        self._pricing_loaded_at: Optional[float] = None
        self._config_cache: Dict[str, Dict[str, float]] = {}
        self._config_loaded_at: Optional[float] = None

    # ---------- lease ----------

    async def claim(self, replica: str, capacity: int) -> List[Dict[str, Any]]:
        rows = await self._t._rpc("claim_models", {"p_replica": replica, "p_capacity": capacity})
        return rows or []

    async def heartbeat(self, replica: str) -> Optional[set]:
        """Obnoví lease a vráti množinu modelov, ktoré replika naozaj vlastní.

        `None` = RPC nič nevrátila (staršia verzia funkcie počas rolloutu).
        Volajúci to musí odlíšiť od prázdnej množiny: „neviem" znamená nechať
        bežať, „nevlastním nič" znamená všetko zastaviť.

        Tento návrat je fencing token. Bez neho pomalá (nie mŕtva) replika
        stratí po 90 s lease, iná si tenanta doklaimuje — a pôvodná ho ďalej
        beží. Dve Telethon sessions na jednom účte je presne ten scenár, kvôli
        ktorému účty padajú.
        """
        raw = await self._t._rpc("heartbeat_models", {"p_replica": replica})
        if raw is None:
            return None
        if isinstance(raw, list):
            # `returns setof uuid` chodí z PostgREST ako pole reťazcov; keby to
            # niekedy bolo table-returning, prišli by dicty — pokryjeme oboje.
            out = set()
            for item in raw:
                if isinstance(item, dict):
                    hodnota = item.get("heartbeat_models") or item.get("id")
                else:
                    hodnota = item
                if hodnota:
                    out.add(str(hodnota))
            return out
        return None

    async def release_all(self, replica: str) -> None:
        await self._t._rpc("release_models", {"p_replica": replica})

    async def release(self, model_id: str) -> None:
        await self._t._rpc("release_model", {"p_model": model_id})

    # ---------- monitoring replík ----------

    async def upsert_replica(
        self, replica: str, tenant_count: int, started_at: Optional[str] = None
    ) -> None:
        """Zapíše živý stav repliky do `worker_replicas` (admin monitor).

        `last_seen` posielame explicitne — server default `now()` platí len pri
        inserte a upsert existujúci riadok len updatuje. `started_at` ide do
        tela LEN pri prvom ticku po štarte procesu: PostgREST updatuje výhradne
        stĺpce, ktoré v tele sú, takže ďalšie ticky pôvodný čas štartu nechajú
        tak (admin tak vidí, kedy sa replika naposledy reštartovala).
        """
        row: Dict[str, Any] = {
            "replica_name": replica,
            "tenant_count": tenant_count,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }
        if started_at is not None:
            row["started_at"] = started_at
        await self._t._post(WORKER_REPLICAS, row, upsert=True)

    # ---------- modely ----------

    async def model_row(self, model_id: str) -> Optional[Dict[str, Any]]:
        rows = await self._t._get(MODELS, {"id": f"eq.{model_id}", "select": "*"})
        return rows[0] if rows else None

    async def set_status(self, model_id: str, status: str, reason: str = "") -> None:
        await self._t._patch(
            MODELS, {"id": f"eq.{model_id}"}, {"status": status, "status_reason": reason}
        )

    # ---------- ledger ----------

    async def credit_balance(self, model_id: str) -> float:
        # RPC vráti null, keď účet neexistuje — von musí ísť 0.0, inak by
        # MeteredLlm padol na `None <= 0`. Numeric chodí aj ako string.
        raw = await self._t._rpc("credit_balance", {"p_model": model_id})
        return float(raw or 0)

    async def credit_state(self, model_id: str) -> Tuple[float, bool]:
        """Zostatok + príznak `unlimited` jedným RPC (pred každou odpoveďou).

        `credit_state` je table-returning, takže z PostgREST chodí zoznam
        riadkov; neexistujúci účet = prázdny zoznam. Parsovanie je zámerne
        tolerantné — chýbajúci riadok aj chýbajúci kľúč znamenajú (0.0, False),
        aby MeteredLlm nikdy nedostala None do porovnania. Numeric chodí aj
        ako string, preto float().

        Chybu prenosu (výpadok Supabase) NEPREHLTÁME: 0.0 by tu znamenalo
        „došiel kredit" a modelka by sa kvôli jednému 500-ku pauzla.
        """
        raw = await self._t._rpc("credit_state", {"p_model": model_id})
        row = raw[0] if isinstance(raw, list) and raw else raw
        if not isinstance(row, dict):
            return 0.0, False
        return float(row.get("balance") or 0), bool(row.get("unlimited"))


    # ---------- ceny za kus (hlasovka, fotka) ----------

    async def config(self, key: str, default: float = 0.0) -> Tuple[float, float]:
        """`(cena pre klienta, náš náklad)` z `app_config`, s TTL cache.

        Ceny sú v DB, nie v kóde, lebo tú istú hodnotu potrebuje aj web (musí
        ju napísať skôr, než klient klikne). Dve konštanty v dvoch repozitároch
        by sa raz rozišli a tlačidlo by sľubovalo iné číslo, než sa strhne.

        Výpadok NEPREHLTÁME do nuly — vrátime `default`, aby sa hlasovka radšej
        zaúčtovala za očakávanú cenu, než zadarmo.
        """
        now = time.time()
        if self._config_loaded_at is None or now - self._config_loaded_at > CONFIG_TTL_SECONDS:
            try:
                rows = await self._t._get(APP_CONFIG, {"select": "key,value,our_cost"})
                self._config_cache = {
                    str(r["key"]): {
                        "value": float(r.get("value") or 0),
                        "our_cost": float(r.get("our_cost") or 0),
                    }
                    for r in (rows or [])
                }
                self._config_loaded_at = now
            except Exception:  # noqa: BLE001 — cenník za kus nesmie zhodiť odpoveď
                if not self._config_cache:
                    return float(default), 0.0

        row = self._config_cache.get(key)
        if not row:
            return float(default), 0.0
        return row["value"], row["our_cost"]

    async def charge_unit(
        self, model_id: str, kind: str, key: str, default_price: float
    ) -> None:
        """Zaúčtuje JEDEN kus (hlasovku/fotku) po ÚSPEŠNOM odoslaní.

        Ide tou istou `record_usage` ako tokeny — vďaka tomu platia zľavy
        plánov (`vip` 1:1, `vip_lite` 1.5×) automaticky a ledger má jeden tvar.
        `our_cost` je naša nákupka: pri managed hlase ElevenLabs, pri hlasovke
        cez klientov kľúč a pri fotke nula.

        Zlyhanie zápisu odpoveď NEZHODÍ — správa už odišla, účtovníctvo sa
        dorovná ďalším volaním.
        """
        price, our_cost = await self.config(key, default_price)
        if price <= 0:
            return
        try:
            await self.record_usage(model_id, kind, 0, 0, 1, round(our_cost, 6), round(price, 6))
        except Exception:
            log.exception("Zauctovanie kusu (%s) zlyhalo", kind)

    async def record_usage(
        self,
        model_id: str,
        kind: str,
        in_tok: int,
        out_tok: int,
        units: int,
        atlas_cost: float,
        charged: float,
    ) -> float:
        return await self._t._rpc(
            "record_usage",
            {
                "p_model": model_id,
                "p_kind": kind,
                "p_input_tokens": in_tok,
                "p_output_tokens": out_tok,
                "p_unit_count": units,
                "p_atlas_cost_usd": atlas_cost,
                "p_charged_usd": charged,
            },
        )

    # ---------- cenník ----------

    async def _load_pricing(self) -> None:
        rows = await self._t._get(PRICING, {"select": "*"})
        self._pricing_cache = {row["model_slug"]: row for row in rows}
        self._pricing_loaded_at = time.monotonic()

    async def pricing(self, slug: str) -> Dict[str, Any]:
        stale = (
            self._pricing_loaded_at is None
            or (time.monotonic() - self._pricing_loaded_at) > PRICING_TTL_SECONDS
        )
        if stale:
            await self._load_pricing()
        if slug in self._pricing_cache:
            return self._pricing_cache[slug]
        return self._pricing_cache.get("_default", {})
