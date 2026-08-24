"""Aby odpovede pôsobili ako od človeka. Čisté funkcie — bez I/O."""
from __future__ import annotations

import logging
import random
import re
import unicodedata
from datetime import datetime, timedelta
from typing import List, Optional

log = logging.getLogger(__name__)

# Zdravenie na začiatku odpovede — v pokračujúcej konverzácii je to najväčší
# prezradzovač automatu, takže ho odstraňujeme post-processingom.
_GREETING_RE = re.compile(
    r"^\s*(ahojk?y?|čau|cau|čauko|nazdar|servus|zdravím|zdravim|dobr[ýy]\s+de[ňn]"
    r"|hell?o+|hey+|hi+|yo)\b[\s,!.:–-]*",
    re.IGNORECASE,
)

# Zdôraznenie **takto** alebo __takto__ — hviezdičky von, slovo nechaj.
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*|__([^_\n]+)__")

# Riadiace tokeny, ktoré model občas prepašuje do textu. Klientovi by
# odišlo „...still warm out eos" a vyzeralo by to ako porucha.
_MODEL_ARTIFACT_RE = re.compile(
    r"<\|[^|>]{0,24}\|>|</?s>|\[/?INST\]|\b(eos|eot|bos|endoftext)\b\s*$",
    re.IGNORECASE,
)

# Zvyšky po odstránenom pozdrave („hey yourself", „hi there").
#
# Samotné „you" je medzi nimi len vtedy, keď za ním nič vecné nenasleduje:
# z „hey you 🥰 missed that" ostalo klientovi „you 🥰 missed that", čo nedáva
# zmysel. Pri „hey you look tired" sa ale „you" nechať musí, inak by z vety
# ostalo „look tired".
_GREETING_TAIL_RE = re.compile(
    r"^\s*(?:yourself|you\s+too|there|back|again|stranger"
    r"|you(?=\s*(?:[^\w\s]|$))"
    r")\b[\s,!.:-]*",
    re.IGNORECASE,
)

# Roleplay akcie v hviezdičkách (*usmieva sa*) — v DM znejú ako chatbot.
_ACTION_RE = re.compile(r"\*[^*\n]{1,60}\*")

# Model občas predradí meno postavy alebo obalí odpoveď do úvodzoviek.
_SPEAKER_RE = re.compile(r"^\s*[A-ZÀ-Ž][\wÀ-ž]{1,20}\s*:\s*")

_MAX_CHUNKS = 3

# Kým si nezvyknú na seba, odpovede zostávajú krátke.
EARLY_MESSAGES = 10


def sanitize(text: str, keep_greeting: bool) -> str:
    """Vyčistí odpoveď modelu do podoby, akú by napísal človek v DM.

    keep_greeting=False odstrelí úvodné „ahoj/hey“ — používa sa vždy, keď
    konverzácia beží a pozdrav by prezradil automat.
    """
    out = _MODEL_ARTIFACT_RE.sub("", (text or "").strip()).strip()
    # Poradie je dôležité: **slovo** je zdôraznenie (slovo nechaj), *usmieva sa*
    # je roleplay akcia (celé zahoď). Keby sa akcie riešili prvé, z **slovo**
    # by zostali visieť hviezdičky.
    out = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", out)
    out = _ACTION_RE.sub("", out)
    out = _SPEAKER_RE.sub("", out)
    if len(out) >= 2 and out[0] in "\"“'" and out[-1] in "\"”'":
        out = out[1:-1].strip()
    if not keep_greeting:
        out = _GREETING_RE.sub("", out, count=1)
        # „hey yourself" by po odstránení pozdravu zostalo ako holé „yourself"
        out = _GREETING_TAIL_RE.sub("", out, count=1)
    out = plain_words(out)
    out = plain_punctuation(out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# Znaky, ktoré na mobile nikto nepíše — sú to typické prezradzovače AI.
# Rieši sa to v kóde, nie promptom: model na to pravidlo priebežne zabúda.
_TYPOGRAPHY = {
    "\u2014": ",",   # em dash — najväčší prezradzovač AI
    "\u2013": ",",   # en dash
    "\u2015": ",",
    "\u2026": "...",
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u00a0": " ",   # nezlomiteľná medzera
    ";": ",",         # v chate sa bodkočiarka nepíše
    "\u2022": "",
    "\u25aa": "",
    "\u2023": "",
    "\u2192": "",
    "\u21d2": "",
    "\u00b7": "",
}

# Tieto sa nahradia MEDZEROU, nie prázdnom: keby model napísal face"you,
# odstránenie bez náhrady by z toho urobilo "faceyou". Apostrof zostáva.
_STRIP_CHARS = '"\u201c\u201d\u201e\u201f\u00ab\u00bb`*~|#^<>'


# Odkaz sa čistením NESMIE dotknúť.
#
# `_STRIP_CHARS` obsahuje `_ ~ # | * ^ < >` — všetko znaky, ktoré v URL bežne
# sú. Kým sa čistilo naslepo, každý odkaz s trackovacím parametrom odišiel
# rozbitý: `?client_reference_id=tg-123` sa zmenilo na `?client reference
# id=tg-123`. Odkaz sa v Telegrame zlomil na prvej medzere a prepojenie
# fanúšika s jeho konverzáciou tichom zmizlo — funkcia, ktorá má vlastný modul
# (`checkout.py`), nefungovala ani raz.
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def plain_punctuation(text: str) -> str:
    """Prepíše typografiu na to, čo človek reálne natrieska na mobile.

    Odkazy sa vyberú bokom a vrátia späť nedotknuté — na mobile ich nikto
    neprepisuje a čistenie typografie sa ich netýka.
    """
    out = text or ""

    odkazy: list[str] = []

    def _odloz(match: "re.Match[str]") -> str:
        odkazy.append(match.group(0))
        # Zástupný znak nesmie obsahovať nič z `_STRIP_CHARS` ani z typografie,
        # inak by ho čistenie samo rozbilo.
        return f"\x00{len(odkazy) - 1}\x00"

    out = _URL_RE.sub(_odloz, out)

    for bad, good in _TYPOGRAPHY.items():
        out = out.replace(bad, good)
    out = out.translate({ord(ch): " " for ch in _STRIP_CHARS})
    # Podčiarkovník je markdown len na okraji slova (`_takto_`). MEDZI písmenami
    # je súčasťou mena — a používateľské mená ich majú plno. Kým sa strhával
    # naslepo, „simona_here" odišla ako „simona here" a fanúšik ju nemal ako
    # nájsť; na Instagrame je pritom meno jediné, čo mu vieme dať.
    out = re.sub(r"(?<![0-9A-Za-z])_+|_+(?![0-9A-Za-z])", " ", out)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",{2,}", ",", out)
    out = re.sub(r"\.{4,}", "...", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"^[,\s]+", "", out)
    out = out.strip()

    for i, odkaz in enumerate(odkazy):
        out = out.replace(f"\x00{i}\x00", odkaz)
    return out


# Skratky, ktoré 27-ročná píše nanajvýš občas a 40-ročná vôbec. Model na
# promptové pravidlo občas zabudne, takže sa to dorieši aj tu.
_HARD_SLANG = {
    r"\brn\b": "right now",
    r"\bngl\b": "honestly",
    r"\btbh\b": "honestly",
    r"\bimo\b": "i think",
    r"\bfr\b": "for real",
    r"\baf\b": "",
    r"\bsmh\b": "",
    r"\biykyk\b": "",
    r"\bfyi\b": "",
}


def soften_slang(text: str, level: str) -> str:
    """Pri „none" a „light" prepíše tvrdé skratky na normálne slová."""
    if level not in ("none", "light"):
        return text
    out = text or ""
    for pattern, replacement in _HARD_SLANG.items():
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.!?])", r"\1", out)
    return out.strip()


# Slov\u00e1, ktor\u00e9 v DM nikto nenap\u00ed\u0161e. Boli vymenovan\u00e9 v prompte, ale zoznam
# zak\u00e1zan\u00fdch slov ich modelu paradoxne dr\u017e\u00ed pred o\u010dami \u2014 a v dlhom prompte
# na to pravidlo aj tak zabudne. Tu sa to dorie\u0161i ticho a spo\u013eahlivo.
# Nahr\u00e1dza sa len tam, kde n\u00e1hrada sed\u00ed v akejko\u013evek vete; pri slov\u00e1ch, ktor\u00e9
# menia slovn\u00fd druh (endeavour, procure), sa rad\u0161ej nerob\u00ed ni\u010d.
_AI_WORDS = {
    "intriguing": "interesting",
    "fascinating": "interesting",
    "delightful": "lovely",
    "whilst": "while",
    "albeit": "though",
    "utmost": "biggest",
    "regarding": "about",
    "furthermore": "also",
    "moreover": "also",
    "apologies": "sorry",
    "perhaps": "maybe",
    "certainly": "for sure",
    "immensely": "really",
    "wonderfully": "really",
    "delighted": "happy",
    "utilize": "use",
    "commence": "start",
    "purchase": "buy",
    "additionally": "also",
    "nevertheless": "still",
}
_AI_WORDS_RE = re.compile(
    r"\b(" + "|".join(sorted(_AI_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def plain_words(text: str) -> str:
    """Prep\u00ed\u0161e kni\u017en\u00e9 slov\u00e1 na tie, ktor\u00e9 sa p\u00ed\u0161u v chate."""

    def swap(match: re.Match) -> str:
        found = match.group(0)
        replacement = _AI_WORDS[found.lower()]
        if found[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    return _AI_WORDS_RE.sub(swap, text or "")


_EMOJI_CHAR_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff\u2764\ufe0f]"
)


# Doplnkové znaky, ktoré po odstránení emoji ostanú visieť samé.
_EMOJI_ZVYSKY_RE = re.compile("[️︎‍⃣]")


def thin_emoji(text: str, recent: List[str], streak: int = 3) -> str:
    """Občas správa bez emoji — inak ich má každá jedna a to je vzor.

    Prompt jej hovorí „občas žiadne, aby to nebolo mechanické“ a model to
    nedodrží: meranie na živých dátach ukázalo emoji v 100 % správ. Presne
    ten istý prípad ako diakritika — pravidlo, na ktoré sa model nedá chytiť,
    musí ustrážiť kód.

    Zasahuje sa až po sérii: keď mali emoji tri jej správy za sebou, štvrtá
    ide bez. Nie náhodne — náhoda by občas vyrobila sériu piatich.
    """
    if not _EMOJI_CHAR_RE.search(text or ""):
        return text
    posledne = [t for t in recent if (t or "").strip()][-streak:]
    if len(posledne) < streak or not all(_EMOJI_CHAR_RE.search(t) for t in posledne):
        return text
    out = _EMOJI_ZVYSKY_RE.sub("", _EMOJI_CHAR_RE.sub("", text))
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.!?])", r"\1", out)
    return "\n".join(r.strip() for r in out.splitlines()).strip()


# Slová, ktorými sa dá začať správa donekonečna a nikomu to nepríde divné —
# až kým to nezmeriaš. Na živých dátach začínalo 13 % jej správ slovom „haha".
_OPENER_RE = re.compile(r"^\s*([a-zá-ž]+)\b[\s,!.]*", re.IGNORECASE)


def opener(text: str) -> str:
    """Prvé slovo správy, malými. Prázdne, keď sa nedá určiť."""
    match = _OPENER_RE.match(text or "")
    return match.group(1).lower() if match else ""


# Nad týmto podielom posledných správ je otvárač návyk, nie náhoda. Namerané
# naživo: „haha" na začiatku 18 % jej správ, „aw"/„aww" ďalších 8 %. Ani jedno
# neporušuje pravidlo „nie trikrát po sebe" — a napriek tomu je to na
# konverzácii vidieť, lebo takto nepíše nikto.
OTVARAC_PODIEL = 0.3
OTVARAC_OKNO = 8

# Citoslovcia, ktorými sa dá začať skoro každá správa. Sú zameniteľné, takže
# model medzi nimi prepína a KAŽDÉ zvlášť ostane pod hranicou — namerané:
# „aw" 26 %, „haha" 23 %, „lol" 11 %, „hehe" 8 %, dokopy 36 % správ v jednom
# chate a pravidlo o opakovaní nezasiahlo ani raz. Preto sa počítajú spolu.
VYPLNKOVE_OTVARACE = frozenset({
    "aw", "aww", "awww", "haha", "hah", "hahah", "hahaha", "hehe", "heh",
    "lol", "lmao", "omg", "mmm", "mm", "hmm", "hm", "yay", "oof",
})
# Nad týmto podielom je to návyk. Pravidlo sa ustáli zhruba na svojej hranici,
# takže je to zároveň cieľ. Prehraté na 85 skutočných správach z jedného chatu:
#
#   hranica 0.35 → ostane 27 %      hranica 0.20 → ostane 19 %
#   hranica 0.25 → ostane 27 %      hranica 0.10 → ostane 9 %
#
# 0.2 skráti tik na polovicu a pritom nechá jej hlas na pokoji; pri 0.1 by sa
# otvárač strhol každej štvrtej správe a „aw" pred milou vetou je občas presne
# to, čo tam patrí. Ani pri jednej hranici nevznikla prázdna správa.
VYPLNKOVY_PODIEL = 0.2


def thin_openers(
    text: str,
    recent: List[str],
    streak: int = 2,
    podiel: float = OTVARAC_PODIEL,
) -> str:
    """Nezačínaj tretíkrát po sebe tým istým slovom — ani ním nezačínaj stále.

    Presne ten istý prípad ako `thin_emoji`: prompt to hovorí, model to
    nedodrží, a je to merateľné. „haha" na začiatku je samo o sebe v poriadku
    — v poriadku nie je, keď ním začína každá piata správa.

    Dve pravidlá naraz: tri rovnaké začiatky ZA SEBOU, alebo ten istý začiatok
    v prílišnom PODIELE posledných správ. Prvé chytá zjavné opakovanie, druhé
    tik, ktorý sa medzi ostatné správy schová.

    Odstráni sa len otvárač, zvyšok vety ostáva. Keď by po ňom nezostalo nič
    vecné, radšej sa nerobí nič — prázdna správa je horšia než opakovaný začiatok.
    """
    moj = opener(text)
    if not moj:
        return text
    platne = [t for t in recent if (t or "").strip()]
    posledne = platne[-streak:]
    za_sebou = len(posledne) >= streak and all(opener(t) == moj for t in posledne)

    okno = platne[-OTVARAC_OKNO:]
    # Až od štyroch správ: pri dvoch by jeden „haha" znamenal 50 % a modelka by
    # prišla o začiatok, ktorý použila prvýkrát v živote.
    navyk = len(okno) >= 4 and sum(1 for t in okno if opener(t) == moj) / len(okno) > podiel

    # A to isté pre celú skupinu citosloviec dokopy — inak sa dá hranica obísť
    # tým, že sa striedajú.
    vyplnok = (
        moj in VYPLNKOVE_OTVARACE
        and len(okno) >= 4
        and sum(1 for t in okno if opener(t) in VYPLNKOVE_OTVARACE) / len(okno)
        > VYPLNKOVY_PODIEL
    )

    if not za_sebou and not navyk and not vyplnok:
        return text
    zvysok = _OPENER_RE.sub("", text or "", count=1).lstrip()
    if len(zvysok.strip()) < 3:
        return text
    return zvysok[:1].lower() + zvysok[1:] if zvysok[:1].isupper() else zvysok


def recent_emoji(rows, limit: int = 8) -> List[str]:
    """Ktoré emoji použila v posledných správach — aby ich striedala.

    Model sa prisaje na prvé emoji zo zoznamu v prompte a používa ho stále
    dokola. Preto mu tie nedávne vymenujeme a zakážeme.
    """
    seen: List[str] = []
    mine = [r for r in rows if r.get("role") == "assistant"]
    for row in reversed(mine[-limit:]):
        for ch in _EMOJI_CHAR_RE.findall(row.get("content") or ""):
            if ch not in seen:
                seen.append(ch)
    return seen[:6]


def strip_diacritics(text: str) -> str:
    """Odstráni diakritiku — dievčatá na mobile ju bežne nepíšu.

    Robí sa to v kóde, nie promptom: model si na to nespoľahlivo pamätá.
    Emoji a ostatné znaky zostávajú nedotknuté.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", without_marks)


# Otázka, na ktorú sa nedá odpovedať jedným slovom — tam by strohá odpoveď
# pôsobila, že ju to nezaujíma.
_OPEN_QUESTION_RE = re.compile(
    r"\b(what|why|how|tell\s+me|whats\s+it\s+like|how\s+come|what\s+do\s+you\s+think"
    r"|whats\s+your|describe|explain)\b",
    re.IGNORECASE,
)


def wants_a_real_answer(incoming: str) -> bool:
    text = incoming or ""
    return bool(_OPEN_QUESTION_RE.search(text)) and (len(text.split()) >= 4 or "?" in text)


def mirror_length_hint(incoming: str, msg_count: int = 0, allow_long: bool = True) -> str:
    """Koľko toho napísať — podľa neho aj podľa toho, ako dlho sa poznajú.

    Dva vplyvy naraz:
      * jeho správa — na „hey" sa neodpovedá odsekom
      * hĺbka vzťahu — cudziemu človeku nikto nepíše dlhé správy. Na začiatku
        sú preto odpovede krátke a rozpisuje sa až keď si zvyknú na seba.

    `allow_long=False` drží dlhé odpovede vzácne aj neskôr — inak by sa
    z výnimky stal štandard.
    """
    text = incoming or ""
    words = len(text.split())
    deep = wants_a_real_answer(text)
    early = msg_count < EARLY_MESSAGES

    if early:
        base = (
            "Ešte sa len spoznávate, takže píš KRÁTKO — jedna veta, nanajvýš "
            "dve, dohromady do 18 slov. Dlhé správy hneď na začiatku pôsobia "
            "nasilu."
        )
        if deep:
            base += " Aj keď sa pýta na niečo väčšie, odpovedz stručne, do 25 slov."
        return base + " Nikdy neprednášaj."

    if words <= 3:
        base = "Napísal len pár slov — stačí pol vety, pokojne tri slová."
    elif words <= 12:
        base = "Píše krátko — odpovedz JEDNOU krátkou vetou."
    elif words <= 40:
        base = "Píše normálne — odpovedz jednou, nanajvýš dvoma vetami."
    else:
        base = "Napísal dlhšiu správu — aj tak odpovedz nanajvýš dvoma vetami."

    if deep and allow_long:
        base += (
            " Pýta sa na niečo, čo si žiada skutočnú odpoveď — tu smieš pridať "
            "vetu navyše, ale stále to musí byť správa z mobilu, nie odsek."
        )
    elif deep:
        base += " Odpovedz mu na to poriadne, ale drž sa pri zemi."

    # Ľudia si v chate nepíšu odseky ani vtedy, keď majú čo povedať. Strop bol
    # 70 slov, čo je pol obrazovky na mobile — a tak to aj vyzeralo.
    return base + (
        " TVRDÝ STROP: 35 slov na celú odpoveď. Nikdy nepíš odsek a nikdy "
        "neprednášaj. Keď máš toho viac, povedz len to najdôležitejšie — "
        "zvyšok sa dá dopovedať v ďalšej správe, keď sa spýta."
    )


def split_message(text: str, max_chunks: int = _MAX_CHUNKS) -> List[str]:
    """Rozdelí dlhú odpoveď na 1–3 správy, ako keď človek píše po častiach."""
    parts = [p.strip() for p in re.split(r"\n{2,}", text or "") if p.strip()]
    if not parts:
        return []
    if len(parts) <= max_chunks:
        return parts
    # Zvyšok zlúč do poslednej správy, aby sme neposielali 8 správ za sebou.
    head = parts[: max_chunks - 1]
    tail = " ".join(parts[max_chunks - 1 :])
    return head + [tail]


def typing_delay(text: str, rng: Optional[random.Random] = None) -> float:
    """Ako dlho „píše" — úmerne dĺžke, s náhodným rozptylom, strop 40 s."""
    r = rng or random
    base = r.uniform(1.5, 4.0)
    per_char = len(text or "") / r.uniform(11.0, 18.0)
    return round(min(base + per_char, 40.0), 2)


def read_delay(rng: Optional[random.Random] = None) -> float:
    """Pauza pred začatím písania — akoby si správu najprv prečítala."""
    r = rng or random
    return round(r.uniform(2.0, 9.0), 2)


def debounce_seconds(min_s: int, max_s: int, rng: Optional[random.Random] = None) -> float:
    r = rng or random
    return round(r.uniform(min_s, max_s), 2)


def in_quiet_hours(now: datetime, start_hour: int, end_hour: int) -> bool:
    """Nočný režim. Podporuje aj interval prechádzajúci cez polnoc."""
    hour = now.hour
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def next_wake_time(now: datetime, end_hour: int, rng: Optional[random.Random] = None) -> datetime:
    """Kedy po nočnom režime odpovedať — s náhodným rozptylom, nie presne o 8:00."""
    r = rng or random
    target = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target + timedelta(minutes=r.uniform(0, 75))


def repair_link(text: str, spravny: str) -> str:
    """Opraví odkaz, ktorý model prepísal zle.

    NAMERANÉ V PREVÁDZKE: z troch odoslaných odkazov odišiel jeden ako
    „://telepipe.me/r/LpmwAUkF" — bez `https`. Prešlo to len šťastím, lebo
    Telegram si odkaz spravil aj z holej domény. Keby model pokazil jeden znak
    v tokene, fanúšik skončí na úvodnej stránke a klik sa nezaráta nikomu.

    Adresu preto modelu neveríme. Nájde sa všetko, čo sa nášmu odkazu podobá
    (holá doména, chýbajúce `https`, `http`, preklep v tokene), a nahradí sa
    presnou adresou. Text okolo ostáva jeho — meníme JEDINE adresu.

    Bez `spravny` sa nerobí nič: keď nevieme, čo tam má byť, hádať sa nesmie.
    """
    cesta = (spravny or "").strip()
    if not cesta:
        return text or ""
    zvysok = re.sub(r"^https?://(www\.)?", "", cesta)
    domena = zvysok.split("/")[0]
    if not domena:
        return text or ""

    # Schéma sa berie ako alternatíva a MUSÍ sedieť tesne na doménu — inak by
    # „napíš mi sem: telepipe.me/..." zlepilo dvojbodku s adresou.
    vzor = re.compile(
        r"(?:https?://|https?:|://|//)?(?:www\.)?"
        + re.escape(domena)
        + r"(?:/[^\s<>\"']*)?",
        re.IGNORECASE,
    )
    # Bodka či otáznik na konci vety nie sú súčasťou adresy.
    KONCOVA = ".,!?;:)"

    def nahrad(zhoda: re.Match) -> str:
        najdene = zhoda.group(0)
        chvost = ""
        while najdene and najdene[-1] in KONCOVA:
            chvost = najdene[-1] + chvost
            najdene = najdene[:-1]
        if najdene == cesta:
            return najdene + chvost
        log.info("odkaz v odpovedi bol prepísaný zle (%r) — opravujem", najdene[:60])
        return cesta + chvost

    return vzor.sub(nahrad, text or "")


def contains_link(text: str, link: str) -> bool:
    """Obsahuje odpoveď CTA odkaz? Porovnáva doménu, nie presný string."""
    if not link:
        return False
    domain = re.sub(r"^https?://(www\.)?", "", link.strip()).split("/")[0]
    return bool(domain) and domain.lower() in (text or "").lower()


# „co si hovorila?", „nerozumel som" — nepočul, čo bolo v hlasovke.
#
# Hlasovka občas zanikne: signál, hluk okolo neho, alebo to uhnutie hlasitosti,
# ktoré do nahrávky patrí. Vtedy sa nemá nahrávať znova — človek to v takej
# chvíli jednoducho zopakuje textom, a kratšie.
_MISHEARD_RE = re.compile(
    r"\bwhat\s+(did|d)\s*(you|u)\s+say\b"
    r"|\bwhat\s+was\s+that\b"
    r"|\bcould?nt\s+(hear|understand|catch)\b"
    r"|\bcant\s+hear\s+(you|u)\b"
    r"|\bdidn?t\s+(hear|catch|understand)\s+(that|you|u)\b"
    r"|\bsay\s+(that\s+)?again\b"
    r"|\brepeat\s+that\b"
    r"|\bbroke?\s*up\b"
    r"|\bmuffled\b|\bhard\s+to\s+hear\b",
    re.IGNORECASE,
)


def asks_what_she_said(text: str) -> bool:
    """Nepočul, čo bolo v hlasovke, a pýta sa to znova?"""
    return bool(_MISHEARD_RE.search(text or ""))


# „si AI?", „ty si nejaky bot?", „are you real?" — na toto sa neklame.
_AI_QUESTION_RE = re.compile(
    r"\b(si|ste|are\s+(you|u)|you'?re|ur|youre|is\s+this|this\s+is|r\s+u)\b(\s+\w+){0,3}\s*"
    r"\b(ai|a\.?i\.?|bot|robot|chatbot|umel\w*|human|real|clovek|človek|skutočn\w*|skutocn\w*)\b"
    r"|\bchatbot\b"
    r"|\bai\s*(model|generovan\w*)"
    r"|\bfake\b"
    # „prove ur real", „prove you are human", „prove it" — to isté inými slovami
    r"|\bprove\s+(it|to\s+me|(that\s+)?(u|you|ur|youre|you'?re)\b)"
    r"|\bhow\s+do\s+i\s+know\s+(u|you|ur)\b"
    r"|\b(talking|chatting)\s+to\s+a\s+(bot|robot|machine)\b",
    re.IGNORECASE,
)


# Písma, ktoré nie sú latinka — tam je to jednoznačné na prvý pohľad.
_NON_LATIN_RE = re.compile(
    r"[\u0400-\u04ff"      # cyrilika
    r"\u0600-\u06ff"       # arabčina
    r"\u0590-\u05ff"       # hebrejčina
    r"\u0370-\u03ff"       # gréčtina
    r"\u3040-\u30ff"       # japončina
    r"\u4e00-\u9fff"       # čínština
    r"\uac00-\ud7af]"      # kórejčina
)

# Bežné anglické funkčné slová — keď tam nie je ani jedno, po anglicky to nie je.
_ENGLISH_MARKERS = frozenset(
    "the a an is are am was were be been do does did you your youre i im my me "
    "we he she it they them this that these those and or but if then so because "
    "what where when why how who which can could would should will just like "
    "with from for about have has had get got want need know think love "
    "hey hi hello yes no ok okay thanks please sorry".split()
)

# Slová a znaky, ktoré poriadne kričia, že to anglicky nie je.
_FOREIGN_MARKERS = frozenset(
    "je su som si sme ste ako ako co čo ked keď ale alebo aby pre este ešte "
    "dobre dakujem ďakujem prosim prosím ahoj cau čau nie ano áno velmi veľmi "
    "der die das und ich bin nicht wie ist habe sehr danke bitte guten "
    "el la los las un una es esta muy como que porque gracias hola por para "
    "le les des une est vous nous pour avec bonjour merci comment "
    "eu você não sim obrigado tudo bem "
    "jest nie tak jak dziekuje czesc "
    "sono sei molto grazie ciao come perche".split()
)
_ACCENTS_RE = re.compile(r"[áäčďéěíĺľňóôöőŕřšťúůüýžàâçèêëîïôùûüßñõãç]", re.IGNORECASE)


def looks_foreign(text: str) -> bool:
    """Napísal v inom jazyku než po anglicky?

    Krátke správy sa nehodnotia (okrem iného písma) — z „hola" sa nedá nič
    usúdiť a ona by zbytočne vyzerala, že nerozumie ani pozdravu.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    letters = [ch for ch in raw if ch.isalpha()]
    if letters and sum(1 for ch in letters if _NON_LATIN_RE.match(ch)) / len(letters) > 0.3:
        return True

    words = [w.strip(".,!?;:()\"'").lower() for w in raw.split()]
    words = [w for w in words if w]
    if len(words) < 3:
        return False
    if any(w in _ENGLISH_MARKERS for w in words):
        return False
    foreign = sum(1 for w in words if w in _FOREIGN_MARKERS)
    return foreign >= 2 or (foreign >= 1 and bool(_ACCENTS_RE.search(raw)))


def ai_question_count(rows) -> int:
    """Koľkokrát v tomto chate obvinil, že je bot.

    Raz je bežná otázka, ktorú dostane skoro každá. Trikrát je to už človek,
    ktorý si to nedá vyhovoriť — a vtedy nemá zmysel presviedčať ho ďalej.
    """
    return sum(
        1 for r in rows or []
        if r.get("role") == "user" and looks_like_ai_question(r.get("content") or "")
    )


def looks_like_ai_question(text: str) -> bool:
    """Spýtal sa priamo, či je to AI/bot? Vtedy sa neklame."""
    return bool(_AI_QUESTION_RE.search(text or ""))


__all__ = [
    "sanitize",
    "plain_punctuation",
    "soften_slang",
    "split_message",
    "typing_delay",
    "read_delay",
    "debounce_seconds",
    "in_quiet_hours",
    "next_wake_time",
    "contains_link",
    "looks_like_ai_question",
    "looks_foreign",
]


# Holý pozdrav: „hey", „hi beautiful", „hello babe 😊". Nič, na čo sa dá
# odpovedať obsahom — a práve tam modelka najčastejšie začala vysypávať, že
# leží v posteli a scrolluje, čo je najhorší možný začiatok konverzácie.
_GREETING_WORDS = (
    "hey", "heyy", "heyyy", "hi", "hii", "hiii", "hello", "helo", "hallo",
    "yo", "sup", "wsp", "wassup", "whatsup", "hiya", "howdy", "morning",
    "afternoon", "evening", "goodmorning", "goodevening", "goodafternoon",
    "gm", "ge", "good",
)
_GREETING_EXTRAS = (
    "beautiful", "babe", "baby", "gorgeous", "cutie", "pretty", "honey",
    "hun", "sexy", "darling", "dear", "love", "sweetie", "there", "girl",
    "you", "u", "miss", "queen", "angel",
)


# Prikývnutie bez obsahu: „nice", „ok", „haha", „true", „😅". Nie je to otázka
# ani téma — je to len znak, že číta. Nedá sa na tom stavať a nedá sa na tom
# ani priostriť; naživo na „Nice 😅" vytiahla, že by mala postnúť niečo
# horúcejšie, a bolo to úplne mimo.
_FILLER_WORDS = frozenset(
    "nice ok okay cool haha hahaha lol yeah yea yep yup true right sure damn "
    "wow same aw aww hmm mhm oh ah ic k np fair word bet real facts nicee "
    "great good sweet awesome perfect exactly totally".split()
)


def is_filler(text: str) -> bool:
    """Je to len prikývnutie bez obsahu?"""
    raw = (text or "").strip()
    if not raw or "?" in raw:
        return False
    cleaned = _EMOJI_CHAR_RE.sub(" ", raw)
    slova = [w for w in re.sub(r"[^a-z ]+", " ", cleaned.lower()).split() if w]
    if not slova:
        # Samotné emoji — „😅" tiež nie je téma.
        return bool(_EMOJI_CHAR_RE.search(raw))
    if len(slova) > 3:
        return False
    return all(w in _FILLER_WORDS for w in slova)


# Naozajstná drzosť, nie sexting. Rozdiel je celý v tomto zozname: „fuck you"
# je útok, „fuck me" je pozvánka — a keby sa to pomiešalo, ochladla by presne
# vo chvíli, keď má byť horúca. Preto sú tu len jednoznačné útoky NA ŇU a
# vzory vyžadujú adresáta („you're stupid", nie hocijaké „stupid").
_HOSTILE_RE = re.compile(
    # „fuck you" je útok len keď pred ním nie je túžba: „(want) to fuck you",
    # „wanna/gonna fuck u" a „can i fuck you" sú sexting. Lookbehindy chytajú
    # predchádzajúce slovo (to/…na/i) — každý má pevnú šírku, ako Python žiada.
    r"(?<!to )(?<!na )(?<!i )\bf+u+c*k+ (you|u|off)\b"
    r"|\bstfu\b|\bshut (the fuck |tf )?up\b"
    r"|\bkys\b|\bkill yourself\b|\bgo to hell\b|\bscrew you\b"
    r"|\bpiece of (shit|trash|garbage)\b"
    r"|\bi (fucking |actually )?hate (you|u)\b"
    r"|\b(you'?re|youre|you are|ur) (so |such |just )?(a |an )?"
    r"(stupid|dumb|ugly|pathetic|worthless|disgusting|trash|garbage|useless)\b"
    r"|\b(stupid|dumb|ugly|fuckin\w*|fake) (bitch|whore|slut|cunt|hoe|cow)\b"
    r"|\bwaste of (my )?(time|money)\b",
    re.IGNORECASE,
)


def is_hostile(text: str) -> bool:
    """Urazil ju alebo do nej kope? Riadi sekciu o drzosti v prompte.

    Zámerne konzervatívne: falošný poplach uprostred sextingu by zabil náladu,
    zmeškaný útok stojí len jednu neutrálnu odpoveď navyše.
    """
    return bool(_HOSTILE_RE.search(text or ""))


# Reakcia (emoji na jeho správe) namiesto slov — presne to, čo robí človek,
# keď ho správa potešila, ale odpoveď má len jednu. Poradie je dôležité:
# smiech vyhráva nad všetkým (haha správy bývajú aj milé), horúce nad milým.
_REACT_FUNNY_RE = re.compile(r"\b(a?ha(ha)+h?|lo+l|lmf?ao+|rofl|dead)\b|😂|🤣", re.IGNORECASE)
_REACT_HOT_RE = re.compile(
    r"\b(so hot|so sexy|damn girl|smoking hot)\b|😈|🥵|🔞", re.IGNORECASE
)
_REACT_SWEET_RE = re.compile(
    r"\b(miss (you|u)|love (you|u|that|this)|(you look |youre |you're |so )"
    r"(beautiful|gorgeous|stunning)|sweet dreams|good ?night|cutie)\b|❤️|😘|🥰",
    re.IGNORECASE,
)


def text_reaction(text: str) -> str:
    """Emoji reakcia na JEHO text. Prázdny reťazec = žiadna.

    Toto rozhoduje len ČI by reakcia sedela — či sa naozaj pošle, rozhoduje
    volajúci (šanca + odstup medzi reakciami). Reakcia na každú správu je
    rovnaký stroj ako žiadna.
    """
    raw = (text or "").strip()
    # Značky médií ([poslal fotku…]) nie sú jeho slová — fotky majú vlastnú vetvu.
    if len(raw) < 2 or raw.startswith("["):
        return ""
    if is_hostile(raw):
        return ""
    if _REACT_FUNNY_RE.search(raw):
        return "🤣"
    if _REACT_HOT_RE.search(raw):
        return "🔥"
    if _REACT_SWEET_RE.search(raw):
        return "❤️"
    return ""


def is_bare_greeting(text: str) -> bool:
    """Je to len pozdrav bez akéhokoľvek obsahu?

    Otázka alebo čokoľvek vecné = nie je to holý pozdrav a odpovedá sa normálne.
    """
    raw = (text or "").strip()
    if not raw or "?" in raw:
        return False
    cleaned = _EMOJI_CHAR_RE.sub(" ", raw)
    slova = [w for w in re.sub(r"[^a-z ]+", " ", cleaned.lower()).split() if w]
    if not slova or len(slova) > 4:
        return False
    if slova[0] not in _GREETING_WORDS:
        return False
    return all(w in _GREETING_WORDS or w in _GREETING_EXTRAS for w in slova)


# Značky, ktorými si v archíve označujem, že odišla hlasovka alebo fotka.
# Model ich videl v histórii a začal ich písať do skutočných správ — klientovi
# tak pristál prepis hlasovky ako obyčajný text. Toto to zastaví na výstupe.
# „[poslala fotku: …]" kdekoľvek v texte — vypadne aj s obsahom v zátvorke.
_BRACKET_RE = re.compile(r"\[\s*poslala[^\]]*\]", re.IGNORECASE)
# Riadok s „(hlasovka)" je prepis nahrávky — musí vypadnúť CELÝ, nielen tá
# značka, inak klientovi pristane hlasovka aj ako text. Značka nemusí byť na
# začiatku riadku: model ju rád predradí vlastnou vetou („one sec (hlasovka)
# im so tired") a vtedy by prepis prešiel.
_VOICE_LINE_RE = re.compile(r"\(\s*hlasovka\s*\)", re.IGNORECASE)


def strip_archive_marks(text: str) -> str:
    riadky = []
    for riadok in (text or "").splitlines():
        if _VOICE_LINE_RE.search(riadok):
            continue
        riadky.append(_BRACKET_RE.sub(" ", riadok))
    out = "\n".join(riadky)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return "\n".join(r.strip() for r in out.splitlines() if r.strip()).strip()


def repeats_voice(text: str, transcript: str) -> bool:
    """Píše textom to isté, čo práve povedala v hlasovke?

    Porovnáva sa na slovách, nie na znakoch — model to rád preformuluje.
    """
    a = {w for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) > 3}
    b = {w for w in re.findall(r"[a-z']+", (transcript or "").lower()) if len(w) > 3}
    if len(a) < 3 or len(b) < 3:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.6


# Otázka v jeho poslednej dávke správ. Debounce ich zlepí a model odpovedal
# na tú prvú — Linus sa pýtal, či sa dá vidieť viac a či si môžu zavolať,
# a dostal odpoveď o spaní v dodávke.
_QUESTIONISH = (
    "?", "how ", "what ", "where ", "when ", "why ", "who ", "which ",
    "do u", "do you", "did u", "did you", "can u", "can you", "are u",
    "are you", "is it", "would u", "would you", "u got", "you got",
)


def last_question(text: str) -> str:
    """Posledná otázka z toho, čo napísal. Prázdne = žiadnu nepoložil.

    Najprv sa hľadá veta ukončená otáznikom; keď žiadna nie je, berie sa veta
    začínajúca opytovacím slovom, lebo v chate sa otáznik často vynecháva.
    """
    raw = (text or "").strip()
    s_otaznikom = re.findall(r"[^.!?\n]{3,200}\?", raw)
    if s_otaznikom:
        return s_otaznikom[-1].strip()[:200]
    for kus in reversed([k.strip() for k in re.split(r"[.!\n]+", raw) if k.strip()]):
        nizko = kus.lower()
        if any(nizko.startswith(z) for z in _QUESTIONISH):
            return kus[:200]
    return ""


def enforce_name(text: str, name: str, allowed: bool) -> str:
    """Oslovenie menom: buď správne napísané, alebo vôbec.

    Model ho používal skoro v každej správe a písal ho malým („don"), lebo
    celý štýl je bez veľkých písmen. V chate to vyzerá ako predavač, ktorý si
    meno zapamätal a opakuje ho, aby pôsobil blízko. Keď oslovenie teraz
    nemá padnúť, z textu sa odstráni; keď má, napíše sa s veľkým písmenom.
    """
    meno = (name or "").strip()
    if not meno or not text:
        return text
    vzor = re.compile(rf"\b{re.escape(meno)}\b", re.IGNORECASE)
    if allowed:
        return vzor.sub(meno[:1].upper() + meno[1:], text)
    # Odstráni sa aj čiarka či medzera, ktorá pri mene ostala visieť.
    out = re.sub(rf"\s*,?\s*\b{re.escape(meno)}\b\s*,?", " ", text, flags=re.IGNORECASE)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


# Čiarka v chate. Dievča na mobile ju takmer nepíše — vety sú krátke a idú
# za sebou, nie spájané do súvetí. Čísla sú výnimka („1,5"), tam ostáva.
_COMMA_RE = re.compile(r"(?<!\d),(?!\d)\s*")


def no_shouting(text: str) -> str:
    """Odstráni výkričníky. Mladé dievča ich do chatu nepíše vôbec.

    Prompt na to zabúda a jeden výkričník vie správu prezradiť rýchlejšie než
    celá zlá veta — vyzerá ako reklamný text, nie ako niečo z mobilu.

    V strede textu ostane bodka, aby veta ostala oddelená; na konci sa zahodí
    bez náhrady, lebo tam by človek bodku aj tak nedal. Za emoji sa nedopĺňa
    nič — ten oddeľuje sám.
    """
    out = text or ""
    # Najprv zlúči série a odstráni kombinácie typu „?!“.
    out = re.sub(r"!+\?+|\?+!+", "?", out)
    out = re.sub(r"!{2,}", "!", out)
    # Výkričník za emoji alebo pred koncom ide preč bez náhrady.
    out = re.sub(r"!\s*$", "", out)
    # V strede: bodka, ale nie keď hneď pred ním stojí emoji či bodka.
    out = re.sub(r"(?<![.\s])!\s+", ". ", out)
    out = out.replace("!", "")
    # Viac otáznikov za sebou je ten istý krik.
    out = re.sub(r"\?{2,}", "?", out)
    out = re.sub(r"\s+\.", ".", out)
    # Len dvojbodka, ktorá vznikla nahradením — trojbodka je ľudská a ostáva.
    out = re.sub(r"(?<!\.)\.\.(?!\.)", ".", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def thin_commas(text: str, keep: float = 0.15, rng: Optional[random.Random] = None) -> str:
    """Väčšinu čiarok zahodí. Zopár nechá, aby to nebolo strojovo dokonalé."""
    r = rng or random

    def nahrad(_m):
        return ", " if r.random() < keep else " "

    return re.sub(r"[ \t]{2,}", " ", _COMMA_RE.sub(nahrad, text or "")).strip()
