"""Načítanie vaultu z Fanvue — na požiadanie z dashboardu.

PREČO TO NIE JE V DASHBOARDE
----------------------------
V predlohe (`simona-dashboard`) si synchronizáciu robil web sám: prečítal
prístupový token z DB a volal Fanvue API priamo z Next.js. V Telepipe je token
šifrovaný (`fanvue.access_token_enc`, AES-256-GCM) a dešifrovací seam je
JEDINÝ — `fanvue_tenant.TenantFanvueDb`. Web ten kľúč nikdy nedostane do rúk
a nemá ho prečo mať.

Preto fronta: dashboard vloží riadok do `fanvue_sync_requests` (klient smie
vyplniť jediný stĺpec, `model_id` — migrácia 015) a worker ju vyberie. Výsledok
sa zapíše späť do toho istého riadku, takže tlačidlo vie ukázať aj „4 priečinky,
12 nových fotiek", aj chybu. Pri fire-and-forget by len bliklo.

ČO SYNCHRONIZÁCIA SMIE PREPÍSAŤ
-------------------------------
Vault drží fotky, my držíme to, čo o nich vault nevie: čo na nich je, koľko
stoja, či sa smú posielať a komu už odišli. Preto sa existujúcemu riadku
osviežuje LEN to, čo je fakt na strane Fanvue — `folder`, `kind`, `thumb_url`.
`caption`, `fits`, `price_cents`, `active`, `spicy_override`, `sent_count`
a `posted_at` sú naše a synchronizácia sa ich nedotkne. (`spicy` je odvodená
hodnota, ktorú dopočítava trigger z migrácie 016.) (`fvmedia.sync` z predlohy to riešila
tak, že známe položky preskočila úplne — lenže potom sa nikdy neosviežil náhľad
ani presun fotky do iného priečinka.)

Prečo sa náhľad ukladá, keď je adresa podpísaná a expiruje: dashboard by inak
musel volať Fanvue API pri každom zobrazení stránky, a na to by potreboval ten
token. Stará adresa v najhoršom prípade neukáže obrázok — a ďalší klik na
„načítať z vaultu" ju opraví.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import fvmedia

log = logging.getLogger(__name__)

# Ako často sa pozerá do fronty. Človek klikne a čaká pri obrazovke, takže
# dlhší interval by pôsobil, že sa nič nedeje; kratší by bol dotaz navyše
# každú sekundu pre modelku, ktorá nesynchronizuje mesiace.
POLL_S = 4.0

# Ako často sa upratuje fronta a čo sa považuje za staré. Fronta je krátkodobá
# pracovná pamäť (dashboard z nej číta výsledok posledného kliku), takže denný
# odstup stačí a upratovanie nesmie behať každé štyri sekundy — bol by to dotaz
# navyše pri každom kole každej modelky.
PRUNE_EVERY_S = 3600.0
PRUNE_OLDER_THAN_H = 24

# Stĺpce, ktoré sa smú osviežiť na už známej fotke. Zvyšok je naše rozhodnutie
# a synchronizácia doň nesiaha — viď hlavička súboru.
REFRESHABLE = ("folder", "kind", "thumb_url")


def thumb_of(item: Dict[str, Any]) -> str:
    """Adresa náhľadu z položky vaultu. Prázdne = Fanvue žiadnu nevrátil.

    Varianty treba vypýtať menovite (`variants=thumbnail,main`, robí to
    `fanvue_api.folder_media`) a `thumbnail` nemá vygenerovaná každá položka —
    vtedy poslúži `main`. Bez tohto poradia by časť zbierky ostala bez obrázka.
    """
    variants = item.get("variants") or []
    if not isinstance(variants, (list, tuple)):
        return ""
    for wanted in ("thumbnail", "main"):
        for variant in variants:
            if isinstance(variant, dict) and str(variant.get("variantType") or "") == wanted:
                url = str(variant.get("url") or "")
                if url:
                    return url
    return ""


def fresh_row(
    item: Dict[str, Any], folder: str, folder_price_cents: int = 0
) -> Optional[Dict[str, Any]]:
    """Nová položka vaultu na riadok pre `fv_media`. None = nepoužiteľná.

    Cena: Fanvue k obrázku navrhuje `recommendedPrice` a tá má prednosť —
    je to jeho odhad na konkrétnu fotku. Keď žiadnu nenavrhne, použije sa
    východisková cena priečinka. Bez ceny by sa fotka z plateného priečinka
    neposlala vôbec (`fvmedia.pick(paid=True)` ju odfiltruje), takže priečinková
    cena je to, čo novú zbierku vôbec rozbehne.
    """
    row = fvmedia.flatten(item, folder)
    if not row:
        return None
    row["thumb_url"] = thumb_of(item)
    if not int(row.get("price_cents") or 0):
        row["price_cents"] = max(0, int(folder_price_cents or 0))
    return row


def refresh_patch(known: Dict[str, Any], item: Dict[str, Any], folder: str) -> Dict[str, Any]:
    """Čo sa na už známej fotke zmenilo. Prázdny slovník = netreba zapisovať.

    Zámerne sa porovnáva, nie zapisuje naslepo: pri stovkách fotiek by bezhlavý
    upsert znamenal stovky zápisov pri každom kliknutí a `synced_at` by sa hýbal
    aj vtedy, keď sa nič nestalo.
    """
    novy = fvmedia.flatten(item, folder)
    if not novy:
        return {}
    kandidat = {"folder": folder, "kind": novy.get("kind") or "image", "thumb_url": thumb_of(item)}
    patch: Dict[str, Any] = {}
    for key in REFRESHABLE:
        hodnota = kandidat.get(key)
        # Prázdny náhľad neprepisuje starý: Fanvue ho občas nevráti a mať starú
        # adresu je lepšie než nemať žiadnu.
        if key == "thumb_url" and not hodnota:
            continue
        if str(known.get(key) or "") != str(hodnota or ""):
            patch[key] = hodnota
    return patch


async def run_once(db, api, creator_uuid: str) -> Dict[str, int]:
    """Zosúladí `fv_folders` a `fv_media` s vaultom. Vracia, čo sa stalo.

    Priečinok, ktorý pribudne, dostane rolu `ignore` (default stĺpca) — nič sa
    nezačne posielať samo od seba len preto, že si Marek vo Fanvue založil
    priečinok.
    """
    if not creator_uuid:
        raise ValueError("Fanvue účet nie je pripojený (chýba creator_uuid).")

    folders = await api.vault_folders(creator_uuid)
    known_folders = {str(f.get("name") or ""): f for f in await db.folders()}
    known_media = {str(m.get("media_uuid") or ""): m for m in await db.all_media()}

    nove: List[Dict[str, Any]] = []
    videne = 0
    spracovane = 0

    for folder in folders:
        name = str(folder.get("name") or "")
        if not name:
            continue
        spracovane += 1
        items = await api.folder_media(name)
        await db.save_folder(name, {"media_count": len(items)})
        cena_priecinka = int((known_folders.get(name) or {}).get("price_cents") or 0)

        for item in items:
            videne += 1
            uuid = str(item.get("uuid") or item.get("mediaUuid") or "")
            known = known_media.get(uuid) if uuid else None
            if known is None:
                row = fresh_row(item, name, cena_priecinka)
                if row and row["media_uuid"] not in known_media:
                    nove.append(row)
                    known_media[row["media_uuid"]] = row
                continue
            patch = refresh_patch(known, item, name)
            if patch:
                await db.update_media(uuid, patch)

    await db.upsert_media(nove)
    await db.mark_vault_synced()
    log.info(
        "Vault: %s priečinkov, %s položiek, %s nových fotiek",
        spracovane, videne, len(nove),
    )
    return {"folders": spracovane, "media_new": len(nove), "media_seen": videne}


class VaultSync:
    """Vyberá `fanvue_sync_requests` a načítava vault.

    Beží ako samostatná úloha vedľa Fanvue agenta a štartuje už pri
    `fanvue.connected` — teda AJ keď je odpisovanie vypnuté. Priradiť
    priečinkom rolu a fotkám cenu musí ísť skôr, než sa agent zapne; inak by
    prvá zapnutá modelka buď mlčala (nemá čo poslať), alebo by poslala fotku
    z priečinka, o ktorom ešte nikto nepovedal, na čo je.
    """

    def __init__(
        self,
        db,
        api,
        poll_s: float = POLL_S,
        prune_every_s: float = PRUNE_EVERY_S,
        prune_older_than_h: int = PRUNE_OLDER_THAN_H,
    ) -> None:
        self._db = db
        self._api = api
        self._poll_s = poll_s
        self._prune_every_s = prune_every_s
        self._prune_older_than_h = prune_older_than_h
        # None = ešte sa neupratovalo. Prvé kolo teda uprace hneď — riadky
        # z minulého behu workera už nikto nečíta.
        self._pruned_at: Optional[float] = None

    async def run(self) -> None:
        log.info("Fanvue vault sync beží, fronta sa kontroluje každé %.0f s", self._poll_s)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - slučka nesmie umrieť
                log.exception("Kolo synchronizácie vaultu zlyhalo: %s", exc)
            await self.maybe_prune()
            await asyncio.sleep(self._poll_s)

    async def maybe_prune(self) -> bool:
        """Uprace dobehnuté požiadavky, ak je na to čas. `False` = ešte nie.

        Nikto ich doteraz nemazal a pri dennej synchronizácii tabuľka rastie
        donekonečna. Zlyhanie sa len zaloguje: upratovanie nie je dôvod, aby
        prestala fungovať samotná synchronizácia.
        """
        teraz = time.monotonic()
        if self._pruned_at is not None and teraz - self._pruned_at < self._prune_every_s:
            return False
        self._pruned_at = teraz
        try:
            await self._db.prune_sync(self._prune_older_than_h)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - upratovanie nie je kritická cesta
            log.warning("Upratovanie fronty synchronizácie zlyhalo: %s", exc)
            return False
        return True

    async def tick(self) -> bool:
        """Jedna požiadavka. `False` = fronta bola prázdna.

        Riadok sa dopíše VŽDY, aj keď synchronizácia zlyhá: `finished_at is
        null` je zároveň zámok (partial unique index z migrácie 015), takže
        nedokončená požiadavka by zablokovala tlačidlo aj na ďalšie pokusy.
        """
        request = await self._db.pending_sync()
        if not request:
            return False

        request_id = int(request["id"])
        await self._db.start_sync(request_id)
        try:
            settings = await self._db.settings()
            out = await run_once(
                self._db, self._api, str(settings.get("creator_uuid") or "")
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - chyba patrí do frontu, nie do logu
            log.warning("Synchronizácia vaultu zlyhala: %s", exc)
            await self._db.finish_sync(request_id, ok=False, error=str(exc)[:400])
            return True

        await self._db.finish_sync(request_id, ok=True, **out)
        return True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def newest_pending(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Najstaršia nedokončená požiadavka zo zoznamu. None = žiadna.

    Fronta je na modelku najviac jednoprvková (partial unique index), toto je
    len poistka pre prípad, že by index niekedy padol.
    """
    cakajuce = [r for r in rows if not r.get("finished_at")]
    if not cakajuce:
        return None
    return min(cakajuce, key=lambda r: int(r.get("id") or 0))
