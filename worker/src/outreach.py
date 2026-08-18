"""Pozdrav na druhý deň — JEDINÁ chvíľa, kedy modelka píše prvá.

Po celý zvyšok času reaguje výhradne na prichádzajúce správy. Výnimka je práve
jedna a je zámerne úzka: keď je zapnutá (`behavior.morning_enabled`), deň po
tom, ako s niekým naozaj začala konverzáciu, sa mu RAZ ozve krátkym „hey". Nič
viac — žiadne nadväzovanie na tému, žiadne opakovanie ďalšie dni, žiadny odkaz.

PREČO TAK ÚZKO. Predtým to bolo bohaté kontextové oslovenie, ktoré sa opakovalo
každých pár dní a spomínalo konkrétne veci z chatu. V praxi to vyzeralo, že
modelka sama od seba píše divné správy „od veci" do stíchnutej konverzácie —
presne to, čo klient nahlásil. Jednoduchý pozdrav na druhý deň je to, čo spraví
skutočný človek: na druhý deň sa ozve „ahoj", a potom nechá priestor druhému.

Pravidlá sú v kóde, lebo tu sa chybami platí najviac:

  * len ľuďom, s ktorými reálna konverzácia naozaj bola (`MIN_MESSAGES`)
  * len RAZ za celý život konverzácie (`last_outreach_at` je vodoznak)
  * len keď prvý kontakt bol na SKORŠÍ deň v JEJ časovom pásme — „druhý deň"
    sa rozhoduje podľa jej rána, nie podľa UTC
  * kto zaplatil alebo je v ručnom režime, sa nerieši
  * rozložené v čase, nie štyridsať správ o 7:00 naraz

To posledné nie je kozmetika: dávka správ odoslaná v jednej minúte je presne
to, čo Telegram na spamovaní rozoznáva.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

# Koľko hodín po začiatku cyklu sa ranné pozdravy rozprestrú.
SPREAD_HOURS = 2.5

# Konverzácia musí mať aspoň toľko správ, inak nie je čo pozdravovať —
# jedna-dve správy nie sú konverzácia, na ktorú sa druhý deň nadväzuje.
MIN_MESSAGES = 4

# Po koľkých dňoch ticha už nemá zmysel sa ozvať. Keď niekto napísal raz a
# zmizol na týždeň, pozdrav „na druhý deň" by prišiel do prázdna.
MAX_GAP_DAYS = 7


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


def deserves(user: Dict[str, Any], now_local: datetime) -> bool:
    """Má sa tomuto človeku dnes ráno ozvať tým jedným pozdravom?

    `now_local` MUSÍ byť tz-aware v ČASOVOM PÁSME modelky — „druhý deň" sa
    rozhoduje podľa jej rána, nie podľa UTC (klient v BA vidí správu večer,
    ale u nej v NYC je ráno).
    """
    if user.get("human_takeover") or not user.get("ai_enabled", True):
        return False
    if user.get("paid") or (user.get("funnel_stage") or "") == "converted":
        return False
    if int(user.get("msg_count") or 0) < MIN_MESSAGES:
        return False

    # Vodoznak: keď sa už raz ozvala, druhýkrát nikdy. `last_outreach_at`
    # nie je NULL práve vtedy, keď pozdrav už odišiel.
    if _parse(user.get("last_outreach_at")) is not None:
        return False

    prvy = _parse(user.get("created_at"))
    if prvy is None:
        return False
    prvy_lokal = prvy.astimezone(now_local.tzinfo)
    # Prvý kontakt musí byť na SKORŠÍ lokálny deň. Rovnaký deň = ešte nie je
    # „druhý deň"; skorší = druhý deň (alebo neskôr, keby modelka práve deň
    # po prvom kontakte spala — vtedy pozdraví pri najbližšom ráne, stále raz).
    if prvy_lokal.date() >= now_local.date():
        return False

    posledny = _last_contact(user)
    if posledny is None:
        return False
    if (now_local.astimezone(timezone.utc) - posledny) > timedelta(days=MAX_GAP_DAYS):
        return False
    return True


def due(
    users: Sequence[Dict[str, Any]],
    now_local: datetime,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """Koho z týchto ľudí dnes ráno pozdraviť."""
    vybrati = [user for user in users if deserves(user, now_local)]
    return vybrati[:limit]


def delay_for(tg_id: int, day: str, spread_hours: float = SPREAD_HOURS) -> float:
    """O koľko sekúnd po začiatku cyklu má odísť pozdrav tomuto človeku.

    Stabilné pre daný deň a daného človeka, ale každý deň iné poradie.
    """
    rng = random.Random(f"{tg_id}:{day}")
    return rng.random() * spread_hours * 3600


# Za aký čas po otvorení okna sa rozpustí to, čo prišlo cez noc. Kratšie než
# ranné pozdravy — na správu, ktorá čaká od tretej rána, sa nedá odpovedať
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
    """Čo modelu povedať, keď píše ten jeden pozdrav na druhý deň."""
    meno = (user.get("partner_name") or "").strip()
    riadky = [
        "YOU ARE WRITING FIRST — A SIMPLE NEXT-DAY HELLO",
        "This is NOT a reply. It is a new day and you are just saying hi first, "
        "the way you would text someone the day after you met. Keep it to a SHORT "
        "casual greeting and NOTHING else — like 'hey', 'heyy', 'hey you :)', "
        "'morning'. One line, a few words at most.",
        "Do NOT bring up anything you talked about before, do NOT ask a real "
        "question, do NOT send a link or push anything. Never mention that you are "
        "writing first, or that he went quiet, or that it is a new day.",
    ]
    if meno:
        riadky.append(f"You may use his name ({meno}) — 'hey {meno}' feels personal.")
    return "\n".join(riadky)
