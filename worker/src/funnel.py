"""Stavový automat funnelu. Čisté funkcie — bez I/O, plne testovateľné.

Stavy: cold → warm → link_sent → converted
Pravidlá o linku sú vynútené tu, nie promptom — model ich nemôže obísť.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

COLD = "cold"
WARM = "warm"
LINK_SENT = "link_sent"
CONVERTED = "converted"

STAGES = (COLD, WARM, LINK_SENT, CONVERTED)

# Signály záujmu o obsah / o ňu — SK, CZ, EN.
_INTEREST_PATTERNS = (
    r"\bfot(k|ky|ku|ečk)",
    r"\bpic(s|ture)?\b",
    r"\bvideo",
    r"\bobsah\b",
    r"\bcontent\b",
    r"\bpos(l|el)i\b",
    r"\bsend\b",
    r"\bexklu[zs]iv",
    r"\bnud",
    r"\bsexy\b",
    r"\bkras(n|na|ne)",
    r"\bbeautiful\b",
    r"\bgorgeous\b",
    r"\bkolko\b|\bkoľko\b|\bhow much\b",
    r"\bcena\b|\bprice\b|\bplat(it|im)\b|\bpay\b",
    r"\bfanvue\b|\bonlyfans\b|\bof\b",
    r"\bprivat|\bprivate\b",
    r"\bviac\b|\bmore\b",
)
_INTEREST_RE = re.compile("|".join(_INTEREST_PATTERNS), re.IGNORECASE)

_PAID_PATTERNS = (
    r"\bzaplatil\b|\bzaplatila\b|\bpaid\b|\bsubscribed\b",
    r"\bpredplatil\b|\bsom tam\b|\bjoined\b",
)
_PAID_RE = re.compile("|".join(_PAID_PATTERNS), re.IGNORECASE)

# Priamo si pýta odkaz / kde ju nájde — vtedy sa link smie poslať hneď.
_LINK_REQUEST_RE = re.compile(
    r"\b(fanvue|onlyfans|only\s?fans|\bof\b)\b"
    r"|\b(where|kde)\b.{0,25}\b(find|see|nájd|najd|vidi|watch|subscribe)"
    r"|\b(send|posli|pošli|give|daj)\b.{0,15}\b(link|odkaz|profile|page)\b"
    r"|\byour\s+(link|page|profile)\b"
    r"|\bhow\s+(do|can)\s+i\s+(see|get|subscribe)",
    re.IGNORECASE,
)

# Chce explicitný obsah alebo sexuálny chat — vtedy sa navádza na platformu.
_EXPLICIT_RE = re.compile(
    r"\bnude?s?\b|\bnaked\b|\btits?\b|\bboobs?\b|\bass\b|\bpussy\b|\bdick\b|\bcock\b"
    r"|\bhorny\b|\bsext(ing)?\b|\bcum\b|\bfuck\b|\bsuck\b|\bsex\b"
    r"|\bexclusive\b|\bspicy\b|\bnsfw\b|\bonly\s?for\s?me\b"
    r"|\bshow\s+me\s+(more|your)\b|\bsend\s+(nudes?|pics?|photos?)\b"
    r"|\bwanna\s+see\b|\bwant\s+to\s+see\s+(more|you)\b",
    re.IGNORECASE,
)


def detect_interest(text: str) -> bool:
    """Prejavil užívateľ záujem o obsah alebo o ňu?"""
    return bool(_INTEREST_RE.search(text or ""))


def detect_paid_claim(text: str) -> bool:
    """Tvrdí užívateľ, že už zaplatil / je predplatiteľ?"""
    return bool(_PAID_RE.search(text or ""))


# Predstavenie sa. Meno sa ukladá do DB, aby sa naň už nikdy nepýtala.
_NAME_PATTERNS = (
    r"\bmy\s+name\s*(?:is|'s)\s+([A-Za-z][a-z'\-]{1,14})",
    r"\bname'?s\s+([A-Za-z][a-z'\-]{1,14})",
    r"\bcall\s+me\s+([A-Za-z][a-z'\-]{1,14})",
    r"\bi'?m\s+([A-Za-z][a-z'\-]{1,14})\b",
    r"\bim\s+([A-Za-z][a-z'\-]{1,14})\b",
    r"\bit'?s\s+([A-Za-z][a-z'\-]{1,14})\s+(?:here|btw)",
    r"\bthis\s+is\s+([A-Za-z][a-z'\-]{1,14})\b",
)
_NAME_RES = tuple(re.compile(p, re.IGNORECASE) for p in _NAME_PATTERNS)

# „im good", „im from ohio" — toto nie sú mená.
_NOT_NAMES = {
    "good", "great", "fine", "ok", "okay", "well", "here", "new", "from", "just",
    "bored", "horny", "sorry", "back", "looking", "trying", "gonna", "going",
    "not", "so", "very", "really", "still", "always", "single", "married", "older",
    "young", "curious", "interested", "into", "down", "free", "busy", "tired",
    "drunk", "high", "happy", "sad", "lonely", "the", "and", "but", "with", "your",
    "you", "him", "her", "guy", "man", "dude", "male", "female", "years", "old",
    "in", "at", "on", "up", "out", "off", "too", "also", "sure", "yes", "no",
    "nice", "cool", "hot", "big", "small", "rich", "poor", "hungry", "thinking",
    "wondering", "asking", "wanting", "hoping", "waiting", "watching", "working",
}


def extract_name(text: str) -> str:
    """Vytiahne meno, keď sa predstaví. Prázdny string, keď sa nepredstavil."""
    for pattern in _NAME_RES:
        match = pattern.search(text or "")
        if not match:
            continue
        candidate = match.group(1).strip("'-")
        if len(candidate) < 2 or candidate.lower() in _NOT_NAMES:
            continue
        return candidate[:1].upper() + candidate[1:].lower()
    return ""


_ASKS_NAME_RE = re.compile(
    r"\bwhat'?s?\s+your\s+name\b"
    r"|\bwhat\s+should\s+i\s+call\s+(you|u)\b"
    r"|\bwho\s+am\s+i\s+(talking|texting)\s+to\b"
    r"|\byour\s+name\s*\?"
    r"|\bdo\s+(you|u)\s+have\s+a\s+name\b",
    re.IGNORECASE,
)


def asks_for_name(text: str) -> bool:
    """Spýtala sa práve na meno? Aby sa to už nezopakovalo."""
    return bool(_ASKS_NAME_RE.search(text or ""))


def detect_link_request(text: str) -> bool:
    """Pýta si odkaz alebo sa priamo pýta, kde ju nájde."""
    return bool(_LINK_REQUEST_RE.search(text or ""))


def detect_explicit_interest(text: str) -> bool:
    """Chce explicitný obsah alebo sexuálny chat."""
    return bool(_EXPLICIT_RE.search(text or ""))


def next_stage(user: Dict[str, Any], incoming_text: str) -> str:
    """Vypočíta nový stage po prijatí správy. `msg_count` už zahŕňa túto správu."""
    stage = user.get("funnel_stage") or COLD
    if user.get("paid"):
        return CONVERTED
    if stage in (LINK_SENT, CONVERTED):
        return stage
    if stage == COLD:
        warm_enough = int(user.get("msg_count") or 0) >= 3
        if warm_enough or detect_interest(incoming_text):
            return WARM
    return stage


def can_send_link(
    user: Dict[str, Any],
    now: datetime,
    min_messages: int,
    cooldown_hours: int,
    max_pushes: int,
    fast_track: bool = False,
) -> bool:
    """Smie AI v tejto odpovedi ponúknuť odkaz na platformu?

    `fast_track` = sám si pýta odkaz alebo chce explicitný obsah. Vtedy sa
    preskočí podmienka „aspoň N správ a fáza warm“ — nemá zmysel držať pred
    ním odkaz, keď oň práve žiada. Cooldown a strop pushov platia vždy.
    """
    if user.get("paid") or (user.get("funnel_stage") or COLD) == CONVERTED:
        return False
    if not fast_track:
        if (user.get("funnel_stage") or COLD) == COLD:
            return False
        if int(user.get("msg_count") or 0) < min_messages:
            return False
    if int(user.get("link_push_count") or 0) >= max_pushes:
        return False
    last = _parse_ts(user.get("link_sent_at"))
    if last and now - last < timedelta(hours=cooldown_hours):
        return False
    return True


def hot_and_stuck(user: Dict[str, Any], explicit_now: bool) -> bool:
    """Odkaz už má, stále tlačí na explicitné veci a stále neprešiel.

    Toto je koniec bežného funnelu: odkaz dostal, pripomenutie dostal, a aj
    tak sa nepohol. Ďalšia zmienka o stránke ho už len otravuje — jediné, čo
    v takej chvíli ešte funguje, je dať mu ochutnať to, po čom prišiel.
    """
    if user.get("paid") or (user.get("funnel_stage") or COLD) == CONVERTED:
        return False
    return bool(explicit_now) and int(user.get("link_push_count") or 0) > 0


def stage_after_link(user: Dict[str, Any]) -> str:
    """Stage po tom, čo odpoveď skutočne obsahovala odkaz."""
    if user.get("paid"):
        return CONVERTED
    return LINK_SENT


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# Ako často smie pripomenúť už poslaný odkaz. Bez stropu ho spomenula v každej
# jednej odpovedi a celý chat vyzeral ako reklama.
LINK_REMINDER_GAP = 5

_MENTIONED_RE = re.compile(
    r"\b(my page|the link|link higher|on my page|fanvue|up there|higher up)\b",
    re.IGNORECASE,
)


def recently_reminded(rows, window: int = LINK_REMINDER_GAP) -> bool:
    """Spomenula odkaz alebo stránku v posledných `window` svojich správach?

    Berie sa to z archívu, takže na to netreba ďalší stĺpec v databáze a
    prežije to aj restart.
    """
    jej = [r for r in rows or [] if r.get("role") == "assistant"]
    return any(_MENTIONED_RE.search(r.get("content") or "") for r in jej[-window:])


# Kedy má prestať čakať, kým sa spýta sám.
#
# Reálny prípad: 52 správ, otvoril sa jej o podvádzajúcej bývalej aj o samote,
# napísal „glad you reached out to me today" — a o stránke nepadlo ani slovo,
# lebo pravidlo znelo „spomeň ju, až keď sa spýta". Takýto človek sa nespýta
# nikdy, on hľadá blízkosť. Niekto ho musí naviesť.
#
# Prvý deň sa ale nenavádza vôbec. Kto dostane pozvánku v deň zoznámenia, vie,
# že bol cieľ; kto ju dostane na druhý deň, už má dôvod prísť. Meria sa to
# preto v dňoch, nie v počte správ — dvadsať správ za hodinu ešte neznamená nič.
LEAD_AFTER_HOURS = 20
# Prvých dvadsať správ je čisté spoznávanie — ako sa má, čo robí, aký mal deň.
# Presne tie nudné veci, ktoré si píšu skutoční ľudia. Kým to neprejde, na
# stránku sa netlačí vôbec; predtým sa začínalo po dvanástich a bolo to skoro.
LEAD_MIN_MESSAGES = 20


def should_lead(user: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Má už začať sama smerovať rozhovor k stránke?"""
    if user.get("paid") or (user.get("funnel_stage") or COLD) == CONVERTED:
        return False
    if int(user.get("link_push_count") or 0) > 0:
        return False
    if int(user.get("msg_count") or 0) < LEAD_MIN_MESSAGES:
        return False

    zaciatok = _parse_ts(user.get("created_at"))
    if zaciatok is None:
        return False
    hodin = ((now or datetime.now(timezone.utc)) - zaciatok).total_seconds() / 3600
    return hodin >= LEAD_AFTER_HOURS


# „video call", „facetime", „lets meet", „cam" — chce hovor alebo stretnutie.
_WANTS_CALL_RE = re.compile(
    r"\b(video\s*(call|chat)|facetime|face\s*time|skype|zoom|whatsapp\s*call)\b"
    r"|\b(call|ring|phone)\s+(me|u|you|us)\b"
    r"|\b(let'?s|wanna|want\s+to|we\s+should)\s+(call|talk\s+on\s+the\s+phone|meet|meet\s*up|hang\s*out)\b"
    r"|\bcan\s+(we|i)\s+(call|facetime|meet|see\s+you\s+in\s+person)\b"
    r"|\b(meet|see)\s+(u|you)\s+(in\s+person|irl|for\s+real)\b"
    r"|\bon\s+cam\b|\bwebcam\b",
    re.IGNORECASE,
)


def wants_call(text: str) -> bool:
    """Pýta si videohovor, telefonát alebo stretnutie naživo."""
    return bool(_WANTS_CALL_RE.search(text or ""))
