"""Epizódy, sľuby a vyťahovanie z archívu.

Fakty hovoria, ČO o ňom vie. Toto hovorí, ČO SA MEDZI NIMI STALO — a to je
vec, po ktorej ostane pocit „ona si ma pamätá". Plus archív prestáva byť
mŕtvy náklad: k jeho poslednej správe sa dotiahnu staré úseky, ktoré s ňou
súvisia, aj keby boli spred mesiaca.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

# Sedenie = zhluk správ oddelený tichom. Po tomto tichu sa predošlé sedenie
# uzavrie a zapíše ako epizóda.
SESSION_GAP_H = 6

_EPISODE_SYSTEM = """\
Zhrň jedno sedenie konverzácie tak, ako by si si ho pamätal človek — dej,
nie zoznam faktov.

Vráť IBA JSON: {"title": "...", "body": "...", "mood": "..."}
- title: 3-6 slov, o čom to sedenie bolo
- body: 1-2 vety, čo sa dialo a v akom bol rozpoložení
- mood: jedno slovo (unavený, natešený, na dne, uvoľnený, nadržaný, otrávený)

Píš vecne a po slovensky. Nič si nedomýšľaj."""

_LOOP_SYSTEM = """\
Nájdi v konverzácii SĽUBY A OTVORENÉ NITKY z JEJ strany — veci, ktoré povedala,
že urobí alebo dopovie neskôr.

Vráť IBA JSON pole:
[{"what": "sľúbila mu povedať, kde ho nájde", "closed": false}]

- closed: true, ak to už medzitým splnila
- Ak nič také nie je, vráť []
- Len jej sľuby, nie jeho."""


def _json_block(raw: str) -> Any:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------- sedenia ----------

def session_closed(rows: Sequence[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """Skončilo predošlé sedenie? (ticho dlhšie než SESSION_GAP_H)"""
    stamps = [_parse_ts(r.get("created_at")) for r in rows]
    stamps = [s for s in stamps if s]
    if len(stamps) < 2:
        return False
    reference = now or datetime.now(timezone.utc)
    return reference - stamps[-1] >= timedelta(hours=SESSION_GAP_H)


def last_session(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Správy posledného súvislého sedenia (od poslednej dlhej pauzy po koniec)."""
    out: List[Dict[str, Any]] = []
    previous: Optional[datetime] = None
    for row in rows:
        stamp = _parse_ts(row.get("created_at"))
        if stamp and previous and stamp - previous >= timedelta(hours=SESSION_GAP_H):
            out = []
        out.append(row)
        if stamp:
            previous = stamp
    return out


async def write_episode(
    llm, db, tg_id: int, rows: Sequence[Dict[str, Any]], her_name: str
) -> bool:
    """Zapíše epizódu za práve uzavreté sedenie. Zlyháva potichu.

    Vracia True, keď epizóda naozaj vznikla — volajúci si podľa toho poznačí,
    že toto sedenie má vybavené, a nebude ho skúšať dokola.
    """
    session = last_session(rows)
    if len(session) < 3:
        return False
    stamps = [_parse_ts(r.get("created_at")) for r in session]
    stamps = [s for s in stamps if s]
    if not stamps:
        return False
    import memory

    lines = [memory.speaker_line(r, her_name) for r in session]
    try:
        raw = await llm.structured(_EPISODE_SYSTEM, "\n".join(lines))
        parsed = _json_block(raw)
        if not isinstance(parsed, dict):
            return False
        await db.add_episode(
            tg_id,
            {
                "started_at": stamps[0].isoformat(),
                "ended_at": stamps[-1].isoformat(),
                "title": str(parsed.get("title") or "")[:120],
                "body": str(parsed.get("body") or "")[:600],
                "mood": str(parsed.get("mood") or "")[:40],
            },
        )
        log.info("%s: zapísaná epizóda %r", tg_id, parsed.get("title"))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Epizódu pre %s sa nepodarilo zapísať: %s", tg_id, exc)
    return False


# ---------- sľuby ----------

async def sync_loops(llm, db, tg_id: int, rows: Sequence[Dict[str, Any]], her_name: str) -> None:
    """Nájde nové sľuby a uzavrie splnené. Zlyháva potichu."""
    if not rows:
        return
    import memory

    lines = [memory.speaker_line(r, her_name) for r in rows]
    try:
        raw = await llm.structured(_LOOP_SYSTEM, "\n".join(lines))
        parsed = _json_block(raw)
        if not isinstance(parsed, list):
            return
        existing = await db.open_loops(tg_id)
        known = {(row["what"] or "").strip().lower() for row in existing}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            what = str(item.get("what") or "").strip()[:200]
            if not what:
                continue
            match = next((r for r in existing if (r["what"] or "").lower() == what.lower()), None)
            if item.get("closed"):
                if match:
                    await db.close_loop(match["id"])
            elif what.lower() not in known:
                await db.add_loop(tg_id, what)
    except Exception as exc:  # noqa: BLE001
        log.warning("Sľuby pre %s sa nepodarilo spracovať: %s", tg_id, exc)


# ---------- podklady do promptu ----------

def _ago(stamp: Optional[datetime], reference: datetime) -> str:
    if not stamp:
        return ""
    days = max(int((reference - stamp).total_seconds() // 86400), 0)
    if days == 0:
        return "dnes"
    if days == 1:
        return "včera"
    if days < 30:
        return f"pred {days} dňami"
    return f"pred {days // 30} mesiacmi"


def episodes_block(rows: Sequence[Dict[str, Any]], now: Optional[datetime] = None) -> str:
    """Epizódy s ľudským datovaním, nie s dátumami."""
    if not rows:
        return ""
    reference = now or datetime.now(timezone.utc)
    lines = []
    for row in rows:
        when = _ago(_parse_ts(row.get("ended_at")), reference)
        body = (row.get("body") or row.get("title") or "").strip()
        if not body:
            continue
        mood = (row.get("mood") or "").strip()
        lines.append(f"- [{when}] {body}" + (f" (nálada: {mood})" if mood else ""))
    return "\n".join(lines)


def loops_block(rows: Sequence[Dict[str, Any]]) -> str:
    open_rows = [r for r in rows if not r.get("closed_at")]
    if not open_rows:
        return ""
    return "\n".join(f"- {r['what']}" for r in open_rows)


def archive_block(rows: Sequence[Dict[str, Any]], her_name: str, now: Optional[datetime] = None) -> str:
    """Staré úseky, ktoré súvisia s tým, čo práve napísal."""
    if not rows:
        return ""
    reference = now or datetime.now(timezone.utc)
    lines = []
    for row in rows:
        when = _ago(_parse_ts(row.get("created_at")), reference)
        who = her_name if row.get("role") == "assistant" else "on"
        content = (row.get("content") or "").strip()[:200]
        if content:
            lines.append(f"- [{when}] {who}: {content}")
    return "\n".join(lines)


def search_terms(text: str) -> str:
    """Z jeho správy spraví dopyt do archívu — bez bežných slov."""
    words = re.findall(r"[A-Za-zÀ-ž']{4,}", text or "")
    stop = {
        "that", "this", "with", "what", "when", "your", "youre", "have", "just",
        "like", "about", "there", "here", "they", "them", "then", "than",
        "would", "could", "should", "still", "really", "gonna", "wanna", "yeah",
        "know", "think", "want", "need", "good", "well", "much", "some", "more",
    }
    picked = [w for w in words if w.lower() not in stop][:6]
    # Jedno všeobecné slovo by z archívu vytiahlo len balast.
    return " ".join(picked) if len(picked) >= 2 else ""
