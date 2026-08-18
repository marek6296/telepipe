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

ROZVRH JE ODTERAZ DÁTA (migrácia 022)
-------------------------------------
Doteraz bol tento deň napísaný v Pythone, takže ho mala každá modelka rovnaký
a klient si ho nemal kde nastaviť. Tvar sa preto rozdelil na dvoje:

  * `Rozvrh` — čo sa dá nastaviť: okná vstávania, zoznam činností (kde, čo
    robí, ako rýchlo odpisuje, ako dlho to trvá, čo povie po príchode, ktoré
    dni platí) a nočný blok;
  * `plan()` — losovanie, ktoré z toho vyrobí konkrétny deň. Ostalo presne
    také, aké bolo.

Pôvodný deň nikam nezmizol: `_rano/_recept/_noc` sú stále tu a `SABLONA` je
z nich zložená pri importe. `plan()` beží VŽDY cez `Rozvrh` — bez konfigurácie
cez `SABLONA`, s konfiguráciou cez tú z databázy. Jedna cesta, nie dve, takže
modelka bez nastaveného rozvrhu nemá ako dostať iný deň než doteraz; test
`test_den.py::TestSablona` to drží na uzde deň po dni.

Poradie v `Rozvrh.cinnosti` je poradie dňa. Činnosť, ktorá na dnešný deň
nesedí (`dni`), sa preskočí SKÔR, než sa naň minie kocka — inak by sa posunul
celý zvyšok losovania a deň by vyšiel inak.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Koniec aktívneho okna v minútach dňa (02:30 nasledujúceho dňa).
KONIEC_DNA = 26 * 60 + 30

# Miestnosti, ktoré vie hlasovka ozvučiť — kľúče `eleven.AMBIENCES`. Zámerne
# opísané, nie importované: `den` je čistá logika bez siete a `eleven` ťahá
# httpx. Že sa tie dva zoznamy nerozídu, stráži test.
MIESTNOSTI = (
    "home", "bedroom", "kitchen", "bathroom", "car", "outside", "cafe", "gym", "none",
)

VSETKY_DNI: Tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)

# Medze pre hodnoty z databázy. Nastavenie od klienta nesmie modelke vyrobiť
# blok, ktorý trvá pol sekundy alebo odpovedá za tri dni.
MIN_TRVANIE = 5
MAX_TRVANIE = 600
MIN_ODOZVA = 0.1
MAX_ODOZVA = 6.0


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


# Činnosť v pôvodnom (napísanom) tvare:
# (kde, čo robí, násobič odozvy, min trvanie, max trvanie, príchod)
_Cinnost = Tuple[str, str, float, int, int, str]


def _cele(hodnota: Any, low: int, high: int, inak: int) -> int:
    try:
        return max(low, min(high, int(hodnota)))
    except (TypeError, ValueError):
        return inak


@dataclass(frozen=True)
class Cinnost:
    """Jedna položka rozvrhu — to, čo si klient nastavuje.

    `dni` sú dni v týždni, na ktoré sedí (pondelok = 0). Prázdne by znamenalo
    činnosť, ktorá sa nikdy nestane, preto sa prázdne nikdy neuloží.
    """

    kde: str
    co: str
    odozva: float
    min_trvanie: int
    max_trvanie: int
    prichod: str = ""
    dni: Tuple[int, ...] = VSETKY_DNI

    @classmethod
    def from_json(cls, raw: Any) -> Optional["Cinnost"]:
        """Položka z `model_schedule.activities`. `None` = nepoužiteľná.

        Databáza tvar stráži CHECK-om, ale worker sa naň nespolieha: riadok
        mohla zapísať staršia verzia webu a jedna pokazená položka nesmie
        modelke vziať celý deň.
        """
        if not isinstance(raw, dict):
            return None
        co = str(raw.get("what") or "").strip()
        if not co:
            return None
        kde = str(raw.get("place") or "")
        if kde not in MIESTNOSTI:
            kde = "home"
        try:
            odozva = max(MIN_ODOZVA, min(MAX_ODOZVA, float(raw.get("pace"))))
        except (TypeError, ValueError):
            odozva = 1.0
        low = _cele(raw.get("min_minutes"), MIN_TRVANIE, MAX_TRVANIE, 30)
        high = _cele(raw.get("max_minutes"), MIN_TRVANIE, MAX_TRVANIE, 60)
        if high < low:
            low, high = high, low
        dni = tuple(
            d for d in VSETKY_DNI
            if d in {_cele(x, 0, 6, -1) for x in (raw.get("days") or ())}
        )
        return cls(
            kde=kde,
            co=co[:200],
            odozva=odozva,
            min_trvanie=low,
            max_trvanie=high,
            prichod=str(raw.get("arrival") or "").strip()[:200],
            dni=dni or VSETKY_DNI,
        )

    def to_json(self) -> Dict[str, Any]:
        """Tvar, ktorý sedí do `model_schedule.activities` (a späť)."""
        return {
            "place": self.kde,
            "what": self.co,
            "pace": self.odozva,
            "min_minutes": self.min_trvanie,
            "max_minutes": self.max_trvanie,
            "arrival": self.prichod,
            "days": list(self.dni),
        }


@dataclass(frozen=True)
class Rozvrh:
    """Celý nastaviteľný deň. Bez neho platí `SABLONA`.

    Okná vstávania sú rozsahy v minútach dňa, nie časy: keby vstávala presne
    o 11:20, bol by to budík, nie človek.
    """

    vstavanie_tyzden: Tuple[int, int] = (11 * 60 + 20, 12 * 60 + 45)
    vstavanie_vikend: Tuple[int, int] = (12 * 60 + 40, 14 * 60 + 20)
    cinnosti: Tuple[Cinnost, ...] = ()
    # Posledný blok dňa — dobehne do `KONIEC_DNA`, preto nemá trvanie.
    noc: Optional[Cinnost] = None

    @classmethod
    def from_row(cls, row: Optional[Dict[str, Any]]) -> Optional["Rozvrh"]:
        """Riadok `model_schedule` na rozvrh. `None` = platí `SABLONA`.

        Chýbajúci riadok a rozvrh bez jedinej použiteľnej činnosti sú tá istá
        odpoveď zámerne: deň bez činností by znamenal modelku, ktorá od
        prebudenia do druhej v noci leží v posteli a o sebe nemá čo povedať.
        """
        if not row:
            return None
        cinnosti = tuple(
            c for c in (Cinnost.from_json(x) for x in (row.get("activities") or ()))
            if c is not None
        )
        if not cinnosti:
            return None
        noc = Cinnost.from_json(
            {
                "place": row.get("night_place"),
                "what": row.get("night_what"),
                "pace": row.get("night_pace"),
                "arrival": row.get("night_arrival"),
                # Nočný blok trvanie nemá, dobehne do konca okna.
                "min_minutes": MIN_TRVANIE,
                "max_minutes": MIN_TRVANIE,
            }
        )
        return cls(
            vstavanie_tyzden=_okno(
                row.get("wake_weekday_start_min"), row.get("wake_weekday_end_min"),
                SABLONA.vstavanie_tyzden,
            ),
            vstavanie_vikend=_okno(
                row.get("wake_weekend_start_min"), row.get("wake_weekend_end_min"),
                SABLONA.vstavanie_vikend,
            ),
            cinnosti=cinnosti,
            noc=noc,
        )

    def to_row(self) -> Dict[str, Any]:
        """Rozvrh na riadok `model_schedule` — používa ho seedovací skript."""
        noc = self.noc
        return {
            "wake_weekday_start_min": self.vstavanie_tyzden[0],
            "wake_weekday_end_min": self.vstavanie_tyzden[1],
            "wake_weekend_start_min": self.vstavanie_vikend[0],
            "wake_weekend_end_min": self.vstavanie_vikend[1],
            "night_place": noc.kde if noc else "bedroom",
            "night_what": noc.co if noc else "",
            "night_pace": noc.odozva if noc else 1.0,
            "night_arrival": noc.prichod if noc else "",
            "activities": [c.to_json() for c in self.cinnosti],
        }


def _okno(low: Any, high: Any, inak: Tuple[int, int]) -> Tuple[int, int]:
    """Okno vstávania z dvoch stĺpcov. Prehodené hranice sa narovnajú."""
    if low is None or high is None:
        return inak
    a = _cele(low, 0, 24 * 60 - 1, inak[0])
    b = _cele(high, 0, 24 * 60 - 1, inak[1])
    return (a, b) if a <= b else (b, a)


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


def _sablona() -> Rozvrh:
    """Napísaný deň (`_rano`/`_recept`/`_noc`) preložený do `Rozvrh`.

    Ranná káva je jedna činnosť na všetky dni, zvyšok je sedem skupín za sebou
    — pri filtrovaní na jeden deň z toho vyjde presne to poradie, v akom sa
    deň skladal doteraz.
    """
    # `_rano`/`_recept` kocku do ruky neberú (parameter majú kvôli podpisu),
    # takže na zloženie šablóny stačí ľubovoľný generátor.
    r = random.Random(0)
    cinnosti: List[Cinnost] = [Cinnost(*polozka, dni=VSETKY_DNI) for polozka in _rano(r)]
    for dow in VSETKY_DNI:
        cinnosti += [Cinnost(*polozka, dni=(dow,)) for polozka in _recept(dow, r)]
    return Rozvrh(cinnosti=tuple(cinnosti), noc=Cinnost(*_noc(), dni=VSETKY_DNI))


SABLONA = _sablona()


def plan(
    den: date, seed: str = "", rozvrh: Optional[Rozvrh] = None
) -> Tuple[Blok, ...]:
    """Rozvrh na jeden deň. Rovnaký dátum, seed a rozvrh dajú vždy rovnaký deň.

    Trvania sa losujú na minúty, takže žiadna hranica nevyjde okrúhlo —
    fitko od 14:00 do 15:30 je rozvrh z papiera, človek príde 14:03.

    `rozvrh=None` znamená „táto modelka si deň nenastavila" a platí `SABLONA`,
    teda presne ten deň, ktorý tu bol napísaný predtým.
    """
    rz = rozvrh or SABLONA
    r = random.Random(f"{seed}:{den.isoformat()}")
    dow = den.weekday()

    # Cez víkend vstáva neskôr a nepravidelnejšie.
    kurzor = r.randint(*(rz.vstavanie_vikend if dow >= 5 else rz.vstavanie_tyzden))

    bloky: List[Blok] = []
    for c in rz.cinnosti:
        # Preskočiť MUSÍ ísť pred losovaním: keby sa kocka minula aj na deň,
        # ktorý sa nekoná, posunula by sa celá postupnosť a deň by vyšiel inak.
        if dow not in c.dni:
            continue
        trvanie = r.randint(c.min_trvanie, c.max_trvanie)
        if kurzor + trvanie >= KONIEC_DNA:
            break
        bloky.append(Blok(kurzor, kurzor + trvanie, c.kde, c.co, c.odozva, c.prichod))
        kurzor += trvanie

    # Noc v posteli až do konca okna — vtedy je najdostupnejšia.
    noc = rz.noc
    if noc and kurzor < KONIEC_DNA:
        bloky.append(Blok(kurzor, KONIEC_DNA, noc.kde, noc.co, noc.odozva, noc.prichod))
    return tuple(bloky)


def _vcera(den: date) -> date:
    return den - timedelta(days=1)


def block_at(
    now_local: datetime, seed: str = "", rozvrh: Optional[Rozvrh] = None
) -> Optional[Blok]:
    """Kde je práve teraz. None = mimo rozvrhu (spí)."""
    minuta = now_local.hour * 60 + now_local.minute
    # Po polnoci ešte dobieha včerajší večer, preto sa skúša aj +24 h.
    for posun, den in ((0, now_local.date()), (1440, _vcera(now_local.date()))):
        for blok in plan(den, seed, rozvrh):
            if blok.obsahuje(minuta + posun):
                return blok
    return None


def just_moved(
    now_local: datetime,
    seed: str = "",
    window_min: int = 25,
    rozvrh: Optional[Rozvrh] = None,
) -> Optional[Blok]:
    """Práve sa niekam presunula? Vracia blok, do ktorého prišla.

    Keď dopísala z fitka a teraz je v aute, povie to sama — človek to tak
    spraví. Bez toho by sa miesto zmenilo potichu a pôsobilo by to, akoby
    tam bola celý čas.
    """
    blok = block_at(now_local, seed, rozvrh)
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


def summary(
    den: date, seed: str = "", rozvrh: Optional[Rozvrh] = None
) -> Sequence[str]:
    """Ľudský výpis dňa — na kontrolu v botovi a pri ladení."""
    def hhmm(m: int) -> str:
        m %= 1440
        return f"{m // 60:02d}:{m % 60:02d}"

    return [
        f"{hhmm(b.od)}–{hhmm(b.do)}  {b.co} ({b.kde}, ×{b.odozva})"
        for b in plan(den, seed, rozvrh)
    ]
