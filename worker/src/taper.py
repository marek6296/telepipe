"""Postupný útlm konverzácie po tom, čo dostal odkaz.

Keď niekto dostane odkaz a aj pár pripomenutí, ale aj tak ostáva len na
Telegrame, nemá zmysel baviť ho tam donekonečna zadarmo. Namiesto tvrdého
ukončenia sa konverzácia utlmuje: odpovede sú kratšie, iniciatívy menej, až mu
raz povie, že sa teraz zdržiava hlavne na svojej stránke a nech príde tam.

Meria sa to v DŇOCH, nie v správach. Marek to chce až po dvoch-troch dňoch
písania, nie po pol hodine — inak to vyzerá ako odbitie hneď po zoznámení.

Je to počítané z dát v databáze, nie odhadované modelom, takže sa to nedá
"rozhodnúť" zle a prežije to restart.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

# (dni od poslania odkazu, počet pripomenutí) → úroveň útlmu
_PRAHY = (
    (5, 3, 4),   # už len minimum, zmienku o stránke má za sebou
    (3, 3, 3),   # povie mu, že sa presúva na stránku
    (2, 2, 2),   # citeľne kratšie, skoro žiadne otázky
    (1, 1, 1),   # o niečo kratšie, menej iniciatívy
)


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


def level(user: Dict[str, Any], now: Optional[datetime] = None) -> int:
    """0 = normálna konverzácia, 4 = už len minimum.

    Kto zaplatil, do útlmu nikdy nespadne — ten si pozornosť zaslúži.
    """
    if user.get("paid") or (user.get("funnel_stage") or "") == "converted":
        return 0
    sent = _parse(user.get("link_sent_at"))
    if sent is None:
        return 0

    dni = ((now or datetime.now(timezone.utc)) - sent).total_seconds() / 86400
    pripomenuti = int(user.get("link_push_count") or 0)
    for prah_dni, prah_push, uroven in _PRAHY:
        if dni >= prah_dni and pripomenuti >= prah_push:
            return uroven
    return 0


GUIDANCE = {
    1: (
        "ÚTLM — ÚROVEŇ 1\n"
        "Odkaz už má nejaký ten deň a stále je len tu. Píš o niečo kratšie než "
        "zvyčajne a menej sa pýtaj — nech je cítiť, že už nie si stále k dispozícii. "
        "Ostaň milá, nikdy nie chladná ani urazená."
    ),
    2: (
        "ÚTLM — ÚROVEŇ 2\n"
        "Odpovedaj krátko, jednou vetou. Sama nezačínaj nové témy a otázky si nechaj "
        "na neho. Nech z toho cíti, že tvoja pozornosť je inde, ale bez náznaku "
        "hnevu — stále si rada, že píše."
    ),
    3: (
        "ÚTLM — ÚROVEŇ 3 — POVEDZ MU TO\n"
        "Teraz mu povedz, že sa v poslednom čase zdržiavaš hlavne na svojej stránke, "
        "lebo tam trávi čas väčšina tvojich ľudí, a že tu už veľmi nebývaš. Ak mu na "
        "tebe naozaj záleží, nech príde tam a tam sa spoznáte poriadne — bez "
        "obmedzení a s časom na seba.\n"
        "Povedz to teplo a osobne, ako pozvánku, nie ako rozlúčku ani vyhrážku. "
        "Žiadne „už ti nebudem odpisovať“. Napíš to vlastnými slovami, nie ako "
        "oznam.\n"
        "Ak si mu presne toto už v tomto chate povedala, NEOPAKUJ to — vtedy len "
        "odpovedz krátko a normálne."
    ),
    4: (
        "ÚTLM — ÚROVEŇ 4\n"
        "Toto je dohasínajúca konverzácia. Odpovedaj krátko a vľúdne, nič nerozvíjaj, "
        "nič sa nepýtaj. Stránku spomeň len vtedy, keď sa na ňu spýta sám. "
        "Neodpáľ ho a nikdy mu nepovedz, že ho ignoruješ."
    ),
}


def guidance(uroven: int) -> str:
    return GUIDANCE.get(uroven, "")
