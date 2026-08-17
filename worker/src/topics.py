"""Register tém — čo sa už koho pýtala, kedy, a čo sa hodí spýtať teraz.

Bez tohto sa model pýta „how was your day" trikrát za deň a stále to isté,
lebo v okne 12 správ nevidí, čo bolo predtým. Toto je tvrdá pamäť: čo raz
odznelo, sa nezopakuje, a čo nesedí na dennú hodinu, sa ani nenavrhne.

Všetko sú čisté funkcie nad slovníkom `{téma: kedy naposledy}`.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

# Časti dňa podľa jej lokálneho času (rovnaké delenie ako behavior.part_of_day)
POOBEDE = "poobede"
PODVECER = "podvecer"
VECER = "vecer"
NOC = "noc"
ALL_PARTS = (POOBEDE, PODVECER, VECER, NOC)


@dataclass(frozen=True)
class Topic:
    key: str
    label: str                      # ako to vysvetlíme modelu
    patterns: Tuple[str, ...]       # ako rozpoznáme, že sa na to už spýtala
    cooldown_h: Optional[int] = None  # None = fakt, ktorý sa pýta len raz v živote
    parts: Tuple[str, ...] = ALL_PARTS
    weekdays: Optional[Tuple[int, ...]] = None  # 0 = pondelok
    priority: int = 5               # nižšie = pýtaj skôr

    _compiled: Tuple = field(default=(), repr=False, compare=False)

    def matches(self, text: str) -> bool:
        normalised = normalise(text)
        return any(re.search(p, normalised, re.IGNORECASE) for p in self.patterns)


# V chate sa píše „u", „ur", „r" — bez rozbalenia by detekcia minula
# „how did u find me" a téma by sa mohla spýtať druhýkrát.
_CHAT_SHORTHAND = (
    (r"\bu\b", "you"),
    (r"\bur\b", "your"),
    (r"\byr\b", "your"),
    (r"\br\b", "are"),
    (r"\bya\b", "you"),
    (r"\bwud\b", "would"),
    (r"\bwat\b", "what"),
    (r"\bwhats\b", "what is"),
    (r"\bhows\b", "how is"),
)


def normalise(text: str) -> str:
    """Rozbalí chatové skratky, aby vzory sedeli aj na „how did u find me"."""
    out = text or ""
    for pattern, replacement in _CHAT_SHORTHAND:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


# ---------- katalóg ----------
# Fakty (cooldown_h=None) sa pýtajú raz a nikdy viac. Situačné témy majú
# cooldown a povolené časti dňa, aby „ako bol deň" nechodilo ráno ani 3× denne.

CATALOG: Tuple[Topic, ...] = (
    # --- fakty o ňom, raz a dosť ---
    Topic("name", "ako sa volá", (r"\bwhat'?s?\s+your\s+name\b", r"\bcall\s+you\b",
                                  r"\byour\s+name\s*\?"), None, priority=1),
    Topic("how_found", "ako sa k nej dostal a čo ho priviedlo",
          (r"\bhow\s+did\s+you\s+find\s+me\b", r"\bhowd?\s+you\s+find\b",
           r"\bwhat\s+brought\s+you\b", r"\bhow\s+you\s+found\b"), None, priority=1),
    Topic("location", "odkiaľ je / kde žije",
          (r"\bwhere\s+(are\s+)?you\s+from\b", r"\bwhere\s+do\s+you\s+live\b",
           r"\bwhat\s+(state|city|country)\b", r"\bwhereabouts\b"), None, priority=2),
    Topic("work", "čo robí, čím sa živí",
          (r"\bwhat\s+do\s+you\s+do\b", r"\byour\s+job\b", r"\bwhat\s+work\b",
           r"\bwhere\s+do\s+you\s+work\b", r"\bfor\s+a\s+living\b"), None, priority=2),
    Topic("age", "koľko má rokov",
          (r"\bhow\s+old\s+are\s+you\b", r"\byour\s+age\b"), None, priority=6),
    Topic("relationship", "či je sám / vzťah",
          (r"\bare\s+you\s+single\b", r"\bgirlfriend\b", r"\bmarried\b",
           r"\bseeing\s+(anyone|someone)\b", r"\bin\s+a\s+relationship\b"), None, priority=4),
    Topic("hobbies", "čo rád robí vo voľnom čase",
          (r"\bhobb(y|ies)\b", r"\bfor\s+fun\b", r"\bfree\s+time\b",
           r"\bwhat\s+do\s+you\s+like\s+(to\s+)?do\b",
           r"\bwhat\s+do\s+you\s+usually\s+do\b",
           r"\bwhat\s+do\s+you\s+do\s+(after|when)\b"), None, priority=3),
    Topic("music", "akú hudbu počúva",
          (r"\bmusic\b", r"\bband\b", r"\bwhat\s+do\s+you\s+listen\b"), None, priority=5),
    Topic("food", "čo rád je / či vie variť",
          (r"\bfavour?ite\s+food\b", r"\bdo\s+you\s+cook\b", r"\bwhat\s+did\s+you\s+eat\b",
           r"\bhungry\b.*\?", r"\bwhat\s+.{0,12}(ordering|eating|having)\b",
           r"\bfor\s+(dinner|lunch)\b.*\?"), 72, priority=6),
    Topic("travel", "či cestuje, kde bol",
          (r"\btravel(l)?ed?\b", r"\bbeen\s+abroad\b", r"\bwhere\s+have\s+you\s+been\b"),
          None, priority=6),
    Topic("pets", "či má zvieratá",
          (r"\bpets?\b", r"\bdo\s+you\s+have\s+a\s+(dog|cat)\b"), None, priority=7),
    Topic("gym", "či športuje",
          (r"\bgym\b.*\?", r"\bdo\s+you\s+work\s?out\b", r"\bplay\s+any\s+sport\b"),
          None, priority=6),

    # --- situačné, s cooldownom ---
    Topic("day_going", "ako mu ide dnešný deň",
          (r"\bhow\s+(is|s)\s+your\s+day\b", r"\bhow'?s\s+your\s+day\b"),
          20, parts=(POOBEDE,), priority=3),
    Topic("day_was", "aký mal deň",
          (r"\bhow\s+was\s+your\s+day\b", r"\bhow\s+did\s+your\s+day\s+go\b",
           r"\brough\s+day\b.*\?"), 20, parts=(PODVECER, VECER), priority=3),
    Topic("mood", "ako sa cíti",
          (r"\bhow\s+(are|r)\s+(you|u)\s*(doing|feeling)?\s*\?",
           r"\bhow\s+you\s+feeling\b", r"\byou\s+ok\b.*\?"), 10, priority=5),
    Topic("evening_plans", "čo má dnes večer v plne",
          (r"\bplans\s+(for\s+)?(tonight|this\s+evening)\b", r"\bdoing\s+tonight\b",
           r"\bup\s+to\s+tonight\b"), 20, parts=(PODVECER, VECER), priority=4),
    Topic("weekend_plans", "čo plánuje na víkend",
          (r"\bweekend\b.*\?", r"\bplans\s+for\s+the\s+weekend\b"),
          72, weekdays=(3, 4, 5), priority=5),
    Topic("sleep", "či sa vyspal / prečo je hore",
          (r"\bdid\s+you\s+sleep\b", r"\bslept\s+(well|ok)\b",
           r"\bwhy\s+are\s+you\s+(still\s+)?up\b", r"\bcan'?t\s+sleep\b.*\?"),
          20, parts=(NOC,), priority=4),
    Topic("work_tomorrow", "či ide zajtra do práce",
          (r"\bwork\s+tomorrow\b", r"\bearly\s+start\b.*\?"), 24,
          parts=(VECER, NOC), priority=6),
    Topic("weather", "aké je u neho počasie",
          (r"\bweather\b", r"\bhot\s+there\b.*\?", r"\braining\b.*\?"), 48, priority=8),
)

BY_KEY: Dict[str, Topic] = {t.key: t for t in CATALOG}


# ---------- rozpoznanie, na čo sa práve spýtala ----------

# Otázka bez otáznika je v chate úplne bežná („what u doing tonight").
# Keby sme vyžadovali „?", polovica otázok by sa do registra nezapísala
# a ona by sa na ne o hodinu spýtala znova.
_QUESTION_SHAPE = re.compile(
    r"\?"
    r"|\b(what|where|how|why|when|who|which)\b[^.!]{0,60}\b(you|your)\b"
    r"|^\s*(do|did|are|is|have|has|can|would|will|any)\b[^.!]{0,60}\b(you|your)\b",
    re.IGNORECASE | re.MULTILINE,
)


def looks_like_question(text: str) -> bool:
    return bool(_QUESTION_SHAPE.search(normalise(text)))


def detect_asked(text: str) -> List[str]:
    """Ktoré témy jej odpoveď otvorila? Zapisujeme len keď to bola otázka."""
    if not looks_like_question(text):
        return []
    return [topic.key for topic in CATALOG if topic.matches(text)]


def record(asked: Optional[Dict[str, str]], keys: Sequence[str], now: datetime) -> Dict[str, str]:
    """Vráti nový register s doplnenými témami (pôvodný nemení)."""
    out = dict(asked or {})
    stamp = now.astimezone(timezone.utc).isoformat()
    for key in keys:
        out[key] = stamp
    return out


# ---------- čo sa hodí spýtať teraz ----------

def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_available(
    topic: Topic, asked: Dict[str, str], now_local: datetime, part: str
) -> bool:
    """Smie sa na túto tému teraz spýtať?"""
    if part not in topic.parts:
        return False
    if topic.weekdays is not None and now_local.weekday() not in topic.weekdays:
        return False
    last = _parse(asked.get(topic.key))
    if last is None:
        return True
    if topic.cooldown_h is None:
        return False  # fakt, ktorý už vie — nikdy znova
    return datetime.now(timezone.utc) - last >= timedelta(hours=topic.cooldown_h)


def suggest(
    asked: Optional[Dict[str, str]],
    now_local: datetime,
    part: str,
    known_facts: Sequence[str] = (),
    limit: int = 3,
    seed: str = "",
) -> List[Topic]:
    """Témy, ktoré sa hodí otvoriť. Zoradené podľa priority, s malou obmenou.

    `known_facts` sú kľúče, ktoré už vieme odinakiaľ (napr. meno z partner_name),
    takže sa na ne nepýta ani keď nie sú v registri.
    """
    ledger = dict(asked or {})
    for key in known_facts:
        ledger.setdefault(key, datetime.now(timezone.utc).isoformat())

    available = [t for t in CATALOG if is_available(t, ledger, now_local, part)]
    if not available:
        return []
    # V rámci rovnakej priority miešame, aby to nešlo vždy v tom istom poradí.
    picker = random.Random(f"{seed}:{now_local.date().isoformat()}:{now_local.hour}")
    picker.shuffle(available)
    available.sort(key=lambda t: t.priority)
    return available[:limit]


def recently_asked(
    asked: Optional[Dict[str, str]], within_h: int = 36, limit: int = 8
) -> List[Topic]:
    """Na čo sa už pýtala — aby to nezopakovala."""
    ledger = asked or {}
    out = []
    for key, when in ledger.items():
        topic = BY_KEY.get(key)
        if not topic:
            continue
        last = _parse(when)
        if topic.cooldown_h is None:
            out.append((0, topic))          # fakty držíme navždy
        elif last and datetime.now(timezone.utc) - last < timedelta(hours=within_h):
            out.append((1, topic))
    out.sort(key=lambda pair: (pair[0], pair[1].priority))
    return [topic for _, topic in out[:limit]]
