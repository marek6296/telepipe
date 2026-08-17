"""Kontextové okno konverzácie + rolling summary + analýza štýlu."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def to_chat_history(
    rows: List[Dict[str, Any]], now: Optional[datetime] = None
) -> List[Dict[str, str]]:
    """Prevedie DB riadky na formát pre LLM.

    Ku správam, pred ktorými bola citeľná medzera, pripíše časovú značku
    („[pred 3 h]“). Bez toho model nevie, či to bolo pred minútou alebo včera,
    a napíše „ahoj“ do rozbehnutej konverzácie.
    """
    reference = now or datetime.now(timezone.utc)
    history: List[Dict[str, str]] = []
    previous: Optional[datetime] = None

    for row in rows:
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        stamp = _parse_ts(row.get("created_at"))
        if stamp and previous:
            gap_min = (stamp - previous).total_seconds() / 60
            if gap_min >= 20:
                content = f"[{_ago(stamp, reference)}] {content}"
        elif stamp and previous is None and (reference - stamp).total_seconds() > 3600:
            content = f"[{_ago(stamp, reference)}] {content}"
        if stamp:
            previous = stamp
        history.append({"role": role, "content": content})

    return _merge_consecutive(history)


def _ago(stamp: datetime, reference: datetime) -> str:
    minutes = max(int((reference - stamp).total_seconds() / 60), 0)
    if minutes < 60:
        return f"pred {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"pred {hours} h"
    days = hours // 24
    return "včera" if days == 1 else f"pred {days} dňami"


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


def _merge_consecutive(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Zlúči po sebe idúce správy tej istej role — modely to zvládajú lepšie."""
    merged: List[Dict[str, str]] = []
    for item in history:
        if merged and merged[-1]["role"] == item["role"]:
            merged[-1]["content"] += "\n" + item["content"]
        else:
            merged.append(dict(item))
    return merged


_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]"
)


def describe_style(rows: List[Dict[str, Any]]) -> str:
    """Ako píše on — merané z jeho správ, nie hádané modelom.

    Ide do promptu ako pokyn na prispôsobenie. Deterministické, takže to
    nekolíše medzi odpoveďami a nič to nestojí.
    """
    texts = [
        (r.get("content") or "").strip()
        for r in rows
        if r.get("role") == "user" and (r.get("content") or "").strip()
    ]
    if not texts:
        return ""

    words = [len(t.split()) for t in texts]
    avg = sum(words) / len(words)
    traits = []

    if avg <= 3:
        traits.append("píše veľmi krátko (1–3 slová)")
    elif avg <= 10:
        traits.append("píše krátke správy")
    elif avg <= 30:
        traits.append("píše stredne dlhé správy")
    else:
        traits.append("píše dlhé správy")

    letters = "".join(texts)
    alpha = [ch for ch in letters if ch.isalpha()]
    if alpha:
        upper_ratio = sum(1 for ch in alpha if ch.isupper()) / len(alpha)
        if upper_ratio < 0.02:
            traits.append("všetko malými písmenami")
        elif upper_ratio > 0.6:
            traits.append("PÍŠE VEĽKÝMI PÍSMENAMI")

    if sum(1 for t in texts if _EMOJI_RE.search(t)) >= max(1, len(texts) // 3):
        traits.append("používa emoji")
    else:
        traits.append("emoji skoro nepoužíva")

    if not any(t.endswith((".", "!", "?")) for t in texts):
        traits.append("neukončuje vety interpunkciou")

    questions = sum(1 for t in texts if "?" in t)
    if questions >= max(2, len(texts) // 2):
        traits.append("často sa vypytuje")

    return ", ".join(traits)


def his_samples(rows: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    """Jeho posledné správy ako ukážka štýlu, nie ako opis.

    `describe_style` štýl iba OPÍŠE („píše krátke správy, malými písmenami“) a
    model si z toho musí spôsob písania odvodiť. Ukážka funguje podstatne
    lepšie než opis a máme ju zadarmo — sú to jeho vlastné správy z okna.
    """
    texts = [
        (r.get("content") or "").strip()
        for r in rows
        if r.get("role") == "user" and (r.get("content") or "").strip()
    ]
    # Popis prijatej fotky („[poslal fotku: …]“) nie je jeho písanie a ako
    # ukážka štýlu by len mýlil.
    texts = [t for t in texts if not t.startswith("[")]
    return texts[-limit:]


def needs_summary(user: Dict[str, Any], every: int) -> bool:
    """Je čas prepísať rolling summary?"""
    msg_count = int(user.get("msg_count") or 0)
    last_at = int(user.get("summary_at_msg") or 0)
    return msg_count - last_at >= every


# Značka, ktorou sa v archíve pozná, že správa odznela hlasom. Zapisuje ju
# `_send_generated_voice` aj `_send_voice`.
VOICE_MARK = "(hlasovka)"


def spoken_aloud(content: str) -> bool:
    """Odznela táto správa hlasom?"""
    return (content or "").lstrip().lower().startswith(VOICE_MARK)


def without_voice_mark(content: str) -> str:
    """Text bez značky — samotná značka nie je jej slovo."""
    text = (content or "").lstrip()
    if text.lower().startswith(VOICE_MARK):
        text = text[len(VOICE_MARK):]
    return text.strip()


def speaker_line(row: Dict[str, Any], persona_name: str) -> str:
    """Jeden riadok prepisu pre extraktory, zhrnutie a epizódy.

    Hlasovka sa označí slovami, nie značkou: `(hlasovka)` je moja poznámka a
    model netuší, čo znamená. Bez toho sa po týždni nedá zistiť, či mu niečo
    povedala alebo napísala — a to je rozdiel, ktorý si človek pamätá.
    """
    obsah = (row.get("content") or "").strip()
    if row.get("role") != "assistant":
        return f"On: {obsah}"
    if spoken_aloud(obsah):
        return f"{persona_name} (povedala mu to HLASOM): {without_voice_mark(obsah)}"
    return f"{persona_name}: {obsah}"


def transcript_for_summary(rows: List[Dict[str, Any]], persona_name: str) -> str:
    """Prepis konverzácie pre summarizér. Čistá funkcia."""
    return "\n".join(speaker_line(row, persona_name) for row in rows)


async def refresh_summary(
    db, llm, user: Dict[str, Any], persona_name: str, window: int, fact_sheet: str = ""
) -> None:
    """Prepíše summary v DB. Zlyhanie nesmie zhodiť odpovedanie."""
    tg_id = user["tg_id"]
    try:
        rows = await db.recent_messages(tg_id, window)
        transcript = transcript_for_summary(rows, persona_name)
        summary = await llm.summarize(fact_sheet, transcript)
        if summary:
            await db.update_user(
                tg_id,
                {"summary": summary, "summary_at_msg": int(user.get("msg_count") or 0)},
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Summary pre %s sa nepodarilo prepísať: %s", tg_id, exc)


# Po akej pauze sa rozhovor berie ako nové sedenie.
SESSION_BREAK_H = 3


def session_hours(rows, now=None) -> float:
    """Ako dlho si píšu v kuse, v hodinách.

    Skutočné dievča nevydrží štyri hodiny rovnako nadšené. Prvú hodinu píše
    veľa, potom jej pozornosť prirodzene klesá — a práve tá krivka odlišuje
    človeka od automatu, ktorý je na 40. správe rovnako svieži ako na prvej.
    """
    from datetime import datetime, timezone

    def _ts(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    casy = [c for c in (_ts(r.get("created_at")) for r in rows or []) if c]
    if not casy:
        return 0.0
    casy.sort()
    zaciatok = casy[0]
    for skorsi, neskorsi in zip(casy, casy[1:]):
        if (neskorsi - skorsi).total_seconds() / 3600 >= SESSION_BREAK_H:
            zaciatok = neskorsi
    return max(0.0, ((now or datetime.now(timezone.utc)) - zaciatok).total_seconds() / 3600)
