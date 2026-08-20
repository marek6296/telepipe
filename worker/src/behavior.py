"""Realistické chovanie — časovanie, pauzy, aktívne okno. Čisté funkcie.

Všetko je náhodné v nastavených rozsahoch, aby sa nedal vysledovať vzor.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

REAL = "real"
AI = "ai"

FIELD_LABELS = {
    "mode": "mode",
    "active_tz": "time zone",
    "active_start_min": "active from",
    "active_end_min": "active until",
    "debounce_min_s": "debounce min (s)",
    "debounce_max_s": "debounce max (s)",
    "read_delay_min_s": "time to read min (s)",
    "read_delay_max_s": "time to read max (s)",
    "reply_delay_min_s": "time to reply min (s)",
    "reply_delay_max_s": "time to reply max (s)",
    "seen_only_chance": "chance of 'seen' only",
    "seen_only_min_s": "seen only, then min (s)",
    "seen_only_max_s": "seen only, then max (s)",
    "long_pause_chance": "chance of a long pause",
    "long_pause_min_s": "long pause min (s)",
    "long_pause_max_s": "long pause max (s)",
    "defer_reply_chance": "chance of deferring for hours",
    "defer_min_s": "defer min (s)",
    "defer_max_s": "defer max (s)",
    "greeting_gap_hours": "greets again after (h)",
    "no_diacritics": "no diacritics",
    "slang": "slang",
    "quick_reply_chance": "chance of a quick reply",
    "quick_read_max_s": "quick: seen within (s)",
    "quick_reply_min_s": "quick: reply min (s)",
    "quick_reply_max_s": "quick: reply max (s)",
    "question_chance": "chance she asks a question",
    "chat_days": "days she keeps a chat going",
    "gag_chance": "chance of a cheeky joke",
    "photo_cooldown_min": "gap between photos (min)",
    "photos_enabled": "posielať fotky",
    "summary_every": "summary every N messages",
    "max_replies_per_hour": "max replies/h",
    "max_messages_per_day": "max messages/day",
    "max_links_per_hour": "max links/h",
    "max_outreach_per_hour": "max first-messages/h",
    "max_new_people_per_day": "max new people/day",
    "max_active_chats": "conversations at once",
    "chat_slot_min": "slot frees up after (min)",
    "activity_waves": "activity waves",
    "voices_enabled": "voice notes",
    "voice_chance": "voice note chance",
    "voice_tempo": "speech tempo (×)",
    "voice_ambience_level": "background volume",
    "voice_volume_min": "quietest voice note",
    "voice_volume_max": "loudest voice note",
    "voice_lead_min": "silence at start from",
    "voice_lead_max": "silence at start to",
    "voice_tail_min": "silence at end from",
    "voice_tail_max": "silence at end to",
    "voice_ambience": "room",
    "voice_strength": "voice note quality",
    "voice_when_asked": "voice when she's asked",
    "voice_when_doubted": "voice when doubted",
    "voice_when_he_voices": "voice when he sends voice",
    "voice_when_away": "voice when she's out",
    "voice_on_goodnight": "voice at good night",
    "voice_when_hot": "spicy voice when pushing",
    "morning_enabled": "next-day greeting",
    "morning_max_per_day": "greetings per day",
    "heat": "spiciness",
}

# Čo sa nedá posúvať číslom: prepínače a výbery z pevného zoznamu.
_NON_NUMERIC = (
    "mode", "active_tz", "no_diacritics", "slang", "activity_waves", "heat",
    "voices_enabled", "morning_enabled", "photos_enabled", "voice_ambience", "voice_strength", "voice_source",
    "voice_when_asked", "voice_when_doubted", "voice_when_he_voices",
    "voice_when_away", "voice_on_goodnight", "voice_when_hot",
)

# Výnimky z pravidiel o hlasovkách — prepínače, ktoré sa dajú preklikať.
VOICE_EXCEPTIONS = (
    "voice_when_asked", "voice_when_doubted", "voice_when_he_voices",
    "voice_when_away", "voice_on_goodnight", "voice_when_hot",
)

NUMERIC_FIELDS = tuple(f for f in FIELD_LABELS if f not in _NON_NUMERIC)

# Všetko, čo drží účet mimo dohľadu Telegramu, na jednom mieste. Zoradené od
# toho, čo najviac rozhoduje, po to, čo sa ladí zriedka.
SAFETY_FIELDS = (
    "max_active_chats",
    "chat_slot_min",
    "max_replies_per_hour",
    "max_messages_per_day",
    "max_outreach_per_hour",
    "max_new_people_per_day",
    "morning_max_per_day",
    "max_links_per_hour",
)

# Výbery, ktoré sa v botovi preklikávajú dokola.
AMBIENCE_CYCLE = (
    "home", "bedroom", "kitchen", "bathroom", "car", "outside", "cafe", "gym", "none",
)
STRENGTH_CYCLE = ("soft", "real", "rough")

HEAT_CYCLE = ("mild", "medium", "hot")


@dataclass(frozen=True)
class Behavior:
    mode: str = REAL
    active_tz: str = "America/Los_Angeles"
    active_start_min: int = 732
    active_end_min: int = 150
    debounce_min_s: int = 8
    debounce_max_s: int = 25
    read_delay_min_s: int = 20
    read_delay_max_s: int = 240
    reply_delay_min_s: int = 15
    reply_delay_max_s: int = 150
    seen_only_chance: float = 0.15
    seen_only_min_s: int = 240
    seen_only_max_s: int = 600
    long_pause_chance: float = 0.12
    long_pause_min_s: int = 1200
    long_pause_max_s: int = 2400
    defer_reply_chance: float = 0.01
    defer_min_s: int = 7200
    defer_max_s: int = 10800
    greeting_gap_hours: int = 6
    no_diacritics: bool = True
    slang: str = "light"
    quick_reply_chance: float = 0.30
    quick_read_max_s: int = 5
    quick_reply_min_s: int = 5
    quick_reply_max_s: int = 20
    question_chance: float = 0.45
    # Koľko dní sa s jedným človekom baví, kým stíchne. Viď `taper.py`.
    chat_days: int = 3
    gag_chance: float = 0.07
    # Odstup medzi fotkami. Doteraz sa čítal cez getattr z poľa, ktoré tu
    # nebolo — takže to bola konštanta 45 tváriaca sa ako nastavenie.
    photo_cooldown_min: int = 45
    # Posielať fotky na Telegrame? Default VYPNUTÉ (migrácia 20260819) —
    # bez fotiek v albumoch nie je čo posielať a web to pustí zapnúť len keď
    # v albumoch fotky sú. Album podľa miesta rieši `photos.folder_for`.
    photos_enabled: bool = False
    # Odkial berie hlas: "own" = klientov ElevenLabs kluc, "managed" = nas.
    voice_source: str = "own"
    summary_every: int = 10
    max_replies_per_hour: int = 25
    # Denný strop na ODOSLANÉ SPRÁVY, nie na odpovede — jedna odpoveď sa delí
    # až na tri bubliny a Telegram vidí každú zvlášť. Bez neho dovolil hodinový
    # strop pri 14-hodinovom okne až 560 správ denne; nameraná reálna špička je
    # 96. 0 = bez limitu.
    max_messages_per_day: int = 300
    # Koľkým NOVÝM ľuďom sa smie za 24 h ozvať sama. 0 = bez limitu.
    max_new_people_per_day: int = 20
    max_links_per_hour: int = 2
    # Koľkým ľuďom sa smie za hodinu ozvať SAMA. Odpovedí sa to netýka —
    # odpovedať tomu, kto napísal prvý, nie je vzor, ktorý by komukoľvek vadil.
    # Podozrivé je opačné poradie: účet, ktorý sám oslovuje ľudí, čo oň
    # nepožiadali. Presne to robí ranné oslovenie, a preto je strop tam.
    max_outreach_per_hour: int = 6
    # Koľko rozhovorov vedie NARAZ. Skutočný človek nevedie dvadsať —
    # vedie pár, tie dopíše, a keď utíchnu, pustí sa do ďalších. Kto sa
    # nezmestí, počká; nič sa nestratí, ostáva mu `pending_reply`.
    max_active_chats: int = 5
    # Po akom tichu sa miesto uvoľní. Počíta sa od poslednej správy v tom
    # rozhovore — jeho aj jej, lebo aj čakanie na jeho odpoveď je živý rozhovor.
    chat_slot_min: int = 45
    activity_waves: bool = True
    voices_enabled: bool = True
    eleven_key: str = ""
    eleven_voice_id: str = ""
    voice_ambience: str = "home"
    voice_strength: str = "real"
    voice_chance: float = 0.18
    # Tempo reči. v3 pole `speed` ignoruje, preto sa rýchlosť pri ňom pridáva
    # až pri mixe cez atempo, ktoré nemení výšku hlasu; v2 ju zariadi sám.
    # Nastavené vyššie, než znie prirodzený prednes — do hlasovky sa hovorí
    # citeľne rýchlejšie než sa číta.
    voice_tempo: float = 1.22
    # Ako hlasno je pod hlasom počuť miestnosť.
    voice_ambience_level: float = 0.05
    # Rozsahy, v ktorých sa jednotlivé hlasovky pohybujú (migrácia 029).
    #
    # SÚ TO ROZSAHY, NIE HODNOTY. Každá hlasovka si z nich vylosuje vlastné
    # číslo — v tom je celý zmysel. Séria, v ktorej je každý kus rovnako hlasný
    # a začína rovnako dlhým tichom, sa dá po pár nahrávkach rozoznať; práve to
    # sa celý deň ladilo. Keby si klient nastavil min = max, dostane presne ten
    # strojový výsledok, ale bude to jeho rozhodnutie.
    voice_volume_min: float = 0.07
    voice_volume_max: float = 0.17
    voice_lead_min: float = 1.0
    voice_lead_max: float = 3.0
    voice_tail_min: float = 1.5
    voice_tail_max: float = 4.0
    # Kedy smie hlasovka odísť aj mimo bežných pravidiel.
    #
    # Bežne platí, že sa hlasovkou nezačína a chodí len občas podľa
    # `voice_chance`. Tieto výnimky to obchádzajú, lebo sú to chvíle, keď je
    # hlas najsilnejší — a čakať v nich na šiestu správu alebo na kocku by
    # bola premárnená príležitosť.
    voice_when_asked: bool = True       # sám si ju vypýta
    voice_when_doubted: bool = True     # neverí, že je skutočná
    voice_when_he_voices: bool = True   # sám posiela hlasovky
    voice_when_away: bool = False       # je vonku a „nestíha písať"
    voice_on_goodnight: bool = False    # rozlúčka na konci dňa
    # Odkaz už má, stále tlačí a stále neprešiel. Vtedy je pikantná hlasovka
    # to posledné, čím sa dá pohnúť — a je to práve to, po čom prišiel.
    voice_when_hot: bool = True
    morning_enabled: bool = True
    morning_max_per_day: int = 25
    heat: str = "medium"

    @classmethod
    def from_row(cls, row: Optional[Dict[str, Any]]) -> "Behavior":
        if not row:
            return cls()
        defaults = cls()
        values: Dict[str, Any] = {}
        for field_name in cls.__dataclass_fields__:
            raw = row.get(field_name)
            if raw is None:
                continue
            current = getattr(defaults, field_name)
            if isinstance(current, bool):
                values[field_name] = bool(raw)
            elif isinstance(current, int):
                values[field_name] = int(raw)
            elif isinstance(current, float):
                values[field_name] = float(raw)
            else:
                values[field_name] = str(raw)
        return _ludsky(cls(**values))


# Podlaha, pod ktorú sa nedá nastaviť — nech si klient napíše do políčka čokoľvek.
#
# PREČO TO NIE JE VOĽNÉ. Ostatné nastavenia sú vec vkusu: rýchlejšie, pomalšie,
# viac či menej otázok, to nech si klient nastaví. Tieto štyri čísla ale nie sú
# vkus — pri týchto hodnotách prestane byť modelka človekom. Odpoveď do nuly
# sekúnd, zakaždým rovnako rýchla, s otázkou v každej správe: to nie je „iný
# štýl", to je stroj a Telegramu aj fanúšikom je to zjavné.
#
# Zámerne veľmi nízko. Nie je to náš názor na to, ako sa má odpisovať — je to
# hranica, za ktorou to už nie je odpisovanie.
#
# `question_chance` tu ZÁMERNE NIE JE, hoci otázka v každej správe je rovnaký
# problém. Dá sa totiž zmerať na tom, čo modelka naozaj poslala
# (`ludskost.uz_sa_pytala_dost`), a to je lepšie: strop by len znížil
# pravdepodobnosť, kým meranie vidí výsledok. Navyše by z „pýtaj sa vždy"
# spravil náhodu — teda nastavenie, ktoré robí niečo iné, než hovorí.
MIN_READ_S = 1
MIN_REPLY_S = 3
# Rozptyl medzi min a max. Rovnaké číslo v oboch znamená ROVNAKÝ odstup pri
# každej správe, a pravidelnosť je to prvé, čo si všimne aj človek, aj systém.
MIN_ROZPTYL_S = 5
MAX_QUICK = 0.8


def _ludsky(b: "Behavior") -> "Behavior":
    """Stiahne hodnoty, pri ktorých by modelka prestala pôsobiť ako človek.

    `Behavior` je `frozen`, takže sa nič neprepisuje na mieste — vzniká nová
    inštancia. Je to zámer: nastavenie klienta v databáze ostáva jeho, mení sa
    len to, s čím worker pracuje.
    """
    citanie_min = max(MIN_READ_S, b.read_delay_min_s)
    odpoved_min = max(MIN_REPLY_S, b.reply_delay_min_s)
    return replace(
        b,
        read_delay_min_s=citanie_min,
        reply_delay_min_s=odpoved_min,
        read_delay_max_s=max(citanie_min + MIN_ROZPTYL_S, b.read_delay_max_s),
        reply_delay_max_s=max(odpoved_min + MIN_ROZPTYL_S, b.reply_delay_max_s),
        quick_reply_chance=min(MAX_QUICK, b.quick_reply_chance),
    )


def _span(low: int, high: int, rng: Optional[random.Random]) -> float:
    r = rng or random
    if high < low:
        low, high = high, low
    return round(r.uniform(low, high), 2)


# ---------- aktívne okno ----------

def minutes_of_day(now: datetime) -> int:
    return now.hour * 60 + now.minute


def in_active_window(now: datetime, start_min: int, end_min: int) -> bool:
    """Je teraz v aktívnom okne? Podporuje okno prechádzajúce cez polnoc."""
    if start_min == end_min:
        return True  # 24/7
    current = minutes_of_day(now)
    if start_min < end_min:
        return start_min <= current < end_min
    return current >= start_min or current < end_min


def minutes_until_active(now: datetime, start_min: int, end_min: int) -> int:
    """Koľko minút do začiatku aktívneho okna (0 ak je aktívne)."""
    if in_active_window(now, start_min, end_min):
        return 0
    current = minutes_of_day(now)
    delta = start_min - current
    if delta <= 0:
        delta += 24 * 60
    return delta


def format_window(start_min: int, end_min: int) -> str:
    def hhmm(value: int) -> str:
        return f"{value // 60:02d}:{value % 60:02d}"

    if start_min == end_min:
        return "24/7"
    return f"{hhmm(start_min)}–{hhmm(end_min)}"


# ---------- rozhodnutia o odpovedi ----------

def should_defer_reply(
    behavior: Behavior,
    msg_count: int,
    last_incoming_text: str,
    rng: Optional[random.Random] = None,
) -> float:
    """Občas neodpíše hneď, ale až za pár hodín — ako keď človek zabudne.

    Vracia počet sekúnd odloženia (0 = odpovedz normálne). Nikdy sa neodkladá
    prvá správa ani otázka — na tých by sa dal stratiť záujem.
    """
    if behavior.defer_reply_chance <= 0:
        return 0.0
    if msg_count <= 1:
        return 0.0
    if "?" in (last_incoming_text or ""):
        return 0.0
    r = rng or random
    if r.random() >= behavior.defer_reply_chance:
        return 0.0
    return _span(behavior.defer_min_s, behavior.defer_max_s, rng)


def seen_only_delay(behavior: Behavior, rng: Optional[random.Random] = None) -> float:
    """Ak sa spustí, najprv len „videné“ a odpoveď až po tomto čase."""
    if behavior.seen_only_chance <= 0:
        return 0.0
    r = rng or random
    if r.random() >= behavior.seen_only_chance:
        return 0.0
    return _span(behavior.seen_only_min_s, behavior.seen_only_max_s, rng)


def long_pause_delay(behavior: Behavior, rng: Optional[random.Random] = None) -> float:
    """Občas odíde od telefónu na 20–40 minút."""
    if behavior.long_pause_chance <= 0:
        return 0.0
    r = rng or random
    if r.random() >= behavior.long_pause_chance:
        return 0.0
    return _span(behavior.long_pause_min_s, behavior.long_pause_max_s, rng)


def quick_reply(
    behavior: Behavior,
    incoming_text: str,
    rng: Optional[random.Random] = None,
) -> Optional[tuple]:
    """Občas je pri telefóne a odpovie hneď — (sekundy do videného, do odpovede).

    Vracia None, keď sa režim nespustil. Čas odpovede rastie s dĺžkou jeho
    správy: na „hey" reaguje do pár sekúnd, na odstavec si dá dlhšie, lebo ho
    musí prečítať a napísať viac.
    """
    if behavior.quick_reply_chance <= 0:
        return None
    r = rng or random
    if r.random() >= behavior.quick_reply_chance:
        return None

    words = len((incoming_text or "").split())
    weight = min(words / 40.0, 1.0)
    low, high = behavior.quick_reply_min_s, behavior.quick_reply_max_s
    if high < low:
        low, high = high, low
    target = low + (high - low) * weight
    # ±25 % rozptyl, aby to nebolo vypočítateľné, ale nikdy nad nastavené maximum
    reply_in = round(min(max(target * r.uniform(0.75, 1.25), 1.0), float(high)), 2)
    read_in = round(r.uniform(1.0, max(1.0, behavior.quick_read_max_s)), 2)
    return read_in, reply_in


# ---------- vlny aktivity ----------

# Skutočný človek nie je celý deň rovnako rýchly. Multiplikátor je stabilný
# v rámci hodiny (aby v jednej konverzácii nekmital) a mení sa medzi hodinami.
# Pomalá vlna bola ×1.90 a to samo o sebe vyrobilo z minútovej odpovede
# päťminútovú. Rozdiel medzi hodinami má byť cítiť, ale nie takto.
_WAVES = (
    (0.12, "burst"),   # odpisuje takmer okamžite, aj každú minútu
    (0.40, "rychla"),
    (1.00, "normal"),
    (1.35, "pomala"),
)


def activity_wave(now: datetime, seed: str = "simona") -> tuple:
    """(multiplikátor, názov) pre danú hodinu. Deterministické v rámci hodiny."""
    bucket = random.Random(f"{seed}:{now.date().isoformat()}:{now.hour}").random()
    if bucket < 0.25:
        return _WAVES[0]
    if bucket < 0.60:
        return _WAVES[1]
    if bucket < 0.90:
        return _WAVES[2]
    return _WAVES[3]


def wave_factor(behavior: Behavior, now: datetime, seed: str = "simona") -> float:
    if not behavior.activity_waves:
        return 1.0
    return activity_wave(now, seed)[0]


def read_delay(
    behavior: Behavior,
    rng: Optional[random.Random] = None,
    factor: float = 1.0,
) -> float:
    return round(_span(behavior.read_delay_min_s, behavior.read_delay_max_s, rng) * factor, 2)


def reply_delay(
    behavior: Behavior,
    rng: Optional[random.Random] = None,
    factor: float = 1.0,
) -> float:
    return round(_span(behavior.reply_delay_min_s, behavior.reply_delay_max_s, rng) * factor, 2)


def debounce_delay(behavior: Behavior, rng: Optional[random.Random] = None) -> float:
    return _span(behavior.debounce_min_s, behavior.debounce_max_s, rng)


# ---------- čo práve robí (podľa kalifornského času) ----------

_DAYS_SK = ("pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa")

# Situácie, z ktorých si model môže vybrať. Sú to návrhy, nie príkazy — a sú
# stabilné v rámci hodiny, aby si sama neprotirečila v jednej konverzácii.
_SITUATIONS = {
    "poobede": (
        "práve si vstala a dáva si kávu",
        "je v posilňovni alebo sa z nej vracia",
        "vybavuje veci v meste, je vonku",
        "sedí v kaviarni a nič nerobí",
        "chystá sa na fotenie",
        "upratuje a púšťa si hudbu",
    ),
    "podvecer": (
        "vracia sa domov a je unavená",
        "varí si niečo jednoduché",
        "bola na prechádzke, teraz leží",
        "prezerá si fotky z dneska",
        "chystá sa niekam von s kamoškou",
        "má lenivý večer, nič neplánuje",
    ),
    "vecer": (
        "leží na gauči a pozerá niečo v telefóne",
        "dala si sprchu a chladí sa",
        "počúva hudbu a nič nerobí",
        "je vonku na drinku",
        "leží v posteli a píše si",
        "je jej trochu nudno a hľadá zábavu",
    ),
    "noc": (
        "leží v posteli a nemôže zaspať",
        "je jej teplo a je rozvášnená",
        "je unavená ale ešte nechce spať",
        "je sama doma a je jej nudno",
    ),
}


def part_of_day(now: datetime) -> str:
    hour = now.hour
    if 11 <= hour < 16:
        return "poobede"
    if 16 <= hour < 20:
        return "podvecer"
    if 20 <= hour < 24:
        return "vecer"
    return "noc"


def situation_hint(now: datetime, seed: str = "simona") -> str:
    """Čo práve plauzibilne robí. Stabilné v rámci hodiny."""
    options = _SITUATIONS[part_of_day(now)]
    picker = random.Random(f"{seed}:sit:{now.date().isoformat()}:{now.hour}")
    return picker.choice(options)


def local_time_line(now: datetime, city: str = "") -> str:
    """Presný čas tam, kde modelka býva.

    Mesto sa berie z persony — Simona a Mio žijú v Kalifornii, Ayko v New Yorku,
    takže natvrdo napísaná Kalifornia by tretej modelke klamala.
    """
    kde = f"u teba v {city.strip()}" if city.strip() else "u teba"
    return f"Presný čas {kde}: {_DAYS_SK[now.weekday()]} {now.strftime('%H:%M')}."


# ---------- koniec dňa ----------

def minutes_since_window_start(now: datetime, start_min: int, end_min: int) -> Optional[int]:
    """Koľko minút ubehlo od začiatku aktívneho okna. None = sme mimo neho."""
    if not in_active_window(now, start_min, end_min):
        return None
    current = minutes_of_day(now)
    return (current - start_min) % (24 * 60)


def minutes_to_window_end(now: datetime, start_min: int, end_min: int) -> Optional[int]:
    """Koľko minút do konca aktívneho okna (None ak je 24/7 alebo mimo okna)."""
    if start_min == end_min or not in_active_window(now, start_min, end_min):
        return None
    current = minutes_of_day(now)
    delta = end_min - current
    if delta <= 0:
        delta += 24 * 60
    return delta


def winding_down(now: datetime, start_min: int, end_min: int, window_min: int = 75) -> bool:
    """Blíži sa koniec dňa — má začať uzatvárať a chystať sa spať."""
    left = minutes_to_window_end(now, start_min, end_min)
    return left is not None and left <= window_min


def next_window_open(now: datetime, start_min: int, end_min: int) -> datetime:
    """Kedy sa okno znova otvorí (najbližší začiatok v budúcnosti)."""
    target = now.replace(
        hour=start_min // 60, minute=start_min % 60, second=0, microsecond=0
    )
    if target <= now:
        target += timedelta(days=1)
    return target


# ---------- kontext času pre prompt ----------

def gap_hours(previous: Optional[datetime], now: datetime) -> Optional[float]:
    if not previous:
        return None
    delta = (now - previous).total_seconds() / 3600
    return max(delta, 0.0)


def greeting_allowed(behavior: Behavior, gap: Optional[float]) -> bool:
    """Pozdraviť sa smie len po dlhej medzere — nie 5 minút po predošlej správe."""
    if gap is None:
        return True  # úplne prvá správa
    return gap >= behavior.greeting_gap_hours


def describe_gap(gap: Optional[float]) -> str:
    """Ľudský opis medzery pre prompt."""
    if gap is None:
        return "Toto je jeho prvá správa."
    if gap < 0.05:
        return "Napísal hneď, pokračuje v konverzácii."
    if gap < 1:
        return f"Od tvojej poslednej správy prešlo {int(gap * 60)} minút."
    if gap < 24:
        return f"Od tvojej poslednej správy prešlo {int(gap)} hodín."
    return f"Od tvojej poslednej správy prešlo {int(gap / 24)} dní."


# „idem spať“ — po tom už do ďalšieho cyklu neodpisuje
_GOODNIGHT_RE = re.compile(
    # „sleep well" len keď to nie je otázka na neho („did you sleep well?")
    r"(?<!a )\bgood\s?night\b(?!\s+out)|\bnighty\b|\bgn\b|\bsweet\s+dreams\b"
    r"|(?<!you )(?<!u )\bsleep\s+(well|tight)\b"
    r"|\b(going|goin|off|heading)\s+to\s+(bed|sleep)\b"
    r"|\bi'?m\s+(gonna|going\s+to|off\s+to)\s+(bed|sleep)\b"
    r"|\bgonna\s+(hit\s+the\s+)?(bed|sack|sleep)\b"
    r"|\btime\s+for\s+(bed|sleep)\b",
    re.IGNORECASE,
)


def says_goodnight(text: str) -> bool:
    return bool(_GOODNIGHT_RE.search(text or ""))


def should_sleep_until_morning(
    now: datetime, behavior: "Behavior", her_text: str
) -> Optional[datetime]:
    """Povedala dobrú noc na konci dňa? Vráti čas, dokedy má mlčať.

    Guard na čas je dôležitý: keby o štvrtej poobede odpísala „sleep well“
    jemu (on je v inej zóne), nesmie sa tým uspať na celý deň.
    """
    if not says_goodnight(her_text):
        return None
    if not winding_down(now, behavior.active_start_min, behavior.active_end_min):
        return None
    return next_window_open(now, behavior.active_start_min, behavior.active_end_min)
