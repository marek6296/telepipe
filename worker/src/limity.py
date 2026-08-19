"""Koľko toho smie z účtu odísť, aby si toho Telegram nevšimol.

Dôležité je, že strop na počet správ sám o sebe nestačí — a dokonca meria
nesprávnu vec. Tridsať správ za hodinu dvom ľuďom je normálny človek, ktorý
sa práve rozpísal. Tridsať správ za hodinu tridsiatim ľuďom je rozposielanie,
a presne to je vzor, na ktorý Telegram reaguje.

Preto sú stropy dva a ten druhý je ten dôležitejší:

  * **koľko správ** za hodinu — proti tomu, aby účet nechrlil
  * **koľkým ľuďom sa ozve SAMA** za hodinu — to je tá riziková časť

Ten druhý je dôležitý a zámerne sa NEUPLATŇUJE na odpovede. Odpovedať tomu,
kto napísal prvý, nie je vzor, ktorý by komukoľvek vadil — nech ich je aj
dvadsať. Podozrivé je opačné poradie: účet, ktorý sám oslovuje ľudí, čo
oň nepožiadali. Presne to robí ranné oslovenie, a preto je strop tam.

Prvá verzia mala strop na počet rôznych ľudí aj pri odpovediach a bolo to zle:
kým dvanásť rozhovorov bežalo, trinásty človek by sa odpovede nedočkal nikdy.
Objem odpovedí drží strop na počet správ, ten stačí.

Čo strop zadrží, sa nestratí — človeku ostane `pending_reply` a odpoveď
dobehne v ďalšom cykle.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Set


def uz_oslovenych(tg_ids: Iterable[int]) -> Set[int]:
    """Komu za sledované obdobie odišla aspoň jedna správa."""
    return {int(t) for t in tg_ids if t is not None}


def smie_oslovit(
    tg_id: int,
    oslovenych: Set[int],
    max_za_hodinu: int,
) -> bool:
    """Smie sa práve teraz OZVAŤ SAMA tomuto človeku?

    Kto v tejto hodine už niečo dostal, prejde vždy — pokračovanie rozhovoru
    nikoho nezaujíma. Strop sa uplatní len na ďalšie nové oslovenie.
    """
    if max_za_hodinu <= 0:
        return True  # 0 = strop vypnutý
    if int(tg_id) in oslovenych:
        return True
    return len(oslovenych) < max_za_hodinu


def koho_oslovit(
    fronta: Sequence[int],
    oslovenych: Set[int],
    max_za_hodinu: int,
    volnych_sprav: int,
) -> list:
    """Z kandidátov vyberie tých, ktorým sa teraz smie ozvať sama.

    Poradie sa zachováva — kto čaká dlhšie, ide skôr. Rozhoduje sa postupne,
    lebo každý nový človek zaberie miesto ďalšiemu.
    """
    vybrati: list = []
    zatial = set(oslovenych)
    for tg_id in fronta:
        if len(vybrati) >= max(volnych_sprav, 0):
            break
        if not smie_oslovit(tg_id, zatial, max_za_hodinu):
            continue
        vybrati.append(tg_id)
        zatial.add(int(tg_id))
    return vybrati


# ---------- koľko rozhovorov naraz ----------

def obsadene_miesta(
    aktivni: Iterable[int], max_naraz: int
) -> int:
    """Koľko miest je práve obsadených. Len na výpis a do logu."""
    return len(set(aktivni)) if max_naraz > 0 else 0


def ma_miesto(tg_id: int, aktivni: Set[int], max_naraz: int) -> bool:
    """Smie sa s TÝMTO človekom teraz písať?

    Skutočný človek nevedie dvadsať rozhovorov naraz. Vedie pár, tie dopíše,
    a keď utíchnu, pustí sa do ďalších. Presne to robí toto: kým je miesto
    obsadené, nový človek počká — a nič sa nestratí, ostáva mu `pending_reply`.

    Kto miesto už drží, prejde vždy. Rozhovor sa nesmie preseknúť v polovici
    len preto, že medzitým napísal niekto ďalší.
    """
    if max_naraz <= 0:
        return True  # 0 = vypnuté, píše všetkým
    if int(tg_id) in aktivni:
        return True
    return len(aktivni) < max_naraz


def kto_ide_na_rad(
    fronta: Sequence[int],
    aktivni: Set[int],
    max_naraz: int,
    volnych_sprav: int,
) -> list:
    """Z čakajúcich vyberie tých, na ktorých je teraz miesto.

    `fronta` má byť zoradená od toho, kto čaká najdlhšie — inak by sa na
    posledného nedostalo nikdy. Rozhoduje sa postupne, lebo každý pustený
    zaberie miesto ďalšiemu.
    """
    vybrati: list = []
    obsadene = set(aktivni)
    for tg_id in fronta:
        if len(vybrati) >= max(volnych_sprav, 0):
            break
        if not ma_miesto(tg_id, obsadene, max_naraz):
            continue
        vybrati.append(tg_id)
        obsadene.add(int(tg_id))
    return vybrati


# ---------- keď sa Telegram ozve sám ----------

# Ako dlho po `PeerFloodError` nemá zmysel skúšať čokoľvek. Je to najvážnejšia
# odpoveď, akú Telegram dá — znamená „účet máme označený za rozposielača".
# Pokračovať v písaní po nej je najrýchlejšia cesta k zablokovaniu.
PEER_FLOOD_PAUZA_H = 24

# Nad túto dĺžku čakania sa už oplatí ozvať Marekovi, nie len zapísať do logu.
HLASIT_NAD_S = 300

# Koľko flood chýb za hodinu znamená „účet je na hrane". Jeden FloodWait je
# bežná prevádzka, tri za hodinu už nie — a keďže Telethon má auto-sleep
# vypnutý (`flood_sleep_threshold=0` v runner.py), vidíme aj tie sekundové,
# ktoré boli doteraz neviditeľné. To je práve tá informácia, ktorá chýbala:
# PeerFlood nepríde z čista jasna, ohlási sa drobnými.
FLOOD_VAROVANIE_ZA_HODINU = 3


# ---------- rozbeh nového účtu ----------

# Čerstvý účet s novým číslom, ktorý od prvej sekundy píše na plný strop, je pre
# Telegram oveľa podozrivejší než ten istý objem na účte starom rok. Doteraz sa
# nerozlišovalo vôbec.
#
# Krivka je zámerne hrubá — ide o rád veličiny, nie o presnosť. Prvý deň štvrtina,
# do troch dní polovica, do týždňa tri štvrtiny, potom plný strop.
_ROZBEH = (
    (24, 0.25),    # prvý deň
    (72, 0.50),    # do troch dní
    (168, 0.75),   # do týždňa
)


def rozbeh_podiel(hodin_od_pripojenia: Optional[float]) -> float:
    """Akú časť stropov smie čerstvý účet využiť. 1.0 = plný strop.

    `None` (neznámy čas pripojenia) = plný strop. Brzdiť účet len preto, že
    nevieme, kedy vznikol, by bolo horšie než nebrzdiť.
    """
    if hodin_od_pripojenia is None or hodin_od_pripojenia < 0:
        return 1.0
    for hranica, podiel in _ROZBEH:
        if hodin_od_pripojenia < hranica:
            return podiel
    return 1.0


def s_rozbehom(strop: int, podiel: float) -> int:
    """Strop zmenšený rozbehom. Vypnutý strop (0) ostáva vypnutý.

    Nikdy nespadne na nulu: štvrtina z troch je nula, a nulový strop dnes
    znamená „bez limitu" — čiže by rozbeh spôsobil pravý opak toho, čo má.
    """
    if strop <= 0:
        return strop
    return max(int(strop * podiel), 1)


# Triedy sa berú priamo z Telethonu, nie podľa názvu. Porovnávanie mien by
# ticho minulo podtriedu aj premenovanie — a chyba, ktorá sa takto stratí,
# skončí opakovaným pokusom, čiže presne tým, čo nemá nastať.
from telethon.errors import (  # noqa: E402
    FloodWaitError,
    PeerFloodError,
    SlowModeWaitError,
)

_CAKACIE = (FloodWaitError, SlowModeWaitError)


def flood_pauza_s(exc: Exception) -> Optional[int]:
    """Koľko sekúnd sa nemá nič posielať. None = nejde o flood chybu.

    Telegram pri `FloodWaitError` sám povie, koľko chce čakať, a to číslo sa
    má rešpektovať do sekundy. Opakovaný pokus počas čakania ho predlžuje.
    """
    if isinstance(exc, PeerFloodError):
        return PEER_FLOOD_PAUZA_H * 3600
    if isinstance(exc, _CAKACIE):
        try:
            return max(int(getattr(exc, "seconds", 0)), 1)
        except (TypeError, ValueError):
            return 60
    return None


def je_spam_priznak(exc: Exception) -> bool:
    """Je to tá chyba, ktorá znamená „účet je označený"?"""
    return isinstance(exc, PeerFloodError)
