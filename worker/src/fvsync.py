"""Zosúladenie chatu s tým, čo máme uložené.

Webhook nie je jediná cesta, ako sa v chate niečo objaví. Marek môže odpísať
ručne z Fanvue appky, doručenie sa môže po piatich pokusoch nenávratne
stratiť a poradie udalostí Fanvue nezaručuje vôbec. Keby sa modelka
spoliehala len na frontu, nadväzovala by na rozhovor, ktorý nepozná celý.

Preto sa pred každou odpoveďou prečíta skutočný stav chatu a porovná sa
s uloženým. Čo chýba, doplní sa; až potom sa odpovedá.

Z toho vypadnú tri veci naraz:

**Ručná odpoveď sa rešpektuje.** Keď je posledná správa od nej alebo od
Mareka, niekto to už vyriešil — vtedy sa mlčí. Ručné prevzatie chatu tak
funguje samo, bez prepínača.

**Séria správ dostane jednu odpoveď.** Tri správy za sebou vyrobia tri
udalosti; keby sa odpovedalo na každú, píše trikrát. Odpovedá sa na stav,
nie na udalosť.

**Nákup sa dá zistiť.** `purchasedAt` na platenej správe hovorí, že si ju
naozaj kúpil — inak by sme o tom nevedeli.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def role_of(message: Dict[str, Any], creator_uuid: str) -> str:
    """`assistant` = od modelky (aj keď to napísal Marek ručne), inak `user`."""
    sender = (message.get("sender") or {}).get("uuid") or ""
    return "assistant" if str(sender) == str(creator_uuid) else "user"


def as_text(message: Dict[str, Any]) -> str:
    """Text správy tak, ako má ísť do pamäte.

    Prílohu treba poznačiť slovom, nie mlčaním — inak by v histórii bola
    prázdna správa a modelka by nevedela, že vôbec niečo poslala.
    """
    text = str(message.get("text") or "").strip()
    if message.get("hasMedia"):
        druh = str(message.get("mediaType") or "media").lower()
        znacka = "(hlasovka)" if druh == "audio" else f"({druh})"
        cena = ((message.get("pricing") or {}).get("USD") or {}).get("price")
        if cena:
            znacka = f"{znacka[:-1]} za ${int(cena) / 100:.2f})"
        text = f"{znacka} {text}".strip()
    return text


def missing(
    stored_uuids: set,
    fetched: Sequence[Dict[str, Any]],
    creator_uuid: str,
    bez_uuid: Sequence[str] = (),
) -> List[Dict[str, str]]:
    """Správy, ktoré nemáme — od najstaršej, nech poradie v pamäti sedí.

    Fanvue vracia najnovšie prvé, takže sa zoznam obracia.

    `bez_uuid` sú znenia, ktoré už máme uložené BEZ identifikátora — poslali
    sme ich my a Fanvue nám k nim id nevrátilo. Bez tejto poistky by sa každá
    taká správa pri zosúladení pridala druhýkrát: dedup vyššie pozná len uuid,
    a to sa jej priradí až teraz. Naostro bolo takto zdvojených 6 % správ
    a modelka mala v histórii vlastnú poslednú vetu dvakrát.
    """
    uz_mame = {str(t) for t in bez_uuid}
    out: List[Dict[str, str]] = []
    for message in reversed(list(fetched)):
        uuid = str(message.get("uuid") or "")
        if not uuid or uuid in stored_uuids:
            continue
        text = as_text(message)
        if not text:
            continue
        if text[:2000] in uz_mame:
            # Zapíše sa len raz: druhá rovnaká správa v tom istom ťahu je už
            # naozaj nová (človek zopakoval to isté).
            uz_mame.discard(text[:2000])
            continue
        out.append(
            {
                "message_uuid": uuid,
                "role": role_of(message, creator_uuid),
                "content": text[:2000],
            }
        )
    return out


def newest(fetched: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Najnovšia správa. Fanvue ich vracia zoradené od najnovšej."""
    for message in fetched:
        if message.get("uuid"):
            return message
    return None


def stay_quiet(fetched: Sequence[Dict[str, Any]], creator_uuid: str) -> bool:
    """Má teraz mlčať?

    Keď je posledná správa od nej alebo od Mareka, niekto to už vyriešil.
    Druhá odpoveď by mu do toho písala a mohla by protirečiť.
    """
    posledna = newest(fetched)
    if posledna is None:
        return False
    return role_of(posledna, creator_uuid) == "assistant"


def bought(fetched: Sequence[Dict[str, Any]]) -> int:
    """Koľko platených správ si v tomto chate naozaj kúpil."""
    return sum(1 for m in fetched if m.get("purchasedAt"))


def last_bought_at(fetched: Sequence[Dict[str, Any]]) -> str:
    """Kedy kúpil naposledy. Prázdne = nikdy."""
    casy = [str(m.get("purchasedAt")) for m in fetched if m.get("purchasedAt")]
    return max(casy) if casy else ""
