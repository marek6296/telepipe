"""Hlasovka na mieru: či ju poslať, odkiaľ znie a ako sa má povedať.

Tri veci stoja medzi napísanou odpoveďou a nahrávkou, ktorá znie ako človek:

  * **Rozhoduje model, nie zhoda slov.** Pri nahratých súboroch stačil prekryv
    slov s prepisom, lebo sa vyberalo z hotovej hŕbky. Keď sa nahrávka vyrába
    na mieru, o jej odoslaní má rozhodnúť ten, kto píše odpoveď — pozná tón,
    tému aj to, čo sa práve deje. Preto smie odpoveď uviesť riadkom
    `[HLAS: pozadie=auto, emocia=unavena]`, ktorý sa do chatu nikdy nedostane.

  * **Miestnosť podľa toho, kde je.** Keď pred piatimi minútami napísala, že je
    v meste, hlasovka nesmie znieť z kuchyne. Zdroj pravdy je rozhovor, nie
    nastavenie — to ostáva len ako východisko, keď z rozhovoru nič nevyplýva.

  * **Hovorená podoba.** Písaná veta prečítaná nahlas znie čítane. Skutočná
    hlasovka začína uprostred myšlienky, opravuje sa a má výplňové slová.

Všetko je fail-open: keď čokoľvek zlyhá, odpoveď odíde ako text.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# Ako sa volajú miestnosti v `eleven.AMBIENCES`. Model ich smie pomenovať aj
# po slovensky, aj po anglicky — prekladá sa to tu, nie v prompte.
_AMBIENCE_ALIASES = {
    "doma": "home", "home": "home", "gauc": "home", "byt": "home",
    "spalna": "bedroom", "bedroom": "bedroom", "postel": "bedroom", "bed": "bedroom",
    "kuchyna": "kitchen", "kitchen": "kitchen",
    "kupelna": "bathroom", "bathroom": "bathroom", "sprcha": "bathroom",
    "auto": "car", "car": "car", "cesta": "car",
    "vonku": "outside", "outside": "outside", "mesto": "outside",
    "street": "outside", "ulica": "outside", "prechadzka": "outside",
    "kaviaren": "cafe", "cafe": "cafe", "kava": "cafe",
    "fitko": "gym", "gym": "gym", "posilnovna": "gym",
    "ticho": "none", "none": "none", "nic": "none",
}

# Kde je, odvodené z toho, čo si napísali. Poradie je dôležité: konkrétnejšie
# miesto vyhráva nad všeobecným, preto sa ide zhora nadol a berie sa prvá zhoda.
_MIESTA: Tuple[Tuple[str, str], ...] = (
    ("gym", r"\b(at the |in the )?gym\b|\bworkout\b|\bworking out\b|\blifting\b|\bleg day\b"),
    ("car", r"\bin (the|my) car\b|\bdriving\b|\bon my way\b|\bstuck in traffic\b"),
    ("cafe", r"\b(at a|in a|at the) (cafe|coffee ?shop|starbucks)\b|\bgetting coffee\b"),
    ("bathroom", r"\bin the (shower|bath|tub)\b|\bjust showered\b|\btaking a bath\b"),
    ("kitchen", r"\bin the kitchen\b|\bcooking\b|\bmaking (food|dinner|lunch|breakfast)\b"),
    ("bedroom", r"\bin bed\b|\blaying in bed\b|\bin my bed\b|\bgoing to sleep\b|\bunder the covers\b"),
    ("outside", r"\boutside\b|\bon a walk\b|\bwalking\b|\bat the beach\b|\bin the park\b"
                r"|\bshopping\b|\brunning errands\b|\bdowntown\b|\bin the city\b"),
    ("home", r"\bon the couch\b|\bat home\b|\bin my (apartment|place|room)\b|\bchilling home\b"),
)
_MIESTA_RE = tuple((meno, re.compile(vzor, re.IGNORECASE)) for meno, vzor in _MIESTA)


# ---------- riadok [HLAS: ...] od modelu ----------

_DIRECTIVE_RE = re.compile(
    r"\[\s*HLAS\s*:([^\]]*)\]",
    re.IGNORECASE,
)


def parse_directive(text: str) -> Tuple[Optional[Dict[str, str]], str]:
    """Odchytí `[HLAS: ...]` a vráti (pokyny, text bez neho).

    Pokyny sú None, keď model hlas nechcel — a to je bežný a správny výsledok.
    Riadok sa odstráni VŽDY, aj keď je pokazený: do chatu nesmie odísť nikdy.
    """
    raw = text or ""
    match = _DIRECTIVE_RE.search(raw)
    cisty = _DIRECTIVE_RE.sub(" ", raw)
    cisty = re.sub(r"[ \t]{2,}", " ", cisty)
    cisty = "\n".join(r.strip() for r in cisty.splitlines())
    cisty = re.sub(r"\n{3,}", "\n\n", cisty).strip()
    if not match:
        return None, cisty

    pokyny: Dict[str, str] = {}
    for kus in match.group(1).split(","):
        if "=" not in kus:
            continue
        kluc, _, hodnota = kus.partition("=")
        kluc = re.sub(r"[^a-z]", "", kluc.strip().lower())
        hodnota = hodnota.strip().strip("\"'").lower()
        if kluc and hodnota:
            pokyny[kluc] = hodnota
    return pokyny, cisty


def ambience_from(
    pokyny: Optional[Dict[str, str]],
    her_recent: Sequence[str] = (),
    claims: Sequence[str] = (),
    fallback: str = "home",
    schedule: str = "",
) -> str:
    """Odkiaľ má hlasovka znieť.

    Poradie dôvery: čo povedal model → dnešný rozvrh → čo si o sebe povedala
    v starších správach → nastavenie. Nastavenie je posledné zámerne: keď je
    podľa rozvrhu v aute, nesmie hlasovka znieť z kuchyne len preto, že to tak
    má niekto nastavené v dashboarde.
    """
    if pokyny:
        surove = pokyny.get("pozadie") or pokyny.get("miesto") or pokyny.get("ambience") or ""
        meno = _AMBIENCE_ALIASES.get(re.sub(r"[^a-z]", "", surove))
        if meno:
            return meno

    # Rozvrh je pred jej staršími správami. Model vidí celú konverzáciu, takže
    # keď pred piatimi minútami napísala, že je v aute, povie to v pokyne
    # vyššie. Keď pokyn nedá, rozhoduje rozvrh — inak by veta spred dvoch
    # hodín („im at the gym") posielala hlasovku z fitka aj z gauča.
    if schedule:
        return schedule

    for text in list(her_recent)[::-1] + list(claims):
        for meno, vzor in _MIESTA_RE:
            if vzor.search(text or ""):
                return meno
    return fallback or "home"


# Značky, ktorými sa v archíve pozná, že hlasovku poslal ON.
_JEHO_HLASOVKA = ("[poslal hlasovku", "[v hlasovke povedal")


def he_sent_voice(text: str) -> bool:
    """Poslal on hlasovku? Rozpoznáva sa zo značky, ktorú robí `_hear_voice`."""
    nizke = (text or "").lower()
    return any(z in nizke for z in _JEHO_HLASOVKA)


def exception_reason(
    behavior,
    asked_for_voice: bool = False,
    doubts_her: bool = False,
    he_voiced: bool = False,
    away: bool = False,
    winding_down: bool = False,
    hot_stuck: bool = False,
) -> str:
    """Prečo smie hlasovka odísť aj mimo bežných pravidiel. "" = žiadny dôvod.

    Bežne sa hlasovkou nezačína a chodí len občas podľa `voice_chance`. Toto sú
    chvíle, keď je hlas najsilnejší a čakať v nich na šiestu správu alebo na
    kocku by bola premárnená príležitosť. Každá sa dá vypnúť zvlášť — Marek
    ich zapína podľa toho, koľko chce míňať.

    Vracia názov dôvodu, nie len True: ide do logu, takže sa dá spätne zistiť,
    prečo tá hlasovka odišla.
    """
    dovody = (
        (asked_for_voice, "voice_when_asked", "vypýtal si ju"),
        (doubts_her, "voice_when_doubted", "neverí, že je skutočná"),
        (he_voiced, "voice_when_he_voices", "sám poslal hlasovku"),
        (away, "voice_when_away", "je vonku a nestíha písať"),
        (winding_down, "voice_on_goodnight", "rozlúčka na koniec dňa"),
        (hot_stuck, "voice_when_hot", "odkaz má, tlačí a stále neprešiel"),
    )
    for nastalo, prepinac, popis in dovody:
        if nastalo and getattr(behavior, prepinac, False):
            return popis
    return ""


def wants_voice(pokyny: Optional[Dict[str, str]]) -> bool:
    """Chcel model túto odpoveď povedať nahlas?"""
    if not pokyny:
        return False
    # Samotná prítomnosť riadku je súhlas; „nie" je poistka, keby ho model
    # napísal aj vtedy, keď hlas nechce.
    return (pokyny.get("posli") or pokyny.get("send") or "ano") not in ("nie", "no", "false", "0")


def tempo_from(pokyny: Optional[Dict[str, str]], fallback: float) -> float:
    """Tempo reči z pokynov. Mimo rozumného rozsahu sa berie nastavenie."""
    if not pokyny:
        return fallback
    try:
        hodnota = float((pokyny.get("tempo") or "").replace(",", "."))
    except ValueError:
        return fallback
    return hodnota if 0.85 <= hodnota <= 1.45 else fallback


# ---------- prepis do hovorenej podoby ----------

_SPOKEN_SYSTEM = """\
Prepíš správu do podoby, ktorú niekto NAHOVORÍ do telefónu ako hlasovku.

Obsah aj význam ostávajú presne tie isté. Mení sa RYTMUS.

Toto je najdôležitejšie: hlas prečíta presne to, čo mu napíšeš. Keď mu dáš
hladkú vetu, prečíta ju ako vetu — rovnomerne, od začiatku do konca, a znie to
ako oznam v rozhlase. Skutočná reč rovnomerná nie je. Zrýchľuje, spomaľuje,
zasekne sa, niečo prehltne a niečo natiahne. Ten rytmus musíš napísať TY,
inak v nahrávke nebude.

AKO SA TO PÍŠE:

1. Nerovnaké vety. Striedaj veľmi krátke s dlhšími. Nikdy tri rovnako dlhé
   za sebou. Krátka veta = dôraz a prirodzené spomalenie.

2. Pauzy píš bodkou alebo tromi bodkami, nie čiarkou. Čiarka je pre hlas
   len nádych, bodka je zastavenie, tri bodky sú váhanie.
       nie:  ugh it was long, i was on my feet all day, im wiped
       áno:  ugh it was long. i was on my feet all day... im so wiped

3. Zaváhania a výplne tam, kde by ich človek naozaj mal — na začiatku
   myšlienky alebo pred niečím, čo si musí premyslieť:
       hmm  ·  like  ·  i mean  ·  honestly  ·  no wait  ·  ok so
   Nie do každej vety. Jedna, nanajvýš dve na celú nahrávku.

4. Občas sa oprav alebo začni znova. To je najsilnejší signál, že hovorí
   človek a nie stroj:
       i was gonna go but... no wait, it was the other one

4b. HĽADANIE SLOVA. Toto je to najľudskejšie a chýba to najviac. Človek
   nevysype peknú vetu jedným dychom — rozbehne ju, zasekne sa na slove
   a doloví ho o chvíľu neskôr:
       we went to that place by the water... uhh... the thai one
       i had that thing... whats it called... the pasta thing
       it was like... i dont know... three hours maybe
   Vetu teda pokojne preruš tromi bodkami a slovo dopovedz až za nimi.
   Nie v každej nahrávke a nikdy nie na tom istom mieste vety — raz hneď
   na začiatku, inokedy až na konci, väčšinou vôbec.

5. Natiahnuté slovo tam, kde niekto premýšľa: „soooo", „i dooont know".
   Veľmi striedmo, nanajvýš raz.

6. Emoji sa nehovoria — vyhoď ich, náladu prenes do slov a do rytmu.
   Skratky rozpíš: „u" na „you", „btw" na „by the way".

7. DYCH. Toto v nahrávkach chýba najviac a je to hneď počuť — človek sa
   medzi myšlienkami nadýchne, stroj nie. Nádych patrí PRED dlhšiu vetu
   alebo tam, kde sa mení téma, výdych za niečo, čo ju stálo silu.
       [inhales] no a potom mi povedal ze...
       ...a to bolo cele. [exhales] neviem
   Nie v každej nahrávke a nikdy nie okato — jeden dych stačí a v krátkej
   hlasovke pokojne ani jeden.

8. Ostatné smerovanie hrania, dokopy s dychom nanajvýš dve na nahrávku:
   [laughs] [sighs] [giggles] [whispers]
   Dávaj ich tam, kde naozaj patria — smiech za vtip, vzdych za únavu.

PRÍKLADY (rovnaký obsah, iný rytmus):

vstup:  just some random cooking show, half watching half scrolling
výstup: hmm just some random cooking show. im like... half watching it,
        half scrolling honestly

vstup:  like fifteen more minutes then im out, legs are toast
výstup: like fifteen more minutes. then im out. [sighs] my legs are toast

vstup:  pretty warm still out here, sun going down now
výstup: its still pretty warm out here actually. [inhales] sun's going down
        now... its kinda nice

POVINNE: každá nahrávka musí mať aspoň JEDNU z týchto vecí —
zaváhanie, veľmi krátku vetu na dôraz, tri bodky uprostred, natiahnuté slovo
alebo tag. Keď len vymeníš čiarku za bodku, je to stále prečítaná veta a hlas
ju odrecituje rovnomerne. Nikdy ale nedávaj všetky naraz — jedna, dve stačia.

NIKDY nič nezopakuj. Tú istú vec nepovedz dvakrát, ani inými slovami.
Nič nedopĺňaj obsahovo — pridávaš rytmus, nie nové informácie.

Vráť IBA výsledný text, nič iné. Žiadne vysvetlenie, žiadne úvodzovky."""


def _strip_emoji(text: str) -> str:
    return re.sub(
        "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff❤️]",
        "",
        text or "",
    )


def says_twice(text: str) -> bool:
    """Zaznie v tom tá istá vec dvakrát?

    Hlasovka má jednu, nanajvýš dve vety, takže zopakovaná trojica slov v nej
    nie je štylistika, ale chyba prepisu. Naživo z jednej vety vyšla nahrávka,
    kde „hey stranger" zaznelo trikrát za sebou.
    """
    slova = re.findall(r"[a-z']+", (text or "").lower())
    if len(slova) < 6:
        return False
    trojice = [" ".join(slova[i : i + 3]) for i in range(len(slova) - 2)]
    return len(trojice) != len(set(trojice))


def fallback_spoken(text: str) -> str:
    """Keď model na prepis nie je po ruke — aspoň to, čo sa nedá povedať.

    Emoji a odkazy sa nahlas nečítajú a skratky znejú ako hláskovanie.
    """
    out = _strip_emoji(text or "")
    for skratka, slovo in (
        (r"\bu\b", "you"), (r"\bur\b", "your"), (r"\br\b", "are"),
        (r"\bbtw\b", "by the way"), (r"\bidk\b", "i dont know"),
        (r"\blol\b", "haha"), (r"\bomg\b", "oh my god"), (r"\btho\b", "though"),
    ):
        out = re.sub(skratka, slovo, out, flags=re.IGNORECASE)
    out = re.sub(r"https?://\S+", "", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


async def to_spoken(llm, text: str, nalada: str = "") -> str:
    """Prepíše odpoveď do hovorenej podoby s tagmi pre v3.

    Zlyhanie nie je problém — vráti sa aspoň očistený text, ktorý sa dá
    prehovoriť. Nahrávka je bonus, nikdy nesmie zdržať odpoveď.
    """
    zaklad = fallback_spoken(text)
    if not zaklad:
        return ""
    zadanie = zaklad if not nalada else f"Nálada: {nalada}\n\nSpráva:\n{zaklad}"
    try:
        out = await llm.structured(_SPOKEN_SYSTEM, zadanie, max_tokens=400, temperature=0.75)
    except Exception as exc:  # noqa: BLE001 - prepis nesmie zhodiť odpoveď
        log.warning("Prepis do hovorenej podoby zlyhal: %s", exc)
        return zaklad
    out = (out or "").strip().strip('"')
    if not out:
        return zaklad
    # Model občas vráti vysvetlenie namiesto textu. Strop bol `+160 znakov`,
    # čo pri krátkej vete znamenalo štvornásobok — a do toho sa zmestilo to
    # isté povedané trikrát. Naživo z „hey stranger, was wondering when ud pop
    # up again" vyšla nahrávka, kde to zaznelo tri razy za sebou.
    # Hovorená podoba je legitímne dlhšia než písaná: pauzy, zaváhania a
    # výplňové slová sú znaky navyše, ale práve ony robia rytmus. Strop je
    # preto voľnejší — proti nafúknutiu chráni detektor opakovania nižšie.
    if len(out) > max(len(zaklad) * 2.0, len(zaklad) + 90):
        log.info("Prepis bol podozrivo dlhý (%s → %s), beriem pôvodný",
                 len(zaklad), len(out))
        return zaklad
    if says_twice(out):
        log.info("Prepis opakoval tú istú vec, beriem pôvodný: %r", out[:80])
        return zaklad
    return out
