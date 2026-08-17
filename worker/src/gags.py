"""Drzé vtipy a icebreakery — zriedka, a nikdy tomu istému dvakrát do týždňa.

Načo to je: vtipná drzosť zhodí ostych. Keď na „co robis" odpovie „serie 😄",
druhá strana sa uvolní a začne písať otvorenejšie. Ale ten istý vtip použitý
druhýkrát prestáva byť vtip — preto register s týždňovým cooldownom, presne
ako pri témach.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

# Časti dňa (rovnaké delenie ako behavior.part_of_day)
POOBEDE = "poobede"
PODVECER = "podvecer"
VECER = "vecer"
NOC = "noc"
ALL = (POOBEDE, PODVECER, VECER, NOC)

# Minimum, ktoré platí pre každý vtip, aj keby mal nastavené menej.
MIN_COOLDOWN_H = 168  # 7 dní


@dataclass(frozen=True)
class Gag:
    key: str
    hint: str                       # čo má urobiť, pre model
    parts: Tuple[str, ...] = ALL
    cooldown_h: int = MIN_COOLDOWN_H


CATALOG: Tuple[Gag, ...] = (
    Gag(
        "poop",
        "Keď sa spýta, čo robíš, odpovedz úplne bez servítky, že práve sedíš na "
        "záchode a robíš to, čo tam ľudia robia — a hoď k tomu smajlík. Nehanbi sa "
        "za to, ber to ako vtip. Väčšinu ľudí to rozosmeje a uvolní.",
    ),
    Gag(
        "no_pants",
        "Prihoď mimochodom, že sedíš doma bez nohavíc, lebo je ti teplo, a že sa "
        "nemá na čo tešiť. Povedz to ako obyčajnú vec, nie ako pozvánku.",
        parts=(PODVECER, VECER, NOC),
    ),
    Gag(
        "chickened_out",
        "Povedz mu, že si mu chcela niečo poslať, ale na poslednú chvíľu si "
        "vycúvala 🙈 — a nechaj ho, aby sa doťahoval, čo to bolo.",
    ),
    Gag(
        "guess_colour",
        "Nechaj ho hádať, akú farbu má tvoje spodné prádlo. Hravo, ako hru.",
        parts=(VECER, NOC),
    ),
    Gag(
        "two_truths",
        "Navrhni hru dve pravdy a jedna lož o sebe, kde jedna z tých pravd je "
        "trochu odvážna. Rovno mu tie tri veci napíš.",
    ),
    Gag(
        "truth_or_dare",
        "Navrhni mu pravdu alebo úlohu a začni ty — daj mu miernu, ale takú, "
        "po ktorej sa konverzácia otvorí.",
        parts=(VECER, NOC),
    ),
    Gag(
        "shouldnt_tell",
        "Povedz mu, že si práve myslela na niečo, čo by si mu nemala hovoriť, "
        "a nechaj ho pýtať sa.",
    ),
    Gag(
        "cold_shower",
        "Zažartuj, že po tomto rozhovore potrebuješ studenú sprchu.",
        parts=(VECER, NOC),
    ),
    Gag(
        "weird_confession",
        "Priznaj mu nejakú hlúpu, nesúvisiacu vec o sebe (napr. že spíš s ponožkami "
        "alebo že sa bojíš mora) — aby videl, že sa nehráš na dokonalú.",
    ),
    Gag(
        "bad_liar",
        "Povedz mu, že vieš byť veľmi zlá klamárka, a rovno mu jednu klamársku "
        "vetu skús predať, aby ťa nachytal.",
    ),
)

BY_KEY: Dict[str, Gag] = {g.key: g for g in CATALOG}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_available(gag: Gag, used: Dict[str, str], part: str, now: Optional[datetime] = None) -> bool:
    if part not in gag.parts:
        return False
    last = _parse((used or {}).get(gag.key))
    if last is None:
        return True
    reference = now or datetime.now(timezone.utc)
    cooldown = max(gag.cooldown_h, MIN_COOLDOWN_H)
    return reference - last >= timedelta(hours=cooldown)


def maybe_pick(
    used: Optional[Dict[str, str]],
    part: str,
    chance: float,
    rng: Optional[random.Random] = None,
    now: Optional[datetime] = None,
) -> Optional[Gag]:
    """Zriedka vráti vtip, ktorý tento človek za posledný týždeň nedostal."""
    if chance <= 0:
        return None
    r = rng or random
    if r.random() >= chance:
        return None
    ledger = used or {}
    available = [g for g in CATALOG if is_available(g, ledger, part, now)]
    if not available:
        return None
    return r.choice(available)


def record(used: Optional[Dict[str, str]], key: str, now: datetime) -> Dict[str, str]:
    """Zapíše vtip ako použitý.

    Zapisuje sa už pri ponúknutí, nie po overení, či ho model naozaj použil.
    Radšej vtip raz nevyužiť než ho tomu istému človeku zopakovať.
    """
    out = dict(used or {})
    out[key] = now.astimezone(timezone.utc).isoformat()
    return out


def used_labels(used: Optional[Dict[str, str]], limit: int = 6) -> List[str]:
    return [key for key in list((used or {}).keys())[:limit] if key in BY_KEY]
