"""Constrained response intents; the model writes prose, the server owns links."""
import re
from datetime import datetime, timedelta, timezone

from conversation_policy import allowed_destination, normalise, rng_for, parse_time, day_key

URL = re.compile(r'https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:com|net|org|me|io|link|co)\b\S*', re.I)
PROMO = re.compile(r'\b(?:highlights?|link|bio|profile|telegram|t\.me|fanvue|onlyfans)\b', re.I)
TAGS = re.compile(r'\[\[(LINK|TELEGRAM|LINKPAGE|HIGHLIGHTS|REMIND|PHOTO)\]\]')


def link_targets(settings):
    mode = settings.get('funnel_target', '')
    return {target: allowed_destination(target, settings) for target in ('telegram', 'bio_link')
            if mode in (target, 'both') and allowed_destination(target, settings)}


def classify_link(text, settings):
    urls = URL.findall(text or '')
    if len(urls) != 1:
        return 'unknown'
    url = urls[0].rstrip(".,!?);\"'}]")
    return next((target for target in ('telegram', 'bio_link')
                 if allowed_destination(target, settings) == url), 'unknown')


def link_budgets(actions, settings, now=None):
    now = now or datetime.now(timezone.utc)
    recent = [(a, parse_time(a.get('reserved_at'))) for a in actions]
    recent = [(a, stamp) for a, stamp in recent if stamp and (stamp >= now-timedelta(hours=24) or day_key(stamp) == day_key(now))]
    today = lambda rows: sum(day_key(stamp) == day_key(now) for _, stamp in rows)
    rolling = lambda rows: sum(stamp > now-timedelta(hours=24) for _, stamp in rows)
    gap = lambda rows, hours: any(stamp > now-timedelta(hours=hours) for _, stamp in rows)
    common = today(recent) < 6 and rolling(recent) < 6 and not gap(recent, 1)
    result = {}
    for target, cap, hours in (('telegram', 4, 2), ('bio_link', 2, 4)):
        rows = [(a, stamp) for a, stamp in recent
                if (a.get('payload', {}).get('link_target') or classify_link(a.get('text', ''), settings)) in (target, 'unknown')]
        result[target] = common and today(rows) < cap and rolling(rows) < cap and not gap(rows, hours)
    return result


def prepare_operator_response(raw, settings, offer, persona):
    """Exact configured owner destinations, independent of Auto invitations.

    The reservation still enforces recipient restrictions and delivery limits.
    """
    destination = str(persona.get('cta_link') or '').strip()
    urls = URL.findall(raw or '')
    if (re.fullmatch(r'https://(?:www\.)?fanvue\.com/[^\s@]+', destination)
            and len(urls) == 1 and urls[0] == destination and not TAGS.findall(raw or '')):
        return dict(kind='dm', text=raw.strip(), link=True, reminder=False, link_target='fanvue')
    if len(urls) == 1 and not TAGS.findall(raw or ''):
        target = next((key for key in ('telegram', 'bio_link') if allowed_destination(key, settings) == urls[0]), '')
        if target:
            return dict(kind='dm', text=raw.strip(), link=True, reminder=False, link_target=target)
    return prepare_response(raw, settings, offer)


def prepare_response(raw, settings, offer):
    result = dict(kind='dm', text='', link=False, reminder=False, link_target='')
    text = raw.strip()
    markers = TAGS.findall(text)
    if len(markers) > 1:
        return result
    marker = markers[0] if markers else ''
    targets = link_targets(settings)
    default_target = 'telegram' if settings.get('funnel_target') == 'both' else settings.get('funnel_target', '')
    target = {'TELEGRAM': 'telegram', 'LINKPAGE': 'bio_link'}.get(marker, default_target)
    urls = URL.findall(text)
    if urls:
        # Approved text keeps its exact destination; budget changes never swap URLs.
        if len(urls) != 1 or marker:
            return result
        target = next((key for key, url in targets.items() if url == urls[0]), '')
        if not target:
            return result
        text = text.replace(urls[0], '[[LINK]]')
        marker = 'LINK'
    if re.search(r'onlyfans', text, re.I):
        return result
    if re.search(r'fanvue', text, re.I) and not offer.get('fanvue_return'):
        return result
    if marker in ('LINK', 'TELEGRAM', 'LINKPAGE'):
        permission = offer.get('telegram_link' if target == 'telegram' else 'bio_link',
                               offer.get('link') if target == default_target else False)
        destination = targets.get(target)
        if not permission or not destination:
            return result
        result.update(text=TAGS.sub(lambda _: destination, text), link=True, link_target=target)
    elif marker == 'HIGHLIGHTS':
        if offer.get('highlights'):
            result.update(text=TAGS.sub('', text).strip(), reminder=True, link_target='bio_link')
    elif marker == 'REMIND':
        if offer.get('remind') or offer.get('fanvue_return'):
            result.update(text=TAGS.sub('', text).strip(), reminder=True)
    elif marker == 'PHOTO':
        if offer.get('photo'):
            result['kind'] = 'photo'
    elif PROMO.search(text):
        if (offer.get('remind') or offer.get('fanvue_return')) and not re.search(r'highlights?|bio|profile|telegram', text, re.I):
            result.update(text=text, reminder=True)
    elif '[[' not in text and ']]' not in text:
        result['text'] = text
    return result


def age_evidence(text):
    low = normalise(text)
    ages = [int(n) for n in re.findall(r'\b(?:im|i m|i am|mam|tengo|j ai|ich bin) (\d{1,3})\b', low)]
    if any(n < 18 for n in ages):
        return 'minor_or_conflicting'
    if re.search(r'\b(pretend|say|imagine|roleplay|suppose)\b', low):
        return ''
    if len(ages) == 1 and 18 <= ages[0] <= 100:
        return 'adult_self_declared'
    return ''


def small_typo(text, seed):
    """Optional tiny style variation only on a known ordinary word, never identifiers."""
    rng = rng_for('typo:' + seed)
    if rng.randrange(20) != 0 or URL.search(text):
        return text, {}
    words = list(re.finditer(r'\b(really|maybe|little|thanks|sorry|because|probably)\b', text))
    if not words:
        return text, {}
    match = rng.choice(words)
    word = match.group()
    typo = word[:2] + word[3] + word[2] + word[4:]
    if typo == word:
        return text, {}
    return text[:match.start()] + typo + text[match.end():], {'written': typo, 'intended': word}
