"""Krátky odkaz, na ktorom sa dá zmerať klik.

PREČO NIE PRIAMO FANVUE
-----------------------
Jedenásť ľudí dostalo odkaz a nula zaplatila — a nedalo sa zistiť, ktorá
polovica je pokazená. „Nikto neklikol" a „klikli a nekúpili" sú dve opačné
diagnózy: prvá je vec konverzácie, druhá vec samotnej stránky. Medzi nimi sa
dovtedy rozhodovalo hádaním.

Krátky odkaz cez našu doménu klik zapíše a presmeruje ďalej. Atribúcia
(`client_reference_id`) sa nestráca — dopĺňa sa až pri presmerovaní, takže
funguje presne ako doteraz.

CIEĽ SA NEUKLADÁ
----------------
V databáze je len token a dvojica model + tg_id. Kam odkaz vedie, sa skladá až
pri kliknutí z aktuálnej `persona.cta_link`. Vďaka tomu odkaz poslaný minulý
týždeň funguje aj po tom, ako si klient stránku premenuje — a nemáme dve miesta,
kde by mohla žiť iná adresa.

KEĎ SA TO NEPODARÍ, IDE PÔVODNÝ ODKAZ
-------------------------------------
Meranie je bonus. Keby výpadok databázy alebo chýbajúca doména znamenali, že
modelka nepošle nič, vymenili by sme informáciu za tržbu. Preto sa pri
akomkoľvek probléme vracia obyčajný Fanvue odkaz.
"""
from __future__ import annotations

import logging
import secrets
import string
from typing import Any, Optional

log = logging.getLogger(__name__)

# Dĺžka tokenu. Šesť znakov z 58-znakovej abecedy je ~38 bitov — dosť na to,
# aby sa nedal uhádnuť, a stále krátke natoľko, že odkaz v chate nevyzerá ako
# sledovacia URL z reklamy.
DLZKA = 8
# Bez znakov, ktoré si ľudia mýlia (0/O, 1/l/I) — odkaz môže niekto prepisovať.
ABECEDA = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")


def novy_token() -> str:
    return "".join(secrets.choice(ABECEDA) for _ in range(DLZKA))


def zloz(base_url: str, token: str) -> str:
    """Z tokenu hotová adresa. Prázdna základňa = nemáme kam ukazovať."""
    base = (base_url or "").strip().rstrip("/")
    if not base or not token:
        return ""
    return f"{base}/r/{token}"


async def pre_konverzaciu(db: Any, tg_id: int, base_url: str) -> str:
    """Krátky odkaz pre tento chat. Prázdny reťazec = použi pôvodný.

    Token je na dvojicu model+človek stály: keď mu odkaz pošle druhýkrát, je to
    ten istý odkaz a kliky sa nerozsypú do dvoch riadkov.
    """
    if not base_url:
        return ""
    try:
        token = await db.ensure_short_link(int(tg_id))
    except Exception as exc:  # noqa: BLE001 - radšej pôvodný odkaz než žiadny
        log.warning("%s: krátky odkaz sa nepodarilo pripraviť (%s)", tg_id, exc)
        return ""
    return zloz(base_url, token or "")
