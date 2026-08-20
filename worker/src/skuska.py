"""Skúšobný chat: majiteľ píše botovi, modelka mu odpovie ako fanúšikovi.

PREČO TO EXISTUJE
-----------------
Persónu si klient nastaví (alebo mu ju napíše AI builder) a potom nemá ako
zistiť, či to znie dobre — kým mu nenapíše prvý skutočný človek. To je zlé
miesto na prvý test: chyba v tóne alebo v jazyku stojí lead, ktorý sa už
nevráti. Tu si ju vyskúša na sebe.

ČO TO NIE JE
------------
Nie je to simulácia celého odpisovania. Časovanie, „videné", hlasovky, fotky,
útlm ani funnel sa tu nediať nebudú a ani nesmú — bola by to druhá kópia
`userbot._reply_locked` a rozišla by sa s tou pravou v prvom týždni. Toto
overuje JEDINÚ vec, na ktorej naozaj záleží: ako znie, keď odpisuje.

Prompt sa preto stavia rovnakou funkciou (`persona.build_system_prompt`) a
odpoveď prechádza rovnakým čistením (`humanize`) ako v ostrej prevádzke. Keď
sa zmení jedno, zmení sa aj druhé.

HISTÓRIA ŽIJE V PAMÄTI, NIE V DATABÁZE
--------------------------------------
Skúšobná konverzácia nesmie pristáť medzi skutočnými: pokazila by štatistiky,
pamäť aj denný súhrn. Preto je držaná len v procese a reštart ju zmaže — čo je
pri skúške presne to, čo človek aj čaká.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import humanize
from persona import build_system_prompt

log = logging.getLogger(__name__)

# Koľko správ si zo skúšobného chatu pamätáme. Viac netreba: kto skúša, píše
# pár správ a pozerá, ako znie — nie ako si pamätá vlaňajšie Vianoce.
PAMAT = 20

# Fanúšik, za ktorého sa majiteľ v skúške vydáva. Čísla sú zámerne „rozbehnutá
# konverzácia": pri `msg_count: 0` by dostával len prvé opatrné vety a
# nedozvedel by sa nič o tom, ako znie normálne.
def novy_fanusik() -> Dict[str, Any]:
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


class Skuska:
    """Skúšobné konverzácie, jedna na majiteľa."""

    def __init__(self) -> None:
        self._chaty: Dict[int, List[Dict[str, str]]] = {}
        self._user: Dict[int, Dict[str, Any]] = {}

    def bezi(self, chat_id: int) -> bool:
        return chat_id in self._chaty

    def zapni(self, chat_id: int) -> None:
        self._chaty[chat_id] = []
        self._user[chat_id] = novy_fanusik()

    def vypni(self, chat_id: int) -> None:
        self._chaty.pop(chat_id, None)
        self._user.pop(chat_id, None)

    def vycisti(self, chat_id: int) -> None:
        """Začne odznova, ale skúška beží ďalej."""
        if self.bezi(chat_id):
            self.zapni(chat_id)

    def historia(self, chat_id: int) -> List[Dict[str, str]]:
        return list(self._chaty.get(chat_id) or [])

    async def odpoved(
        self,
        chat_id: int,
        text: str,
        persona: Dict[str, Any],
        behavior: Any,
        llm: Any,
    ) -> List[str]:
        """Jedna odpoveď modelky — rozdelená na bubliny ako v ostrom chate."""
        historia = self._chaty.setdefault(chat_id, [])
        user = self._user.setdefault(chat_id, novy_fanusik())
        historia.append({"role": "user", "content": text})
        del historia[:-PAMAT]

        user["msg_count"] = int(user.get("msg_count") or 0) + 1
        system = build_system_prompt(
            persona,
            user,
            # Odkaz sa v skúške NEPOSIELA. Nie je komu a klient by si zvykol
            # posudzovať vetu, ktorá v skutočnom chate príde inokedy a inak.
            allow_link=False,
            asked_if_ai=humanize.looks_like_ai_question(text),
            behavior=behavior,
            foreign=humanize.looks_foreign(text),
            bare_greeting=humanize.is_bare_greeting(text),
            his_question=humanize.last_question(text),
        )
        raw = await llm.reply(system, historia)

        # Čistenie ide TOU ISTOU cestou ako ostrá odpoveď. Import je lokálny,
        # aby `skuska` nezaťahovala celý userbot pri importe modulu — a aby sa
        # nedal spraviť kruh, keby userbot niekedy potreboval skúšku.
        from userbot import UserBot

        jej_nedavne = [
            m["content"] for m in historia if m["role"] == "assistant"
        ][-6:]
        cisty = UserBot._uprav_odpoved(
            raw or "",
            behavior,
            # Odstup od jej poslednej správy. V skúške sa píše plynule, takže
            # nula — pozdraviť sa smie len vtedy, keď pozdraví on.
            0.0,
            False,
            jej_nedavne,
            he_greeted=humanize.is_bare_greeting(text),
        )
        kusy = [k for k in humanize.split_message(cisty) if k.strip()]
        if not kusy:
            log.info("skúška %s: po vyčistení nezostal text", chat_id)
            return []
        historia.append({"role": "assistant", "content": " ".join(kusy)})
        del historia[:-PAMAT]
        return kusy
