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

ROZSAH FÁZY 3.2
---------------
Fáza 3.1 priniesla pripojenie účtu a frontu udalostí; táto dopĺňa dátovú vrstvu
odpisovania (`fv_users`, `fv_messages`, `fv_folders`, `fv_media`,
`fv_media_sends`, migrácia 012) — teda všetko, čo agent potrebuje, aby vedel
komu, čo a s akou históriou odpisuje. Odpisovanie samo ostáva za vypínačom
`fanvue.enabled` (default false, prepína ho majiteľ v dashboarde): pripojiť účet
a spustiť agenta sú dve vedomé rozhodnutia, nie jedno.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from crypto import decrypt, encrypt
from db import unseal_eleven_key

log = logging.getLogger(__name__)

FANVUE = "/fanvue"
EVENTS = "/fanvue_events"
PERSONA = "/persona"
BEHAVIOR = "/behavior"
USERS = "/dm_users"
MESSAGES = "/dm_messages"
FACTS = "/facts"

FV_USERS = "/fv_users"
FV_MESSAGES = "/fv_messages"
FV_FOLDERS = "/fv_folders"
FV_MEDIA = "/fv_media"
FV_SENDS = "/fv_media_sends"

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

    async def _post(self, path: str, body: Any, upsert: bool = False) -> None:
        await self._t._post(path, body, upsert=upsert)

    def _own(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Riadok na zápis s `model_id`. Zapisuje sa cez service kľúč (RLS
        neplatí), takže tenanta drží iba toto — preto to má vlastné meno a
        prechádza tadiaľ KAŽDÝ zápis, nie len tie, na ktoré si spomenieme."""
        return {"model_id": self.model_id, **row}

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

        Riadok ide cez ten istý ElevenLabs seam ako `TenantDb.get_behavior()` —
        `fvvoice.make()` z neho číta `eleven_key` ako čistý text a hlasovky na
        Fanvue nemajú dôvod fungovať inak než na Telegrame.
        """
        rows = await self._get(BEHAVIOR, {"model_id": self._mine, "select": "*"})
        if not rows:
            return {}
        return unseal_eleven_key(rows[0], self._key, self.model_id)

    async def linked_tg_ids(self) -> set:
        """Telegram id, ktoré už patria nejakému fanúšikovi. Jeden človek
        nemôže byť dvaja.

        Strážcom jednoznačnosti je táto množina (`fanmatch.best(…, taken=…)`),
        nie unikátny index v DB — pozri komentár v migrácii 012.
        """
        rows = await self._get(
            FV_USERS,
            {"model_id": self._mine, "select": "tg_id", "tg_id": "not.is.null"},
        )
        return {int(r["tg_id"]) for r in rows if r.get("tg_id") is not None}

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

    # ---------- fanúšikovia a správy ----------
    #
    # Od tohto miesta nižšie je to tá istá dátová vrstva ako v predlohe
    # (`fanvue_api.FanvueDb`), len s `model_id` v každom filtri aj v každom tele
    # zápisu. Upserty nepotrebujú `on_conflict`: primárne kľúče tabuliek z 012 sú
    # presne tie zložené `(model_id, …)`, ktoré PostgREST odvodí sám.

    async def fan(self, fan_uuid: str) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            FV_USERS,
            {"model_id": self._mine, "fan_uuid": f"eq.{fan_uuid}", "select": "*"},
        )
        return rows[0] if rows else None

    async def upsert_fan(self, fan_uuid: str, patch: Dict[str, Any]) -> None:
        await self._post(FV_USERS, self._own({"fan_uuid": fan_uuid, **patch}), upsert=True)

    async def update_fan(self, fan_uuid: str, patch: Dict[str, Any]) -> None:
        await self._patch(
            FV_USERS, {"model_id": self._mine, "fan_uuid": f"eq.{fan_uuid}"}, patch
        )

    async def add_message(
        self, fan_uuid: str, role: str, content: str, message_uuid: str = ""
    ) -> None:
        """Jedna správa do archívu.

        Predloha tu posielala `Prefer: resolution=merge-duplicates`, keď mala
        `message_uuid` — lenže PK bol `id` (bigserial), takže z toho bol vždy
        obyčajný insert. Zostáva teda insert, a to zámerne: duplicitám bráni
        `known_message_uuids()` v `reconcile`, ktorý najprv zistí, čo už máme.
        """
        row: Dict[str, Any] = {"fan_uuid": fan_uuid, "role": role, "content": content}
        if message_uuid:
            row["message_uuid"] = message_uuid
        await self._post(FV_MESSAGES, self._own(row))

    async def add_messages(self, fan_uuid: str, rows: List[Dict[str, str]]) -> None:
        """Doplnenie viacerých správ naraz. Prázdny zoznam nič nerobí."""
        if rows:
            await self._post(
                FV_MESSAGES, [self._own({"fan_uuid": fan_uuid, **r}) for r in rows]
            )

    async def known_message_uuids(self, fan_uuid: str, limit: int = 200) -> set:
        rows = await self._get(
            FV_MESSAGES,
            {
                "model_id": self._mine,
                "fan_uuid": f"eq.{fan_uuid}",
                "select": "message_uuid",
                "message_uuid": "not.is.null",
                "order": "id.desc",
                "limit": str(limit),
            },
        )
        return {r["message_uuid"] for r in rows if r.get("message_uuid")}

    async def history(self, fan_uuid: str, limit: int = 16) -> List[Dict[str, str]]:
        rows = await self._get(
            FV_MESSAGES,
            {
                "model_id": self._mine,
                "fan_uuid": f"eq.{fan_uuid}",
                "select": "role,content",
                "order": "id.desc",
                "limit": str(limit),
            },
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ---------- obsah z vaultu ----------

    async def folders(self) -> List[Dict[str, Any]]:
        return await self._get(
            FV_FOLDERS, {"model_id": self._mine, "select": "*", "order": "name.asc"}
        )

    async def save_folder(self, name: str, patch: Dict[str, Any]) -> None:
        await self._post(FV_FOLDERS, self._own({"name": name, **patch}), upsert=True)

    async def upsert_media(self, rows: List[Dict[str, Any]]) -> None:
        """Zápis po dávkach. Existujúce si nechajú popis aj cenu — tie sú naše,
        vo vaulte nie sú a prepísať ich synchronizáciou by bola škoda."""
        if rows:
            await self._post(FV_MEDIA, [self._own(r) for r in rows], upsert=True)

    async def media_in(self, folder: str) -> List[Dict[str, Any]]:
        return await self._get(
            FV_MEDIA,
            {
                "model_id": self._mine,
                "folder": f"eq.{folder}",
                "active": "is.true",
                "select": "*",
            },
        )

    async def all_media(self) -> List[Dict[str, Any]]:
        return await self._get(
            FV_MEDIA, {"model_id": self._mine, "select": "*", "order": "folder.asc"}
        )

    async def update_media(self, media_uuid: str, patch: Dict[str, Any]) -> None:
        await self._patch(
            FV_MEDIA, {"model_id": self._mine, "media_uuid": f"eq.{media_uuid}"}, patch
        )

    async def sent_media(self, fan_uuid: str) -> set:
        """Čo už tento človek videl. Dvakrát to isté je najlacnejší spôsob,
        ako sa prezradiť."""
        rows = await self._get(
            FV_SENDS,
            {"model_id": self._mine, "fan_uuid": f"eq.{fan_uuid}", "select": "media_uuid"},
        )
        return {r["media_uuid"] for r in rows}

    async def record_send(self, media_uuid: str, fan_uuid: str, price_cents: int) -> None:
        await self._post(
            FV_SENDS,
            self._own(
                {"media_uuid": media_uuid, "fan_uuid": fan_uuid, "price_cents": price_cents}
            ),
            upsert=True,
        )


# ---------------------------------------------------------------------------
# Spustenie agenta vedľa Telegramu
# ---------------------------------------------------------------------------


async def start_fanvue(cfg, g, transport, llm, cleanup: list) -> Optional[asyncio.Task]:
    """Spustí Fanvue agenta pre tenanta, ak má prečo bežať. Inak vráti None.

    Podmienky (všetky musia platiť):
      * worker vie o Fanvue appke (FANVUE_CLIENT_ID + FANVUE_CLIENT_SECRET),
      * modelka má pripojený účet (`fanvue.connected`),
      * odpisovanie na Fanvue je zapnuté (`fanvue.enabled`) — vypínač
        v dashboarde, default false, viď hlavička súboru.

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
