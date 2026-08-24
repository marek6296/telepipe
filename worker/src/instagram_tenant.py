"""Instagram tabuľky jednej modelky.

Rovnaká úloha ako `fanvue_tenant.TenantFanvueDb`, len pre tretiu platformu:
každý dotaz nesie `model_id`, aby sa dve modelky nikdy nevideli navzájom.

TOKEN SA DEŠIFRUJE AŽ TU, na hranici čítania. Von ide čistý text, ktorý ide
rovno do volania Instagramu — nikde inde v procese nemá čo robiť.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from crypto import decrypt

log = logging.getLogger(__name__)

INSTAGRAM = "/instagram"
IG_USERS = "/ig_users"
IG_MESSAGES = "/ig_messages"
PERSONA = "/persona"
BEHAVIOR = "/behavior"


class TenantInstagramDb:
    """Instagram dáta jednej modelky. Rozhranie kopíruje `TenantFanvueDb`."""

    def __init__(self, transport, model_id: str, encryption_key: str) -> None:
        self._t = transport
        self.model_id = model_id
        self._key = encryption_key

    @property
    def _mine(self) -> str:
        """Hodnota filtra `model_id` — píše sa v každom dotaze, nech je to vidieť."""
        return f"eq.{self.model_id}"

    async def _get(self, path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        return await self._t._get(path, params)

    async def _patch(self, path: str, params: Dict[str, str], body: Dict[str, Any]) -> None:
        await self._t._patch(path, params, body)

    async def _post(self, path: str, body: Any, upsert: bool = False) -> None:
        await self._t._post(path, body, upsert=upsert)

    # ---------- pripojenie a nastavenia ----------

    async def settings(self) -> Dict[str, Any]:
        """Riadok `instagram` aj s dešifrovaným tokenom.

        Prázdny slovník znamená „modelka Instagram nemá" — nie chybu. Volajúci
        na to reaguje tak, že agenta ani nespustí.
        """
        rows = await self._get(INSTAGRAM, {"model_id": self._mine, "select": "*"})
        if not rows:
            return {}
        row = dict(rows[0])
        row["access_token"] = self._token(row.pop("access_token_enc", ""))
        return row

    def _token(self, sealed: Any) -> str:
        """Dešifruje token; poškodený nezhodí agenta.

        Prázdny reťazec znamená „nemáme token" a agent sa v tom kole ani
        nespustí — to je lepšie než pád v strede kola.
        """
        text = str(sealed or "")
        if not text:
            return ""
        try:
            return decrypt(text, self._key)
        except Exception:  # noqa: BLE001 - zlý kľúč nesmie zhodiť tenanta
            log.error("model %s: Instagram token sa nedá dešifrovať", self.model_id)
            return ""

    async def save(self, patch: Dict[str, Any]) -> None:
        await self._patch(INSTAGRAM, {"model_id": self._mine}, patch)

    # ---------- persona (spoločná so všetkými agentmi) ----------

    async def persona(self) -> Dict[str, Any]:
        rows = await self._get(PERSONA, {"model_id": self._mine, "select": "*"})
        return dict(rows[0]) if rows else {}

    async def behavior(self) -> Dict[str, Any]:
        rows = await self._get(BEHAVIOR, {"model_id": self._mine, "select": "*"})
        return dict(rows[0]) if rows else {}

    # ---------- ľudia ----------

    async def user(self, igsid: str) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            IG_USERS, {"model_id": self._mine, "igsid": f"eq.{igsid}", "select": "*"}
        )
        return dict(rows[0]) if rows else None

    async def ensure_user(self, igsid: str, username: str = "") -> Dict[str, Any]:
        existujuci = await self.user(igsid)
        if existujuci:
            # Meno sa mohlo medzitým objaviť (v prvej správe ho Instagram
            # nemusí dať) — doplní sa, ale nikdy sa neprepíše na prázdne.
            if username and not (existujuci.get("username") or ""):
                await self.update_user(igsid, {"username": username})
                existujuci["username"] = username
            return existujuci

        await self._post(
            IG_USERS,
            {"model_id": self.model_id, "igsid": igsid, "username": username},
            upsert=True,
        )
        return (await self.user(igsid)) or {
            "model_id": self.model_id,
            "igsid": igsid,
            "username": username,
            "msg_count": 0,
            "pointed_count": 0,
        }

    async def update_user(self, igsid: str, patch: Dict[str, Any]) -> None:
        await self._patch(
            IG_USERS, {"model_id": self._mine, "igsid": f"eq.{igsid}"}, patch
        )

    # ---------- správy ----------

    async def known_mids(self, igsid: str, limit: int = 60) -> set:
        """Ktoré správy už v histórii máme.

        Konverzácie sa ťahajú opakovane, takže bez tohto by tá istá správa
        pribudla do histórie pri každom kole a modelka by na ňu odpovedala znova.
        """
        rows = await self._get(
            IG_MESSAGES,
            {
                "model_id": self._mine,
                "igsid": f"eq.{igsid}",
                "select": "mid",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
        return {str(r.get("mid") or "") for r in rows if r.get("mid")}

    async def add_message(self, igsid: str, role: str, content: str, mid: str = "") -> None:
        await self._post(
            IG_MESSAGES,
            {
                "model_id": self.model_id,
                "igsid": igsid,
                "mid": mid,
                "role": role,
                "content": content[:4000],
            },
        )

    async def history(self, igsid: str, limit: int = 16) -> List[Dict[str, str]]:
        """Posledných `limit` správ, od najstaršej — v tvare pre LLM."""
        rows = await self._get(
            IG_MESSAGES,
            {
                "model_id": self._mine,
                "igsid": f"eq.{igsid}",
                "select": "role,content,created_at",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )
        return [
            {"role": str(r.get("role") or "user"), "content": str(r.get("content") or "")}
            for r in reversed(rows)
        ]
