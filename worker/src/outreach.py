"""Ranné oslovenie — jediná situácia, kedy modelka píše prvá.

Po celý zvyšok dňa reaguje výhradne na prichádzajúce správy. Ráno je výnimka:
komu sa večer rozlúčila alebo kto deň predtým stíchol, tomu sa ozve sama.
Pre klienta je to najsilnejší moment celého dňa — nikto nečaká, že napíše prvá.

Pravidlá sú v kóde, lebo tu sa chybami platí najviac:

  * len ľuďom, s ktorými reálna konverzácia naozaj bola
  * nikdy dva dni po sebe tomu, kto neodpovedal — po dvoch tichých ránach koniec
  * nikdy dvakrát za ten istý deň
  * kto zaplatil alebo je v ručnom režime, sa nerieši
  * rozložené v čase, nie štyridsať správ o 12:12 naraz

To posledné nie je kozmetika: dávka správ odoslaná v jednej minúte je presne
to, čo Telegram na spamovaní rozoznáva.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

# Koľko hodín po začiatku cyklu sa ranné správy rozprestrú.
SPREAD_HOURS = 2.5

# Po koľkých tichých ránach za sebou to vzdá.
MAX_SILENT = 2

# Ako dlho po vlastnom oslovení sa neozve znova.
#
# Pôvodných 20 hodín znamenalo, že komu napísala a on odpovedal, tomu napísala
# prvá aj ďalší deň — a ďalší, a ďalší. V chate to vyzerá ako rozposielanie,
# nie ako že si spomenula. Ozve sa raz a potom nechá priestor jemu; keď mu
# na nej záleží, napíše sám, a to je práve ten signál, ktorý chceme vidieť.
OUTREACH_COOLDOWN_DAYS = 4

# Konverzácia musí mať aspoň toľko správ, inak nie je čo nadväzovať.
MIN_MESSAGES = 4

# Ako dávno musí byť posledná správa, aby malo zmysel ozvať sa.
MIN_GAP_HOURS = 8

# A ako dávno najviac — po týždni ticha je to už len otravovanie.
MAX_GAP_HOURS = 24 * 7


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


def _last_contact(user: Dict[str, Any]) -> Optional[datetime]:
    casy = [_parse(user.get("last_incoming_at")), _parse(user.get("last_reply_at"))]
    known = [c for c in casy if c]
    return max(known) if known else None


def deserves(user: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Má zmysel ozvať sa tomuto človeku dnes ráno?"""
    reference = now or datetime.now(timezone.utc)

    if user.get("human_takeover") or not user.get("ai_enabled", True):
        return False
    if user.get("paid") or (user.get("funnel_stage") or "") == "converted":
        return False
    if int(user.get("msg_count") or 0) < MIN_MESSAGES:
        return False
    if int(user.get("outreach_silent") or 0) >= MAX_SILENT:
        return False

    # Ozvala sa nedávno sama — druhýkrát nie, ani keď medzitým odpovedal.
    posledne = _parse(user.get("last_outreach_at"))
    if posledne and (reference - posledne) < timedelta(days=OUTREACH_COOLDOWN_DAYS):
        return False

    kontakt = _last_contact(user)
    if kontakt is None:
        return False
    odstup = (reference - kontakt).total_seconds() / 3600
    return MIN_GAP_HOURS <= odstup <= MAX_GAP_HOURS


def due(
    users: Sequence[Dict[str, Any]],
    now: Optional[datetime] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """Koho z týchto ľudí osloviť teraz.

    Rozprestretie je odvodené z ich ID, nie z náhody — vďaka tomu si každý
    drží svoj čas aj naprieč restartmi a poradie sa medzi dňami mení.
    """
    reference = now or datetime.now(timezone.utc)
    vybrati = []
    for user in users:
        if not deserves(user, reference):
            continue
        vybrati.append(user)
    return vybrati[:limit]


def delay_for(tg_id: int, day: str, spread_hours: float = SPREAD_HOURS) -> float:
    """O koľko sekúnd po začiatku cyklu má odísť správa tomuto človeku.

    Stabilné pre daný deň a daného človeka, ale každý deň iné poradie.
    """
    rng = random.Random(f"{tg_id}:{day}")
    return rng.random() * spread_hours * 3600


# Za aký čas po otvorení okna sa rozpustí to, čo prišlo cez noc. Kratšie než
# ranné oslovenia — na správu, ktorá čaká od tretej rána, sa nedá odpovedať
# až o dve hodiny.
BACKLOG_SPREAD_H = 1.25


def backlog_ready(
    tg_id: int, day: str, minutes_since_open: float,
    spread_hours: float = BACKLOG_SPREAD_H,
) -> bool:
    """Je už rad na tohto človeka s odpoveďou na nočnú správu?

    Kto napíše, kým modelka spí, mal odpoveď hneď pri otvorení okna — a keďže
    sweeper berie všetkých naraz, celý rad dostal odpoveď v priebehu pár minút.
    Skutočný človek sa zobudí, odpíše dvom a na zvyšok si spomenie neskôr.

    Poradie je odvodené z jeho id a z dátumu, nie z náhody: drží sa aj cez
    restart workera a medzi dňami sa mení.
    """
    return minutes_since_open >= delay_for(tg_id, day, spread_hours) / 60


def guidance(user: Dict[str, Any]) -> str:
    """Čo modelu povedať, keď píše ranné oslovenie."""
    meno = (user.get("partner_name") or "").strip()
    ticho = int(user.get("outreach_silent") or 0)

    riadky = [
        "PÍŠEŠ MU PRVÁ — RANNÉ OSLOVENIE",
        "Toto nie je odpoveď, ozývaš sa sama od seba na začiatku svojho dňa. "
        "Nadviaž na to, o čom ste sa bavili naposledy — spomeň konkrétnu vec "
        "z vašej konverzácie, nech je jasné, že si na neho myslela.",
        "Buď krátka, jedna veta, maximálne dve. Žiadne generické „good morning, "
        "how are you“ — tak píše automat. Nikdy nespomínaj, že si mu písala prvá "
        "ani že si sa ozvala, lebo dlho nepísal.",
        "Neposielaj odkaz a netlač na nič. Cieľom je len znovu rozbehnúť rozhovor.",
    ]
    if meno:
        riadky.append(f"Volá sa {meno} — oslov ho menom, pôsobí to osobne.")
    if ticho:
        riadky.append(
            "Naposledy ti neodpovedal. O to ľahšie to musí byť — žiadna výčitka, "
            "žiadne „kam si zmizol“, len milá zmienka a otázka, na ktorú sa dá "
            "odpovedať jedným slovom."
        )
    return "\n".join(riadky)
