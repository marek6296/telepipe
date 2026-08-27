"""Kontext od majiteľa — „toto je Jason z Instagramu, už sme si písali".

PREČO TO EXISTUJE. Majiteľ si s niekým píše inde (Instagram, iná appka) a
dotiahne ho na Telegram. Modelka o tom nevie nič, takže ho privíta ako úplne
cudzieho človeka — a pre niekoho, kto si „s ňou" týždeň písal, je to prvá vec,
ktorá nesedí. Jedna veta od majiteľa to spraví celé.

JE TO INÁ VEC NEŽ `summary` A `facts`. Tie si modelka odvodzuje z konverzácie,
takže pri prvej správe sú prázdne. Toto je vklad zvonku a platí hneď.

VŽDY SA UKLADÁ PO ANGLICKY. Majiteľ píše po slovensky, chat beží po anglicky
a poznámka ide do promptu medzi ostatné fakty — keby tam ostala slovenčina,
ťahala by odpoveď k slovenčine spolu so sebou.
"""
from __future__ import annotations

from typing import Any

# Dlhšia poznámka prestáva byť kontextom a stáva sa scenárom. Toto má povedať,
# KTO to je a odkiaľ sa poznajú, nie ako sa má správať.
MAX_ZNAKOV = 400

_SYSTEM = (
    "You turn a note from an account owner into a short third-person fact "
    "sheet for her chat assistant.\n"
    "The note says who this person is and where they know each other from. It "
    "may be written in any language — always answer in ENGLISH.\n"
    "Rules:\n"
    "- Keep every fact. Drop nothing, invent nothing.\n"
    "- Third person about the fan and about her: „He is Jason from Instagram. "
    "They have been talking there for two weeks.\"\n"
    "- Plain statements, no instructions, no advice on how to reply.\n"
    "- Two or three short sentences at most.\n"
    "Answer with the sentences only — no preface, no quotes, no bullet points."
)


def orez(text: str) -> str:
    """Vstup od majiteľa do rozumného tvaru."""
    return " ".join(str(text or "").split())[:MAX_ZNAKOV]


async def do_anglictiny(llm: Any, note: str) -> str:
    """Poznámku od majiteľa na anglický fakt. Pri zlyhaní vráti pôvodný text.

    Zlyhať sa tu smie: poznámka v slovenčine je stále lepšia než žiadna. Model
    z nej vytiahne zmysel aj tak, len ju to ťahá k slovenčine — a to je menšia
    škoda než privítať známeho ako cudzieho.
    """
    cisty = orez(note)
    if not cisty:
        return ""
    try:
        out = await llm.structured(_SYSTEM, cisty, max_tokens=300, temperature=0.2)
    except Exception:  # noqa: BLE001 — radšej slovenská poznámka než žiadna
        return cisty
    hotovo = orez(out)
    return hotovo or cisty


def blok(note: str) -> str:
    """Sekcia do promptu. Prázdna poznámka = prázdny reťazec."""
    cisty = orez(note)
    if not cisty:
        return ""
    return (
        "TOHTO ČLOVEKA UŽ POZNÁŠ\n"
        f"{cisty}\n"
        "Toto vieš odinakiaľ, nie z tohto chatu — nepýtaj sa na to, čo tu už "
        "stojí, a netvár sa, že ho vidíš prvýkrát.\n"
        "Zároveň to NEVYSYP hneď v prvej správe a nevymenúvaj, čo o ňom vieš. "
        "Píš ako človek, ktorý toho druhého pozná: normálne, akoby ste "
        "nadviazali tam, kde ste prestali."
    )
