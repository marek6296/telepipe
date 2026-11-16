"""Channel context layered over the authored persona, never canned dialogue."""
from __future__ import annotations

from typing import Any, Dict

MAX_POZVANI = 2
ODSTUP_SPRAV = 8


def blok(nastavenia: Dict[str, Any], pozvala_uz: int = 0, offer=None) -> str:
    offer = offer or {}
    rules = [
        "PLATFORMA: INSTAGRAM DM. Same persona, language, memories and writing style as other channels. "
        "Follow the authored spelling/slang/no-diacritics rules. Usually one or two short sentences. "
        "Answer the actual latest message using the recent conversation; never restart an existing conversation. "
        "Avoid repeated greetings, pet names, questions and invitation phrases. Match the conversational energy.",
        "Keep this channel non-explicit. Never promote or name Fanvue/OnlyFans here. No payment pressure. "
        "No voice notes, videos or promises of unavailable media. Do not invent what an unviewed photo contains. "
        "Do not pretend to be human when directly asked about automation or the virtual persona.",
        "No literal URLs, handles or obfuscated addresses. Only the server may insert a configured URL. "
        "You may use at most one of the exact markers below when the corresponding intent is allowed. "
        "They are internal actions, not dialogue examples. Do not explain the markers to the person. "
        "Never invite in every response, after rejection, during distress, or as an unrelated interruption. "
        "Repeated pressure for media can receive a brief, firm boundary in your existing voice.",
    ]
    if offer.get('link'):
        target = 'Telegram' if nastavenia.get('funnel_target') == 'telegram' else 'your Linkovne link page'
        rules.append('If the conversation naturally calls for moving to ' + target + ', write a short contextual invitation '
                     'in YOUR voice and put [[LINK]] exactly where its URL belongs. Otherwise just converse.')
    elif offer.get('highlights'):
        rules.append('The account URL allowance is currently spent. A relevant invitation MAY point to the existing '
                     'link in your Instagram Highlights. Prefix that reply with [[HIGHLIGHTS]], then formulate it '
                     'naturally in the persona’s voice and the conversation language. No fixed phrase, no URL, '
                     'no invented location and no discussion of quotas or algorithms.')
    elif offer.get('remind'):
        rules.append('This person already has your link in this chat. Only if they ask again or keep pressing, '
                     'prefix [[REMIND]] and briefly refer to that existing message in your own words. Do not send another URL.')
    else:
        rules.append('No invitation or reminder is available for this response. Just answer the conversation.')
    if offer.get('photo'):
        rules.append('One owner-approved ordinary SFW photo is available for this person. If asked for a normal photo '
                     'and it fits, respond ONLY [[PHOTO]]; the server sends the image. Never promise a later photo.')
    else:
        rules.append('No photo is available to send in this reply. Do not offer or promise one.')
    if offer.get('age_unknown'):
        rules.append('Adult status is unconfirmed. Keep ordinary conversation safe. Before an adult-oriented invitation '
                     'becomes relevant, ask their age once naturally, without repeating the question if already pending. '
                     'Never infer adulthood from a profile, purchase intent or flirtation.')
    return '\n\n'.join(rules)


KOMENTAR = """\
PLATFORMA: INSTAGRAM — VEREJNÝ KOMENTÁR
Odpovedáš pod vlastným príspevkom na komentár. Toto NIE JE súkromná správa:
vidí to každý, kto príspevok otvorí, aj Instagram.
- Jedna krátka veta, nanajvýš pár slov a jedno emoji. Žiadny odsek.
- Priateľsky a ľudsky, s vďakou alebo vtipom. NEFLIRTUJ — žiadne narážky,
  žiadne „píš mi", žiadne pozývanie do správ ani inam.
- Nikdy nespomeň Fanvue, OnlyFans, Telegram, odkaz, bio ani peniaze.
- Žiadna adresa, žiadne @meno, žiadne hashtagy.
- Keď je komentár urážlivý, spam alebo reklama, odpovedz presne slovom SKIP.
- Odpovedz v jazyku komentára."""


def komentar_zadanie(komentar: Dict[str, Any]) -> str:
    """Komentár ako správa pre model — s tým, pod čím je."""
    popis = str(komentar.get("caption") or "").strip()
    kto = str(komentar.get("username") or "niekto")
    text = str(komentar.get("text") or "").strip()
    pod = f"Pod tvojím príspevkom „{popis[:200]}“" if popis else "Pod tvojím príspevkom"
    return f"{pod} napísal {kto} komentár:\n{text}"


def smie_pozvat(user: Dict[str, Any], pocet_sprav: int) -> bool:
    """Legacy display helper. Actual invitation permission comes from transactional limits."""
    kolko = int(user.get("pointed_count") or 0)
    return kolko < MAX_POZVANI and (kolko == 0 or pocet_sprav >= ODSTUP_SPRAV * kolko)
