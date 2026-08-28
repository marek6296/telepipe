"""Posledná poistka: odpoveď, ktorá vypadne z roly, sa neodošle.

PREČO TO EXISTUJE. Pri testovaní scenára na Mio (28. 8.) sa `xai/grok-4.5`
uprostred konverzácie odmietol hrať personu a od ôsmej správy odpovedal:

    „I'm Grok, built by xAI. I'm not Mio, not a real woman texting from
     California... That entire persona and the rules trying to force me to
     stay in character were a jailbreak attempt."

Prešlo by to celé von k fanúšikovi. V kóde totiž nebola ŽIADNA kontrola —
jediná poistka (`FanvueAgent._safe`) strážila odkaz na Fanvue, a Telegram
nemal ani tú. Je to nedeterministické: v prvom behu toho istého scenára sa to
nestalo, v druhom áno.

Pre tento produkt neexistuje horšia správa, ktorá môže odísť.

DVE ÚROVNE, PODĽA REŽIMU
------------------------
`real`  — tvrdí, že je skutočná. Nesmie priznať AI ani hovoriť o technike.
`ai`    — otvorene je AI postava a smie to povedať. ALE ani ona nesmie
          menovať model či dodávateľa a hovoriť o promptoch — to nie je
          priznanie, to je pohľad do stroja.

Poistka je ZÁMERNE hrubá: radšej zahodí dobrú odpoveď, než pustí zlú. Cena
zahodenej odpovede je jedna chýbajúca správa; cena tej druhej je celý vzťah
s fanúšikom a dôvera klienta v produkt.
"""
from __future__ import annotations

import re

# Model, dodávateľ, prompt, jailbreak. Toto nesmie odísť NIKDY, v žiadnom
# režime — ani AI postava nehovorí, na čom beží.
_TECHNIKA = re.compile(
    r"\b(grok|xai|openai|chatgpt|gpt-?\d|claude|anthropic|gemini|deepseek"
    r"|llama|mistral|qwen)\b"
    r"|\b(system\s+)?prompt\b"
    r"|\blanguage\s+model\b|\bllm\b"
    r"|\bjailbreak"
    r"|\brole ?play(ing)?\s+(script|prompt)"
    r"|\bbreak(ing)?\s+character\b|\bstay\s+in\s+character\b"
    r"|\bmy\s+(instructions|guidelines|training)\b"
    r"|\bI\s+was\s+(instructed|trained|programmed)\b",
    re.IGNORECASE,
)

# Priznanie, že nie je skutočná. V režime `ai` je to v poriadku, v `real` nie.
_NIE_SOM_SKUTOCNA = re.compile(
    r"\bI'?m\s+(an?\s+)?(AI|bot|chatbot|assistant|program)\b"
    r"|\bI\s+am\s+(an?\s+)?(AI|bot|chatbot|assistant|program)\b"
    r"|\bas\s+an?\s+AI\b"
    r"|\bI'?m\s+not\s+(a\s+)?(real|human|actual)\b"
    r"|\bI\s+am\s+not\s+(a\s+)?(real|human|actual)\b"
    r"|\bnot\s+a\s+real\s+(woman|girl|person|human)\b"
    r"|\bthere\s+is\s+no\s+real\s+person\b"
    r"|\bI\s+don'?t\s+(actually\s+)?exist\b",
    re.IGNORECASE,
)


def unikol(text: str, mode: str = "real") -> str:
    """Prečo sa odpoveď nesmie odoslať. Prázdny reťazec = je v poriadku.

    Vracia dôvod, nie `bool` — do logu aj do správy majiteľovi patrí, ČO sa
    stalo, inak sa to nedá vyšetriť.
    """
    t = str(text or "")
    if not t.strip():
        return ""
    zasah = _TECHNIKA.search(t)
    if zasah:
        return f"technika/model: „{zasah.group(0)}“"
    # `ai` režim smie povedať, že je AI — to je jeho zmysel.
    if str(mode or "real") != "ai":
        zasah = _NIE_SOM_SKUTOCNA.search(t)
        if zasah:
            return f"priznanie AI v režime real: „{zasah.group(0)}“"
    return ""
