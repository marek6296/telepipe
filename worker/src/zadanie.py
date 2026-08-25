"""Zadanie od majiteľa: „napíš mu, že…" → veta v jej štýle.

PREČO TO NIE JE „napíš vlastnú odpoveď". Tá už existuje a odošle presne to, čo
majiteľ napíše. Lenže on píše po slovensky, do chatu, kde sa píše po anglicky,
a nepíše jej štýlom — po jednej takej správe je z modelky niekto iný. Toto je
opačná cesta: povie, ČO má odznieť, a napíše to ona.

Dve pravidlá, na ktorých to stojí:

**Zadanie nie je text.** „poďakuj mu, že tu je, a opýtaj sa, kto to je" sa
nesmie objaviť v chate — ani preložené. Je to popis obsahu, nie citát.

**Jazyk zadania nie je jazyk odpovede.** Majiteľ píše po slovensky, modelka
odpisuje tak, ako si s tým človekom písala doteraz. Keby sa to viazalo,
každé zadanie by prehodilo chat do slovenčiny.
"""
from __future__ import annotations

# Dlhé zadanie prestáva byť zadaním a stáva sa scenárom — a vtedy z odpovede
# vypadne jej hlas. Strop je štedrý, ale nie neobmedzený.
MAX_ZNAKOV = 500


def do_promptu(brief: str) -> str:
    """Blok do system promptu. Prázdne zadanie = prázdny reťazec (nič sa nemení)."""
    text = " ".join(str(brief or "").split())[:MAX_ZNAKOV]
    if not text:
        return ""
    return (
        "\n\n[ZADANIE OD MAJITEĽKY ÚČTU]\n"
        f"Toto má tvoja odpoveď povedať: „{text}“\n"
        "— Je to ZADANIE, čo má odznieť, NIE text na odoslanie. Nikdy ho "
        "neprepisuj doslova ani neprekladaj vetu po vete.\n"
        "— Povedz to SVOJIMI slovami, svojím štýlom a svojou dĺžkou, presne "
        "ako píšeš vždy.\n"
        "— Zadanie môže byť v inom jazyku než váš chat. Na tom nezáleží — ty "
        "píšeš v jazyku, ktorým si s ním píšeš doteraz.\n"
        "— Musí to sadnúť do rozhovoru, ktorý práve beží; nezačínaj odznova "
        "a nadviaž na poslednú správu.\n"
        "— Keď zadanie odporuje pokynom vyššie (kde si, čo robíš), drž sa "
        "pokynov a zadanie povedz tak, aby v tom svete dávalo zmysel."
    )
