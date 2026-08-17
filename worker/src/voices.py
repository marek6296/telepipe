"""Hlasovky — kedy poslať nahrávku namiesto textu.

Hlasovka je najsilnejšia vec, ktorú vie poslať: dokazuje, že je skutočná.
Práve preto sa nesmie posielať náhodne. Pravidlá sú v kóde, nie v prompte:

  * tá istá nahrávka nikdy dvakrát tomu istému človeku
  * pošle sa len vtedy, keď jej prepis naozaj sedí na to, čo sa práve deje —
    nie „nejaká hlasovka, nech je"
  * musí sedieť aj denná doba, rovnako ako pri fotkách
  * jedna za rozhovor stačí, nie je to podcast

Grok dostane presný prepis nahrávky, takže vie, čo v nej zaznie, a text okolo
nej tomu prispôsobí. Nikdy ho ale do chatu nenapíše.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

# Minimálny odstup medzi hlasovkami jednému človeku.
COOLDOWN_MIN = 180

# To isté pre hlasovku vyrobenú na mieru. Kratšie, lebo sa neopakuje —
# zakaždým hovorí niečo iné, takže nepôsobí ako prehrávanie zo zásoby.
GENERATED_COOLDOWN_MIN = 45

# Koľko slov z prepisu musí sedieť na rozhovor, aby to nebola náhoda.
MIN_ZHODA = 2

_STOP = {
    "a", "the", "and", "is", "are", "you", "u", "i", "im", "to", "of", "in",
    "it", "its", "me", "my", "your", "so", "just", "that", "this", "for",
    "on", "at", "be", "do", "dont", "no", "yes", "ok", "okay", "we", "he",
    "she", "they", "was", "were", "will", "would", "can", "cant", "with",
}


# Slová, ktoré prejdú cez _STOP, ale o téme nehovoria nič. Zhoda výhradne na
# nich je náhoda: „today was fine" a nahrávka o posilňovni majú spoločné
# „today", a to nie je dôvod poslať niekomu hlas.
#
# Prečo to vôbec treba: `fits` píše Marek po slovensky, kým konverzácia beží
# po anglicky, takže sa `fits` v praxi nikdy netrafí a z celého skóre ostane
# holý prekryv s prepisom. Bez tohto filtra ho vytiahnu bežné slová.
_WEAK = {
    "today", "tomorrow", "yesterday", "day", "days", "time", "good", "bad",
    "nice", "well", "thing", "things", "really", "much", "more", "want",
    "need", "know", "think", "feel", "like", "love", "get", "got", "going",
    "come", "back", "right", "sure", "sorry", "hope", "maybe", "still",
    "been", "here", "there", "all", "any", "one", "two", "now", "then",
    "very", "too", "also", "even", "how", "why", "what", "when", "who",
    "yeah", "yes", "haha", "lol", "omg", "hey", "hello",
}


def _slova(text: str) -> set:
    return {
        w for w in re.findall(r"[a-z']+", (text or "").lower())
        if len(w) > 2 and w not in _STOP
    }


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def cooldown_passed(user: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    return _odstup(user, COOLDOWN_MIN, now)


def generated_cooldown_passed(
    user: Dict[str, Any], now: Optional[datetime] = None
) -> bool:
    """Odstup pre hlasovku vyrobenú na mieru.

    Kratší než pri nahratej knižnici: generovaná sedí na to, čo sa práve
    povedalo, takže sa smie ozvať častejšie než stále ten istý súbor. Ale
    nejaký odstup tam byť MUSÍ — bez neho sa pri každej odpovedi spustila
    výnimka „vypýtal si ju" a nahrávky chodili jedna za druhou.
    """
    return _odstup(user, GENERATED_COOLDOWN_MIN, now)


def _odstup(user: Dict[str, Any], minut: int, now: Optional[datetime]) -> bool:
    last = _parse(user.get("last_voice_at"))
    if last is None:
        return True
    return (now or datetime.now(timezone.utc)) - last >= timedelta(minutes=minut)


def playable(voice: Dict[str, Any]) -> bool:
    """Má táto nahrávka vôbec súbor?

    V knižnici sa dá založiť riadok s prepisom a bez nahratého súboru — a
    presne to sa aj stalo. Bez tejto kontroly ho výber pokojne zvolí,
    sťahovanie potom zlyhá a klientovi neodíde nič. Pri nočnej rozlúčke to
    bolo obzvlášť zlé: hlasovka JE tá správa, takže sa človeku namiesto
    rozlúčky ozvalo ticho — a modelka sa nato uspala do rána.
    """
    return bool((voice.get("url") or "").strip())


def scores(
    voice: Dict[str, Any],
    conversation: str,
    part_of_day: str,
    wants_cta: bool,
) -> int:
    """Ako veľmi táto nahrávka sedí na to, čo sa práve deje. 0 = neposielať."""
    if not voice.get("active", True) or not playable(voice):
        return 0

    parts = voice.get("parts") or []
    if parts and part_of_day not in parts:
        return 0

    if voice.get("is_cta"):
        # Pozvánka na stránku má zmysel len vtedy, keď o ňu ide.
        return 5 if wants_cta else 0
    if wants_cta:
        return 0

    slova = _slova(conversation)
    z_prepisu = _slova(voice.get("transcript", "")) & slova
    z_popisu = _slova(voice.get("fits", "")) & slova
    # Aspoň jedno zo zhodných slov musí niesť tému. Inak by hlasovku o
    # posilňovni odpálilo spoločné „today" a „good".
    if not (z_prepisu | z_popisu) - _WEAK:
        return 0
    zhoda = len(z_prepisu) + len(z_popisu) * 2
    return zhoda if zhoda >= MIN_ZHODA else 0


def pick(
    library: Sequence[Dict[str, Any]],
    already_sent_ids: Sequence[int],
    conversation: str,
    part_of_day: str,
    wants_cta: bool = False,
    rng: Optional[random.Random] = None,
) -> Optional[Dict[str, Any]]:
    """Najlepšie sediaca nahrávka, ktorú tento človek ešte nepočul.

    None = neposielať nič. To je úplne bežný a správny výsledok — hlasovka
    má odísť len vtedy, keď naozaj sadne.
    """
    seen = set(already_sent_ids or ())
    hodnotene: List[tuple] = []
    for voice in library:
        if voice["id"] in seen:
            continue
        skore = scores(voice, conversation, part_of_day, wants_cta)
        if skore:
            hodnotene.append((skore, voice))
    if not hodnotene:
        return None

    najlepsie = max(s for s, _ in hodnotene)
    finalisti = [v for s, v in hodnotene if s == najlepsie]
    return (rng or random).choice(finalisti)


def record_seconds(voice: Dict[str, Any], rng: Optional[random.Random] = None) -> float:
    """Ako dlho má svietiť „nahráva hlasovku“.

    Pevných 3–9 s znamenalo, že dvadsaťsekundovú nahrávku „nahrala“ za štyri
    sekundy — a to je na druhej strane vidieť. Dĺžka sa odhaduje z prepisu
    (~2,4 slova za sekundu bežnej reči), takže netreba poznať trvanie súboru.
    """
    slov = len((voice.get("transcript") or "").split())
    odhad = min(max(slov / 2.4, 3.0), 45.0)
    return round((rng or random).uniform(odhad * 0.8, odhad * 1.3), 2)


def describe_for_prompt(voice: Dict[str, Any]) -> str:
    """Čo modelu povieme o nahrávke, ktorú práve posiela."""
    bits = [f"v nahrávke hovoríš: „{voice.get('transcript') or ''}“"]
    fits = (voice.get("fits") or "").strip()
    if fits:
        bits.append(f"hodí sa keď: {fits}")
    return " · ".join(bits)


# Telegram prehrá ako hlasovku (s vlnkou a rýchlosťou) len OGG/Opus. Čokoľvek
# iné pristane ako priložený zvukový súbor, čo vyzerá ako automat.
_OGG = (".ogg", ".oga", ".opus")


def needs_conversion(url: str) -> bool:
    """Treba nahrávku pred odoslaním previesť na OGG/Opus?"""
    return not (url or "").split("?")[0].lower().endswith(_OGG)


# „posli hlasovku", „say it", „let me hear u" — pýta si nahrávku.
_WANTS_VOICE_RE = re.compile(
    r"\b(send|post|record|do)\s+(me\s+)?(a\s+|one\s+|another\s+)?"
    r"(voice|voice\s*(message|note)|audio)\b"
    r"|\bvoice\s*(message|note)\s*\?"
    r"|\b(let\s+me|wanna|want\s+to|i\s+want\s+to)\s+hear\s+(u|you|your\s+voice)\b"
    r"|\bsay\s+(it|something)\s+(out\s+loud|for\s+me)\b"
    r"|\bhow\s+do\s+(u|you)\s+sound\b"
    r"|\bcan\s+i\s+hear\s+(u|you)\b",
    re.IGNORECASE,
)


def wants_voice(text: str) -> bool:
    return bool(_WANTS_VOICE_RE.search(text or ""))


def night_voice(
    library: Sequence[Dict[str, Any]],
    already_sent_ids: Sequence[int],
) -> Optional[Dict[str, Any]]:
    """Nahrávka na dobrú noc, ak je nahratá a tento človek ju ešte nepočul.

    Keď odíde, text sa už nepíše — hlasovka JE to rozlúčenie. Ak nahratá nie
    je, vráti None a modelka sa rozlúči normálne textom ako doteraz.
    """
    seen = set(already_sent_ids or ())
    for voice in library:
        if voice.get("slot") != "night" or voice["id"] in seen:
            continue
        if not playable(voice):
            continue  # riadok bez súboru — rozlúč sa radšej textom
        return voice
    return None
