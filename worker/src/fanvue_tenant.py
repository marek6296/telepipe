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
import contextlib
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from crypto import decrypt, encrypt
from db import AccountKeyCache, ScheduleCache, unseal_eleven_key

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
SYNC = "/fanvue_sync_requests"
CONTROL_BOT_SETTINGS = "/control_bot_settings"

# `fanvue_agent` číta `event["type"]`, v DB je stĺpec `event_type` (aby sa
# nebilo s rezervovaným slovom a sedelo to s webhookom). PostgREST vie stĺpec
# premenovať priamo v selecte, takže agent o rozdiele nevie.
EVENT_SELECT = "id,type:event_type,payload,created_at"


class TenantFanvueDb:
    """Fanvue tabuľky jednej modelky. Rozhranie kopíruje `fanvue_api.FanvueDb`."""

    def __init__(
        self, transport, model_id: str, encryption_key: str, account_id: str = ""
    ) -> None:
        self._t = transport
        self.model_id = model_id
        self._key = encryption_key
        # Vlastná cache (nie zdieľaná s `TenantDb`): jeden dotaz za päť minút
        # navyše je lacnejší než previazať dve vrstvy, ktoré sa dnes nepoznajú.
        self._account_key = AccountKeyCache(transport, account_id)
        self._schedule = ScheduleCache(transport, model_id)

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

    async def _delete(self, path: str, params: Dict[str, str]) -> None:
        await self._t._delete(path, params)

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
        return unseal_eleven_key(
            rows[0], self._key, self.model_id, await self._account_key.sealed()
        )

    async def schedule(self) -> Dict[str, Any]:
        """Nastavený deň (migrácia 022). `{}` = platí šablóna z `den`.

        Ten istý dôvod ako pri zóne vyššie: kde práve je, je vlastnosť tej
        osoby, nie platformy. Keď je na fotení, nedvíha to ani na Fanvue.
        """
        return await self._schedule.row()

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
                "select": "tg_id,first_name,username,link_sent_at,link_clicked_at,funnel_stage",
                "order": "last_incoming_at.desc.nullslast",
                "limit": str(limit),
            },
        )

    async def control_bot_settings(self) -> Dict[str, Any]:
        """Čo má control bot hlásiť. Prázdny slovník = platia defaulty z `oznamy`.

        Je to tá istá tabuľka aj to isté správanie ako v `db.TenantDb` — Fanvue
        agent posiela majiteľovi notifikácie o platbách a odberoch a musí sa
        pýtať na to isté miesto ako telegramová vetva.

        Chýbajúci riadok NIE JE chyba: modelka mohla vzniknúť pred migráciou,
        ktorá tabuľku pridala. Vtedy je lepšie hlásiť podľa rozumného základu
        než nehlásiť nič.
        """
        try:
            rows = await self._get(
                CONTROL_BOT_SETTINGS, {"model_id": self._mine, "select": "*"}
            )
        except Exception:  # noqa: BLE001 — notifikácie nesmú zhodiť odpisovanie
            log.exception("nastavenia control bota sa nepodarilo načítať")
            return {}
        return rows[0] if rows else {}

    async def get_user(self, tg_id: int) -> Optional[Dict[str, Any]]:
        """Telegramová konverzácia podľa id. `None` = takú nemáme.

        Fanvue agent ju potrebuje, keď platbu spojí s Telegramom: notifikácia
        má povedať MENOM, z ktorého chatu ten predplatiteľ prišiel.
        """
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{int(tg_id)}",
                "select": "tg_id,username,first_name,partner_name,paid,funnel_stage",
            },
        )
        return rows[0] if rows else None

    async def update_user(self, tg_id: int, patch: Dict[str, Any]) -> None:
        """Zmena telegramovej konverzácie z Fanvue strany.

        Používa sa na jedinú vec: kto zaplatil na Fanvue, prestáva byť
        v Telegrame lead. Bez toho by mu modelka ďalej pripomínala stránku,
        ktorú si práve kúpil, a po skončení okna by ho ešte aj odstrihla.
        """
        await self._patch(
            USERS, {"model_id": self._mine, "tg_id": f"eq.{int(tg_id)}"}, patch
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

    async def has_media(self) -> bool:
        """Je v trezore vôbec niečo? Jeden riadok stačí — nepočítame, pýtame sa.

        Bez tejto otázky prompt sľuboval obsah, ktorý neexistuje.
        """
        rows = await self._get(
            FV_MEDIA, {"model_id": self._mine, "select": "media_uuid", "limit": "1"}
        )
        return bool(rows)

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

    # ---------- fronta „načítaj vault" ----------
    #
    # Dashboard nemá ako vault načítať sám: prístupový token je šifrovaný a
    # dešifrovací seam je tento súbor. Web preto len vloží riadok do
    # `fanvue_sync_requests` (smie vyplniť jediný stĺpec, `model_id` — migrácia
    # 015) a `fvvault.VaultSync` si ho tu vyberie.

    async def pending_sync(self) -> Optional[Dict[str, Any]]:
        """Najstaršia nedokončená požiadavka. None = fronta je prázdna."""
        rows = await self._get(
            SYNC,
            {
                "model_id": self._mine,
                "finished_at": "is.null",
                "select": "id,requested_at,started_at",
                "order": "id.asc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def start_sync(self, request_id: int) -> None:
        await self._patch(
            SYNC,
            {"model_id": self._mine, "id": f"eq.{request_id}"},
            {"started_at": datetime.now(timezone.utc).isoformat()},
        )

    async def finish_sync(
        self,
        request_id: int,
        ok: bool,
        folders: int = 0,
        media_new: int = 0,
        media_seen: int = 0,
        error: str = "",
    ) -> None:
        """Uzavretie požiadavky. Píše sa aj po zlyhaní.

        `finished_at is null` je zároveň zámok (partial unique index z 015):
        keby sa neúspešná požiadavka nechala otvorená, tlačidlo v dashboarde
        by ostalo zablokované aj pre ďalšie pokusy.
        """
        await self._patch(
            SYNC,
            {"model_id": self._mine, "id": f"eq.{request_id}"},
            {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "ok": bool(ok),
                "folders": int(folders),
                "media_new": int(media_new),
                "media_seen": int(media_seen),
                "error": str(error or "")[:400],
            },
        )

    async def prune_sync(self, older_than_h: int = 24) -> None:
        """Zmaže dobehnuté požiadavky staršie než `older_than_h`.

        Fronta je krátkodobá pracovná pamäť: dashboard z nej číta jedinú vec —
        ako dopadol POSLEDNÝ klik. Riadok spred týždňa už nikto neuvidí, ale
        pri modelke, ktorá synchronizuje denne, by tabuľka rástla donekonečna
        (nikto ju doteraz nemazal). Nedokončené riadky sa NEmažú ani keď sú
        staré — `finished_at is null` je zámok tlačidla a jeho tiché zmiznutie
        by zamaskovalo zaseknutú synchronizáciu.
        """
        hranica = datetime.now(timezone.utc) - timedelta(hours=max(1, int(older_than_h)))
        await self._delete(
            SYNC,
            {
                "model_id": self._mine,
                "finished_at": f"lt.{hranica.isoformat()}",
            },
        )

    async def mark_vault_synced(self) -> None:
        """Kedy naposledy vault dobehol. Ide bokom od frontu, aby to karta
        vedela ukázať aj vtedy, keď je zoznam požiadaviek dávno prečítaný."""
        await self._patch(
            FANVUE,
            {"model_id": self._mine},
            {"media_synced_at": datetime.now(timezone.utc).isoformat()},
        )


# ---------------------------------------------------------------------------
# Spustenie agenta vedľa Telegramu
# ---------------------------------------------------------------------------

# Ako často sa prezerá riadok `fanvue`. Pripojenie účtu ani prepnutie vypínača
# nie je nič, na čo by človek čakal so stopkami, ale reštartovať kvôli tomu
# tenanta (a tým aj Telethon session) je horšie než jeden dotaz za pol minúty.
WATCH_S = 30.0

# Ako blízko ku koncu platnosti sa prístupový token obnovuje dopredu. Päť minút
# je desaťnásobok kola dozoru — token teda nikdy nevyprší medzi dvoma kontrolami.
TOKEN_MARGIN_S = 300.0


def _ts(value: Any) -> Optional[datetime]:
    """ISO reťazec z DB → aware datetime. Nepodarok je `None`, nie výnimka."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class FanvueSupervisor:
    """Drží Fanvue tenanta v súlade s riadkom `fanvue`.

    PREČO TO NIE JE JEDNORAZOVÝ ŠTART
    ---------------------------------
    Pôvodne sa stav prečítal RAZ pri štarte tenanta. Kto pripojil Fanvue až
    potom, nedostal ani agenta, ani načítanie vaultu — a nedozvedel sa prečo,
    lebo v dashboarde bolo všetko „pripojené". Ožilo to až reštartom celej
    modelky, čo znamená aj odpojenie Telethonu, teda cenu, ktorú prepnutie
    vypínača nemá stáť. Preto sa riadok kontroluje priebežne.

    Dve úlohy, dve rôzne podmienky:
      * **načítanie vaultu** (`fvvault.VaultSync`) stačí `connected`. Priradiť
        priečinkom rolu a fotkám cenu musí ísť SKÔR, než sa agent zapne — inak
        by prvá zapnutá modelka buď mlčala (nemá čo poslať), alebo poslala
        fotku z priečinka, o ktorom ešte nikto nepovedal, na čo je;
      * **odpisovanie** (`FanvueAgent`) navyše potrebuje `enabled` — vypínač
        v dashboarde, default false. Pripojiť účet a rozbehnúť odpisovanie sú
        dve vedomé rozhodnutia, nie jedno.

    `tick()` je idempotentný: čo už beží, sa nespúšťa druhý raz, a čo bežať
    nemá, sa zruší. Nič z toho nehádže — Fanvue nesmie zhodiť Telegram.
    """

    def __init__(self, cfg, g, transport, llm, poll_s: float = WATCH_S, control=None) -> None:
        self._cfg = cfg
        self._g = g
        self._transport = transport
        self._llm = llm
        self._poll_s = poll_s
        # Control bot pre semi-auto (Fanvue karty idú do Telegram bota).
        self._control = control
        self._db = TenantFanvueDb(
            transport, cfg.model_id, g.encryption_key, getattr(cfg, "account_id", "")
        )
        self._api = None
        self.vault_task: Optional[asyncio.Task] = None
        self.agent_task: Optional[asyncio.Task] = None
        # Aby sa do logu nepísalo to isté každých 30 sekúnd.
        self._last_state: Optional[tuple] = None
        # Odtlačok obnovovacieho tokenu, s ktorým obnova zlyhala (viď
        # `_refresh_token_if_stale`). `None` = skúšať sa smie.
        self._token_fail: Optional[str] = None

    @property
    def model_id(self) -> str:
        return getattr(self._cfg, "model_id", "?")

    async def run(self) -> None:
        """Nekonečná slučka kontrol. Končí len zrušením.

        Spí PRED prvou kontrolou: prvý `tick()` už spravil `start_fanvue`
        synchrónne a zopakovať ho hneď by bol len dotaz navyše pri štarte
        každej modelky.
        """
        while True:
            await asyncio.sleep(self._poll_s)
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - dozor nesmie umrieť
                log.exception("model %s: kolo dozoru nad Fanvue zlyhalo: %s",
                              self.model_id, exc)

    async def tick(self) -> None:
        """Jedna kontrola: dorovná bežiace úlohy podľa riadku `fanvue`."""
        try:
            row = await self._db.settings()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - výpadok DB nič nevypína
            # Zámerne sa NIČ nezastavuje: nedostupná Supabase neznamená, že
            # niekto Fanvue odpojil, a vypnúť agenta kvôli jednému 500-ku by
            # bolo horšie než nechať ho bežať do ďalšieho kola.
            log.warning("model %s: stav Fanvue sa nenačítal (%s)", self.model_id, exc)
            return

        connected = bool(row.get("connected"))
        enabled = connected and bool(row.get("enabled"))

        if not connected:
            await self._stop_agent()
            await self._stop_vault()
            await self._close_api()
        else:
            self._ensure_api()
            await self._refresh_token_if_stale(row)
            self._ensure_vault()
            if enabled:
                self._ensure_agent()
            else:
                await self._stop_agent()

        stav = (connected, enabled)
        if stav != self._last_state:
            self._last_state = stav
            if enabled:
                log.info("model %s: Fanvue agent beží ako @%s",
                         self.model_id, row.get("handle") or "?")
            elif connected:
                log.info("model %s: Fanvue pripojený, odpisovanie vypnuté — beží len vault",
                         self.model_id)
            else:
                log.info("model %s: Fanvue nie je pripojený", self.model_id)

    async def close(self) -> None:
        """Upratovanie po tenantovi. `runner._drain_cleanup` volá `close()`."""
        await self._stop_agent()
        await self._stop_vault()
        await self._close_api()

    # ---------- jednotlivé úlohy ----------

    @staticmethod
    def _zije(task: Optional[asyncio.Task]) -> bool:
        return task is not None and not task.done()

    def _ensure_api(self) -> None:
        if self._api is None:
            from fanvue_api import Fanvue

            self._api = Fanvue(self._db, self._g.fanvue_client_id, self._g.fanvue_client_secret)

    async def _refresh_token_if_stale(self, row: Dict[str, Any]) -> None:
        """Udrž uložený prístupový token čerstvý, aj keď agent nebeží.

        Fanvue dáva prístupovému tokenu hodinu. `fanvue_api._access_token` ho
        obnovuje lenivo — teda len vtedy, keď sa naozaj ide volať ich API. Pri
        pripojenom, ale VYPNUTOM agentovi (`enabled = false`) nevolá nikto, takže
        token ticho vyprší a v dashboarde to roky vyzerá ako porucha, hoci
        pripojenie je zdravé. Presne to hlásil Marek pri Simone.

        Obnova sa preto spúšťa odtiaľto, z kola dozoru, ktorý riadok aj tak číta.

        PROTI TOČENIU SA DOKOLA: keď obnova zlyhá, zapamätá si odtlačok
        obnovovacieho tokenu, s ktorým zlyhala, a s tým istým to už neskúša.
        Zmysel má až nový token — teda opätovné pripojenie účtu. Bez toho by
        neplatný refresh token búchal na Fanvue každých 30 sekúnd a chybu do
        `fanvue.last_error` prepisoval dokola.
        """
        api = self._api
        refresh = str(row.get("refresh_token") or "")
        if api is None or not refresh:
            return

        expires = _ts(row.get("expires_at"))
        now = datetime.now(timezone.utc)
        if expires is not None and expires - timedelta(seconds=TOKEN_MARGIN_S) > now:
            return

        # Odtlačok, nie token — v pamäti procesu nemá čo ležať zbytočne.
        fingerprint = hashlib.sha256(refresh.encode()).hexdigest()[:16]
        if fingerprint == self._token_fail:
            return

        try:
            await api.ensure_token()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Fanvue nesmie zhodiť Telegram
            # `last_error` píše samotný `_access_token` — tu len prestaneme skúšať.
            self._token_fail = fingerprint
            log.warning(
                "model %s: obnova Fanvue tokenu zlyhala (%s) — čakám na nové pripojenie",
                self.model_id, exc,
            )
        else:
            self._token_fail = None
            log.debug("model %s: Fanvue token obnovený dopredu", self.model_id)

    def _ensure_vault(self) -> None:
        if self._zije(self.vault_task):
            return
        import fvvault

        self.vault_task = asyncio.create_task(fvvault.VaultSync(self._db, self._api).run())

    def _ensure_agent(self) -> None:
        if self._zije(self.agent_task):
            return
        # Import cez modul (nie `from … import FanvueAgent`), aby sa v testoch
        # dal podvrhnúť monkeypatchom na module.
        import fanvue_agent

        agent = fanvue_agent.FanvueAgent(self._db, self._api, self._llm, self._control)
        # Semi-auto: control bot musí vedieť, kam doručiť schválenú Fanvue odpoveď.
        if self._control is not None:
            self._control.register_sender("fanvue", agent)
        self.agent_task = asyncio.create_task(agent.run())

    async def _stop_agent(self) -> None:
        await self._zrus(self.agent_task)
        self.agent_task = None

    async def _stop_vault(self) -> None:
        await self._zrus(self.vault_task)
        self.vault_task = None

    @staticmethod
    async def _zrus(task: Optional[asyncio.Task]) -> None:
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _close_api(self) -> None:
        api, self._api = self._api, None
        if api is not None:
            with contextlib.suppress(Exception):
                await api.close()


async def start_fanvue(
    cfg, g, transport, llm, cleanup: list, control=None
) -> Optional["FanvueSupervisor"]:
    """Rozbehne dozor nad Fanvue pre tenanta. None = worker o appke nevie.

    Vráti sa DOZOR, nie úloha agenta: agent môže vzniknúť aj zaniknúť za behu
    (majiteľ prepne vypínač), takže jedna úloha by bola pravda len v okamihu
    štartu. Prvý `tick()` beží synchrónne, aby pripojená modelka nečakala na
    prvý interval; potom prevezme slučka.

    Podmienka nad všetkým je, že worker o Fanvue appke vôbec vie
    (FANVUE_CLIENT_ID + FANVUE_CLIENT_SECRET) — bez nej sa do DB ani nepozrie.

    `llm` je ten istý `MeteredLlm` ako pre Telegram — Fanvue tak platí z toho
    istého kreditu a bez zostatku sa neodpisuje ani tam. Do `cleanup` ide úloha
    dozoru a hneď za ňou samotný dozor: runner ide zoznamom odpredu, takže sa
    najprv zruší slučka a až potom sa `close()`-om pozatvárajú jej deti.

    Nič sa tu nechytá: volajúci (runner) to obaľuje `try/except` presne ako
    kontrolného bota — Fanvue nesmie zhodiť odpisovanie na Telegrame.
    """
    if not (getattr(g, "fanvue_client_id", "") and getattr(g, "fanvue_client_secret", "")):
        log.debug("model %s: Fanvue appka nie je nastavená — preskakujem", cfg.model_id)
        return None

    sup = FanvueSupervisor(cfg, g, transport, llm, control=control)
    await sup.tick()
    cleanup.append(asyncio.create_task(sup.run()))
    cleanup.append(sup)
    return sup
