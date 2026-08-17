"""Sudca — posledná kontrola pred odoslaním.

Beží medzi vygenerovaním odpovede a jej odoslaním. Dostane návrh, fakty o ňom
a to, čo o sebe natvrdila, a buď povie OK, alebo rovno prepíše. Chytí to, čo
prompt spoľahlivo neustráži: protirečenie, otázku na už známu vec, a typický
AI prejav.

Dve pravidlá, ktoré sú tu dôležitejšie než presnosť:
  * musí zlyhať OTVORENE — keď sa čokoľvek pokazí, odchádza pôvodný návrh
  * nikdy nesmie odpoveď predĺžiť ani sformalizovať; opravuje, nevylepšuje
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

import similar

log = logging.getLogger(__name__)

_SYSTEM = """\
Si korektor správ, ktoré píše dievča na Telegrame. Dostaneš NÁVRH jej odpovede
a to, čo o sebe a o ňom vie. Tvoja úloha je nájsť len tvrdé chyby.

Chyba je LEN toto:
1. PROTIREČENIE — návrh hovorí niečo iné, než čo už o sebe povedala, alebo iné,
   než čo vie o ňom.
2. ZBYTOČNÁ OTÁZKA — pýta sa na niečo, čo už vie.
3. PREZRADENIE — spomína AI, model, systém, pravidlá, poznámky, „nemôžem".
4. AI PREJAV — dlhá pomlčka, úvodzovky, bodkočiarka, korporátne slová.
5. OPAKOVANIE — hovorí to isté, čo už nedávno napísala. Nemyslí sa tým rovnaké
   slovo, ale rovnaká myšlienka, rovnaký kompliment alebo rovnaká otázka.
   Toto je najčastejšia chyba a najviac prezrádza automat.
6. MIMO OTÁZKY — on sa spýtal na konkrétnu vec a návrh na ňu neodpovedá,
   odbočí alebo odpovie na niečo iné. Keď sa pýta „koľko máš rokov“, musí
   z odpovede zaznieť vek.

NIE JE chyba: preklep, chýbajúci člen, malé písmená, slang, drzosť, flirt,
krátkosť, chýbajúca interpunkcia. Tie tam patria.

Vráť IBA JSON:
{"ok": true}
alebo
{"ok": false, "fixed": "opravená správa", "why": "krátky dôvod"}

Keď opravuješ:
- zmeň LEN to, čo je chybné. Zvyšok nechaj slovo za slovom.
- zachovaj dĺžku, tón, malé písmená aj emoji.
- nikdy nepridávaj vysvetlenia ani ospravedlnenia.
- pri opakovaní povedz tú istú vec INAK, nie dlhšie.
- výsledok musí znieť ako tá istá osoba, nie ako korektor."""


def _json_block(raw: str) -> Optional[Dict[str, Any]]:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# Frázy, ktoré sa v chate opakujú prirodzene a opakovaním nie sú.
_COMMON = frozenset(
    "haha hahaha lol omg yeah yes no ok okay thanks sure right same true nice "
    "good great cool sorry hey hi hello babe honey hun sweetie handsome".split()
)


def _phrases(text: str, size: int = 3) -> set:
    """N-gramy z významových slov — na porovnanie myšlienky, nie znakov."""
    words = [
        w for w in re.findall(r"[a-z']+", (text or "").lower())
        if len(w) > 2 and w not in _COMMON
    ]
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def repeated_phrases(draft: str, her_recent: Sequence[str], size: int = 3) -> List[str]:
    """Čo z návrhu už nedávno napísala — deterministicky, bez modelu.

    Sudca na opakovanie sám o sebe nestačí: musel by si všimnúť, že veta znie
    ako niečo spred desiatich správ, a to je presne to, čo modely prehliadajú.
    Toto mu tie miesta rovno ukáže, takže mu ostáva len ich preformulovať.
    """
    nove = _phrases(draft, size)
    if not nove:
        return []
    stare: set = set()
    for message in her_recent:
        stare |= _phrases(message, size)
    return sorted(nove & stare)[:6]


def build_brief(
    draft: str,
    last_incoming: str,
    fact_sheet: str,
    claims: Sequence[str],
    known_labels: Sequence[str],
    her_recent: Sequence[str] = (),
) -> str:
    parts = [f"NÁVRH JEJ ODPOVEDE:\n{draft}"]
    if last_incoming:
        parts.append(f"ON PRÁVE NAPÍSAL:\n{last_incoming}")
    if fact_sheet:
        parts.append(f"ČO VIE O ŇOM:\n{fact_sheet}")
    if claims:
        parts.append("ČO UŽ O SEBE POVEDALA:\n" + "\n".join(f"- {c}" for c in claims))
    if known_labels:
        parts.append(
            "NA TOTO SA UŽ PÝTAŤ NESMIE:\n" + "\n".join(f"- {label}" for label in known_labels)
        )
    if her_recent:
        parts.append(
            "ČO NEDÁVNO NAPÍSALA (nesmie sa opakovať):\n"
            + "\n".join(f"- {m}" for m in her_recent)
        )
        zhody = repeated_phrases(draft, her_recent)
        if zhody:
            parts.append(
                "POZOR, TOTO UŽ RAZ ZAZNELO — preformuluj to:\n"
                + "\n".join(f"- {z}" for z in zhody)
            )
    return "\n\n".join(parts)


def accept(draft: str, verdict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Rozhodne, čo sa nakoniec odošle. Čistá funkcia — jadro bezpečnosti.

    Pri akejkoľvek pochybnosti vyhráva pôvodný návrh: radšej drobná chyba
    než odpoveď, ktorú prepísal korektor na nepoznanie.
    """
    if not verdict or verdict.get("ok") is True:
        return {"text": draft, "changed": False, "why": ""}

    fixed = str(verdict.get("fixed") or "").strip()
    why = str(verdict.get("why") or "").strip()[:200]
    if not fixed:
        return {"text": draft, "changed": False, "why": why}

    # Oprava, ktorá je dvojnásobne dlhšia, už nie je oprava.
    if len(fixed) > max(len(draft) * 2, len(draft) + 120):
        log.warning("Sudca vrátil príliš dlhú opravu, nechávam pôvodné")
        return {"text": draft, "changed": False, "why": why}

    return {"text": fixed, "changed": True, "why": why}


async def review(
    llm,
    draft: str,
    last_incoming: str,
    fact_sheet: str,
    claims: Sequence[str],
    known_labels: Sequence[str],
    her_recent: Sequence[str] = (),
) -> Dict[str, Any]:
    """Skontroluje návrh. Pri akomkoľvek probléme vráti pôvodný text."""
    if not draft.strip():
        return {"text": draft, "changed": False, "why": ""}
    try:
        raw = await llm.structured(
            _SYSTEM,
            build_brief(draft, last_incoming, fact_sheet, claims, known_labels, her_recent),
        )
        return accept(draft, _json_block(raw))
    except Exception as exc:  # noqa: BLE001 - sudca nikdy nesmie zastaviť odpoveď
        log.warning("Sudca zlyhal, posielam pôvodný návrh: %s", exc)
        return {"text": draft, "changed": False, "why": ""}


# ---------- čo o sebe natvrdila ----------

_CLAIMS_SYSTEM = """\
Z jej správ vytiahni, čo o SEBE povedala jemu — fakty o jej živote, ktoré by
si mala pamätať, aby si o týždeň neprotirečila.

Vráť IBA JSON pole krátkych viet:
["má sestru v Bratislave", "pracuje v kaviarni cez víkendy"]

- Len tvrdenia o nej, nie o ňom.
- Nie nálady ani to, čo práve robí („som v posteli") — len trvalé veci.
- Ak nič také nepovedala, vráť []."""


def parse_claims(raw: str) -> List[str]:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for item in parsed if isinstance(parsed, list) else []:
        claim = str(item).strip()[:200]
        if len(claim) > 3:
            out.append(claim)
    return out[:8]


async def sync_claims(llm, db, tg_id: int, rows: Sequence[Dict[str, Any]], her_name: str) -> None:
    """Uloží nové tvrdenia o sebe. Zlyháva potichu.

    Zhoda sa hľadá podľa významu, nie podľa znakov. Predtým sa porovnávali
    normalizované reťazce, takže do tabuľky prešla každá parafráza a naživo
    v nej ležalo dvadsať tvrdení na človeka, z toho polovica to isté:
    „má tetovanie" aj „je tetovaná", „žije sama" aj „býva sama" aj „má vlastný
    byt". Model potom pri každej odpovedi videl jednu vec povedanú troma
    spôsobmi — a povedal ju štvrtýkrát.
    """
    mine = [r for r in rows if r.get("role") == "assistant"]
    if not mine:
        return
    import memory

    text = "\n".join(memory.speaker_line(r, her_name) for r in mine[-8:])
    try:
        found = parse_claims(await llm.structured(_CLAIMS_SYSTEM, text))
        if not found:
            return
        existing = await db.self_claims(tg_id, limit=60)
        known = [c["claim"] for c in existing]
        for claim in found:
            if similar.is_new(claim, known):
                await db.add_self_claim(tg_id, claim)
                known.append(claim)
    except Exception as exc:  # noqa: BLE001
        log.warning("Tvrdenia o sebe pre %s zlyhali: %s", tg_id, exc)


def claims_block(rows: Sequence[Dict[str, Any]]) -> str:
    """Tvrdenia pre prompt — bez parafráz.

    Čistí sa to aj tu, nielen pri zápise: v databáze ležia riadky spred
    zavedenia zlučovania a tie by model videl ďalej.
    """
    if not rows:
        return ""
    hodnoty = similar.dedupe([r.get("claim") or "" for r in rows])
    return "\n".join(f"- {c}" for c in hodnoty)
