"""Fakty o ňom — append-only pamäť, ktorá sa neprepisuje sama zo seba.

Prečo nie summary: summary sa prepisuje z predošlého summary, takže po
pätnástom prepise z toho, čo povedal na začiatku, nezostane nič. A strata je
postupná, takže si jej nikto nevšimne. Fakty sa preto ukladajú samostatne
a summary sa skladá z nich, nie zo seba.

Nová hodnota starú neprepíše, len ju označí za superseded — „rozišiel sa"
nezmaže „má priateľku Sarah", odloží ju.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

import similar

log = logging.getLogger(__name__)

# Kľúče zosúladené s katalógom tém — keď je fakt známy, téma sa už neotvorí.
TOPIC_KEYS = (
    "name", "location", "work", "age", "relationship",
    "hobbies", "music", "food", "travel", "pets", "gym", "how_found",
)

# Celý slovník kľúčov. Zámerne uzavretý.
#
# Predtým si extraktor smel vymyslieť vlastný kľúč a na živých dátach z toho
# vyšlo presne to, čo sa dalo čakať: `past_locations` aj `previous_locations`
# s tou istou hodnotou, `equipment` aj `tools`, `values` aj `wants`. Zlučovanie
# porovnáva kľúče, takže dva názvy toho istého sa nikdy nestretli a fact sheet
# rástol donekonečna.
FACT_KEYS = TOPIC_KEYS + (
    "family", "kids", "health", "money", "car", "home", "past",
    "plans", "values", "mood_pattern", "sport_team", "drink", "smoke",
    "schedule", "tech", "other",
)

# Čo model vracal ako vlastný kľúč a čo to má byť v skutočnosti. Bez tohto by
# uzavretý zoznam len zahodil polovicu faktov namiesto toho, aby ich zaradil.
KEY_ALIASES = {
    "job": "work", "occupation": "work", "profession": "work", "career": "work",
    "workplace": "work", "employment": "work", "business": "work",
    "city": "location", "state": "location", "country": "location",
    "hometown": "location", "origin": "location", "lives": "location",
    "living_situation": "home", "housing": "home", "apartment": "home",
    "past_locations": "past", "previous_locations": "past", "childhood": "past",
    "childhood_location": "past", "history": "past", "background": "past",
    "relationship_history": "relationship", "ex": "relationship",
    "dating": "relationship", "marriage": "relationship", "wife": "relationship",
    "girlfriend": "relationship", "partner": "relationship", "single": "relationship",
    "loneliness": "relationship",
    "children": "kids", "kid_name": "kids", "son": "kids", "daughter": "kids",
    "parents": "family", "siblings": "family", "brother": "family",
    "sister": "family", "mother": "family", "father": "family", "pet": "pets",
    "dog": "pets", "cat": "pets",
    "hobby": "hobbies", "interests": "hobbies", "free_time": "hobbies",
    "tv": "hobbies", "tv_shows": "hobbies", "shows": "hobbies", "movies": "hobbies",
    "games": "hobbies", "gaming": "hobbies", "reading": "hobbies",
    "bike": "hobbies", "motorcycle": "hobbies", "fishing": "hobbies",
    "workout": "gym", "fitness": "gym", "training": "gym", "sport": "gym",
    "sports": "gym", "team": "sport_team",
    "band": "music", "artist": "music", "genre": "music",
    "drinks": "drink", "alcohol": "drink", "beer": "drink", "coffee": "drink",
    "smoking": "smoke", "cigarettes": "smoke",
    "vehicle": "car", "truck": "car", "driving": "car",
    "income": "money", "salary": "money", "finances": "money",
    "beliefs": "values", "belief": "values", "wants": "values",
    "preferences": "values", "preference": "values", "mindset": "values",
    "goals": "plans", "future": "plans", "dreams": "plans",
    "vacation": "travel", "trips": "travel", "trip": "travel",
    "equipment": "tech", "tools": "tech", "phone": "tech", "computer": "tech",
    "birthday": "age", "born": "age",
    "routine": "schedule", "work_schedule": "schedule", "shift": "schedule",
    "found": "how_found", "discovery": "how_found",
}

# Kľúče, ktoré popisujú OKAMIH, nie človeka. Tie sa neukladajú nikdy.
#
# Na živých dátach mal najaktívnejší klient uložené ako trvalý fakt, že „leží
# na gauči a pozerá seriál" — pod štyrmi kľúčmi naraz. O týždeň by to mala
# v prompte pod hlavičkou „ČO O ŇOM VIEŠ" a pýtala by sa naň ako na fakt.
# Na to, čo práve robí, je história konverzácie.
_TRANSIENT_KEYS = frozenset(
    """
    activity current_activity currently doing status now today tonight
    time current_time weekend yesterday tomorrow moment situation
    current_mood feeling state whereabouts current_location
    """.split()
)

# A to isté podľa znenia — model niekedy okamih zabalí do legitímneho kľúča.
_TRANSIENT_RE = re.compile(
    r"\b(right now|at the moment|currently|just (got|came|woke|finished|started)"
    r"|is (watching|eating|drinking|laying|lying|sitting|texting)"
    r"|on the couch|in bed now|still early|still up|about to"
    r"|today|tonight|this (morning|afternoon|evening|weekend)"
    r"|prave|momentalne|dnes|vecer|teraz)\b",
    re.IGNORECASE,
)

_EXTRACT_SYSTEM = """\
Si extraktor faktov. Z konverzácie vytiahni, čo sa dozvedelo O ŇOM (nie o nej).

Vráť IBA JSON pole, nič iné, v tvare:
[{"key": "work", "value": "vodič kamiónu, jazdí po západnom pobreží"}]

POVOLENÉ KĽÚČE — iný nepoužívaj, radšej zvoľ najbližší alebo "other":
name, location, work, age, relationship, hobbies, music, food, travel, pets,
gym, how_found, family, kids, health, money, car, home, past, plans, values,
mood_pattern, sport_team, drink, smoke, schedule, tech, other

UKLADAJ LEN TRVALÉ VECI — také, ktoré o ňom platia aj o mesiac.
NIKDY neukladaj to, čo práve robí, kde práve je, ako sa práve cíti ani čo sa
mu stalo dnes. To si pamätá história konverzácie, tu to len zavadzia.
    ÁNO:  "vodič kamiónu"  ·  "má psa Bruna"  ·  "vyrastal v Michigane"
    NIE:  "leží na gauči"  ·  "je mu smutno"  ·  "má dnes voľno"
          "práve dopozeral seriál"  ·  "u neho je ešte skoro"

Ďalšie pravidlá:
- Len to, čo naozaj povedal. Nič nedomýšľaj a nič nehádaj.
- Hodnota nech je krátka veta alebo fráza, nie citát.
- Jednu vec ulož RAZ. Neposielaj tú istú informáciu pod dvoma kľúčmi.
- Ak sa nič trvalé nedozvedelo, vráť []. Prázdna odpoveď je správna odpoveď.
- Nezaraďuj nič o nej, len o ňom."""


def canonical_key(key: str) -> str:
    """Zjednotí kľúč na jeden z povolených. Neznámy skončí ako „other"."""
    ocisteny = re.sub(r"[^a-z_]", "", (key or "").strip().lower().replace(" ", "_"))
    ocisteny = KEY_ALIASES.get(ocisteny, ocisteny)
    return ocisteny if ocisteny in FACT_KEYS else "other"


def is_transient(key: str, value: str) -> bool:
    """Je to okamih, a nie fakt o človeku?"""
    if re.sub(r"[^a-z_]", "", (key or "").lower()) in _TRANSIENT_KEYS:
        return True
    return bool(_TRANSIENT_RE.search(value or ""))


def _coerce(raw: str) -> List[Dict[str, str]]:
    """Model občas obalí JSON do textu alebo do code fence."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    out: List[Dict[str, str]] = []
    for item in parsed if isinstance(parsed, list) else []:
        if not isinstance(item, dict):
            continue
        surovy = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()[:300]
        if not surovy or not value:
            continue
        if is_transient(surovy, value):
            log.info("Fakt %r zahodený — je to okamih, nie fakt: %r", surovy, value[:60])
            continue
        key = canonical_key(surovy)
        # Tá istá vec pod dvoma kľúčmi v jednej dávke — nechaj prvú.
        if any(similar.same_idea(value, existing["value"]) for existing in out):
            continue
        out.append({"key": key, "value": value})
    return out


def transcript(rows: Sequence[Dict[str, Any]], her_name: str) -> str:
    import memory

    return "\n".join(memory.speaker_line(row, her_name) for row in rows)


def merge_plan(existing: Sequence[Dict[str, Any]], found: Sequence[Dict[str, str]]) -> Dict[str, List]:
    """Čo zapísať: nové fakty a ktoré staré tým odložiť. Čistá funkcia.

    Zhoda sa hľadá v dvoch krokoch a záleží na poradí:

      1. **Tá istá vec inými slovami, kdekoľvek.** Toto je nové a je to to
         dôležitejšie. „má tetovanie" a „je tetovaná" sa predtým porovnávali
         znak po znaku, takže parafráza prešla vždy a pamäť sa ňou zanášala.
         Hľadá sa naprieč VŠETKÝMI aktívnymi faktami, nielen pod tým istým
         kľúčom — presne preto, že práve rozdielne kľúče pre tú istú vec boli
         ten problém.
      2. **Nová hodnota pod známym kľúčom** = zmena, stará sa odloží.
    """
    active = [f for f in existing if f.get("superseded_by") is None]
    podla_kluca = {f["key"]: f for f in active}
    inserts, confirms, supersedes = [], [], []
    # Čo v tejto dávke pribudlo, sa musí porovnávať tiež — inak by dva nové
    # fakty o tom istom prešli oba.
    pribudlo: List[str] = []

    for item in found:
        key, value = item["key"], item["value"]

        dvojnik = next(
            (f for f in active if similar.same_idea(value, f.get("value") or "")), None
        )
        if dvojnik is not None:
            confirms.append(dvojnik["id"])
            continue
        if any(similar.same_idea(value, novy) for novy in pribudlo):
            continue

        current = podla_kluca.get(key)
        if current is not None:
            supersedes.append(current["id"])
        inserts.append(item)
        pribudlo.append(value)

    return {"inserts": inserts, "confirms": confirms, "supersedes": supersedes}


# Koľko faktov sa nanajvýš dostane do promptu. Dlhší zoznam už nie je pamäť,
# ale výpis z databázy — a v prompte uberá miesto tomu, čo nikde inde nie je.
SHEET_LIMIT = 20


def sheet(rows: Sequence[Dict[str, Any]]) -> str:
    """Fakty pre prompt. Podávané ako „vieš o ňom", nikdy ako výpis z databázy.

    Parafrázy sa vyhadzujú ešte tu, nielen pri zápise: v databáze sú roky
    staré riadky spred zavedenia zlučovania a tie by inak model videl ďalej.
    """
    active = [
        f for f in rows
        if f.get("superseded_by") is None
        and not is_transient(f.get("key") or "", f.get("value") or "")
    ]
    if not active:
        return ""
    hodnoty = similar.dedupe([f.get("value") or "" for f in active])
    lines = [f"- {v}" for v in hodnoty[-SHEET_LIMIT:]]
    old = [f for f in rows if f.get("superseded_by") is not None][-3:]
    if old:
        lines.append("Predtým platilo (už nie): " + "; ".join(f["value"] for f in old))
    return "\n".join(lines)


def known_keys(rows: Sequence[Dict[str, Any]]) -> List[str]:
    """Témy, na ktoré sa už netreba pýtať, lebo odpoveď poznáme.

    Okamih uložený pod kľúčom témy sa nepočíta. Naživo bol pod `location`
    zapísaný text „on the couch watching a show" — a tým sa téma „odkiaľ je"
    natrvalo zamkla, hoci to nikdy nezistila.
    """
    return sorted(
        {
            f["key"] for f in rows
            if f.get("superseded_by") is None
            and f["key"] in TOPIC_KEYS
            and not is_transient(f["key"], f.get("value") or "")
        }
    )


async def extract(llm, rows: Sequence[Dict[str, Any]], her_name: str) -> List[Dict[str, str]]:
    """Vytiahne fakty z posledných správ.

    Beží na hlavnom modeli a pri nízkej teplote — chyba v extrakcii žije
    navždy, takže sa tu nešetrí ani na modeli, ani na zopakovateľnosti.
    """
    if not rows:
        return []
    try:
        raw = await llm.structured(_EXTRACT_SYSTEM, transcript(rows, her_name))
        return _coerce(raw)
    except Exception as exc:  # noqa: BLE001 - nesmie zhodiť odpovedanie
        log.warning("Extrakcia faktov zlyhala: %s", exc)
        return []
