"""Fotoknižnica — kedy poslať fotku, ktorú, a aby sa nikdy neopakovala.

Pravidlá, ktoré sú v kóde a nie v prompte, lebo na ne sa musí dať spoľahnúť:
  * tá istá fotka nikdy dvakrát tomu istému človeku
  * každá modelka posiela výhradne svoje fotky (oddelené schémou)
  * medzi fotkami je odstup, aby to nebolo fotoalbum
  * fotka nikdy nejde len tak — vždy musí byť dôvod (`send_reason`)

Dôvody sú presne tri:
  „asked"  — vypýtal si ju,
  „first"  — jedna jediná selfie sama od seba, niekde medzi 5. a 10. správou,
  „revive" — vrátil sa po dlhom tichu a treba to nahodiť.

Knižnica je malá, takže sa fotky musia dávkovať. Preto pri vlastnej
iniciatíve platí prísny filter na dennú dobu: keď nič nesedí, nepošle nič
a počká — lepšie než v noci ukazovať pláž.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

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

# Chce fotku toho, čo práve robí — vtedy má sedieť situácia.
_WANTS_CURRENT_RE = re.compile(
    r"\bwhat\s+(are\s+)?(you|u)\s+(doing|up\s+to|wearing)\b"
    r"|\bpic\s+of\s+what\b|\bshow\s+me\s+what\b|\bright\s+now\b",
    re.IGNORECASE,
)


# „prove ur real", „show me youre not a bot" — pýta si fotku ako dôkaz.
# Odmietnuť ju vtedy je najhorší možný ťah: Linusovi už jedna fotka predtým
# odišla, takže odmietnutie znelo ako priznanie a odišiel aj s účtom.
_WANTS_PROOF_RE = re.compile(
    r"\bprove\s+(it|to\s+me|(that\s+)?(u|you|ur|youre|you'?re)\b)"
    r"|\bshow\s+me\s+(that\s+)?(u|you|ur|youre)\b"
    r"|\b(pic|picture|photo|selfie)\b.{0,20}\b(prove|proof|real)\b"
    r"|\b(prove|proof)\b.{0,20}\b(pic|picture|photo|selfie)\b",
    re.IGNORECASE,
)


def wants_photo(text: str) -> bool:
    """Vypýtal si fotku? Bez toho sa fotka neposiela nikdy."""
    return bool(_WANTS_PHOTO_RE.search(text or ""))


def wants_proof(text: str) -> bool:
    """Pýta si fotku ako dôkaz, že je skutočná."""
    return bool(_WANTS_PROOF_RE.search(text or ""))


def wants_current_moment(text: str) -> bool:
    return bool(_WANTS_CURRENT_RE.search(text or ""))


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
    """Neposielaj fotky jednu za druhou — pôsobí to ako automat."""
    last = _parse(user.get("last_photo_at"))
    if last is None:
        return True
    reference = now or datetime.now(timezone.utc)
    return reference - last >= timedelta(minutes=minutes)


# Prvá selfie od seba padne niekde v tomto rozsahu správ.
FIRST_SELFIE_MIN = 5
FIRST_SELFIE_MAX = 10

# Po akom tichu má zmysel nahodiť konverzáciu fotkou a ako často.
REVIVE_AFTER_H = 12
REVIVE_CHANCE = 0.18


def first_selfie_at(tg_id: int) -> int:
    """Pri koľkej správe pošle prvú selfie sama.

    Odvodené z jeho ID, takže je to pre daného človeka stabilné aj po
    restarte workera, ale medzi ľuďmi to nevychádza rovnako.
    """
    span = FIRST_SELFIE_MAX - FIRST_SELFIE_MIN + 1
    return FIRST_SELFIE_MIN + (abs(int(tg_id)) % span)


def send_reason(
    text: str,
    user: Dict[str, Any],
    gap_hours: Optional[float] = 0.0,
    rng: Optional[random.Random] = None,
) -> Optional[str]:
    """Prečo (a či vôbec) k tejto odpovedi patrí fotka.

    None = nič neposielaj. Random fotky sa neposielajú nikdy, inak by knižnicu
    vyčerpala za pár dní a prestalo by to dávať zmysel.
    """
    if wants_photo(text):
        return "asked"

    # Dôkaz sa dáva len tomu, kto od nej fotku už videl. Vtedy je odmietnutie
    # nekonzistentné a on to okamžite vidí. Kto nevidel žiadnu, sa k nej
    # nedostane cez obvinenie z bota.
    if wants_proof(text) and user.get("last_photo_at"):
        return "proof"

    # Jedna selfie sama od seba za konverzáciu. `last_photo_at` je zároveň
    # príznak „už nejaká išla" — netreba na to ďalší stĺpec.
    if not user.get("last_photo_at"):
        count = int(user.get("msg_count") or 0)
        if count >= first_selfie_at(int(user.get("tg_id") or 0)):
            return "first"
        return None

    # Odstup je None, keď mu ešte nikdy neodpísala (nový človek alebo
    # vymazaná história). Vtedy nie je čo oživovať.
    if (gap_hours or 0) >= REVIVE_AFTER_H and (rng or random).random() < REVIVE_CHANCE:
        return "revive"
    return None


def pick(
    library: Sequence[Dict[str, Any]],
    already_sent_ids: Sequence[int],
    part_of_day: str,
    prefer_spicy: bool = False,
    rng: Optional[random.Random] = None,
    strict_time: bool = False,
    same_set: bool = False,
) -> Optional[Dict[str, Any]]:
    """Vyberie fotku, ktorú tento človek ešte nevidel.

    Uprednostní tie, ktoré sedia na dennú dobu — aby k fotke z postele
    nenapísala, že je práve na nákupoch. Keď si fotku vypýtal, radšej pošle
    aj nesediacu než žiadnu; pri vlastnej iniciatíve (`strict_time`) počká.
    """
    poradie = list(already_sent_ids or ())
    seen = set(poradie)
    available = [p for p in library if p.get("active", True) and p["id"] not in seen]
    if not available:
        return None

    r = rng or random

    # Nadväznosť na poslednú fotku: keď bola z kolekcie, ďalšia ide prednostne
    # z tej istej — ale LEN kým sa rozhovor točí okolo tej chvíle. Séria je
    # „teraz som takto oblečená", nie zásoba na týždeň: keď z tej istej pláže
    # prišla fotka aj včera aj dnes, je to na prvý pohľad zásobník.
    if poradie and same_set:
        podla_id = {p["id"]: p for p in library}
        posledna = podla_id.get(poradie[0])
        kolekcia = (posledna or {}).get("collection") or ""
        if kolekcia:
            rovnaka = [p for p in available if (p.get("collection") or "") == kolekcia]
            if rovnaka:
                available = rovnaka

    if prefer_spicy:
        spicy = [p for p in available if p.get("spicy")]
        if spicy:
            available = spicy

    fitting = [
        p for p in available
        if not p.get("parts") or part_of_day in (p.get("parts") or [])
    ]
    if not fitting:
        return None if strict_time else r.choice(available)
    return r.choice(fitting)


def describe_for_prompt(photo: Dict[str, Any]) -> str:
    """Čo modelu povieme o fotke, ktorú práve posiela."""
    bits = [photo.get("caption") or "fotka teba"]
    situation = (photo.get("situation") or "").strip()
    if situation:
        bits.append(f"situácia: {situation}")
    return " · ".join(bits)


def remaining(library: Sequence[Dict[str, Any]], already_sent_ids: Sequence[int]) -> int:
    seen = set(already_sent_ids or ())
    return sum(1 for p in library if p.get("active", True) and p["id"] not in seen)


# Ako dlho po poslednej fotke ešte platí, že sme „stále v tej chvíli".
SET_WINDOW_MIN = 10

# A ani vtedy nejde ďalšia z tej istej série zakaždým.
SET_CHANCE = 0.5


def set_continues(
    user: Dict[str, Any],
    now: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> bool:
    """Nadviazať ďalšou fotkou z tej istej série?

    Len krátko po predošlej — o deň neskôr už tá istá pláž nie je „práve
    teraz", ale zásobník. A ani v tom okne to nie je zakaždým.
    """
    last = _parse(user.get("last_photo_at"))
    if last is None:
        return False
    minulo = ((now or datetime.now(timezone.utc)) - last).total_seconds() / 60
    if minulo > SET_WINDOW_MIN:
        return False
    return (rng or random).random() < SET_CHANCE
