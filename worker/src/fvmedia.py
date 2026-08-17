"""Fotky na Fanvue — vault je sklad, my mu dávame význam.

Fanvue má vlastný vault aj priečinky a vie ich cez API vypísať. Robiť si
vlastnú knižnicu fotiek by znamenalo mať dve zbierky, ktoré sa rozídu, a pri
každom odoslaní fotku nahrávať znova — do správy sa dá priložiť len médium,
ktoré na Fanvue už existuje.

Preto: **vault drží fotky, my držíme to, čo o nich vault nevie.** Čo na fotke
je, kedy sadne, koľko stojí a hlavne komu už odišla. To posledné je celý dôvod
tejto vrstvy — Fanvue si to nepamätá a poslať tú istú fotku dvakrát je
najlacnejší spôsob, ako sa prezradiť.

Priečinkom sa prideľuje úloha, nie názov: `sfw` sa posiela zadarmo, `nsfw`
za peniaze, `post` je na feed, `ignore` sa nepoužije. Názvy si Marek robí
vo vaulte tak, ako mu vyhovuje.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

ROLES = ("sfw", "nsfw", "post", "ignore")


def role_of(folder_name: str, folders: Sequence[Dict[str, Any]]) -> str:
    for row in folders:
        if str(row.get("name") or "") == folder_name:
            role = str(row.get("role") or "ignore")
            return role if role in ROLES else "ignore"
    return "ignore"


def flatten(vault_item: Dict[str, Any], folder: str) -> Optional[Dict[str, Any]]:
    """Položka z vaultu na riadok pre nás. None = nepoužiteľná.

    Adresy variantov sa zámerne neukladajú — sú podpísané a expirujú.
    Uchováva sa id, nie URL.
    """
    uuid = str(vault_item.get("uuid") or vault_item.get("mediaUuid") or "")
    if not uuid:
        return None
    return {
        "media_uuid": uuid,
        "folder": folder,
        "kind": str(vault_item.get("mediaType") or vault_item.get("type") or "image").lower(),
        # Fanvue si obrázky popisuje samo a robí to prekvapivo dobre.
        "caption": str(vault_item.get("description") or vault_item.get("caption") or "")[:400],
        "price_cents": int(vault_item.get("recommendedPrice") or 0),
    }


def pick(
    media: Sequence[Dict[str, Any]],
    already_sent: set,
    spicy: bool,
    hint: str = "",
    paid: bool = False,
) -> Optional[Dict[str, Any]]:
    """Ktorú fotku poslať. None = nič vhodné, radšej nič než opakovanie.

    Uprednostní tú, ktorej popis sedí na to, o čom je práve reč; medzi
    rovnako vhodnými vyberie tú najmenej použitú, nech sa zbierka míňa
    rovnomerne a nie stále tá istá.

    Pri `paid` sa vyberá len z tých, čo majú cenu. Fotka z plateného
    priečinka bez ceny by odišla zadarmo — a to je presne ten obsah,
    ktorý zadarmo odísť nesmie.
    """
    volne = [
        m
        for m in media
        if m.get("media_uuid") not in already_sent
        and m.get("active", True)
        and bool(m.get("spicy")) == spicy
        # Vo vaulte sedí aj zvuk z hlasoviek. Poslať ho ako fotku by bolo
        # trápne a odhalilo by to, že si obsah nikto nepozrel.
        and str(m.get("kind") or "image") == "image"
        and (not paid or int(m.get("price_cents") or 0) > 0)
    ]
    if not volne:
        return None

    slova = {w for w in _words(hint) if len(w) > 3}
    if slova:
        def zhoda(m: Dict[str, Any]) -> int:
            text = _words(f"{m.get('caption', '')} {m.get('fits', '')}")
            return len(slova & text)

        najlepsia = max(zhoda(m) for m in volne)
        if najlepsia > 0:
            volne = [m for m in volne if zhoda(m) == najlepsia]

    najmenej = min(int(m.get("sent_count") or 0) for m in volne)
    volne = [m for m in volne if int(m.get("sent_count") or 0) == najmenej]
    return random.choice(volne)


def _words(text: Any) -> set:
    return {w for w in str(text or "").lower().replace(",", " ").split() if w}


# Fotka odchádza vtedy, keď si ju vypýta — nie keď to model uzná za vhodné.
# Rozhodnutie musí byť v kóde, inak by ich posielala v každej druhej správe
# a zbierka by sa minula za deň.
_PYTA_SA = (
    "pic", "pics", "photo", "photos", "picture", "pictures", "selfie",
    "show me", "send me", "see you", "see more", "let me see", "wanna see",
)
_OSTRE = (
    "nude", "nudes", "naked", "topless", "tits", "boobs", "ass", "pussy",
    "dirty", "spicy", "nsfw", "sexy pic", "without",
)


def asked_for_photo(text: Any) -> bool:
    low = str(text or "").lower()
    return any(phrase in low for phrase in _PYTA_SA) or any(
        phrase in low for phrase in _OSTRE
    )


def wants_spicy(text: Any) -> bool:
    low = str(text or "").lower()
    return any(phrase in low for phrase in _OSTRE)


AUDIENCES = ("subscribers", "followers-and-subscribers")


def due_to_post(settings: Dict[str, Any], now: Any) -> bool:
    """Je čas pridať príspevok na feed?"""
    if not settings.get("posting_enabled"):
        return False
    hodin = float(settings.get("post_every_h") or 0)
    if hodin <= 0:
        return False
    posledny = settings.get("last_post_at")
    if not posledny:
        return True
    from datetime import datetime, timedelta, timezone

    try:
        kedy = datetime.fromisoformat(str(posledny).replace("Z", "+00:00"))
    except ValueError:
        return True
    if not kedy.tzinfo:
        kedy = kedy.replace(tzinfo=timezone.utc)
    return now - kedy >= timedelta(hours=hodin)


def next_post(media: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Ktorá fotka pôjde na feed. None = niet čo pridať.

    Fotka na feede ostáva navždy, takže tá istá druhý raz je horšia než
    v chate — vidia ju všetci naraz. Berie sa najstaršia nepoužitá, nech sa
    zbierka míňa v poradí, v akom pribudla.
    """
    volne = [
        m
        for m in media
        if m.get("active", True)
        and not m.get("posted_at")
        and str(m.get("kind") or "image") == "image"
    ]
    if not volne:
        return None
    return min(volne, key=lambda m: str(m.get("media_uuid") or ""))


def price_for(media: Dict[str, Any]) -> int:
    """Cena fotky.

    Každá má vlastnú — jedna cena na celý priečinok by znamenala, že sa
    najlepšia fotka predáva za to isté ako najslabšia. Fanvue k obrázku
    navrhuje `recommendedPrice`, ktorá sa preberá pri načítaní z vaultu.
    """
    return int(media.get("price_cents") or 0)


async def sync(db, api, creator_uuid: str) -> Dict[str, int]:
    """Zosúladí zoznam fotiek s vaultom.

    Popisy, ceny a počty odoslaní ostávajú — tie sú naše a vo vaulte nie sú.
    Preto sa zapisujú len tie položky, ktoré ešte nepoznáme.
    """
    if not creator_uuid:
        return {"folders": 0, "new": 0}

    folders = await api.vault_folders(creator_uuid)
    zname = {str(m.get("media_uuid")) for m in await db.all_media()}
    nove: List[Dict[str, Any]] = []

    for folder in folders:
        name = str(folder.get("name") or "")
        if not name:
            continue
        items = await api.folder_media(name)
        await db.save_folder(name, {"media_count": len(items)})
        for item in items:
            row = flatten(item, name)
            if row and row["media_uuid"] not in zname:
                nove.append(row)
                zname.add(row["media_uuid"])

    await db.upsert_media(nove)
    log.info("Vault: %s priečinkov, %s nových fotiek", len(folders), len(nove))
    return {"folders": len(folders), "new": len(nove)}
