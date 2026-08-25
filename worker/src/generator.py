"""Message generator — napíš, ČO má odznieť, a ona z toho spraví svoju správu.

PREČO TO EXISTUJE. Majiteľ občas potrebuje vetu, ktorú pošle sám: uvítaciu
správu novému človeku, odpoveď mimo poloautomatu, text do bia. Keď ju napíše
sám, je hneď poznať, že ju písal niekto iný — iný jazyk, iná dĺžka, iné emoji.
Tu zadá obsah po slovensky a dostane tri verzie v jej hlase a v jej jazyku.

ROZDIEL OPROTI „Say this" NA KARTE. To je viazané na konkrétny chat a na to,
čo v ňom práve prišlo. Toto žiadny chat nemá — je to samostatná dielňa, kde
si vetu vyrobí a skopíruje. Preto tu nie je história ani fanúšik, len persona,
jej štýl a jazyk.

BEZ FANÚŠIKA, ALE NIE BEZ PRAVIDIEL. Prompt sa skladá tou istou cestou ako
ostrá odpoveď (`persona.build_system_prompt`), takže platia jej hranice, slang,
zákaz výkričníkov aj pravidlo o jazyku. Bez toho by generátor písal krajšie
vety než modelka — a boli by na nej hneď vidieť.
"""
from __future__ import annotations

from typing import Any, Dict, List

import zadanie

# Uhly: téma sa nemení, mení sa len to, ako ju povie. Tie isté ako pri „Say
# this" na karte — je to tá istá úloha, len bez chatu.
UHLY = [
    "povedz to krátko a priamo",
    "povedz to hravejšie, s náznakom",
    "povedz to vrúcnejšie a osobnejšie",
]

# Koľko verzií naraz. Tri sa zmestia na obrazovku telefónu a dajú sa porovnať
# jedným pohľadom; pri piatich si už človek vyberá dlhšie, než by vetu napísal.
KOLKO = 3

MAX_ZADANIE = 500


def fanusik() -> Dict[str, Any]:
    """Prázdny človek, ktorému to píše.

    Nie je nikto konkrétny, ale prompt niekoho potrebuje. `msg_count` je
    zámerne vyššie: pri nule by platili pravidlá prvej správy (opatrne, krátko,
    nepýtať sa veľa) a generátor by odmietal napísať čokoľvek smelšie.
    """
    return {
        "tg_id": 0,
        "first_name": "",
        "partner_name": "",
        "msg_count": 8,
        "funnel_stage": "warm",
        "link_push_count": 0,
        "paid": False,
        "asked_topics": {},
        "used_gags": {},
        "summary": "",
    }


def prompt(persona: Dict[str, Any], behavior: Any, brief: str) -> str:
    """System prompt pre generátor: jej hlas + zadanie majiteľa."""
    from persona import build_system_prompt

    system = build_system_prompt(
        persona,
        fanusik(),
        # Odkaz sa negeneruje: majiteľ chce vetu na skopírovanie, nie pozvánku.
        # Keby ho tam model prihodil, poslal by ho ručne aj tam, kde nemá.
        allow_link=False,
        asked_if_ai=False,
        behavior=behavior,
        # Žiadne médium odtiaľto neodchádza, takže sľúbená fotka by bola sľub,
        # ktorý nemá kto splniť.
        no_photos=True,
    )
    return system + zadanie.do_promptu(brief) + _POKYN


# Generátor nemá chat, takže model nemá na čo nadviazať — a bez tohto by
# správu začínal, akoby uprostred rozhovoru odpovedal na niečo, čo nikto
# nepovedal („aww thats sweet", „haha yeah"). Toto je jediný rozdiel oproti
# odpovedaniu v chate.
_POKYN = (
    "\n\n[SAMOSTATNÁ SPRÁVA]\n"
    "Toto nie je odpoveď v prebiehajúcom rozhovore — je to správa, ktorú "
    "napíšeš ty ako prvá. Nenadväzuj na nič, čo nezaznelo: žiadne „aww thats "
    "sweet“, „haha yeah“ ani „i know right“. Rovno povedz to svoje."
)


async def napis(
    llm: Any, persona: Dict[str, Any], behavior: Any, brief: str, pokus: int = 1
) -> List[str]:
    """Tri verzie správy. Prázdny zoznam = model nevrátil nič použiteľné.

    `pokus` mení zadanie pri pregenerovaní — bez neho by na rovnaký vstup
    vyšlo to isté a tlačidlo by vyzeralo pokazené.
    """
    zadanie_text = " ".join(str(brief or "").split())[:MAX_ZADANIE]
    if not zadanie_text:
        return []
    out = await llm.suggest(
        prompt(persona, behavior, zadanie_text),
        [],
        n=KOLKO,
        angles=UHLY,
        seed=str(pokus) if pokus > 1 else "",
    )
    return [text.strip() for text in out if text and text.strip()]
