"""Ťahy pri obsahu — a nikdy ten istý dvakrát tomu istému človeku.

PREČO. Do promptu pribudol postup, ktorý Marekovi naozaj predal (nechaj ho
vybrať → zaváhaj → exkluzivita → fotka s príbehom). Lenže postup, ktorý sa
zopakuje tretíkrát, prestáva byť postup a stáva sa formulkou — a formulku
človek spozná rýchlejšie než čokoľvek iné. Marek to povedal presne: „nemôžeme
rovnakú taktiku používať na toho istého človeka dookola".

Je to tá istá myšlienka ako `gags.py` na Telegrame: register s odstupom.
Rozdiel je len v tom, že tu nejde o vtipy, ale o to, AKO sa obsah prinesie.

ŤAH NIE JE NÁLADA. Každý z nich je iný spôsob, ako sa k veci dostať — inak by
z toho boli tri opisy tej istej ponuky.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Momenty, v ktorých sa ťah hodí. Zhodujú sa s `fvflow.paid_moment`.
ASKED = "asked"        # vypýtal si to sám
NUDGE = "nudge"        # dlho ticho, prichádza s tým ona
AFTER_BUY = "after_buy"  # práve kúpil a rozhovor pokračuje

# Aj keby mal ťah nastavené menej. Tri dni je minimum, po ktorom si človek
# nespojí, že to už raz počul.
MIN_COOLDOWN_H = 72


@dataclass(frozen=True)
class Tah:
    key: str
    hint: str
    momenty: Tuple[str, ...]
    cooldown_h: int = 120  # 5 dní


CATALOG: Tuple[Tah, ...] = (
    # --- naživo overené: presne takto predali chaty za 64,99 a 69,99 $ ---
    Tah(
        "vyber_z_dvoch",
        "Nechaj HO vybrať. Ponúkni mu dve konkrétne veci a nech si povie, ktorú "
        "chce — v duchu „u want me sitting or bent over?“. Potom mu pošli TO, "
        "čo si vybral, nie to, čo máš najbližšie po ruke.",
        (ASKED, AFTER_BUY),
    ),
    Tah(
        "zavahanie",
        "Zaváhaj nad tou dobrou. Napíš, že nie si si istá, či ju chceš dávať, "
        "a až potom povedz, že preňho áno. Váhanie predáva viac než ponuka — "
        "z lacnej veci robí vzácnu.",
        (ASKED, NUDGE),
    ),
    Tah(
        "pribeh",
        "Priviaž to k spomienke. Jedna veta o tom, kedy to bolo alebo čo sa "
        "vtedy dialo („i remember that pretty damn well“). Fotka s príbehom sa "
        "predáva, fotka s popisom je katalóg.",
        (ASKED, NUDGE, AFTER_BUY),
    ),
    Tah(
        "exkluzivita",
        "Postav to na tom, že to nikto iný nemá. Že si to sem nikdy nedávala a "
        "je to len preňho. Nič iné nekupuje tak spoľahlivo ako pocit, že to "
        "existuje len pre neho.",
        (ASKED, NUDGE),
    ),
    # --- ďalšie cesty k tomu istému, nech sa register má čím striedať ---
    Tah(
        "cerstve",
        "Povedz, že si to práve nafotila a ešte to nikde nie je. Nie ako "
        "ponuka — ako niečo, čím sa pochváliš, lebo si z toho sama nadšená.",
        (NUDGE,),
    ),
    Tah(
        "on_povie",
        "Otoč to na neho: nech ti PRESNE povie, čo by chcel vidieť, a ty mu to "
        "spravíš na mieru. Nechaj ho to opísať, čím konkrétnejšie, tým lepšie.",
        (ASKED, AFTER_BUY, NUDGE),
    ),
    Tah(
        "naladena",
        "Vyjdi zo SEBA, nie z neho — že si dnes taká naladená a niečo si "
        "nafotila. Nepýtaj sa ho, či to chce; povedz, že to máš.",
        (NUDGE,),
    ),
    Tah(
        "odmena",
        "Sprav z toho odmenu za to, aký k tebe je — že si trpezlivý a milý a "
        "že za to niečo dostane. Nikdy nie ako obchod, vždy ako gesto.",
        (AFTER_BUY, NUDGE),
    ),
)

BY_KEY: Dict[str, Tah] = {t.key: t for t in CATALOG}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def je_volny(
    tah: Tah, pouzite: Dict[str, str], moment: str, now: Optional[datetime] = None
) -> bool:
    if moment not in tah.momenty:
        return False
    kedy = _parse((pouzite or {}).get(tah.key))
    if kedy is None:
        return True
    odstup = max(tah.cooldown_h, MIN_COOLDOWN_H)
    return (now or datetime.now(timezone.utc)) - kedy >= timedelta(hours=odstup)


def vyber(
    pouzite: Optional[Dict[str, str]],
    moment: str,
    rng: Optional[random.Random] = None,
    now: Optional[datetime] = None,
) -> Optional[Tah]:
    """Ťah, ktorý tento človek nedostal nedávno.

    Keď sú všetky vyčerpané, vráti `None` a prompt ostane bez pokynu na
    konkrétny ťah — to je lepšie než zopakovať ten, ktorý si pamätá. Bežné
    pravidlá predaja platia aj bez neho.
    """
    if not moment:
        return None
    volne = [t for t in CATALOG if je_volny(t, pouzite or {}, moment, now)]
    if not volne:
        return None
    return (rng or random).choice(volne)


def zapis(pouzite: Optional[Dict[str, str]], kluc: str, now: datetime) -> Dict[str, str]:
    """Zapíše ťah ako použitý.

    Zapisuje sa už pri PONÚKNUTÍ, nie po overení, či ho model naozaj použil —
    rovnako ako pri vtipoch. Radšej ťah raz nevyužiť než ho zopakovať.
    """
    out = dict(pouzite or {})
    out[kluc] = now.astimezone(timezone.utc).isoformat()
    return out


def blok(tah: Optional[Tah]) -> str:
    """Pokyn do promptu. Bez ťahu prázdny reťazec."""
    if tah is None:
        return ""
    return f"AKO TO PRINES TERAZ (inak než minule):\n{tah.hint}"


def pouzite_z(row: Dict[str, Any]) -> Dict[str, str]:
    """Register z riadku fanúšika. Chýbajúci stĺpec = prázdny register."""
    hodnota = (row or {}).get("used_moves")
    return dict(hodnota) if isinstance(hodnota, dict) else {}


def nedavne(pouzite: Optional[Dict[str, str]], limit: int = 6) -> List[str]:
    return [k for k in list((pouzite or {}).keys())[:limit] if k in BY_KEY]
