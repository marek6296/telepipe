"""Odkaz na Fanvue, ktorý si so sebou nesie, komu bol poslaný.

Fanvue vie pri checkoute prevziať `client_reference_id` a potom ho vracia
v každej udalosti o platbe. Keď doň zapíšeme Telegram id, vieme po zaplatení
spojiť fanúšika na Fanvue s človekom, s ktorým si Simona týždeň písala.

Bez toho by na Fanvue začínala od nuly — bola by milá, ale netušila by, že
toho človeka pozná. A ako vedľajší efekt vidno návratnosť po jednotlivých
konverzáciách, nie len súčet.

Dotýka sa to len odkazov na fanvue.com. Čokoľvek iné, čo si Marek nastaví
ako odkaz, ostáva nedotknuté.
"""
from __future__ import annotations

from typing import Any, Optional

# Predpona, podľa ktorej sa na druhej strane pozná, že v hodnote je Telegram id
# a nie čosi iné. Bez nej by sa ručne vyplnené `client_reference_id` dalo
# omylom prečítať ako číslo účtu.
PREFIX = "tg-"


def reference(tg_id: Any) -> str:
    """Hodnota do `client_reference_id`. Prázdne = nemáme čo poslať."""
    try:
        number = int(tg_id)
    except (TypeError, ValueError):
        return ""
    return f"{PREFIX}{number}"


def telegram_id(value: Any) -> Optional[int]:
    """Späť z `client_reference_id` na Telegram id. None = nie je naše."""
    text = str(value or "")
    if not text.startswith(PREFIX):
        return None
    try:
        return int(text[len(PREFIX):])
    except ValueError:
        return None


def attributed(link: str, tg_id: Any) -> str:
    """Odkaz doplnený o to, komu ide.

    Cudzie odkazy ani odkazy bez id nechá tak — radšej nech ide von presne to,
    čo si Marek nastavil, než aby sa doň niečo prilepilo naslepo.
    """
    link = (link or "").strip()
    if not link or "fanvue.com" not in link.lower():
        return link

    ref = reference(tg_id)
    if not ref:
        return link

    # Ak už tam raz je, druhý raz sa nepridáva.
    if "client_reference_id=" in link:
        return link

    # Kotva musí ostať na konci, inak by sa parameter stal jej súčasťou.
    base, hash_mark, fragment = link.partition("#")
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}client_reference_id={ref}{hash_mark}{fragment}"
