"""Constrained response intents; the model writes prose, the server owns links."""
import re

from conversation_policy import allowed_destination, normalise, rng_for

URL = re.compile(r'https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:com|net|org|me|io|link|co)\b\S*', re.I)
PROMO = re.compile(r'\b(?:highlights?|link|bio|profile|telegram|t\.me|fanvue|onlyfans)\b', re.I)
TAGS = re.compile(r'\[\[(LINK|HIGHLIGHTS|REMIND|PHOTO)\]\]')


def prepare_response(raw, settings, offer):
    result = dict(kind='dm', text='', link=False, reminder=False)
    text = raw.strip()
    markers = TAGS.findall(text)
    if len(markers) > 1:
        return result
    marker = markers[0] if markers else ''
    destination = allowed_destination(settings.get('funnel_target', ''), settings)
    # A human-approved exact configured URL uses the same transactional quota.
    urls = URL.findall(text)
    if urls:
        if len(urls) != 1 or urls[0] != destination or marker:
            return result
        text = text.replace(destination, '[[LINK]]')
        marker = 'LINK'
    if re.search(r'fanvue|onlyfans', text, re.I):
        return result
    if marker == 'LINK':
        if not offer.get('link') or not destination:
            return result
        result.update(text=text.replace('[[LINK]]', destination), link=True)
    elif marker == 'HIGHLIGHTS':
        if offer.get('highlights'):
            result.update(text=TAGS.sub('', text).strip(), reminder=True)
    elif marker == 'REMIND':
        if offer.get('remind'):
            result.update(text=TAGS.sub('', text).strip(), reminder=True)
    elif marker == 'PHOTO':
        if offer.get('photo'):
            result['kind'] = 'photo'
    elif PROMO.search(text):
        if offer.get('remind') and not re.search(r'highlights?|bio|profile|telegram', text, re.I):
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
