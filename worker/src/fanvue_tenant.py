"""Fanvue pre jedného tenanta — dátová vrstva a spustenie agenta.

Šablóna (`/Users/marek/telegram`) mala Fanvue ako SAMOSTATNÚ službu: jeden
proces = jedna modelka = jedna DB schéma (`main_fanvue.py` + `FanvueDb`
s hlavičkami Accept-Profile). V Telepipe beží desiatky modeliek jeden worker
a všetky tabuľky sú v `public` s rozlišovacím `model_id`, takže sa Fanvue
pripája k bežiacemu tenantovi ako ďalšia úloha v tom istom event loope.

`TenantFanvueDb` je preto adaptér: navonok vyzerá ako `fanvue_api.FanvueDb`
(rovnaké mená metód, rovnaké tvary návratových hodnôt), vnútri chodí cez
zdieľaný `SupabaseTransport` a KAŽDÝ dotaz nesie `model_id`.

ŠIFROVACÍ SEAM
--------------
`fanvue_api.Fanvue` (portovaný bez jedinej zmeny) číta `row["access_token"]`
a zapisuje `{"access_token": …}` — teda čistý text. V Telepipe sú tokeny v DB
šifrované (`access_token_enc` / `refresh_token_enc`, AES-256-GCM, rovnaký
`ENCRYPTION_KEY` ako `models.tg_session_enc`). Dešifruje sa preto presne tu, na
hranici čítania a zápisu:

  settings()  →  *_enc z DB  →  dešifrované `access_token` / `refresh_token`
  save()      →  `access_token` / `refresh_token`  →  zašifrované *_enc

Prečo tu a nie inde:
  * `TenantDb` (db.py) kľúč nemá a nemá ho ani prečo mať — Telegram tabuľky
    nič šifrované neobsahujú;
  * `TenantConfig` je zložený z riadku `models` a kľúč (globálny) v ňom nie je;
  * `Config.encryption_key` je globálny a runner ho už drží (`self._g`), takže
    ho stačí odovzdať konštruktoru.
Výsledok: fanvue_api.py ani fanvue_agent.py sa nemuseli dotknúť — porting
kontrakt ostal neporušený a plaintext token neopustí tento súbor smerom do DB.

ROZSAH FÁZY 3.1
---------------
Táto fáza prináša pripojenie účtu a frontu udalostí. Dátová vrstva odpisovania
(`fv_users`, `fv_messages`, `fv_folders`, `fv_media`, `fv_media_sends`) príde vo
fáze 3.2 — metódy, ktoré ju potrebujú, sú nižšie zámerne `NotImplementedError`
s menom chýbajúcej tabuľky, nie ticho prázdne. `start_fanvue` sa k nim navyše
nedostane: agent sa spúšťa len keď je `fanvue.enabled` true, a to je stĺpec bez
klientského grantu s defaultom false. Kým je vypnutý, udalosti sa vo fronte
kopia — namiesto toho, aby ich prázdny agent označil za vybavené a zahodil.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from crypto import decrypt, encrypt

log = logging.getLogger(__name__)

FANVUE = "/fanvue"
EVENTS = "/fanvue_events"
PERSONA = "/persona"
BEHAVIOR = "/behavior"
USERS = "/dm_users"
MESSAGES = "/dm_messages"
FACTS = "/facts"

# `fanvue_agent` číta `event["type"]`, v DB je stĺpec `event_type` (aby sa
# nebilo s rezervovaným slovom a sedelo to s webhookom). PostgREST vie stĺpec
# premenovať priamo v selecte, takže agent o rozdiele nevie.
EVENT_SELECT = "id,type:event_type,payload,created_at"


class TenantFanvueDb:
    """Fanvue tabuľky jednej modelky. Rozhranie kopíruje `fanvue_api.FanvueDb`."""

    def __init__(self, transport, model_id: str, encryption_key: str) -> None:
        self._t = transport
        self.model_id = model_id
        self._key = encryption_key

    @property
    def _mine(self) -> str:
        """Hodnota filtra `model_id` — píše sa v každom dotaze, nech je to vidieť."""
        return f"eq.{self.model_id}"

    async def close(self) -> None:
        """Spojenie patrí poolu (main.py), tu sa nezatvára nič."""

    async def _get(self, path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        return await self._t._get(path, params)

    async def _patch(self, path: str, params: Dict[str, str], body: Dict[str, Any]) -> None:
        await self._t._patch(path, params, body)

    # ---------- nastavenia a tokeny ----------

    async def settings(self) -> Dict[str, Any]:
        """Riadok `fanvue` s DEŠIFROVANÝMI tokenmi.

        Von ide `access_token` / `refresh_token` (čistý text, ako to čaká
        portovaný `fanvue_api.Fanvue`); `*_enc` sa do výsledku nedostanú vôbec,
        aby ich nikto omylom nepovažoval za použiteľné.
        """
        rows = await self._get(FANVUE, {"model_id": self._mine, "select": "*"})
        if not rows:
            return {}
        row = dict(rows[0])
        row["access_token"] = self._plain(row.pop("access_token_enc", ""), "access_token")
        row["refresh_token"] = self._plain(row.pop("refresh_token_enc", ""), "refresh_token")
        return row

    async def save(self, patch: Dict[str, Any]) -> None:
        """Zápis do `fanvue`. Tokeny sa cestou zašifrujú."""
        body = dict(patch)
        for plain, sealed in (
            ("access_token", "access_token_enc"),
            ("refresh_token", "refresh_token_enc"),
        ):
            if plain in body:
                value = body.pop(plain) or ""
                body[sealed] = encrypt(str(value), self._key) if value else ""
        body["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._patch(FANVUE, {"model_id": self._mine}, body)

    def _plain(self, sealed: Any, label: str) -> str:
        """Dešifruje token; poškodený/cudzím kľúčom zapísaný nezhodí agenta.

        Prázdny reťazec znamená „nemáme token" a `fanvue_api` na to reaguje
        vypýtaním nového cez refresh, prípadne zrozumiteľnou chybou. To je
        lepšie než pád v strede kola.
        """
        text = str(sealed or "")
        if not text:
            return ""
        try:
            return decrypt(text, self._key)
        except Exception:  # noqa: BLE001 - zlý kľúč nesmie zhodiť tenanta
            log.error("model %s: %s sa nedá dešifrovať", self.model_id, label)
            return ""

    # ---------- fronta udalostí ----------

    async def pending(self, limit: int = 20) -> List[Dict[str, Any]]:
        return await self._get(
            EVENTS,
            {
                "model_id": self._mine,
                "processed_at": "is.null",
                "select": EVENT_SELECT,
                "order": "id.asc",
                "limit": str(limit),
            },
        )

    async def mark_handled(self, event_id: int) -> None:
        await self._patch(
            EVENTS,
            {"model_id": self._mine, "id": f"eq.{event_id}"},
            {"processed_at": datetime.now(timezone.utc).isoformat()},
        )

    # ---------- most do Telegramu ----------

    async def persona(self) -> Dict[str, Any]:
        rows = await self._get(PERSONA, {"model_id": self._mine, "select": "*"})
        return rows[0] if rows else {}

    async def behavior(self) -> Dict[str, Any]:
        """Chovanie modelky — najmä časová zóna, v ktorej vraj žije.

        Fanvue má vlastné časy odpisovania, ale zóna je vlastnosť tej osoby,
        nie platformy: keď je v Los Angeles noc, je noc na oboch miestach.
        """
        rows = await self._get(BEHAVIOR, {"model_id": self._mine, "select": "*"})
        return rows[0] if rows else {}

    async def linked_tg_ids(self) -> set:
        """Telegram id, ktoré už patria nejakému fanúšikovi.

        Fáza 3.2: kým `fv_users` neexistuje, nie je spárovaný nikto — prázdna
        množina je správna odpoveď, nie výpadok.
        """
        return set()

    async def link_candidates(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Konverzácie, z ktorých mohol prísť — komu odišiel odkaz."""
        return await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "tg_id,first_name,username,link_sent_at,funnel_stage",
                "order": "last_incoming_at.desc.nullslast",
                "limit": str(limit),
            },
        )

    async def telegram_context(self, tg_id: int) -> Dict[str, Any]:
        """Čo o ňom vieme z Telegramu — meno, zhrnutie, fakty.

        Toto je celý dôvod, prečo sa lead spája cez `client_reference_id`:
        na Fanvue nezačína od nuly, ale nadväzuje tam, kde prestali.
        """
        out: Dict[str, Any] = {}
        users = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "first_name,summary,msg_count,paid",
            },
        )
        if users:
            out["user"] = users[0]
        out["facts"] = await self._get(
            FACTS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "key,value",
                "order": "id.desc",
                "limit": "25",
            },
        )
        msgs = await self._get(
            MESSAGES,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "role,content",
                "order": "id.desc",
                "limit": "10",
            },
        )
        out["recent"] = list(reversed(msgs))
        return out

    # ---------- fáza 3.2: dátová vrstva odpisovania ----------
    #
    # Tabuľky fv_users / fv_messages / fv_folders / fv_media / fv_media_sends
    # zatiaľ neexistujú. Radšej hlučné `NotImplementedError` než dotaz, ktorý
    # PostgREST odmietne nezrozumiteľným PGRST205 — a hlavne než ticho vrátené
    # prázdno, po ktorom by agent odpísal do prázdna.

    @staticmethod
    def _later(table: str):
        raise NotImplementedError(
            f"Fanvue tabuľka `{table}` pribudne vo fáze 3.2 (odpisovanie na Fanvue)."
        )

    async def fan(self, fan_uuid: str) -> Optional[Dict[str, Any]]:
        self._later("fv_users")

    async def upsert_fan(self, fan_uuid: str, patch: Dict[str, Any]) -> None:
        self._later("fv_users")

    async def update_fan(self, fan_uuid: str, patch: Dict[str, Any]) -> None:
        self._later("fv_users")

    async def add_message(
        self, fan_uuid: str, role: str, content: str, message_uuid: str = ""
    ) -> None:
        self._later("fv_messages")

    async def add_messages(self, fan_uuid: str, rows: List[Dict[str, str]]) -> None:
        self._later("fv_messages")

    async def known_message_uuids(self, fan_uuid: str, limit: int = 200) -> set:
        self._later("fv_messages")

    async def history(self, fan_uuid: str, limit: int = 16) -> List[Dict[str, str]]:
        self._later("fv_messages")

    async def folders(self) -> List[Dict[str, Any]]:
        self._later("fv_folders")

    async def save_folder(self, name: str, patch: Dict[str, Any]) -> None:
        self._later("fv_folders")

    async def upsert_media(self, rows: List[Dict[str, Any]]) -> None:
        self._later("fv_media")

    async def media_in(self, folder: str) -> List[Dict[str, Any]]:
        self._later("fv_media")

    async def all_media(self) -> List[Dict[str, Any]]:
        self._later("fv_media")

    async def update_media(self, media_uuid: str, patch: Dict[str, Any]) -> None:
        self._later("fv_media")

    async def sent_media(self, fan_uuid: str) -> set:
        self._later("fv_media_sends")

    async def record_send(self, media_uuid: str, fan_uuid: str, price_cents: int) -> None:
        self._later("fv_media_sends")


# ---------------------------------------------------------------------------
# Spustenie agenta vedľa Telegramu
# ---------------------------------------------------------------------------


async def start_fanvue(cfg, g, transport, llm, cleanup: list) -> Optional[asyncio.Task]:
    """Spustí Fanvue agenta pre tenanta, ak má prečo bežať. Inak vráti None.

    Podmienky (všetky musia platiť):
      * worker vie o Fanvue appke (FANVUE_CLIENT_ID + FANVUE_CLIENT_SECRET),
      * modelka má pripojený účet (`fanvue.connected`),
      * odpisovanie na Fanvue je zapnuté (`fanvue.enabled`) — do fázy 3.2
        vypnuté, viď hlavička súboru.

    `llm` je ten istý `MeteredLlm` ako pre Telegram — Fanvue tak platí z toho
    istého kreditu a bez zostatku sa neodpisuje ani tam. Úloha aj HTTP klient
    idú do `cleanup`, ktorý runner odbaví pri `stop()`.

    Nič sa tu nechytá: volajúci (runner) to obaľuje `try/except` presne ako
    kontrolného bota — Fanvue nesmie zhodiť odpisovanie na Telegrame.
    """
    if not (getattr(g, "fanvue_client_id", "") and getattr(g, "fanvue_client_secret", "")):
        log.debug("model %s: Fanvue appka nie je nastavená — preskakujem", cfg.model_id)
        return None

    from fanvue_agent import FanvueAgent
    from fanvue_api import Fanvue

    db = TenantFanvueDb(transport, cfg.model_id, g.encryption_key)
    row = await db.settings()
    if not row.get("connected"):
        return None
    if not row.get("enabled"):
        log.info("model %s: Fanvue pripojený, odpisovanie vypnuté", cfg.model_id)
        return None

    api = Fanvue(db, g.fanvue_client_id, g.fanvue_client_secret)
    task = asyncio.create_task(FanvueAgent(db, api, llm).run())
    # Poradie je dôležité: `_drain_cleanup` ide zoznamom odpredu, takže sa
    # najprv zruší úloha a až potom sa zatvorí klient, ktorý používa.
    cleanup.append(task)
    cleanup.append(api)
    log.info("model %s: Fanvue agent beží ako @%s", cfg.model_id, row.get("handle") or "?")
    return task
