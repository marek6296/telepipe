"""One chronology/current turn for all channels, drafts and regeneration.

Source timestamps stay separate from text and ingestion timestamps. Never merge
unanswered messages across a long pause or reset identity at a session boundary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import humanize

SESSION_GAP = timedelta(hours=4)
_GREETING = re.compile(
    r'^\W*(?:h(?:i+|e+y+|ello|iya)|yo|howdy|morning|afternoon|evening|'
    r'good\s*(?:morning|afternoon|evening)|gm|ahoj|cau|čau|nazdar|hola|hallo)\b',
    re.IGNORECASE,
)
_START = '[CONVERSATION TIMING]'
_END = '[/CONVERSATION TIMING]'


def message_time(row: dict[str, Any]) -> datetime | None:
    # An explicit null source time means UNKNOWN, never "use time of import".
    value = row.get('occurred_at') if 'occurred_at' in row else row.get('created_at')
    if not value:
        return None
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
    except (ValueError, TypeError, OverflowError):
        return None


def _valid_time(row: dict[str, Any], now: datetime) -> datetime | None:
    stamp = message_time(row)
    if stamp and stamp <= now + timedelta(minutes=5):
        return stamp
    return None


def chronological_rows(history: list[dict[str, Any]], now_local: datetime | None = None) -> list[dict[str, Any]]:
    """A late import must not move an old answer after today's inbound.

    Only known source times can be sorted; unknown slots retain their sequence
    position rather than pretending to be older/newer than every known message.
    """
    now = now_local or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    rows = [dict(r) for r in history or []]
    known = [(i, _valid_time(r, now)) for i, r in enumerate(rows)]
    known = [(i, stamp) for i, stamp in known if stamp is not None]
    ordered = sorted(known, key=lambda item: item[1].astimezone(timezone.utc))
    for (slot, _), (source, _) in zip(known, ordered):
        rows[slot] = dict(history[source])
    return rows


@dataclass(frozen=True)
class Turn:
    messages: list[dict[str, str]]
    prompt: str
    incoming: list[dict[str, Any]]
    latest_text: str
    has_greeting: bool
    greeting_only: bool
    starts_new_session: bool
    older_unanswered_count: int


def analyze(history: list[dict[str, Any]], now_local: datetime | None = None) -> Turn:
    now = now_local or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    rows = chronological_rows([r for r in history or [] if r.get('role') in ('user', 'assistant') and str(r.get('content') or '').strip()], now_local=now)
    stamps = [_valid_time(r, now) for r in rows]
    tail = next((i + 1 for i in range(len(rows) - 1, -1, -1) if rows[i]['role'] == 'assistant'), 0)
    start = tail
    new_session = False
    for i in range(max(1, tail), len(rows)):
        previous, current = stamps[i - 1], stamps[i]
        if previous and current and current.astimezone(timezone.utc) - previous.astimezone(timezone.utc) >= SESSION_GAP:
            start = i
            new_session = True
    incoming = rows[start:]
    has_greeting = any(_GREETING.match(str(r['content']).strip()) for r in incoming)
    greeting_only = len(incoming) == 1 and humanize.is_bare_greeting(str(incoming[0]['content']))
    zone = getattr(now.tzinfo, 'key', None) or now.tzname() or 'UTC'
    messages = []
    for i, (row, stamp) in enumerate(zip(rows, stamps)):
        when = stamp.astimezone(now.tzinfo).strftime('%Y-%m-%d %H:%M %Z') if stamp else 'time unknown'
        focus = 'CURRENT TURN' if i >= start else 'BACKGROUND'
        messages.append({'role': row['role'], 'content': f'[Message time: {when}; {focus}]\n{row["content"]}'})
    instructions = [
        _START,
        f'Now: {now.strftime("%Y-%m-%d %H:%M %Z")}; timezone: {zone}. Message times are source times, not import times.',
        'Timing labels are context only: never copy them into your reply. Unknown time means unknown; do not invent a day or duration.',
        f'CURRENT TURN contains the latest {len(incoming)} unanswered message(s). Read them together, including greetings before the very last message.',
        'BACKGROUND preserves the relationship, facts and earlier conversation; it is not a checklist of questions that must all be answered now.',
        'If the current turn explicitly returns to an earlier topic, use the relevant background to answer it. Otherwise follow what he is doing NOW.',
        'A session boundary is not a new acquaintance. Do not reintroduce yourself, forget him or invent reasons for a pause.',
    ]
    if new_session:
        instructions.append('There was a substantial pause before the CURRENT TURN. Treat this as a reopened conversation, not an immediate continuation of the old topic.')
    if has_greeting:
        instructions.append('He greets you in the CURRENT TURN. Acknowledge that naturally in your own voice, even when a check-in or question follows it. This overrides a generic no-greeting rule. Every suggested alternative must fit this opening; do not jump straight to an old unanswered topic.')
    else:
        instructions.append('No greeting occurs in the current turn; do not recycle an earlier answered greeting or force a new hello merely because the date changed.')
    instructions.extend(['Keep the established persona, language and usual reply length; no canned opener, repeated phrases or list of replies.', _END])
    return Turn(messages, '\n'.join(instructions), incoming, '\n'.join(str(r['content']) for r in incoming), has_greeting, greeting_only, new_session, start - tail)


def prompt_with_timing(system: str, turn: Turn) -> str:
    """Regeneration replaces the previous timing block, never accumulates it."""
    clean = re.sub(re.escape(_START) + r'.*?' + re.escape(_END), '', system, flags=re.DOTALL).rstrip()
    return clean + '\n\n' + turn.prompt
