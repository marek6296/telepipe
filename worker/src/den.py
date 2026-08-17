"""Deň, ktorý existuje aj keď nikto nepíše.

Doteraz sa „čo práve robí" hádalo z hodiny (`behavior.situation_hint`) — bol
to návrh, nie plán. Preto sa mohlo stať, že o tretej bola v posilňovni, o pol
štvrtej na fotení a o štvrtej znova v posilňovni: každá hodina si vybrala
nezávisle a deň nedával dokopy zmysel.

Tu je rozvrh. Pre daný deň a danú modelku vznikne raz a je stabilný, takže:

  * **odpovede sedia na to, kde je** — v posilňovni odpisuje raz za pár minút,
    na fotení dlho vôbec, doma na gauči hneď
  * **hlasovka znie odtiaľ, kde naozaj je**
  * **nikdy si neprotirečí** — o pol hodiny je stále tam, kde bola
  * **vie, že sa práve presunula** — keď dopísala z fitka a teraz je v aute,
    povie to sama, lebo tak by to spravil človek

Dve veci, na ktorých to stálo a padalo:

**Časy musia byť nepravidelné.** Fitko od 14:00 do 15:30 je rozvrh z papiera.
Človek príde 14:03 a odíde 15:22. Preto sa každé trvanie losuje na minúty a
žiadna hranica nie je okrúhla.

**Každý deň v týždni musí byť iný.** Keď mal pondelok a streda ten istý tvar
a líšili sa len o pár minút, po týždni bolo vidieť vzor. Každý deň má preto
vlastný priebeh, nie variáciu jedného.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional, Sequence, Tuple

# Koniec aktívneho okna v minútach dňa (02:30 nasledujúceho dňa).
KONIEC_DNA = 26 * 60 + 30


@dataclass(frozen=True)
class Blok:
    """Kus dňa. `od`/`do` sú minúty dňa; `do` môže presiahnuť 1440 (po polnoci)."""

    od: int
    do: int
    kde: str          # miestnosť pre hlasovku (kľúč z eleven.AMBIENCES)
    co: str           # čo robí — ide do promptu
    odozva: float     # násobič oneskorenia odpovede (1.0 = bežne)
    prichod: str = "" # čo povie, keď sa doň práve presunula

    def obsahuje(self, minuta: int) -> bool:
        return self.od <= minuta < self.do


# Činnosť: (kde, čo robí, násobič odozvy, min trvanie, max trvanie, príchod)
_Cinnost = Tuple[str, str, float, int, int, str]


def _rano(r: random.Random, skoro: bool = True) -> List[_Cinnost]:
    """Prebúdzanie. Cez víkend vstáva neskôr."""
    return [
        ("kitchen", "práve vstala a dáva si kávu, ešte je rozospatá", 0.8,
         40, 75, "práve vstala"),
    ]


def _vecer_doma(r: random.Random) -> List[_Cinnost]:
    return [
        ("kitchen", "varí si niečo jednoduché na večeru", 1.1, 25, 50,
         "práve si dala niečo na jedenie"),
        ("home", "leží na gauči a pozerá niečo v telefóne", 0.5, 90, 170, ""),
    ]


def _noc() -> _Cinnost:
    return ("bedroom", "leží v posteli a ešte sa jej nechce spať", 0.6,
            0, 0, "práve si ľahla do postele")


# Každý deň v týždni má vlastný priebeh, nie variáciu jedného. Pondelok = 0.
def _recept(dow: int, r: random.Random) -> List[_Cinnost]:
    gym = ("gym", "je v posilňovni, medzi sériami pozerá do telefónu", 2.4,
           65, 100, "práve dorazila do posilňovne")
    sprcha = ("bathroom", "práve prišla z posilňovne a ide sa osprchovať", 1.7,
              20, 40, "práve prišla z posilňovne")
    fotenie = ("none", "je na fotení a telefón má odložený", 4.0,
               110, 175, "práve prišla na fotenie")

    if dow == 0:  # pondelok — fitko a pokojný večer
        return [
            ("home", "chystá sa do posilňovne, balí si veci", 0.9, 20, 45,
             ""),
            gym, sprcha,
            ("home", "je doma a nič zvláštne nerobí", 0.7, 40, 80, "je doma"),
            *_vecer_doma(r),
        ]
    if dow == 1:  # utorok — fotenie a kaviareň
        return [
            ("bathroom", "chystá sa na fotenie, robí si vlasy a mejkap", 1.4,
             45, 80, ""),
            fotenie,
            ("cafe", "sedí v kaviarni po fotení a nikam sa neponáhľa", 0.9,
             40, 70, "práve sa usadila v kaviarni"),
            ("car", "je na ceste domov", 1.9, 20, 35, "práve sadla do auta"),
            *_vecer_doma(r),
        ]
    if dow == 2:  # streda — mesto a fitko
        return [
            ("outside", "vybavuje veci v meste, je vonku", 1.6, 50, 90,
             "práve vyšla von"),
            gym, sprcha,
            ("home", "leží na gauči a je z toho dňa hotová", 0.6, 60, 110,
             "práve dorazila domov"),
            *_vecer_doma(r),
        ]
    if dow == 3:  # štvrtok — fotenie a kamoška
        return [
            ("bathroom", "chystá sa na fotenie, robí si vlasy", 1.4, 40, 70, ""),
            fotenie,
            ("car", "je na ceste od fotenia", 1.9, 15, 30, "práve sadla do auta"),
            ("cafe", "sedí s kamoškou v kaviarni", 1.3, 50, 90,
             "práve sa stretla s kamoškou"),
            *_vecer_doma(r),
        ]
    if dow == 4:  # piatok — fitko a večer von
        return [
            gym, sprcha,
            ("bedroom", "chystá sa von, vyberá si čo si oblečie", 1.0, 35, 65,
             "práve sa začala chystať von"),
            ("outside", "je vonku s kamoškou, je tam hlučno", 2.2, 130, 200,
             "práve prišla na miesto"),
            ("car", "je na ceste domov, je unavená", 1.8, 20, 35,
             "práve sadla do auta"),
        ]
    if dow == 5:  # sobota — celý deň vonku
        return [
            ("cafe", "dala si neskoré raňajky vonku", 1.0, 50, 90,
             "práve si sadla na raňajky"),
            ("outside", "chodí po meste, nakupuje", 1.7, 90, 150,
             "práve vyšla do mesta"),
            ("bathroom", "je doma a chystá sa na večer", 1.2, 40, 70,
             "práve prišla domov"),
            ("outside", "je vonku, je tam hlasno a veselo", 2.2, 140, 210,
             "práve dorazila von"),
            ("car", "je na ceste domov", 1.8, 20, 35, "práve sadla do auta"),
        ]
    # nedeľa — lenivý deň doma
    return [
        ("home", "je doma v pyžame a nikam sa nechystá", 0.6, 70, 130, ""),
        ("kitchen", "varí si niečo poriadne, má na to čas", 1.0, 45, 80,
         "práve začala variť"),
        ("home", "leží na gauči a pozerá seriál", 0.5, 120, 200,
         "práve si ľahla na gauč"),
        ("bathroom", "dala si dlhú sprchu", 1.6, 20, 35, "práve išla do sprchy"),
    ]


def plan(den: date, seed: str = "") -> Tuple[Blok, ...]:
    """Rozvrh na jeden deň. Rovnaký dátum a seed dajú vždy rovnaký deň.

    Trvania sa losujú na minúty, takže žiadna hranica nevyjde okrúhlo —
    fitko od 14:00 do 15:30 je rozvrh z papiera, človek príde 14:03.
    """
    r = random.Random(f"{seed}:{den.isoformat()}")
    dow = den.weekday()

    # Cez víkend vstáva neskôr a nepravidelnejšie.
    if dow >= 5:
        kurzor = r.randint(12 * 60 + 40, 14 * 60 + 20)
    else:
        kurzor = r.randint(11 * 60 + 20, 12 * 60 + 45)

    bloky: List[Blok] = []
    for kde, co, odozva, low, high, prichod in _rano(r) + _recept(dow, r):
        trvanie = r.randint(low, high)
        if kurzor + trvanie >= KONIEC_DNA:
            break
        bloky.append(Blok(kurzor, kurzor + trvanie, kde, co, odozva, prichod))
        kurzor += trvanie

    # Noc v posteli až do konca okna — vtedy je najdostupnejšia.
    kde, co, odozva, _, _, prichod = _noc()
    if kurzor < KONIEC_DNA:
        bloky.append(Blok(kurzor, KONIEC_DNA, kde, co, odozva, prichod))
    return tuple(bloky)


def _vcera(den: date) -> date:
    return den - timedelta(days=1)


def block_at(now_local: datetime, seed: str = "") -> Optional[Blok]:
    """Kde je práve teraz. None = mimo rozvrhu (spí)."""
    minuta = now_local.hour * 60 + now_local.minute
    # Po polnoci ešte dobieha včerajší večer, preto sa skúša aj +24 h.
    for posun, den in ((0, now_local.date()), (1440, _vcera(now_local.date()))):
        for blok in plan(den, seed):
            if blok.obsahuje(minuta + posun):
                return blok
    return None


def just_moved(
    now_local: datetime, seed: str = "", window_min: int = 25
) -> Optional[Blok]:
    """Práve sa niekam presunula? Vracia blok, do ktorého prišla.

    Keď dopísala z fitka a teraz je v aute, povie to sama — človek to tak
    spraví. Bez toho by sa miesto zmenilo potichu a pôsobilo by to, akoby
    tam bola celý čas.
    """
    blok = block_at(now_local, seed)
    if not blok or not blok.prichod:
        return None
    minuta = now_local.hour * 60 + now_local.minute
    for posun in (0, 1440):
        if 0 <= (minuta + posun) - blok.od <= window_min:
            return blok
    return None


def describe(blok: Optional[Blok]) -> str:
    """Čo o sebe smie povedať. Prázdne = rozvrh nič nehovorí."""
    return blok.co if blok else ""


def arrival(blok: Optional[Blok]) -> str:
    """Veta o tom, že sa práve presunula. Prázdne = nič sa nedeje."""
    return blok.prichod if blok else ""


def where(blok: Optional[Blok], fallback: str = "home") -> str:
    """Odkiaľ má znieť hlasovka."""
    if not blok or not blok.kde:
        return fallback
    return blok.kde


def pace(blok: Optional[Blok]) -> float:
    """Násobič oneskorenia odpovede. 1.0 = bežne, viac = pomalšie."""
    return float(blok.odozva) if blok else 1.0


def busy(blok: Optional[Blok]) -> bool:
    """Je práve tak zaneprázdnená, že by človek čakal dlhé ticho?"""
    return bool(blok and blok.odozva >= 2.5)


def summary(den: date, seed: str = "") -> Sequence[str]:
    """Ľudský výpis dňa — na kontrolu v botovi a pri ladení."""
    def hhmm(m: int) -> str:
        m %= 1440
        return f"{m // 60:02d}:{m % 60:02d}"

    return [f"{hhmm(b.od)}–{hhmm(b.do)}  {b.co} ({b.kde}, ×{b.odozva})" for b in plan(den, seed)]
