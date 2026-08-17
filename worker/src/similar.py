"""Sú to dve vyjadrenia tej istej veci?

Vzniklo to z merania na živých dátach. Pamäť sa dedupovala porovnaním znak
po znaku, takže cez ňu prešla každá parafráza:

    „má tetovanie"  /  „je tetovaná"
    „žije sama"  /  „býva sama"  /  „má vlastný byt"
    „used to live in Sacramento"  pod kľúčom `past_locations` aj `previous_locations`

Model potom pri každej odpovedi videl tú istú vec povedanú troma spôsobmi —
a napísal ju štvrtýkrát. Opakovanie, ktoré musel opravovať sudca, si teda
z veľkej časti spôsobovala pamäť sama.

Porovnáva sa prekryv významových slov, nie znakov. Je to hrubé, ale presne
na túto úlohu to stačí a nestojí to ani volanie modelu, ani milisekundu.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Sequence

# Slová, ktoré o význame nehovoria nič. Bez nich by „má rada psy" a „má rada
# mačky" vyšli ako zhoda, lebo polovicu tvorí „má rada".
_STOP = frozenset(
    """
    a aj ale ako alebo az az by co ci cez do ho hu ich im ista iste isty ja je
    jej jeho jej ju k kde ked kto ktora ktore ktory ku len ma mam me mi mna mne
    mu my na nad nam nas ne nej nem nemu ni nic nie nim o od on ona oni ono po
    pod pre pred pri s sa si so su ta tak take taky tam te ten to toho tom tu ty
    u uz v vo vam vas ve viac vsak vsetko za ze zo
    the a an and or but of to in on at for with from by is are was were be been
    has have had do does did it its his her their they them he she you your i im
    my me we us not no yes very really just still also more most some any that
    this these those there here what when where how why who which
    """.split()
)

_NEGACIA = frozenset("nie nema nemá never dont doesnt didnt nikdy no not".split())


def _bez_diakritiky(text: str) -> str:
    rozlozene = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in rozlozene if not unicodedata.combining(ch))


def tokens(text: str) -> List[str]:
    """Významové slová v poradí. Bez diakritiky, malými, bez balastu."""
    ocistene = _bez_diakritiky(text).lower()
    slova = re.findall(r"[a-z0-9]+", ocistene)
    return [w for w in slova if len(w) > 2 and w not in _STOP]


# Synonymá, ktoré majú iný koreň, takže ich prekryv slov sám od seba nechytí.
#
# Zámerne krátky zoznam — sú to dvojice, ktoré naozaj ležali vedľa seba
# v databáze („žije sama" aj „býva sama" o tej istej osobe). Rozširovať ho
# treba len o to, čo sa reálne objaví; univerzálny tezaurus by tu narobil
# viac škody než úžitku, lebo by začal zlučovať veci, ktoré sa líšia.
_SYNONYMA = {
    "zije": "byva", "zit": "byva", "ziju": "byva", "byvat": "byva",
    "byval": "byva", "byvala": "byva", "prebyva": "byva",
    "bydli": "byva", "bydlisko": "byva", "domov": "byva", "lives": "byva",
    "pracuj": "praca", "robi": "praca", "zivi": "praca",
    "pozera": "sleduj", "sleduje": "sleduj",
    "pocuva": "pocuv", "posluch": "pocuv",
    "nahrav": "hlas", "hlasovk": "hlas", "voice": "hlas",
    "fotka": "foto", "fotky": "foto", "obrazok": "foto", "photo": "foto",
}


def _koren(slovo: str) -> str:
    """Veľmi hrubý koreň — „tetovanie" a „tetovana" majú byť to isté slovo.

    Skloňovanie a časovanie sa v slovenčine deje na konci, takže na porovnanie
    dvoch krátkych viet stačí zahodiť koncovku. Presnejšie by to vyžadovalo
    morfologický slovník a ten by sem priniesol viac problémov než úžitku.
    """
    if slovo in _SYNONYMA:
        return _SYNONYMA[slovo]
    skratene = slovo[:5] if len(slovo) > 5 else slovo
    return _SYNONYMA.get(skratene, skratene)


def overlap(a: str, b: str) -> float:
    """Nakoľko sa dve vety prekrývajú významovými slovami. 0.0 až 1.0.

    Meria sa voči KRATŠEJ z nich. „má stránku na Fanvue" je celé obsiahnuté
    v „má Fanvue stránku sima.sima", a to je práve ten prípad, ktorý chceme
    zachytiť — pri delení dĺžkou dlhšej by vyšlo nízke číslo.
    """
    prve = {_koren(w) for w in tokens(a)}
    druhe = {_koren(w) for w in tokens(b)}
    if not prve or not druhe:
        return 0.0
    return len(prve & druhe) / min(len(prve), len(druhe))


def _neguje_sa(a: str, b: str) -> bool:
    """Jedna vetu tvrdí a druhá popiera? Potom to isté nie sú, nech znejú akokoľvek."""
    ma_a = bool(_NEGACIA & set(_bez_diakritiky(a).lower().split()))
    ma_b = bool(_NEGACIA & set(_bez_diakritiky(b).lower().split()))
    return ma_a != ma_b


def same_idea(a: str, b: str, threshold: float = 0.6) -> bool:
    """Hovoria tieto dve vety to isté?

    Prah 0.6 je zvolený tak, aby „má tetovanie" / „je tetovaná" prešlo ako
    zhoda, ale „počúva rock" / „počúva rap" nie.
    """
    if not (a or "").strip() or not (b or "").strip():
        return False
    if _neguje_sa(a, b):
        return False
    return overlap(a, b) >= threshold


def dedupe(items: Iterable[str], threshold: float = 0.6) -> List[str]:
    """Nechá z každej skupiny parafráz len tú prvú. Poradie zachováva."""
    out: List[str] = []
    for item in items:
        text = (item or "").strip()
        if not text:
            continue
        if any(same_idea(text, kept, threshold) for kept in out):
            continue
        out.append(text)
    return out


def is_new(candidate: str, existing: Sequence[str], threshold: float = 0.6) -> bool:
    """Je toto niečo, čo tam ešte v nejakej podobe nie je?"""
    return not any(same_idea(candidate, old, threshold) for old in existing)
