"""Týždenný súhrn s číslami do control bota.

PREČO NIE JE AKO DENNÝ
----------------------
Denný súhrn je rozprávanie o konverzáciách a stojí volanie modelu. Tento je
opak: štyri čísla a nič viac, takže nestojí nič a môže byť zapnutý defaultne.
Odpovedá na jedinú otázku, ktorú si klient kladie — vyplatilo sa to?

ČÍSLA SÚ ZA OBDOBIE, NIE ZA CELÝ ŽIVOT
--------------------------------------
Celkové súčty po pár mesiacoch prestanú hovoriť čokoľvek: rastú aj vtedy, keď
sa posledný týždeň nedialo nič. Preto `stats_od`.

KEDY
----
V pondelok, po skončení jej aktívneho okna — teda vtedy, čo denný, len raz za
týždeň. Rovnaká poistka proti dvom odoslaniam (`weekly_report_sent_at`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import denny_report

log = logging.getLogger(__name__)

# Deň v týždni, kedy súhrn chodí. Pondelok: v nedeľu večer ho nikto nechce
# čítať a v piatok by chýbal víkend, ktorý je pre túto prácu najsilnejší.
DEN = 0  # pondelok

# Ako dlho po odoslaní sa druhý raz neposiela. Sedem dní mínus rezerva, aby ho
# posunutý koniec okna nepreskočil na ďalší týždeň.
TICHO_H = 120


def treba_poslat(
    now_local: datetime,
    start_min: int,
    end_min: int,
    posledny_iso: Optional[str],
) -> bool:
    """Je pondelok po konci okna a tento týždeň ešte neodišiel?"""
    if now_local.weekday() != DEN:
        return False
    # Časovanie v rámci dňa je to isté ako pri dennom — po skončení jej okna.
    if not denny_report.treba_poslat(now_local, start_min, end_min, None):
        return False

    if not posledny_iso:
        return True
    try:
        posledny = datetime.fromisoformat(str(posledny_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if posledny.tzinfo is None:
        posledny = posledny.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - posledny) >= timedelta(hours=TICHO_H)


def _pct(cast: int, celok: int) -> str:
    return f"{cast / celok * 100:.0f}%" if celok else "—"


def zostav(cisla: Dict[str, int], coiny: float, minuly: Optional[Dict[str, int]] = None) -> str:
    """Text súhrnu. Vždy nejaký je — aj prázdny týždeň je odpoveď.

    (Denný súhrn prázdny deň zamlčí, lebo je to rozprávanie. Tu je ticho samo
    o sebe informácia: klient chce vedieť, že sa nedialo nič.)
    """
    novi = int(cisla.get("novi") or 0)
    odkazy = int(cisla.get("odkazy") or 0)
    zavrete = int(cisla.get("zavrete") or 0)

    riadky = [
        "📈 *Your week*",
        "",
        f"New conversations: *{novi}*",
        f"Link sent to: *{odkazy}*" + (f" ({_pct(odkazy, novi)} of them)" if novi else ""),
        f"Chats she wrapped up: *{zavrete}*",
    ]

    if minuly is not None:
        rozdiel = novi - int(minuly.get("novi") or 0)
        if rozdiel:
            smer = "up" if rozdiel > 0 else "down"
            riadky.append(f"That is {abs(rozdiel)} {smer} on last week.")

    riadky += ["", f"Pipe Coins left: *{int(coiny):,}*".replace(",", " ")]
    if novi == 0:
        riadky += [
            "",
            "_Nobody new wrote to her this week. If that is not what you "
            "expected, check that her Telegram is still connected._",
        ]
    return "\n".join(riadky)
