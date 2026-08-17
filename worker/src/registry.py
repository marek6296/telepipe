"""Globálne operácie nad Supabase — lease, ledger, cenník, stav modelov."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from transport import SupabaseTransport

MODELS = "/models"
PRICING = "/pricing"
WORKER_REPLICAS = "/worker_replicas"

PRICING_TTL_SECONDS = 300


class Registry:
    """Globálne operácie — lease, ledger, cenník, stav modelov."""

    def __init__(self, transport: SupabaseTransport) -> None:
        self._t = transport
        self._pricing_cache: Dict[str, Dict[str, Any]] = {}
        self._pricing_loaded_at: Optional[float] = None

    # ---------- lease ----------

    async def claim(self, replica: str, capacity: int) -> List[Dict[str, Any]]:
        rows = await self._t._rpc("claim_models", {"p_replica": replica, "p_capacity": capacity})
        return rows or []

    async def heartbeat(self, replica: str) -> None:
        await self._t._rpc("heartbeat_models", {"p_replica": replica})

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
