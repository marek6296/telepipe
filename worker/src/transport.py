"""Async prístup k Supabase cez REST API (žiadny sync klient v event loope).

Všetky tabuľky žijú vo verejnej (`public`) schéme spoločného projektu — na
rozdiel od šablóny (`telegram`) tu nepotrebujeme Accept-Profile/Content-Profile
hlavičky, lebo nič nie je v neverejnej schéme.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)


class SupabaseTransport:
    def __init__(self, url: str, service_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{url}/rest/v1",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def _patch(self, path: str, params: Dict[str, str], body: Dict[str, Any]) -> None:
        r = await self._client.patch(path, params=params, json=body)
        r.raise_for_status()

    async def _delete(self, path: str, params: Dict[str, str]) -> None:
        """Zmazanie riadkov. Filtre sú POVINNÉ — PostgREST bez nich zmaže tabuľku.

        Volajúci ich vždy dáva (`model_id` + podmienka), takže tu je to len
        poistka: prázdny `params` by bol tichý `delete from …` bez `where`.
        """
        if not params:
            raise ValueError("_delete bez filtra by zmazal celú tabuľku")
        r = await self._client.delete(path, params=params)
        r.raise_for_status()

    async def _post(self, path: str, body: Any, upsert: bool = False) -> List[Dict[str, Any]]:
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        r = await self._client.post(path, json=body, headers={"Prefer": prefer})
        r.raise_for_status()
        return r.json() if r.content else []

    async def _rpc(self, fn: str, args: Dict[str, Any]) -> Any:
        r = await self._client.post(f"/rpc/{fn}", json=args)
        r.raise_for_status()
        return r.json() if r.content else None
