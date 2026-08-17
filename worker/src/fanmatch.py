"""Kto je ten človek na Fanvue — aj keď neprišiel cez checkout odkaz.

`client_reference_id` je najistejšia cesta, ale nie jediná a nie spoľahlivá:
človek môže odkaz otvoriť inokedy, z iného zariadenia, alebo rovno napísať
platenú správu. Vtedy o ňom nevieme nič okrem mena — a to na spojenie stačí
prekvapivo často, keď sa k nemu pridá druhá stopa: komu sme v poslednom čase
posielali odkaz.

Pravidlo, na ktorom celé stojí: **pri pochybnosti radšej nespájať.**
Zle spojený človek je horší než nespojený. Nespojenému sa Simona prihovorí
ako novému a nič sa nestane; zle spojenému by začala pripomínať zážitky
niekoho iného, a to je koniec.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ako dlho po poslaní odkazu ešte považujeme príchod za súvisiaci. Ľudia
# odkaz neotvárajú hneď — často až večer alebo o pár dní.
LINK_WINDOW_DAYS = 21

# Koľko musí návrh nazbierať, aby sa spojil sám.
THRESHOLD = 6

# O koľko musí byť najlepší návrh pred druhým. Keď dvaja ľudia sedia rovnako
# dobre, nespája sa ani jeden — hádať sa tu nesmie.
MARGIN = 3


def normalise(text: Any) -> str:
    """Meno na porovnateľný tvar: bez diakritiky, bez ozdôb, malé písmená."""
    raw = str(text or "")
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", raw) if not unicodedata.combining(ch)
    )
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def _first_token(text: str) -> str:
    parts = normalise(text).split()
    return parts[0] if parts else ""


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def score(fan: Dict[str, Any], chat: Dict[str, Any], now: datetime) -> Tuple[int, List[str]]:
    """Koľko toho svedčí, že tento Fanvue fanúšik je tento Telegram človek."""
    body = 0
    preco: List[str] = []

    fan_names = {normalise(fan.get("display_name")), normalise(fan.get("handle"))}
    fan_names.discard("")
    chat_names = {normalise(chat.get("first_name")), normalise(chat.get("username"))}
    chat_names.discard("")

    if fan_names & chat_names:
        body += 5
        preco.append("meno sedí celé")
    else:
        fan_first = {_first_token(n) for n in fan_names} - {""}
        chat_first = {_first_token(n) for n in chat_names} - {""}
        # Krstné meno samo osebe je slabá stopa — Johnov sú tisíce. Váhu mu
        # dáva až to, že práve tomuto Johnovi sme nedávno poslali odkaz.
        if fan_first & chat_first:
            body += 3
            preco.append("sedí krstné meno")

    # Meno je PODMIENKA, nie jeden z bodov. Že niekomu nedávno odišiel odkaz,
    # samo osebe nehovorí nič — odkaz dostalo veľa ľudí a prísť mohol
    # ktokoľvek. Bez zhody v mene by sa čerstvosť odkazu sama prehupla cez
    # hranicu a spojila by úplne cudzích ľudí.
    if body == 0:
        return 0, []

    poslany = _ts(chat.get("link_sent_at"))
    if poslany:
        dni = (now - poslany).total_seconds() / 86400
        if dni <= 3:
            body += 4
            preco.append("odkaz dostal pred pár dňami")
        elif dni <= LINK_WINDOW_DAYS:
            body += 2
            preco.append(f"odkaz dostal pred {int(dni)} dňami")

    if str(chat.get("funnel_stage") or "") == "link_sent":
        body += 2
        preco.append("čakáme, či prejde")

    return body, preco


def best(
    fan: Dict[str, Any],
    chats: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    taken: Optional[set] = None,
) -> Optional[Dict[str, Any]]:
    """Najlepší návrh, alebo None keď si nie sme dosť istí.

    `taken` sú Telegram id, ktoré už patria inému fanúšikovi — jeden človek
    nemôže byť dvaja.
    """
    now = now or datetime.now(timezone.utc)
    taken = taken or set()

    hodnotenia: List[Tuple[int, List[str], Dict[str, Any]]] = []
    for chat in chats:
        tg_id = chat.get("tg_id")
        if tg_id is None or int(tg_id) in taken:
            continue
        body, preco = score(fan, chat, now)
        if body > 0:
            hodnotenia.append((body, preco, chat))

    if not hodnotenia:
        return None

    hodnotenia.sort(key=lambda h: h[0], reverse=True)
    najlepsi, preco, chat = hodnotenia[0]
    if najlepsi < THRESHOLD:
        return None

    # Dvaja rovnako dobrí kandidáti znamenajú, že nevieme. Radšej nespojiť.
    if len(hodnotenia) > 1 and najlepsi - hodnotenia[1][0] < MARGIN:
        return None

    return {
        "tg_id": int(chat["tg_id"]),
        "score": najlepsi,
        "why": ", ".join(preco),
        "name": chat.get("first_name") or chat.get("username") or "",
    }
