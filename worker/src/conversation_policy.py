"""Pure decisions shared by channel adapters; no network, secrets or sends."""
from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

LA = 'America/Los_Angeles'


def parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def in_window(value: Any, now: datetime | None = None) -> bool:
    stamp = parse_time(value)
    return bool(stamp and timedelta(0) <= (now or datetime.now(timezone.utc)) - stamp < timedelta(hours=24))


def day_key(now: datetime, tz: str = LA) -> str:
    return now.astimezone(ZoneInfo(tz)).date().isoformat()


def rng_for(seed: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:16], 'big'))


def choose_due(kind: str, now: datetime, seed: str, active: bool = False) -> datetime:
    rng = rng_for(seed)
    chance = rng.random()
    if kind == 'comment':
        seconds = rng.uniform(15 * 60, 6 * 3600)
    elif kind == 'reaction':
        low, high = (120, 600) if chance < .2 else (600, 7200) if chance < .8 else (7200, 16 * 3600)
        seconds = rng.uniform(low, high)
    elif active:
        low, high = (45, 180) if chance < .7 else (180, 480) if chance < .95 else (480, 1200)
        seconds = rng.uniform(low, high)
    else:
        low, high = (120, 300) if chance < .15 else (300, 1500) if chance < .7 else (1500, 5400) if chance < .95 else (5400, 10800)
        seconds = rng.uniform(low, high)
    return now + timedelta(seconds=seconds)


def normalise(value: Any) -> str:
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(value or '').lower()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def identity_denied(text: str) -> bool:
    text = normalise(text)
    return bool(re.search(r'\b(not me|that is not me|thats not me|wrong person|different person|not the (guy|person)|nie som (ja|on)|to nie som|iny clovek|no soy yo|persona equivocada)\b', text))


def identity_candidate(current: dict, candidates: list[dict], now: datetime | None = None) -> dict | None:
    """Recent invitation + name can recognize, but never verifies account ownership."""
    now = now or datetime.now(timezone.utc)
    handle = normalise(current.get('username'))
    name = normalise(current.get('display_name'))
    text = normalise(current.get('text'))
    rejected = set(current.get('rejected_identity_ids') or [])
    if identity_denied(text):
        return None
    scored = []
    for row in candidates:
        if row.get('id') in rejected or row.get('platform') == current.get('platform'):
            continue
        rh, rn = normalise(row.get('username')), normalise(row.get('display_name'))
        score, reasons = 0, []
        if handle and rh and handle == rh:
            score += 5
            reasons.append('matching handle')
        elif handle and rh and len(handle) >= 5 and SequenceMatcher(None, handle, rh).ratio() >= .82:
            score += 3
            reasons.append('similar handle')
        first = rn.split()[0] if rn else (rh.split()[0] if rh else '')
        if name and first and name.split()[0] == first:
            score += 3
            reasons.append('matching given name')
        introduced = bool(first and len(first) >= 3 and re.search(
            r'\b(?:im|i am|i m|its me|it s me|my name is|to som ja|som|soy|me llamo|sono)\s+' + re.escape(first) + r'\b', text))
        if introduced:
            score += 7
            reasons.append('introduced own matching name')
        # Time alone cannot establish any relation.
        if not score:
            continue
        invited = parse_time(row.get('last_invite_at'))
        recent = bool(invited and timedelta(0) <= now - invited <= timedelta(hours=6)
                      and row.get('invite_target') == current.get('platform'))
        if recent:
            score += 4
            reasons.append('recent invitation to this channel')
        scored.append((score, row, reasons, recent))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < 5 or (len(scored) > 1 and scored[0][0] - scored[1][0] < 3):
        return None
    score, row, reasons, recent = scored[0]
    return {'identity_id': row['id'], 'status': 'recognized' if score >= 9 and recent else 'candidate',
            'private_context_allowed': False, 'score': score, 'reasons': reasons}


def input_kind(text: str, story: bool = False) -> str:
    if not text.strip():
        return 'unknown'
    if not any(c.isalnum() for c in text) and any(ord(c) > 0x2600 for c in text):
        return 'reaction'
    return 'dm'


def select_comment(text: str, seed: str) -> bool:
    low = normalise(text)
    if not low and not text.strip():
        return False
    if re.search(r'\b(buy followers|promote it|dm us|click my|check my|send pic|nudes|kill yourself|scam|fuck you)\b', low) or re.search(r'https?://|www\.', text, re.I):
        return False
    chance = .8 if '?' in text else .1 if not any(c.isalnum() for c in text) else .25
    return rng_for('comment:' + seed).random() < chance


def allowed_destination(target: str, settings: dict) -> str:
    if target == 'telegram':
        handle = str(settings.get('telegram_handle') or '').strip().lstrip('@')
        return 'https://t.me/' + handle if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{4,31}', handle) else ''
    if target != 'bio_link':
        return ''
    raw = str(settings.get('bio_link') or '').strip()
    try:
        url = urlsplit(raw)
        if (url.scheme != 'https' or url.hostname not in {'linkovne.com', 'www.linkovne.com'}
                or url.username or url.password or url.port not in (None, 443)
                or not url.path.strip('/') or any(c.isspace() for c in raw)):
            return ''
    except ValueError:
        return ''
    return raw


def opt_out(text: str) -> str:
    low = normalise(text).replace('don t', 'dont')
    if re.search(r'\b(stop sending links|no more links|dont send links|neposielaj odkazy|neposielaj linky)\b', low):
        return 'links'
    if re.search(r'\b(dont message me|do not message me|stop messaging|leave me alone|nepis mi|nepis uz|stop contacting)\b', low):
        return 'contact'
    return ''


def reactive_opt_in(text: str) -> bool:
    low = normalise(text)
    return bool(re.search(r'\b(you can (?:reply|message|text)(?: to)? me again|you can reply again|feel free to reply|uz mi mozes normalne odpisovat|mozes mi zas odpisovat)\b', low))


def direct_request(text: str) -> bool:
    """A new question permits only its reactive text answer, never marketing."""
    if opt_out(text):
        return False
    low = normalise(text)
    return '?' in text or bool(re.search(r'^(how are you|where are you|can you tell me|please tell me|ako sa mas|kde si|prosim povedz)', low))


def mood_for(model_id: str, local_day: str) -> str:
    return rng_for('mood:' + model_id + ':' + local_day).choices(
        ['relaxed', 'playful', 'quiet'], weights=[.55, .3, .15], k=1)[0]
