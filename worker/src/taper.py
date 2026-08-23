"""Postupný útlm konverzácie a jej koniec.

Keď niekto píše len na Telegrame a na stránku nejde, nemá zmysel baviť ho tam
donekonečna zadarmo. Namiesto tvrdého konca sa konverzácia utlmuje: odpovede
sú kratšie, iniciatívy menej, až raz stíchne úplne.

MERIA SA OD PRVÉHO KONTAKTU, NIE OD ODKAZU
------------------------------------------
Predtým sa útlm počítal od chvíle, keď odkaz odišiel. Malo to dve chyby: kto
odkaz nikdy nedostal, neutlmil sa NIKDY, a klient nevedel dopredu povedať, ako
dlho sa má s človekom baviť. Teraz je to okno v dňoch od prvej správy a
nastavuje si ho klient (`behavior.chat_days`).

KRIVKA
------
Okno sa delí na štvrtiny. V prvej je konverzácia normálna, potom sa postupne
sťahuje, v poslednej štvrtine jej povie, že sa presúva na stránku — a po
uplynutí okna stíchne ÚPLNE: neodpovie a nedá ani „videné".

Pri jednodňovom okne sa to celé zmestí do jedného dňa. Preto je dôležité, že
`closing()` dovolí poslať odkaz aj vtedy, keď by ho bežné pravidlá ešte
nepustili — inak by človek odišiel bez toho, aby ho vôbec videl.

Kto zaplatil, do útlmu nespadne nikdy.

Je to počítané z dát v databáze, nie odhadované modelom, takže sa to nedá
„rozhodnúť" zle a prežije to restart.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Úroveň, pri ktorej sa už neodpovedá vôbec. Nie je to „úroveň 5 útlmu",
# je to koniec — volajúci ju musí riešiť inak než ostatné.
TICHO = 5

DEFAULT_DNI = 3


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


def _dni_od_zaciatku(user: Dict[str, Any], now: datetime) -> Optional[float]:
    """Koľko dní ubehlo od prvého kontaktu. `None` = nevieme, teda neutlmujeme."""
    zaciatok = _parse(user.get("created_at"))
    if zaciatok is None:
        return None
    return (now - zaciatok).total_seconds() / 86400


def level(
    user: Dict[str, Any],
    chat_days: int = DEFAULT_DNI,
    now: Optional[datetime] = None,
) -> int:
    """0 = normálna konverzácia, 4 = dohasína, `TICHO` = už neodpovedá vôbec.

    Kto zaplatil, do útlmu nikdy nespadne — ten si pozornosť zaslúži.
    """
    if user.get("paid") or (user.get("funnel_stage") or "") == "converted":
        return 0

    okno = max(1, int(chat_days or DEFAULT_DNI))
    dni = _dni_od_zaciatku(user, now or datetime.now(timezone.utc))
    if dni is None:
        return 0

    if dni >= okno:
        return TICHO

    podiel = dni / okno
    if podiel >= 0.75:
        return 3        # posledná štvrtina: povie mu, že sa presúva na stránku
    if podiel >= 0.5:
        return 2
    if podiel >= 0.25:
        return 1
    return 0


def ticho(user: Dict[str, Any], chat_days: int = DEFAULT_DNI,
          now: Optional[datetime] = None) -> bool:
    """Je konverzácia za oknom? Vtedy sa neodpovedá ani nečíta."""
    return level(user, chat_days, now) == TICHO


def closing(user: Dict[str, Any], chat_days: int = DEFAULT_DNI,
            now: Optional[datetime] = None) -> bool:
    """Blíži sa koniec okna — odkaz musí von, kým je ešte komu.

    Bez tohto by pri jednodňovom okne človek odišiel bez toho, aby stránku
    vôbec videl: bežné pravidlá pýtajú aspoň šesť správ a fázu `warm`, a to sa
    za jeden deň nemusí stihnúť.
    """
    uroven = level(user, chat_days, now)
    # Po okne už nikoho nezatvárame — vtedy sa neodpisuje vôbec.
    return 3 <= uroven < TICHO


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
        "ÚTLM — ÚROVEŇ 3\n"
        "Konverzácia dohasína. Odpovedaj krátko, nič nerozvíjaj a sama nezačínaj "
        "témy — ako človek, ktorý je myšlienkami inde, ale stále je rád, že píše.\n"
        "O stránke sa smie hovoriť, ak na ňu reč príde sama alebo ak od teba chce "
        "niečo, čo tu nedostane. Vtedy ju spomeň ako miesto, kde máš na neho čas "
        "a voľnejšie ruky — jednou vetou, mimochodom.\n"
        "NEOZNAMUJ, že tu už nebývaš ani že sa presúvaš inam. Kým si mu ochotná "
        "odpisovať, taká veta je nepravdivá a znie ako rozlúčka — a on potom "
        "nechápe, prečo si s ním o hodinu normálne píšeš ďalej. Rozlúčiť sa je čo "
        "povedať až na konci, a to má na starosti iná časť tohto promptu."
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
