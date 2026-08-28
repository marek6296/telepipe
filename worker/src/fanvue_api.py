"""Fanvue — REST klient a prístup k jej tabuľkám.

Zámerne nič nezdieľa s Telegram workerom. Fanvue je iná platforma s vlastnou
autorizáciou aj vlastnými limitmi a keby visela na tom istom klientovi, jedna
by vedela zhodiť druhú.

Tokeny sa neobnovujú v dashboarde ani tu zvlášť — obe strany siahajú do tej
istej tabuľky `fanvue` a kto príde k vypršanému tokenu prvý, ten ho obnoví.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

AUTH = "https://auth.fanvue.com/oauth2"
API = "https://api.fanvue.com"

# Fanvue vyžaduje túto hlavičku na každom volaní. Bez nej vracia 400.
API_VERSION = "2025-06-26"


def _ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class FanvueDb:
    """Tabuľky Fanvue v schéme modelky. Rovnaká cesta ako u Telegramu —
    PostgREST a hlavičky Accept-Profile / Content-Profile."""

    def __init__(self, url: str, service_key: str, schema: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{url}/rest/v1",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Accept-Profile": schema,
                "Content-Profile": schema,
            },
            timeout=20.0,
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

    async def _post(self, path: str, body: Any, upsert: bool = False) -> None:
        prefer = "resolution=merge-duplicates" if upsert else "return=minimal"
        r = await self._client.post(path, json=body, headers={"Prefer": prefer})
        r.raise_for_status()

    # ---------- nastavenia a tokeny ----------

    async def settings(self) -> Dict[str, Any]:
        rows = await self._get("/fanvue", {"id": "eq.1", "select": "*"})
        return rows[0] if rows else {}

    async def save(self, patch: Dict[str, Any]) -> None:
        patch = dict(patch)
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._patch("/fanvue", {"id": "eq.1"}, patch)

    # ---------- fanúšikovia a správy ----------

    async def fan(self, fan_uuid: str) -> Optional[Dict[str, Any]]:
        rows = await self._get("/fv_users", {"fan_uuid": f"eq.{fan_uuid}", "select": "*"})
        return rows[0] if rows else None

    async def upsert_fan(self, fan_uuid: str, patch: Dict[str, Any]) -> None:
        await self._post("/fv_users", {"fan_uuid": fan_uuid, **patch}, upsert=True)

    async def update_fan(self, fan_uuid: str, patch: Dict[str, Any]) -> None:
        await self._patch("/fv_users", {"fan_uuid": f"eq.{fan_uuid}"}, patch)

    async def add_message(
        self, fan_uuid: str, role: str, content: str, message_uuid: str = ""
    ) -> None:
        row: Dict[str, Any] = {"fan_uuid": fan_uuid, "role": role, "content": content}
        if message_uuid:
            row["message_uuid"] = message_uuid
        await self._post("/fv_messages", row, upsert=bool(message_uuid))

    async def add_messages(self, fan_uuid: str, rows: List[Dict[str, str]]) -> None:
        """Doplnenie viacerých správ naraz. Prázdny zoznam nič nerobí."""
        if rows:
            await self._post(
                "/fv_messages", [{"fan_uuid": fan_uuid, **r} for r in rows], upsert=True
            )

    async def known_message_uuids(self, fan_uuid: str, limit: int = 200) -> set:
        rows = await self._get(
            "/fv_messages",
            {
                "fan_uuid": f"eq.{fan_uuid}",
                "select": "message_uuid",
                "message_uuid": "not.is.null",
                "order": "id.desc",
                "limit": str(limit),
            },
        )
        return {r["message_uuid"] for r in rows if r.get("message_uuid")}

    async def texty_bez_uuid(self, fan_uuid: str, limit: int = 60) -> set:
        """Znenia správ, ktoré máme uložené BEZ identifikátora Fanvue.

        Tie sme poslali my a Fanvue nám k nim id nevrátilo. Pri zosúladení si
        ich stiahneme späť — už s ich vlastným uuid — a dedup podľa uuid ich
        nespozná, takže by pribudli druhýkrát. Naostro tak bolo 6 % správ
        v chate zdvojených a modelka videla svoju poslednú vetu dvakrát.
        """
        rows = await self._get(
            "/fv_messages",
            {
                "fan_uuid": f"eq.{fan_uuid}",
                "select": "content",
                "message_uuid": "is.null",
                "order": "id.desc",
                "limit": str(limit),
            },
        )
        return {str(r.get("content") or "") for r in rows if r.get("content")}

    async def history(self, fan_uuid: str, limit: int = 16) -> List[Dict[str, str]]:
        rows = await self._get(
            "/fv_messages",
            {
                "fan_uuid": f"eq.{fan_uuid}",
                "select": "role,content",
                "order": "id.desc",
                "limit": str(limit),
            },
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ---------- obsah z vaultu ----------

    async def folders(self) -> List[Dict[str, Any]]:
        return await self._get("/fv_folders", {"select": "*", "order": "name.asc"})

    async def save_folder(self, name: str, patch: Dict[str, Any]) -> None:
        await self._post("/fv_folders", {"name": name, **patch}, upsert=True)

    async def upsert_media(self, rows: List[Dict[str, Any]]) -> None:
        """Zápis po dávkach. Existujúce si nechajú popis aj cenu — tie sú naše,
        vo vaulte nie sú a prepísať ich synchronizáciou by bola škoda."""
        if rows:
            await self._post("/fv_media", rows, upsert=True)

    async def media_in(self, folder: str) -> List[Dict[str, Any]]:
        return await self._get(
            "/fv_media", {"folder": f"eq.{folder}", "active": "is.true", "select": "*"}
        )

    async def all_media(self) -> List[Dict[str, Any]]:
        return await self._get("/fv_media", {"select": "*", "order": "folder.asc"})

    async def update_media(self, media_uuid: str, patch: Dict[str, Any]) -> None:
        await self._patch("/fv_media", {"media_uuid": f"eq.{media_uuid}"}, patch)

    async def sent_media(self, fan_uuid: str) -> set:
        """Čo už tento človek videl. Dvakrát to isté je najlacnejší spôsob,
        ako sa prezradiť."""
        rows = await self._get(
            "/fv_media_sends", {"fan_uuid": f"eq.{fan_uuid}", "select": "media_uuid"}
        )
        return {r["media_uuid"] for r in rows}

    async def record_send(self, media_uuid: str, fan_uuid: str, price_cents: int) -> None:
        await self._post(
            "/fv_media_sends",
            {"media_uuid": media_uuid, "fan_uuid": fan_uuid, "price_cents": price_cents},
            upsert=True,
        )

    # ---------- fronta udalostí ----------

    async def pending(self, limit: int = 20) -> List[Dict[str, Any]]:
        return await self._get(
            "/fv_events",
            {"handled": "is.false", "select": "*", "order": "id.asc", "limit": str(limit)},
        )

    async def mark_handled(self, event_id: int) -> None:
        await self._patch("/fv_events", {"id": f"eq.{event_id}"}, {"handled": True})

    # ---------- most do Telegramu ----------

    async def persona(self) -> Dict[str, Any]:
        rows = await self._get("/persona", {"id": "eq.1", "select": "*"})
        return rows[0] if rows else {}

    async def behavior(self) -> Dict[str, Any]:
        """Chovanie modelky — najmä časová zóna, v ktorej vraj žije.

        Fanvue má vlastné časy odpisovania, ale zóna je vlastnosť tej osoby,
        nie platformy: keď je v Los Angeles noc, je noc na oboch miestach.
        """
        rows = await self._get("/behavior", {"id": "eq.1", "select": "*"})
        return rows[0] if rows else {}

    async def linked_tg_ids(self) -> set:
        """Telegram id, ktoré už patria nejakému fanúšikovi. Jeden človek
        nemôže byť dvaja."""
        rows = await self._get("/fv_users", {"select": "tg_id", "tg_id": "not.is.null"})
        return {int(r["tg_id"]) for r in rows if r.get("tg_id") is not None}

    async def link_candidates(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Konverzácie, z ktorých mohol prísť — komu odišiel odkaz.

        Berú sa aj tie bez odkazu, lebo zhoda v celom mene je stopa aj sama
        osebe; poradie podľa poslednej správy drží zoznam pri živých.
        """
        return await self._get(
            "/dm_users",
            {
                "select": "tg_id,first_name,username,link_sent_at,link_clicked_at,funnel_stage",
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
            "/dm_users",
            {"tg_id": f"eq.{tg_id}", "select": "first_name,summary,msg_count,paid"},
        )
        if users:
            out["user"] = users[0]
        facts = await self._get(
            "/facts",
            {"tg_id": f"eq.{tg_id}", "select": "key,value", "order": "id.desc", "limit": "25"},
        )
        out["facts"] = facts
        msgs = await self._get(
            "/dm_messages",
            {
                "tg_id": f"eq.{tg_id}",
                "select": "role,content",
                "order": "id.desc",
                "limit": "10",
            },
        )
        out["recent"] = list(reversed(msgs))
        return out


class Fanvue:
    """Volania do Fanvue API. Token si obnovuje sám, keď mu vyprší."""

    def __init__(self, db: FanvueDb, client_id: str, client_secret: str) -> None:
        self._db = db
        self._id = client_id
        self._secret = client_secret
        self._client = httpx.AsyncClient(base_url=API, timeout=30.0)
        self._token = ""
        self._expires: Optional[datetime] = None

    async def close(self) -> None:
        await self._client.aclose()

    async def _access_token(self) -> str:
        now = datetime.now(timezone.utc)
        # Minútová rezerva, nech token nevyprší uprostred volania.
        if self._token and self._expires and self._expires - timedelta(seconds=60) > now:
            return self._token

        row = await self._db.settings()
        if not row.get("connected"):
            raise RuntimeError("Fanvue účet nie je pripojený.")

        stored = _ts(row.get("expires_at"))
        if row.get("access_token") and stored and stored - timedelta(seconds=60) > now:
            self._token = str(row["access_token"])
            self._expires = stored
            return self._token

        refresh = str(row.get("refresh_token") or "")
        if not refresh:
            raise RuntimeError("Chýba obnovovací token — účet treba pripojiť znova.")

        basic = base64.b64encode(f"{self._id}:{self._secret}".encode()).decode()
        r = await httpx.AsyncClient(timeout=30.0).post(
            f"{AUTH}/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            },
            data={"grant_type": "refresh_token", "refresh_token": refresh},
        )
        if r.status_code != 200:
            await self._db.save({"last_error": f"Obnova tokenu: {r.status_code} {r.text[:200]}"})
            raise RuntimeError(f"Obnova tokenu zlyhala: {r.status_code}")

        data = r.json()
        self._token = str(data["access_token"])
        self._expires = now + timedelta(seconds=int(data.get("expires_in") or 3600))
        await self._db.save(
            {
                "access_token": self._token,
                "refresh_token": data.get("refresh_token") or refresh,
                "expires_at": self._expires.isoformat(),
                "scope": data.get("scope") or "",
                "last_error": "",
            }
        )
        return self._token

    async def ensure_token(self) -> str:
        """Obnov uložený token, ak je pri konci — bez toho, aby sa niečo volalo.

        `_access_token` sa doteraz spúšťal iba ako vedľajší efekt volania do
        Fanvue, takže modelke s vypnutým agentom (`enabled = false`) token ticho
        vypršal a v dashboarde svietilo, že „vypršal pred hodinou". Pripojenie
        pritom bolo v poriadku. Dozor (`fanvue_tenant.FanvueSupervisor`) preto
        potrebuje vstup, ktorý obnovu vyvolá sám; logika ostáva jedna.
        """
        return await self._access_token()

    async def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._access_token()}",
            "X-Fanvue-API-Version": API_VERSION,
            "Content-Type": "application/json",
        }

    async def chat_messages(self, user_uuid: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Skutočný stav chatu, od najnovšej správy. Prázdne = nedalo sa."""
        try:
            r = await self._client.get(
                f"/chats/{user_uuid}/messages",
                params={"size": max(1, min(50, limit))},
                headers=await self._headers(),
            )
            r.raise_for_status()
            return r.json().get("data") or []
        except Exception as exc:  # noqa: BLE001 - bez zosúladenia sa dá odpísať
            log.warning("Chat %s sa nepodarilo prečítať: %s", user_uuid[:8], exc)
            return []

    async def send(
        self,
        user_uuid: str,
        text: str,
        media_uuids: Optional[List[str]] = None,
        price_cents: int = 0,
    ) -> str:
        """Pošle správu, prípadne s fotkou a cenou.

        Vracia id odoslanej správy — treba ho uložiť, inak by sa nám vlastná
        správa pri neskoršom zosúladení javila ako cudzia a uložila by sa
        druhý raz. Prázdny reťazec = nepodarilo sa, nič nespadne.
        """
        payload: Dict[str, Any] = {"text": text}
        if media_uuids:
            payload["mediaUuids"] = list(media_uuids)
            if price_cents > 0:
                payload["price"] = int(price_cents)
        try:
            r = await self._client.post(
                f"/chats/{user_uuid}/message",
                json=payload,
                headers=await self._headers(),
            )
            if r.status_code >= 400:
                log.warning("Fanvue správa neprešla: %s %s", r.status_code, r.text[:200])
                return ""
            try:
                # Keď id nevráti, správa aj tak odišla — vráti sa zástupný
                # znak, aby to volajúci nepovažoval za zlyhanie.
                return str((r.json() or {}).get("uuid") or "") or "-"
            except Exception:  # noqa: BLE001
                return "-"
        except Exception as exc:  # noqa: BLE001 - odpisovanie musí bežať ďalej
            log.warning("Fanvue správa zlyhala: %s", exc)
            return ""

    async def upload(
        self, creator_uuid: str, data: bytes, filename: str, media_type: str = "audio"
    ) -> str:
        """Nahrá súbor do vaultu a vráti jeho uuid. Prázdne = nepodarilo sa.

        Fanvue používa trojkrokový multipart upload cez S3: založí sa
        záznam, vypýta sa podpísaná adresa na každý kúsok a nakoniec sa
        upload uzavrie. Hlasovka sa zmestí do jedného kúska, ale krokom sa
        vyhnúť nedá.
        """
        if not (data and creator_uuid):
            return ""
        try:
            head = await self._headers()
            r = await self._client.post(
                "/media/uploads",
                json={
                    "name": filename,
                    "filename": filename,
                    "mediaType": media_type,
                    "sizeBytes": len(data),
                },
                headers=head,
            )
            if r.status_code >= 400:
                log.warning("Upload sa nezaložil: %s %s", r.status_code, r.text[:200])
                return ""
            session = r.json()
            media_uuid = str(session.get("mediaUuid") or "")
            upload_id = str(session.get("uploadId") or "")
            part_size = int(session.get("partSize") or len(data)) or len(data)
            if not (media_uuid and upload_id):
                return ""

            kusky = [data[i : i + part_size] for i in range(0, len(data), part_size)]
            hotove = []
            async with httpx.AsyncClient(timeout=120.0) as s3:
                for cislo, kusok in enumerate(kusky, start=1):
                    # Zámerne bez `/creators/` — tá cesta existuje tiež, ale
                    # pýta si write:creator navyše a vracia 403. Táto vystačí
                    # s právami, ktoré na odosielanie aj tak potrebujeme.
                    u = await self._client.get(
                        f"/media/uploads/{upload_id}/parts/{cislo}/url",
                        headers=head,
                    )
                    u.raise_for_status()
                    # Odpoveď je text/plain, nie JSON — úvodzovky treba odstrániť.
                    adresa = u.text.strip().strip('"')
                    put = await s3.put(adresa, content=kusok)
                    put.raise_for_status()
                    hotove.append(
                        {
                            "PartNumber": cislo,
                            "ETag": (put.headers.get("ETag") or "").strip('"'),
                        }
                    )

            done = await self._client.patch(
                f"/media/uploads/{upload_id}", json={"parts": hotove}, headers=head
            )
            if done.status_code >= 400:
                log.warning("Upload sa neuzavrel: %s %s", done.status_code, done.text[:200])
                return ""
            return media_uuid
        except Exception as exc:  # noqa: BLE001 - hlasovka je bonus, nie podmienka
            log.warning("Upload zlyhal: %s", exc)
            return ""

    async def post(
        self,
        text: str,
        media_uuids: List[str],
        audience: str,
        price_cents: int = 0,
    ) -> bool:
        """Zverejní príspevok na feed. False = nepodarilo sa, nič nespadne.

        `audience` je povinné. Cena má na Fanvue spodnú hranicu 300 centov
        a bez média ju API neprijme, tak sa nižšia radšej zahodí ako by mal
        príspevok vyjsť s cenou, ktorú nikto nechcel.
        """
        payload: Dict[str, Any] = {"audience": audience}
        if text:
            payload["text"] = text[:5000]
        if media_uuids:
            payload["mediaUuids"] = list(media_uuids)
            if price_cents >= 300:
                payload["price"] = int(price_cents)
        try:
            r = await self._client.post(
                "/posts", json=payload, headers=await self._headers()
            )
            if r.status_code >= 400:
                log.warning("Príspevok neprešiel: %s %s", r.status_code, r.text[:200])
                return False
            return True
        except Exception as exc:  # noqa: BLE001 - odpisovanie musí bežať ďalej
            log.warning("Príspevok zlyhal: %s", exc)
            return False

    async def vault_folders(self, creator_uuid: str) -> List[Dict[str, Any]]:
        """Priečinky vo vaulte. Prázdne = žiadne alebo sa nedali načítať."""
        try:
            r = await self._client.get(
                f"/creators/{creator_uuid}/vault/folders", headers=await self._headers()
            )
            r.raise_for_status()
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("Priečinky vaultu sa nenačítali: %s", exc)
            return []
        return body.get("data") or body.get("items") or []

    async def folder_media(self, folder: str) -> List[Dict[str, Any]]:
        """Obsah priečinka aj s popisom.

        Ide cez `GET /media?folderName=`, nie cez endpoint priečinka — ten
        vracia holé uuid bez popisu a museli by sme dopytovať každú položku
        zvlášť. Popis si Fanvue robí samo a robí to dobre.
        """
        from urllib.parse import quote

        out: List[Dict[str, Any]] = []
        page = 1
        while page <= 20:  # poistka proti nekonečnu, nie limit zbierky
            try:
                r = await self._client.get(
                    "/media",
                    params={
                        "folderName": folder,
                        "variants": "thumbnail,main",
                        "page": page,
                        "size": 50,
                    },
                    headers=await self._headers(),
                )
                r.raise_for_status()
                body = r.json()
            except Exception as exc:  # noqa: BLE001
                log.warning("Obsah priečinka %s sa nenačítal: %s", folder, exc)
                break
            out.extend(body.get("data") or [])
            if not (body.get("pagination") or {}).get("hasMore"):
                break
            page += 1
        return out

    async def whoami(self) -> Dict[str, Any]:
        r = await self._client.get("/users/me", headers=await self._headers())
        r.raise_for_status()
        return r.json()
