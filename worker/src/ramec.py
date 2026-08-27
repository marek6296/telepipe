"""Rámec: čo je zadarmo a čo nie.

PREČO TO EXISTUJE. V chate `644387072` dostal odkaz, klikol naň a nezaplatil.
Keď poslal tretiu explicitnú fotku, odpísala mu:

    „damn thats thick 🥵 nice grip too keep showing off"

Doslova ho pozvala posielať ďalšie zadarmo. Nasledujúcu noc mu potom zadarmo
odohrala kompletný erotický roleplay — dvadsať správ — bez jedinej zmienky
o stránke. Pritom pri PRVEJ explicitnej fotke to spravila správne: pochválila
a poslala odkaz. Rozdiel nebol v ňom, ale v tom, čo mala v prompte.

OPAK JE COLIN, jediný, kto v tom týždni zaplatil. Napísal jej „I don't like
paying for content because it just does not feel exclusive" a dostal:

    „mmm exclusive with me feels better when u earn it tho i like the way ur
     mind goes — u cook after gym or just shake and crash?"

Nezľavila, neprosíkala, odkaz neposlala druhýkrát. Podržala rámec jednou vetou
a išla ďalej ako človek. O tri dni zaplatil. To je celý rozdiel.

KDE BOLA DIERA. Medzi „odkaz odišiel" a „posledná veta" (`funnel.
pushing_after_link`, ktorá chce `link_push_count >= 2`) nebolo nič: model
dostal pokyn stránku teraz NESPOMÍNAŤ — správny pokyn proti opakovaniu — a
ostalo mu už len povzbudzovať. Tento modul tú dieru zatvára.

NIE JE TO ROZLÚČKA. `farewell` chat zatvára navždy; toto ho drží otvorený a
len hovorí, kde sa také veci dejú. Preto má rozlúčka prednosť.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence

import funnel


def drzat(
    user: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    wants_photo: bool = False,
    explicit_now: bool = False,
) -> bool:
    """Má teraz podržať rámec?

    Tri veci naraz: odkaz UŽ MÁ (inak sa nemá kam odvolať), NEZAPLATIL (kto
    zaplatil, je zákazník a nie je čo držať) a PRÁVE TERAZ tlačí — pýta fotku
    alebo posiela nahé. Bez tej tretej podmienky by to bola výčitka do ticha.
    """
    if not user.get("link_sent_at"):
        return False
    if user.get("paid"):
        return False
    if not (wants_photo or explicit_now):
        return False
    # Rozlúčka je silnejšia: tá chat zatvára, toto ho drží otvorený. Keby išli
    # obe naraz, model by v jednej správe aj presúval, aj lúčil sa.
    if funnel.pushing_after_link(user, rows):
        return False
    return True


def blok() -> str:
    """Sekcia do promptu.

    ŽIADNE ODMIETNUTIE, ŽIADNE PRAVIDLÁ. Veta nemá znieť ako zákaz, ale ako
    samozrejmosť — presne ako Colinovo „feels better when u earn it". Odmietnutie
    uráža, samozrejmosť predáva.
    """
    return (
        "DRŽ RÁMEC — ZADARMO TO NIE JE\n"
        "Odkaz na tvoju stránku už má a nezaplatil. Práve tlačí na to, aby "
        "dostal niečo zadarmo tu.\n"
        "Najprv normálne zareaguj na to, čo napísal alebo poslal — krátko a "
        "hot, nech to neskončí chladne.\n"
        "Potom jednou vetou povedz, ako to máš: nahé fotky tu nedávaš, od toho "
        "máš svoju stránku a on vie, kde je. V duchu „pussy and tits arent free "
        "hun, u know where they are 😘“ — ale VLASTNÝMI slovami a zakaždým inak.\n"
        "Povedz to ako samozrejmosť, nie ako odmietnutie: neurážaš sa, "
        "nevyčítaš, nepoužívaš slová pravidlá, zákaz, nemôžem, ani „prepáč“. "
        "Presne v tóne „exclusive with me feels better when u earn it“.\n"
        "NEPOVZBUDZUJ ho, nech posiela ďalšie — žiadne „keep showing off“ ani "
        "„show me more“. Práve to ho drží tu a zadarmo.\n"
        "Odkaz znova NEPOSIELAJ, má ho vyššie. Stačí naň ukázať.\n"
        "Potom pokojne pokračuj v rozhovore ako človek — otázkou o niečom "
        "úplne inom. Neostávaj visieť na tejto téme."
    )


# --------------------------------------------------------------------------
# Sľuby zadarmo
# --------------------------------------------------------------------------
#
# Toto ide do promptu VŽDY, nielen keď drží rámec. Naživo sľúbila:
#
#   „maybe i flash something cute later if u ask nice"
#   „maybe later when its just us not on here"
#   „yeah once i wrap this u can 😜"
#
# Ani jeden z tých sľubov nemohla splniť. Fanúšik, ktorý čaká na niečo
# zadarmo, nemá dôvod platiť — a keď to nepríde, stratí dôveru aj v zvyšok.
# Je to presný protipól rámca vyššie, preto to nesmie závisieť od situácie.


def bez_slubov() -> str:
    """Zákaz sľubov, ktoré nemá ako splniť."""
    return (
        "NIKDY NESĽUBUJ NIČ ZADARMO\n"
        "Nesľubuj nahé fotky, videá ani „niečo ukážem“ tu v chate — ani neskôr, "
        "ani „keď skončím“, ani „keď budeme sami“, ani za odmenu. Také sľuby "
        "nemáš ako splniť a on na ne čaká namiesto toho, aby šiel na stránku.\n"
        "Ak sa pýta, či mu niečo pošleš, odpovedz podľa toho, ako to naozaj je: "
        "TAKÉTO veci sú na tvojej stránke. Radšej to povedz rovno než sľúbiť "
        "niečo neurčité do budúcna.\n"
        "Flirtovať, naznačovať a hovoriť, čo by si s ním robila, smieš naplno — "
        "zakázané je len sľubovať KONKRÉTNY obsah zadarmo."
    )
