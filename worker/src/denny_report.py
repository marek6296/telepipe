"""Denný súhrn konverzácií do control bota.

KEDY SA POSIELA
---------------
Po skončení jej aktívneho okna — teda na konci JEJ dňa, nie o polnoci UTC.
Simona odpisuje do 2:30 kalifornského času, takže report jej príde vtedy a
zhrnie presne to, čo za ten deň stihla. Polnoc by jej deň rozsekla naprostred.

Modelka bez okna (24/7) dostane report o polnoci vo svojom pásme — inak by
nebolo kedy.

PREČO TO NIE JE ZAPNUTÉ AUTOMATICKY
-----------------------------------
Stojí to jedno LLM volanie denne. Nie je to veľa, ale je to náklad, ktorý si
nikto nevypýtal — preto `daily_report` defaultne `false`.

ČO ANALYZUJEME A ČO NIE
-----------------------
LEN Telegram konverzácie. Fanvue má vlastné notifikácie (platby, odbery) a
pridať jeho chaty by cenu za report zhruba zdvojnásobilo za informáciu, ktorú
klient dostane aj inak.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Koľko konverzácií ide do rozboru. Viac by report predražilo aj predĺžilo —
# a kto má sto chatov denne, aj tak číta prvých dvadsať.
MAX_KONVERZACII = 20

# Ako dlho po konci okna sa report ešte smie poslať. Keby worker práve
# reštartoval, nemá sa stratiť; ale ani prísť o osem hodín neskôr.
OKNO_PO_KONCI_MIN = 90


def _text_konverzacie(user: Dict[str, Any], spravy: List[Dict[str, Any]]) -> str:
    """Jedna konverzácia ako pár riadkov pre model."""
    meno = str(user.get("first_name") or user.get("username") or user.get("tg_id") or "?")
    poznamky = str(user.get("facts") or "").strip()
    faza = str(user.get("funnel_stage") or "").strip()
    poslal_odkaz = bool(user.get("link_sent_at"))

    riadky = [f"— {meno} (fáza: {faza or 'neznáma'}, odkaz poslaný: {'áno' if poslal_odkaz else 'nie'})"]
    if poznamky:
        riadky.append(f"  čo o ňom vieme: {poznamky[:300]}")
    for sprava in spravy[-8:]:
        kto = "on" if sprava.get("role") == "user" else "ona"
        obsah = str(sprava.get("content") or "").replace("\n", " ").strip()
        if obsah:
            riadky.append(f"  {kto}: {obsah[:160]}")
    return "\n".join(riadky)


POKYN = """\
Si asistent, ktorý pomáha majiteľovi AI modelky. Dostaneš prehľad jej
konverzácií za posledný deň a napíšeš mu KRÁTKY súhrn do Telegramu.

Píš vecne a stručne, po anglicky. Toto je pracovná správa, nie marketing.

Štruktúra:
1. Jedna veta, ako deň dopadol celkovo.
2. HOT — kto je pripravený a prečo (meno + jedna veta). Ak nikto, napíš to.
3. COLD — kto stráca záujem alebo nereaguje (meno + jedna veta).
4. NOVÍ — koho pribudlo.
5. Ak niečo vyžaduje pozornosť majiteľa, napíš to na koniec jednou vetou.

Nevymýšľaj si mená ani fakty, ktoré v podklade nie sú. Keď je podklad chudobný,
povedz to rovno namiesto vaty. Maximálne 200 slov. Bez markdown nadpisov,
Telegram ich nevie."""


def treba_poslat(
    now_local: datetime,
    start_min: int,
    end_min: int,
    posledny_iso: Optional[str],
) -> bool:
    """Je čas na report a ešte dnes neodišiel?

    Poistka proti dvom reportom za deň je dôležitejšia, než sa zdá: sweeper
    beží každé tri minúty a bez nej by v okne po konci poslal report
    tridsaťkrát.
    """
    minuty = now_local.hour * 60 + now_local.minute

    # 24/7 modelka nemá koniec okna — vtedy polnoc.
    if start_min == end_min:
        v_case = minuty < OKNO_PO_KONCI_MIN
    else:
        po_konci = (minuty - end_min) % (24 * 60)
        v_case = 0 <= po_konci < OKNO_PO_KONCI_MIN

    if not v_case:
        return False

    if not posledny_iso:
        return True
    try:
        posledny = datetime.fromisoformat(str(posledny_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if posledny.tzinfo is None:
        posledny = posledny.replace(tzinfo=timezone.utc)
    # Menej než 20 hodín od posledného = dnes už bol.
    return (datetime.now(timezone.utc) - posledny) >= timedelta(hours=20)


async def zostav(db, llm, hodin: int = 24) -> Optional[str]:
    """Vyrobí text reportu. `None` = nie je o čom písať.

    Prázdny deň sa ZÁMERNE nehlási: správa „dnes sa nič nedialo" každý večer je
    presne ten druh notifikácie, po ktorej si človek vypne všetky.
    """
    users = await db.recent_conversations(limit=MAX_KONVERZACII)
    if not users:
        return None

    hranica = datetime.now(timezone.utc) - timedelta(hours=hodin)
    bloky: List[str] = []
    novych = 0
    aktivnych = 0

    for user in users:
        posledna = user.get("last_incoming_at")
        if not posledna:
            continue
        try:
            kedy = datetime.fromisoformat(str(posledna).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if kedy.tzinfo is None:
            kedy = kedy.replace(tzinfo=timezone.utc)
        if kedy < hranica:
            continue

        aktivnych += 1
        vytvoreny = user.get("created_at")
        if vytvoreny:
            try:
                zalozeny = datetime.fromisoformat(str(vytvoreny).replace("Z", "+00:00"))
                if zalozeny.tzinfo is None:
                    zalozeny = zalozeny.replace(tzinfo=timezone.utc)
                if zalozeny >= hranica:
                    novych += 1
            except (TypeError, ValueError):
                pass

        try:
            spravy = await db.recent_messages(int(user.get("tg_id")), 12)
        except Exception:  # noqa: BLE001 — jedna pokazená konverzácia report nezhodí
            spravy = []
        bloky.append(_text_konverzacie(user, spravy))

    if not aktivnych:
        return None

    podklad = (
        f"Za posledných {hodin} hodín: {aktivnych} aktívnych konverzácií, "
        f"z toho {novych} nových ľudí.\n\n" + "\n\n".join(bloky)
    )

    try:
        text = await llm.report(POKYN, podklad)
    except Exception:  # noqa: BLE001
        log.exception("Denný report sa nepodarilo vygenerovať")
        return None

    text = (text or "").strip()
    if not text:
        return None
    return f"📊 <b>Daily summary</b>\n\n{text}"
