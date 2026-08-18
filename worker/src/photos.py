"""Fotoknižnica — kedy poslať fotku, z ktorého albumu, a aby sa nikdy neopakovala.

ŠESŤ PEVNÝCH ALBUMOV. Klient nahráva fotky do albumov, modelka posiela z toho,
ktorý sedí na miesto v jej harmonograme (v gyme fotku z gymu). Voľné „kolekcie"
z minulosti nahradili pevné kľúče — nedá sa vytvoriť preklep ani zabudnúť dennú
dobu.

Pravidlá sú v kóde, nie v prompte, lebo na ne sa musí dať spoľahnúť:
  * tá istá fotka nikdy dvakrát tomu istému človeku
  * ALBUM sa v jednom chate použije najviac RAZ — keď z neho odišla fotka,
    druhá z toho istého smie odísť len do 30 min a len keď si ju vypýta alebo
    pochybuje; potom sa ten album v chate už nikdy nepoužije
  * fotka nikdy nejde len tak — vždy musí byť dôvod (`send_reason`)
  * posiela sa len keď je to zapnuté (`behavior.photos_enabled`) — gate je
    v userbote, nie tu

Dôvody sú presne tri:
  „asked" — vypýtal si ju,
  „proof" — pochybuje, že je skutočná (fotka + ironická hláška),
  „first" — jedna jediná selfie sama od seba, medzi 10. a 20. správou.

FANVUE SA TOHTO NETÝKA: Fanvue má vlastný vault a vlastnú cestu.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

# Pevné albumy. Poradie tu nie je náhodné — je to fallback poradie, keď album
# podľa miesta nesedí (viď `pick`).
FOLDERS = ("home", "gym", "city", "bed_morning", "bed_night", "universal")

# „posli fotku", „what are you wearing", „show me" — vypýtanie si fotky.
_WANTS_PHOTO_RE = re.compile(
    r"\b(send|post|share|show)\s+(me\s+)?(a\s+|another\s+|one\s+)?"
    r"(pic|pics|picture|photo|photos|selfie|selfies|snap|something)\b"
    r"|\b(pic|picture|photo|selfie)\s*\?"
    r"|\bcan\s+i\s+see\s+(you|u|more)\b"
    r"|\blet\s+me\s+see\s+(you|u)\b"
    r"|\bwhat\s+(are\s+)?(you|u)\s+wearing\b"
    r"|\bwhat\s+do\s+(you|u)\s+look\s+like\b"
    r"|\bshow\s+me\s+what\b"
    r"|\bsend\s+(something|nudes?)\b"
    r"|\bany\s+(pics|photos)\b",
    re.IGNORECASE,
)

# „prove ur real", „show me youre not a bot" — pýta si fotku ako dôkaz.
_WANTS_PROOF_RE = re.compile(
    r"\bprove\s+(it|to\s+me|(that\s+)?(u|you|ur|youre|you'?re)\b)"
    r"|\bshow\s+me\s+(that\s+)?(u|you|ur|youre)\b"
    r"|\b(pic|picture|photo|selfie)\b.{0,20}\b(prove|proof|real)\b"
    r"|\b(prove|proof)\b.{0,20}\b(pic|picture|photo|selfie)\b"
    r"|\b(are|r)\s+(you|u)\s+(a\s+)?(bot|ai|real|fake)\b"
    r"|\b(you'?re|youre|ur)\s+(a\s+)?(bot|ai|fake)\b",
    re.IGNORECASE,
)


def wants_photo(text: str) -> bool:
    """Vypýtal si fotku? Bez toho sa fotka neposiela nikdy (okrem prvej)."""
    return bool(_WANTS_PHOTO_RE.search(text or ""))


def wants_proof(text: str) -> bool:
    """Pochybuje, že je skutočná / obviňuje ju z bota."""
    return bool(_WANTS_PROOF_RE.search(text or ""))


# ---------- album podľa miesta v harmonograme ----------

def folder_for(place: str, hour: int) -> str:
    """Ktorý album sedí na to, kde práve je a v akú hodinu.

    Mapa je vedomé rozhodnutie (potvrdené s Marekom): kuchyňa a kúpeľňa patria
    „domov", kaviareň a auto do „mesta", posteľ sa delí podľa hodiny na ráno
    a noc. Čo nesedí, spadne na univerzál.
    """
    p = (place or "").lower()
    if p == "gym":
        return "gym"
    if p in ("outside", "cafe", "car"):
        return "city"
    if p == "bedroom":
        # Ráno/cez deň = „bed morning", večer/noc = „bed night".
        return "bed_morning" if 4 <= hour < 15 else "bed_night"
    if p in ("home", "kitchen", "bathroom"):
        return "home"
    return "universal"


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def cooldown_passed(user: Dict[str, Any], minutes: int, now: Optional[datetime] = None) -> bool:
    """Neposielaj fotky jednu za druhou — pôsobí to ako automat.

    Výnimka: okno na druhú fotku z toho istého albumu (30 min) rieši `pick`
    cez `window_open`; cooldown a okno sa nemiešajú — cooldown platí na
    VLASTNÚ iniciatívu, okno na vyžiadanú druhú fotku.
    """
    last = _parse(user.get("last_photo_at"))
    if last is None:
        return True
    reference = now or datetime.now(timezone.utc)
    return reference - last >= timedelta(minutes=minutes)


# Prvá selfie od seba padne niekde v tomto rozsahu správ — neskôr než predtým,
# nech konverzácia najprv chvíľu beží.
FIRST_SELFIE_MIN = 10
FIRST_SELFIE_MAX = 20

# Ako dlho po prvej fotke z albumu smie ešte odísť druhá z toho istého —
# a to len keď si ju vypýta alebo pochybuje. Po ňom sa album v chate zavrie.
SECOND_WINDOW_MIN = 30


def first_selfie_at(tg_id: int) -> int:
    """Pri koľkej správe pošle prvú selfie sama. Stabilné pre daného človeka."""
    span = FIRST_SELFIE_MAX - FIRST_SELFIE_MIN + 1
    return FIRST_SELFIE_MIN + (abs(int(tg_id)) % span)


def send_reason(text: str, user: Dict[str, Any]) -> Optional[str]:
    """Prečo (a či vôbec) k tejto odpovedi patrí fotka. None = neposielaj.

    Náhodné/„revive" fotky sa neposielajú vôbec: jedna na začiatku, potom už
    len na vyžiadanie alebo pri pochybnosti. Tak sa albumy nevyčerpajú.
    """
    if wants_photo(text):
        return "asked"
    # Dôkaz/pochybnosť sa rieši len tomu, kto od nej fotku UŽ videl — inak sa
    # k nej cez obvinenie z bota dostane ktokoľvek hneď v prvej správe.
    if wants_proof(text) and user.get("last_photo_at"):
        return "proof"
    # Jedna selfie sama od seba za konverzáciu. `last_photo_at` je zároveň
    # príznak „už nejaká išla".
    if not user.get("last_photo_at"):
        count = int(user.get("msg_count") or 0)
        if count >= first_selfie_at(int(user.get("tg_id") or 0)):
            return "first"
    return None


def used_folders(library: Sequence[Dict[str, Any]], sent_ids: Sequence[int]) -> set:
    """Albumy, z ktorých už v tomto chate nejaká fotka odišla."""
    seen = set(sent_ids or ())
    return {(p.get("folder") or "universal") for p in library if p["id"] in seen}


def last_folder(library: Sequence[Dict[str, Any]], sent_ids: Sequence[int]) -> Optional[str]:
    """Album poslednej poslanej fotky (`sent_ids` je od najnovšej)."""
    if not sent_ids:
        return None
    podla_id = {p["id"]: p for p in library}
    posledna = podla_id.get(sent_ids[0])
    return (posledna or {}).get("folder") or "universal" if posledna else None


def window_open(user: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Je posledná fotka dosť čerstvá, aby smela odísť druhá z toho albumu?"""
    last = _parse(user.get("last_photo_at"))
    if last is None:
        return False
    reference = now or datetime.now(timezone.utc)
    return (reference - last) <= timedelta(minutes=SECOND_WINDOW_MIN)


def pick(
    library: Sequence[Dict[str, Any]],
    sent_ids: Sequence[int],
    schedule_folder: str,
    reason: str,
    open_folder: Optional[str] = None,
    can_reopen: bool = False,
    prefer_spicy: bool = False,
    rng: Optional[random.Random] = None,
) -> Optional[Dict[str, Any]]:
    """Vyberie fotku podľa albumovej logiky. None = neposielaj nič.

    - `schedule_folder`: album podľa toho, kde práve je (z `folder_for`).
    - `open_folder` + `can_reopen`: album poslednej fotky a či sme ešte
      v 30-min okne — vtedy smie odísť DRUHÁ z toho istého (len pri „asked"/
      „proof").
    - Album sa použije najviac raz za chat: `used_folders` sa preskakujú.
    """
    r = rng or random
    seen = set(sent_ids or ())
    used = used_folders(library, sent_ids)

    def volne(folder: str) -> List[Dict[str, Any]]:
        pics = [
            p for p in library
            if p.get("active", True) and p["id"] not in seen
            and (p.get("folder") or "universal") == folder
        ]
        if prefer_spicy:
            spicy = [p for p in pics if p.get("spicy")]
            if spicy:
                return spicy
        return pics

    # Druhá fotka z otvoreného albumu — len keď si vypýtal/pochybuje a sme
    # ešte v okne. Toto je JEDINÁ cesta, ako z už použitého albumu ešte niečo
    # odíde.
    if reason in ("asked", "proof") and open_folder and can_reopen:
        cont = volne(open_folder)
        if cont:
            return r.choice(cont)

    # Nový album, každý najviac raz za chat. Priorita: kde práve je → univerzál.
    poradie = [schedule_folder, "universal"]
    if reason in ("asked", "proof"):
        # Vypýtal si ju — keď album podľa miesta ani univerzál nesedí, siahni
        # po hociktorom nepoužitom. Pri „first" (vlastná iniciatíva) NIE:
        # radšej nič než fotka z pláže, keď je podľa rozvrhu v posteli.
        poradie += [f for f in FOLDERS if f not in poradie]

    for folder in poradie:
        if folder in used:
            continue
        pics = volne(folder)
        if pics:
            return r.choice(pics)
    return None


def describe_for_prompt(photo: Dict[str, Any]) -> str:
    """Čo modelu povieme o fotke, ktorú práve posiela."""
    bits = [photo.get("caption") or "fotka teba"]
    situation = (photo.get("situation") or "").strip()
    if situation:
        bits.append(f"situácia: {situation}")
    return " · ".join(bits)


def remaining(library: Sequence[Dict[str, Any]], sent_ids: Sequence[int]) -> int:
    seen = set(sent_ids or ())
    return sum(1 for p in library if p.get("active", True) and p["id"] not in seen)
