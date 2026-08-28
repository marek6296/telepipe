"""Hlasovka vyrobená na mieru, priamo na to, čo práve napísal.

Nahraté hlasovky sú dobré, ale je ich pár a nikdy nesedia presne. Toto je
druhá cesta: text odpovede sa pošle na AI Modelka Web, tam ho prehovorí jej
vlastný hlas cez ElevenLabs a worker to pošle ako hlasovku. Klient tak dostane
hlas odpovedajúci presne na svoju otázku — to už sa nedá odlíšiť od človeka.

Je to zámerne fail-open a zámerne skúpe:

  * bez `VOICE_API_URL` sa nič nedeje a všetko beží ako doteraz
  * keď služba zlyhá alebo mešká, odpoveď odíde ako text — nikdy sa nečaká
  * generuje sa len občas, lebo každá hlasovka stojí peniaze a keby prišla
    na každú správu, je to podozrivejšie než keby neprišla vôbec

Reťaz je rovnaká ako na stránke — voice memo a potom voice realizer. Prvý krok
beží tam (ElevenLabs, jej uložený hlas), druhý tu, lebo realizer na stránke
je ffmpeg v prehliadači a ten sa z workera zavolať nedá. Hodnoty filtrov sú
prevzaté z `lib/voiceFx.ts`, nie vymyslené — sú odladené sluchom oproti
skutočnej nahrávke a raz som si už overil, čo sa stane, keď si ich vymyslím.

Kontrakt endpointu (POST, JSON):
    { "text": "...", "ambience": "home" }
  hlavička:  Authorization: Bearer <VOICE_API_KEY>
  odpoveď:   { "voiceUrl": "...", "ambienceUrl": "...", "ambienceLevel": 0.42 }
"""
from __future__ import annotations

import logging
import math
import random
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# Koľko sekúnd sa čaká na vyrobenie. Dlhšie nemá zmysel — odpoveď musí odísť.
TIMEOUT_S = 90.0

# Ako často z odpovede spraviť hlas, keď je to inak vhodné.
CHANCE = 0.18

# Hlasovka je jedna, nanajvýš dve vety. Nikto do telefónu nenahovorí odsek —
# dlhá hlasovka je monológ a ten sa nikomu nechce počúvať. Keď je odpoveď
# dlhšia, odíde ako text a je to tak správne.
MIN_CHARS = 25
MAX_CHARS = 150


# Testovací účet chce počuť hlas vždy, aj keď je odpoveď kratšia alebo dlhšia,
# než by sa bežne oplatilo nahovoriť. Inak by mu namiesto nahrávky prišiel text
# a nebolo by čo ladiť.
TEST_MIN_CHARS = 4
TEST_MAX_CHARS = 400


def worth_speaking(
    text: str,
    min_chars: int = MIN_CHARS,
    max_chars: int = MAX_CHARS,
) -> bool:
    """Dá sa táto odpoveď povedať nahlas tak, aby to dávalo zmysel?"""
    t = (text or "").strip()
    if not (min_chars <= len(t) <= max_chars):
        return False
    # Odkaz sa nedá prehovoriť a čítať URL nahlas je to najhoršie, čo môže spraviť.
    if "http" in t.lower() or "fanvue" in t.lower():
        return False
    return True


def should_speak(
    text: str,
    rng: Optional[random.Random] = None,
    chance: Optional[float] = None,
) -> bool:
    limit = CHANCE if chance is None else chance
    return worth_speaking(text) and (rng or random).random() < limit


# Telefónny zvuk. Receptúry sú z odladenej sady, „rough" je najužšia — a to
# je tá, ktorá znie ako hlasovka z mobilu. Mäkšie varianty nechávajú hlas
# priveľmi čistý a je počuť, že to nahrával mikrofón, nie telefón.
_RESONANCE = "equalizer=f=1100:t=q:w=1.6:g=2.5,equalizer=f=4500:t=q:w=2.0:g=-3"

_RECIPES = {
    "soft":  {"band": 7600, "bitrate": "32k", "ceiling": 0.95, "bits": 9, "hiss": 0.003},
    "real":  {"band": 7000, "bitrate": "20k", "ceiling": 0.90, "bits": 9, "hiss": 0.004},
    "rough": {"band": 5600, "bitrate": "12k", "ceiling": 0.86, "bits": 7, "hiss": 0.006},
}
_NORMALISE = "loudnorm=I=-20:TP=-3:LRA=11"

# Tempo reči. ElevenLabs v3 pole `speed` ignoruje (odmerané: 6,40 s bez neho,
# 7,20 s s ním), v2 ho poslúchne, ale hrá horšie — preto sa rýchlosť pridáva
# až tu cez atempo, ktoré nemení výšku hlasu.
DEFAULT_TEMPO = 1.12
# Ako hlasno je počuť miestnosť pod hlasom.
DEFAULT_AMBIENCE_LEVEL = 0.05

# Ako sa má ktorá miestnosť správať pod hlasom.
#
# Rovnaké filtre pre všetky boli chyba: spálňa je dunenie za stenou a patrí
# hlboko pod hlas, ale ulica je okolo teba a keď sa oreže rovnako, znie ako
# tá istá spálňa. Rozdiel medzi miestnosťami má byť počuť, nie len tušiť.
#
#   gain — násobič nastavenej hlasitosti
#   high — dokiaľ siaha zhora (Hz); vyššie = viac prítomná, bližšie k mikrofónu
#   low  — odkiaľ zdola (Hz); nižšie = viac dunenia
#   loss — o koľko dB stiahne samotné pásmo znormalizované pozadie. NAMERANÉ
#          (ffmpeg volumedetect, 10 s vzorka z `sound-generation`, po
#          `loudnorm` a `afftdn`), nie odhadnuté — bez toho sa nedá povedať,
#          kde pozadie skončí voči hlasu a voči šumu kapsuly.
_AMBIENCE_MIX = {
    # V posteli v noci nemá nič buchať. Zostáva len tlmené dunenie televízora
    # spoza steny — má sa tušiť, nie počuť.
    "bedroom":  {"gain": 0.30, "low": 55,  "high": 700,  "loss": -23.0},
    # Doma bolo pásmo 70–1400 Hz a pod ním sa z bytu stalo holé hučanie: všetko,
    # čo sa dá rozpoznať — telka za stenou, chladnička, vŕzgnutie podlahy — leží
    # nad 1400 Hz a orez to zmazal. Zhora teda 3200 Hz. Celkovej energie to
    # pridá len necelý decibel, ale je to práve tá, v ktorej sa dá miestnosť
    # rozoznať od šumu.
    "home":     {"gain": 1.00, "low": 60,  "high": 3200, "loss": -23.5},
    "kitchen":  {"gain": 1.10, "low": 80,  "high": 2200, "loss": -25.3},  # chladnička, lyžička
    "bathroom": {"gain": 0.85, "low": 120, "high": 3000, "loss": -28.2},  # kachličky nesú výšky
    "car":      {"gain": 1.60, "low": 40,  "high": 900,  "loss": -21.1},  # motor je dole
    # Na ulici je hluk okolo teba, nie za stenou — tam smie byť výrazný.
    "outside":  {"gain": 2.10, "low": 90,  "high": 3800, "loss": -26.0},
    "cafe":     {"gain": 1.40, "low": 90,  "high": 2600, "loss": -26.0},
    "gym":      {"gain": 1.70, "low": 60,  "high": 2800, "loss": -23.5},  # činky aj hudba
    "none":     {"gain": 0.00, "low": 70,  "high": 1400, "loss": -24.5},
}

# Korekcia hlasitosti miestnosti.
#
# PREČO VÔBEC. Nameral som, kde jednotlivé vrstvy naozaj končia: pozadie pri
# nastavenej hladine 0.05 vyšlo na −52.4 dB, šum kapsuly (`hiss` 0.004 pri
# strength „real") na −52.7 dB. Miestnosť a náš vlastný sykot teda ležali na
# tej istej úrovni — pozadie sa v šume stratilo a z hlasovky bolo počuť iba
# syčanie. Klientovi to znelo, že sa pozadie nerobí vôbec; pritom sa vyrábalo,
# platilo a mixovalo, len ho nebolo za čím počuť.
#
# ×3.0 (+9.5 dB) posunie `home` na −42.9 dB: desať decibelov nad šumom a
# devätnásť pod hlasom. Pomery medzi miestnosťami sa NEMENIA — `gain` ostáva
# tak, ako je vyladený, mení sa spoločná hladina.
AMBIENCE_MAKEUP = 3.0

# Hranice, v ktorých musí miestnosť skončiť, nech ju klient nastaví akokoľvek.
#
# Bez spodnej by tiché miestnosti (spálňa) ležali pod šumom kapsuly a nebolo
# by ich počuť ani pri troche dobrej vôle. Bez hornej by posuvník na maxime
# spravil izbu hlasnejšiu než ju samu — `home` pri hladine 1.0 vychádza na
# −15 dB, teda deväť decibelov NAD hlasom.
AMBIENCE_MIN_OVER_HISS_DB = 6.0
AMBIENCE_MIN_UNDER_VOICE_DB = 6.0

# Stredná hlasitosť bieleho šumu je nižšia než jeho `volume` násobič — namerané
# −52.7 dB pri 0.004, čo je o 4.7 dB menej, než by dal samotný prepočet.
_WHITE_NOISE_OFFSET_DB = -4.7

# Kam `loudnorm` normalizuje hlas, kým sa naň pustí `VOICE_GAIN`.
_NORMALISE_TARGET_DB = -20.0

# Zámerne veľmi krátke stlmenie na samom konci súboru.
#
# NIE JE TO EFEKT. Pozadie hrá do konca nahrávky rovnako hlasno — presne tak,
# ako keď človek dohovorí a ešte chvíľu drží tlačidlo. Toto je len poistka
# proti lupnutiu, ktoré vznikne, keď sa šum utne v nenulovej hodnote. 60 ms je
# pod hranicou, kde by to ucho zaregistrovalo ako stíšenie.
ANTI_CLICK_S = 0.06


def _db(value: float) -> float:
    return 20.0 * math.log10(value) if value > 0 else -120.0


def ambience_mix(name: str, level: float, hiss: float = 0.004) -> tuple:
    """(hlasitosť, dolná hranica, horná hranica) pre danú miestnosť.

    Hlasitosť sa počíta v decibeloch, lebo v nich sú aj hranice: „nad šumom" a
    „pod hlasom" sú pomery, nie násobky, a v násobkoch by ich musel každý
    prepočítavať v hlave.
    """
    r = _AMBIENCE_MIX.get(name or "home", _AMBIENCE_MIX["home"])
    if r["gain"] <= 0:
        return 0.0, r["low"], r["high"]

    surova = max(0.0, level) * r["gain"] * AMBIENCE_MAKEUP
    if surova <= 0:
        return 0.0, r["low"], r["high"]

    # Kde tá hlasitosť po pásme skutočne skončí, a kde ležia obe hranice.
    vysledok_db = r["loss"] + _db(surova)
    sum_db = _db(hiss) + _WHITE_NOISE_OFFSET_DB
    hlas_db = _NORMALISE_TARGET_DB + _db(VOICE_GAIN)
    dolna_db = sum_db + AMBIENCE_MIN_OVER_HISS_DB
    horna_db = hlas_db - AMBIENCE_MIN_UNDER_VOICE_DB

    orezane_db = min(max(vysledok_db, dolna_db), horna_db)
    if orezane_db != vysledok_db:
        surova *= 10.0 ** ((orezane_db - vysledok_db) / 20.0)
    return round(surova, 4), r["low"], r["high"]


def _tempo_filter(tempo: float) -> str:
    """atempo zvláda 0.5–2.0; mimo toho sa reťazí. Praktický rozsah je užší."""
    t = max(0.5, min(2.0, float(tempo or DEFAULT_TEMPO)))
    return f"atempo={t:.3f}"


# Ako hlasno je ona sama oproti miestnosti.
#
# Stíšiť ju nešlo cez `volume` na konci reťazca — ten beží až na celom mixe,
# takže by stiahol aj pozadie. Preto sa hlas stišuje na vlastnej vetve pred
# zmiešaním: miestnosť ostáva presne tam, kde bola, a mení sa len ona.
VOICE_GAIN = 0.65

# Kolísanie hlasitosti jej hlasu a ako dlho trvá jedna vlna.
#
# Profesionálny mikrofón drží úroveň ako pod pravítkom — a práve tá dokonalá
# stálosť je na hlasovke počuť ako prvá. Kto drží telefón v ruke, ten ním
# nechtiac hýbe: hlas raz stúpne, raz klesne. Kolíše len ON, nie miestnosť —
# vzdialenosť od úst sa mení, izba okolo zostáva rovnaká. Predtým to bolo na
# celom mixe, takže sa hýbalo aj pozadie, čo je fyzikálny nezmysel.
VOICE_DRIFT = 0.10
DRIFT_PERIOD_MIN, DRIFT_PERIOD_MAX = 4.5, 9.0

# Náhodné udalosti v hlasitosti.
#
# Aj kolísajúca sínusovka je vzor — pravidelná vlna sa dá po chvíli počuť
# rovnako ako plochá čiara. Skutočná hlasovka má okrem nej zopár nepravidelných
# miest: otočí hlavu a na chvíľu je tichšia, odloží telefón nižšie a vráti ho,
# raz za čas prstom škrtne o mikrofón a jedno slovo zanikne.
#
# Musí ich byť málo. Jedna až tri na krátku nahrávku; keď je toho viac, prestane
# to byť ruka s telefónom a začne to znieť ako pokazená linka.
EVENTS_MIN, EVENTS_MAX = 1, 3
# Krátke uhnutie — otočí hlavu a hlas na chvíľu klesne.
DIP_WIDTH = (0.25, 0.55)
DIP_DEPTH = (0.22, 0.42)
# Občas to uhne poriadne.
BIG_DIP_DEPTH = (0.40, 0.58)
BIG_DIP_CHANCE = 0.25
# Pomalý odchod a návrat — telefón sa vzdiali a zase priblíži.
#
# Toto je hlavná udalosť a musí byť POČUŤ. Jemné kolísanie o pár percent sa
# stratí pod kompresorom a je z neho zase plochá čiara. Skutočná zmena je, keď
# hlas zíde na necelú polovicu a vráti sa — raz za sekundu, inokedy za tri.
# Šírka je preto náhodná v celom tom rozsahu, nie len okolo jednej hodnoty.
GLIDE_WIDTH = (0.7, 2.0)
GLIDE_DEPTH = (0.28, 0.55)
GLIDE_CHANCE = 0.55
# Zádrh na pár stotín, po ktorom jedno slovo nie je rozumieť.
#
# Toto je šanca na CELÚ nahrávku, nie na jednu udalosť — má sa to stať raz za
# veľa hlasoviek. Keby to bolo na udalosť, pri jednej až troch udalostiach by
# zádrh mala každá tretia a z výnimky by bol zvyk.
GLITCH_WIDTH = (0.03, 0.08)
GLITCH_DEPTH = (0.75, 0.92)
GLITCH_CHANCE = 0.05

# Ako často nemá hlas v nahrávke ŽIADNY výkyv — hovorila plynulo a telefón
# držala pevne. Bez toho by mala výkyv každá jedna hlasovka a z výnimky by sa
# stalo pravidlo, ktoré sa dá po pár nahrávkach začuť.
NO_DIPS_CHANCE = 0.35

# Mikrofón v telefóne, nie kondenzátor pred ústami: dolu odrezané dunenie,
# okolo 250 Hz stiahnutá „krabica" z blízkeho snímania a mierne zdôraznené
# stredy, kde telefón nesie zrozumiteľnosť.
_PHONE_MIC = (
    "highpass=f=140,"
    "equalizer=f=250:t=q:w=1.2:g=-3,"
    "equalizer=f=1800:t=q:w=1.8:g=2"
)

# Ticho na začiatku a na konci, kým začne a keď dohovorí.
#
# Človek stlačí nahrávanie, nadýchne sa a až potom začne — a na konci ešte
# chvíľu drží tlačidlo. Nahrávka, ktorá začne prvou slabikou a skončí poslednou,
# je na to príliš presná. Keď je pod ňou miestnosť, v tom tichu je počuť ju,
# čo je presne to, čo sa má stať.
# Jedna až tri sekundy: kým nájde tlačidlo, nadýchne sa a rozhodne sa, čím
# začne. Kratšie ticho pôsobí, akoby nahrávanie spustil stroj presne na slovo.
# Miestnosť pod tým hrá od nultej sekundy — vetva pozadia sa NEODKLADÁ, odkladá
# sa len hlas, takže poslucháč najprv počuje, kde je, a až potom ju.
LEAD_MIN, LEAD_MAX = 1.0, 3.0
# Koniec je dlhší než začiatok. Človek dohovorí, chvíľu ešte drží tlačidlo a
# až potom nahrávanie zastaví — a v tom tichu dobehne miestnosť do stratena.
TAIL_MIN, TAIL_MAX = 1.5, 4.0

# Ako hlasno vyjde celá hlasovka. Rovnaká hlasitosť zakaždým znie ako výstup
# zo stroja; skutočné hlasovky sú raz tichšie, raz hlasnejšie podľa toho, ako
# ďaleko mal človek telefón od úst.
#
# Rozsah je polovičný oproti prvej verzii — hlasovky boli celkovo prehnane
# hlasné. Filter sedí až za kompresorom a pred limiterom, takže sa stíšenie
# neprežerie späť a prejde celé.
#
# Celý rozsah ide dole a hlavne sa ROZŠIRUJE nadol. Strop 0.26 je pod tým, čo
# bolo predtým bežné; spodok 0.10 je nahrávka, pri ktorej mala telefón položený
# ďalej alebo hovorila potichu, aby ju nebolo počuť vedľa. Práve tie tiché sú
# to, čo sérii chýbalo — keď je každá rovnako blízko úst, je to zjavné.
# Pomer hlasu a miestnosti sa tým nemení, `volume` sedí až na celom mixe.
NOTE_MIN, NOTE_MAX = 0.07, 0.17

# Ako hlasno vyjde miestnosť v tejto konkrétnej nahrávke.
#
# Nastavenie z dashboardu je strop, nie pevná hodnota. Skutočné hlasovky nemajú
# pozadie zakaždým rovnako hlasné — okno je raz otvorené, raz privreté, človek
# stojí raz bližšie k ulici a raz ďalej. Rovnaká hladina v každej nahrávke je
# ďalší vzor, ktorý sa dá po pár hlasovkách rozoznať.
AMBIENCE_JITTER_MIN, AMBIENCE_JITTER_MAX = 0.60, 1.00


def ambience_jitter(rng: Optional[random.Random] = None) -> float:
    """Násobič hlasitosti miestnosti pre túto nahrávku."""
    return round(
        (rng or random).uniform(AMBIENCE_JITTER_MIN, AMBIENCE_JITTER_MAX), 3
    )


# Ako sa miestnosť hýbe POČAS nahrávky.
#
# Jedna hladina na celú hlasovku je vzor ako každý iný: skutočná izba nie je
# celý čas rovnako hlasná. Chladnička sa zapne a vypne, auto prejde a stíchne,
# niekto zavrie dvere vo vedľajšej izbe, ona sa otočí a mikrofón zrazu smeruje
# inam. Preto má pozadie vlastné pomalé vlnenie a k tomu zopár nepravidelných
# miest — a keďže sú vlastné, nekopírujú kolísanie hlasu.
#
# Perióda je dlhšia než pri hlase (ten kolíše s pohybom ruky, izba s dianím
# okolo) a hlavne je zakaždým iná, nech sa dve hlasovky nedajú priložiť na seba.
ROOM_DRIFT = 0.30
# Spodná hranica je NAD hornou hranicou vlnenia hlasu (9.0) schválne: keby sa
# obe vlny mohli trafiť na rovnakú periódu, chytili by sa do fázy a stúpali by
# spolu — a to znie, akoby sa s ňou hýbala celá izba.
ROOM_DRIFT_PERIOD_MIN, ROOM_DRIFT_PERIOD_MAX = 9.5, 18.0

# Udalosti v pozadí. NAHOR aj NADOL — auto sa priblíži a vzdiali, dvere zvuk
# odrežú. Šírka je v sekundách: pozadie sa mení pomalšie než hlas, lebo sa hýbe
# svet, nie ruka.
ROOM_EVENTS_MIN, ROOM_EVENTS_MAX = 1, 4
ROOM_EVENT_WIDTH = (0.6, 2.5)
ROOM_EVENT_DEPTH = (0.20, 0.55)
ROOM_SWELL_CHANCE = 0.55


def room_events(duration: float, rng: Optional[random.Random] = None) -> list:
    """Kedy sa miestnosť nadvihne alebo stíši. Zoznam (čas, zmena, šírka).

    Kladná zmena = zosilnie, záporná = stíši sa. Udalosti sa nesmú prekrývať,
    inak by sa sčítali do jedného dlhého kopca a z nepravidelnosti by bol tvar.
    """
    r = rng or random
    if duration < 3.0:
        return []

    udalosti: list = []
    for _ in range(r.randint(ROOM_EVENTS_MIN, ROOM_EVENTS_MAX)):
        sirka = r.uniform(*ROOM_EVENT_WIDTH)
        kedy = r.uniform(0.2, max(0.3, duration - 0.2))
        zmena = r.uniform(*ROOM_EVENT_DEPTH)
        if r.random() >= ROOM_SWELL_CHANCE:
            zmena = -zmena
        if any(abs(kedy - t) < (sirka + w) * 1.5 for t, _, w in udalosti):
            continue
        udalosti.append((round(kedy, 2), round(zmena, 3), round(sirka, 3)))
    return sorted(udalosti)


def room_expression(
    base: float,
    events: list,
    drift: float = ROOM_DRIFT,
    drift_period: float = 12.0,
) -> str:
    """Výraz pre `volume` na vetve miestnosti — vlnenie plus udalosti.

    Rovnaký tvar ako `volume_expression`, ale zmeny idú oboma smermi a dole je
    poistka na nulu: miestnosť smie stíchnuť, do mínusu ísť nesmie.
    """
    vyraz = f"1+{drift}*sin(2*PI*t/{drift_period:.2f})"
    for kedy, zmena, sirka in events:
        znak = "+" if zmena >= 0 else "-"
        vyraz += f"{znak}{abs(zmena)}*exp(-pow((t-{kedy})/{sirka}\\,2))"
    return f"max(0\\,{base:.5f}*({vyraz}))"

# Rozptyl tempa okolo nastavenej hodnoty.
#
# Malo to byť rozptýlenie, ale bol z toho systematický posun: pri +0.18 nahor a
# len -0.06 nadol, a k tomu 72 % šancou na zrýchlenie, vychádzalo z nastavenia
# 1.22 skutočné tempo v priemere 1.28 a v maxime 1.40. Klient to počul ako
# „strašne rýchlo rozpráva" a mal pravdu — nastavil si 1.22 a dostával 1.28.
#
# Mierny sklon nahor ostáva (pomalý prednes hlasovku prezradí ako prvý), ale
# posun je taký malý, aby sa nastavenie zo slidera dalo brať vážne.
TEMPO_UP = 0.08
TEMPO_DOWN = 0.06
FASTER_CHANCE = 0.60


def volume_events(
    duration: float,
    lead: float = 0.0,
    rng: Optional[random.Random] = None,
) -> list:
    """Kedy, ako hlboko a ako dlho hlas klesne. Zoznam (čas, hĺbka, šírka).

    Udalosti sa nesmú prekrývať — dva klesy cez seba by hlas umlčali úplne.
    Preto sa medzi nimi drží odstup a keď sa ďalšia nezmestí, jednoducho nebude.
    """
    r = rng or random
    if duration < 1.5:
        return []
    # Nie každá hlasovka má výkyv. Keď ho má každá, je pravidelnosťou samotná
    # jeho prítomnosť — a to je ten istý vzor, pred ktorým sa tu chránime.
    if r.random() < NO_DIPS_CHANCE:
        return []
    zaciatok, koniec = lead + 0.4, lead + duration - 0.4
    if koniec <= zaciatok:
        return []

    kolko = r.randint(EVENTS_MIN, EVENTS_MAX if duration >= 5 else EVENTS_MIN + 1)
    druhy = []
    for _ in range(kolko):
        if r.random() < GLIDE_CHANCE:
            druhy.append((GLIDE_WIDTH, GLIDE_DEPTH))
        elif r.random() < BIG_DIP_CHANCE:
            druhy.append((DIP_WIDTH, BIG_DIP_DEPTH))
        else:
            druhy.append((DIP_WIDTH, DIP_DEPTH))
    # Zádrh sa losuje raz za nahrávku, nie za udalosť — inak by ho mala každá
    # tretia hlasovka namiesto jednej z dvadsiatich.
    if r.random() < GLITCH_CHANCE:
        druhy.append((GLITCH_WIDTH, GLITCH_DEPTH))

    udalosti: list = []
    for sirka, hlbka in druhy:
        w = r.uniform(*sirka)
        kedy = r.uniform(zaciatok, koniec)
        # Odstup aspoň na dve šírky, nech sa poklesy nesčítajú do ticha.
        if any(abs(kedy - t) < (w + iw) * 2 for t, _, iw in udalosti):
            continue
        udalosti.append((round(kedy, 2), round(r.uniform(*hlbka), 3), round(w, 3)))
    return sorted(udalosti)


def volume_expression(
    events: list,
    base: float = VOICE_GAIN,
    drift: float = VOICE_DRIFT,
    drift_period: float = 6.5,
) -> str:
    """Výraz pre ffmpeg `volume`. Poklesy sú zvony, nie schody — hlas do nich
    plynulo klesne a plynulo sa vráti, presne ako keď sa telefón vzdiali."""
    vyraz = f"1+{drift}*sin(2*PI*t/{drift_period:.2f})"
    for kedy, hlbka, sirka in events:
        vyraz += f"-{hlbka}*exp(-pow((t-{kedy})/{sirka}\\,2))"
    # Poistka: keby sa dva poklesy predsa len stretli, hlas nesmie ísť do mínusu.
    return f"max(0.02\\,{base}*({vyraz}))"


def _rozsah(hodnoty: Optional[tuple], dolny: float, horny: float) -> tuple:
    """Rozsah od klienta, alebo ten zabudovaný. Prevrátený sa otočí.

    Otáčanie je tu preto, že hodnoty idú z databázy a cez API: `uniform(3, 1)`
    síce nespadne, ale vracia čísla, ktoré nikto nenastavil. Lepšie ticho
    opraviť než ticho losovať mimo toho, čo klient videl na obrazovke.
    """
    if not hodnoty:
        return dolny, horny
    a, b = float(hodnoty[0]), float(hodnoty[1])
    return (a, b) if a <= b else (b, a)


def lead_tail(
    rng: Optional[random.Random] = None,
    lead: Optional[tuple] = None,
    tail: Optional[tuple] = None,
) -> tuple:
    """(ticho pred, ticho po) v sekundách. Zakaždým iné."""
    r = rng or random
    l_od, l_do = _rozsah(lead, LEAD_MIN, LEAD_MAX)
    t_od, t_do = _rozsah(tail, TAIL_MIN, TAIL_MAX)
    return round(r.uniform(l_od, l_do), 2), round(r.uniform(t_od, t_do), 2)


def note_volume(
    rng: Optional[random.Random] = None, rozsah: Optional[tuple] = None
) -> float:
    """Hlasitosť celej hlasovky. Nikdy dvakrát rovnaká."""
    od, do = _rozsah(rozsah, NOTE_MIN, NOTE_MAX)
    return round((rng or random).uniform(od, do), 3)


def wobble_tempo(base: float, rng: Optional[random.Random] = None) -> float:
    """Tempo okolo nastaveného — väčšinou rýchlejšie, občas pomalšie.

    Orezáva sa až VÝSLEDOK: pri základe tesne nad hranicou by odchýlka nadol
    spadla pod 0.5, a to `atempo` odmietne a celý mix by neprešiel.
    """
    r = rng or random
    zaklad = max(0.5, min(2.0, float(base or DEFAULT_TEMPO)))
    if r.random() < FASTER_CHANCE:
        vysledok = zaklad + r.uniform(0.0, TEMPO_UP)
    else:
        vysledok = zaklad - r.uniform(0.0, TEMPO_DOWN)
    return round(max(0.5, min(2.0, vysledok)), 3)


def _chain(
    strength: str,
    tempo: float = DEFAULT_TEMPO,
    volume: Optional[float] = None,
    drift_period: float = 6.5,
    events: Optional[list] = None,
) -> tuple:
    r = _RECIPES.get(strength) or _RECIPES["rough"]
    mic = (
        # Hlasovku nikto nediktuje — hovorí sa v nej rýchlejšie, a pomalý
        # prednes je na nej hneď počuť. atempo nemení výšku hlasu.
        f"{_tempo_filter(tempo)},"
        f"{_PHONE_MIC},"
        f"{_RESONANCE},equalizer=f=2200:t=q:w=1.4:g=3,"
        f"asoftclip=type=tanh,acrusher=bits={r['bits']}:mode=log:aa=1"
    )
    chain = (
        # Krátky odraz izby, nie dozvuk — telefón drží pri ústach.
        "aecho=0.85:0.9:17|29:0.13|0.08,"
        f"highpass=f=200,lowpass=f={r['band']},"
        "equalizer=f=2600:t=q:w=1.6:g=5,equalizer=f=300:t=q:w=1.0:g=-3,"
        "acompressor=threshold=-24dB:ratio=6:attack=5:release=180:makeup=5,"
        # Celková hlasitosť hlasovky. Kolísanie sem nepatrí — to je na vetve
        # hlasu, inak by sa hýbala aj miestnosť.
        f"volume={volume if volume is not None else 0.74:.3f},"
        f"alimiter=limit={r['ceiling']}"
    )
    return mic, chain, r["hiss"], r["bitrate"]


async def _duration(path: str) -> Optional[float]:
    """Dĺžka nahrávky v sekundách. None = nedá sa zistiť.

    Treba ju na to, aby poklesy hlasitosti padli tam, kde sa naozaj hovorí,
    a nie do ticha na okrajoch.
    """
    import asyncio

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        return float((out or b"").decode().strip())
    except Exception as exc:  # noqa: BLE001 - bez dĺžky sa kolísanie preskočí
        log.warning("Dĺžku nahrávky sa nepodarilo zistiť: %s", exc)
        return None


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        r = await client.get(url)
        r.raise_for_status()
        return r.content
    except Exception as exc:  # noqa: BLE001
        log.warning("Kus hlasovky sa nepodarilo stiahnuť: %s", exc)
        return None


async def _mix(
    voice: bytes,
    ambience: Optional[bytes],
    level: float,
    strength: str = "rough",
    tempo: float = DEFAULT_TEMPO,
    ambience_name: str = "home",
    lead: float = 0.0,
    tail: float = 0.0,
    volume: Optional[float] = None,
    drift_period: float = 6.5,
) -> Optional[bytes]:
    """Zmieša hlas s miestnosťou a prežene to telefónom. Výstup je OGG/Opus."""
    import asyncio
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        hlas = os.path.join(tmp, "voice.mp3")
        with open(hlas, "wb") as f:
            f.write(voice)

        vstupy = ["-i", hlas]
        if ambience:
            izba = os.path.join(tmp, "room.mp3")
            with open(izba, "wb") as f:
                f.write(ambience)
            vstupy += ["-i", izba]
        # Šum kapsuly je vstup, nie filter, nech index pozadia neuteká.
        vstupy += ["-f", "lavfi", "-i", "anoisesrc=color=white:sample_rate=44100"]

        sum_index = 2 if ambience else 1
        mic, chain, hiss, bitrate = _chain(strength, tempo, volume, drift_period)
        # Ticho pred a po ide AŽ ZA tempo — inak by ho atempo skrátilo spolu
        # s rečou a z pol sekundy by ostala tretina.
        okraje = ""
        if lead > 0:
            okraje += f",adelay={int(lead * 1000)}:all=1"
        if tail > 0:
            okraje += f",apad=pad_dur={tail:.2f}"

        # Kolísanie hlasitosti sa počíta až tu, lebo potrebuje skutočnú dĺžku
        # reči — inak by poklesy padli do ticha na okrajoch, kde ich nikto
        # nepočuje. Dĺžka je po zrýchlení a posunutá o úvodné ticho.
        trvanie = await _duration(hlas)
        udalosti = volume_events(trvanie / max(tempo, 0.1), lead) if trvanie else []
        if udalosti:
            log.info("Kolísanie hlasitosti: %s", udalosti)
        okraje += (
            ",volume='"
            + volume_expression(udalosti, VOICE_GAIN, VOICE_DRIFT, drift_period)
            + "':eval=frame"
        )

        # POZADIE SA NA KONCI NESTMIEVA.
        #
        # Bolo tu stmievanie cez celý chvost, s odôvodnením, že zvuk sa má
        # stratiť skôr, než nahrávanie skončí. To je ale naopak: keď človek
        # dohovorí a ešte dve sekundy drží tlačidlo, izba okolo neho hrá ďalej
        # rovnako. Stíchnuť môže len tak, že sa nahrávanie zastaví. Klient to
        # počul hneď — ten pomalý úbytok bol jediné, čo na hlasovkách drhlo.
        #
        # Ostáva len 60 ms na samom konci, a to nie je efekt: je to poistka
        # proti lupnutiu, keď sa šum utne v nenulovej hodnote. Kratšie než
        # čokoľvek, čo ucho stihne zaregistrovať ako stíšenie.
        koniec = lead + (trvanie or 0.0) / max(tempo, 0.1) + tail
        dozvuk = (
            f",afade=t=out:st={max(0.0, koniec - ANTI_CLICK_S):.2f}:d={ANTI_CLICK_S}"
            if trvanie else ""
        )

        graf = f"[0:a]{_NORMALISE},{mic}{okraje}[hlas];"
        graf += f"[{sum_index}:a]volume={hiss}[sum];"
        if ambience:
            # Miestnosť je dunenie a vzdialené zvuky, nie sykot. Bez orezu
            # výšok znie generované pozadie ako biely šum pod hlasom.
            # afftdn zoberie zo vzorky široký šum a nechá v nej len to, čo má
            # štruktúru — auto, televízor, kvapku. Bez neho je pozadie sykot
            # bez ohľadu na to, o akú miestnosť sme požiadali.
            # `hiss` ide dnu preto, že spodná hranica hlasitosti miestnosti je
            # daná práve šumom kapsuly — a ten sa líši podľa `strength`.
            hlasitost, dolna, horna = ambience_mix(ambience_name, level, hiss)
            # Miestnosť sa hýbe počas celej nahrávky, nie len na začiatku a na
            # konci: vlastné pomalé vlnenie plus zopár nepravidelných miest,
            # kde niečo prejde alebo stíchne. Vlastné je dôležité — keby sa
            # riadila kolísaním hlasu, znelo by to, akoby sa s ňou hýbala celá
            # izba, a to je fyzikálny nezmysel.
            izba_udalosti = room_events(koniec)
            izba_perioda = random.uniform(ROOM_DRIFT_PERIOD_MIN, ROOM_DRIFT_PERIOD_MAX)
            if izba_udalosti:
                log.info("Pohyb pozadia: %s", izba_udalosti)
            graf += (
                f"[1:a]{_NORMALISE},afftdn=nr=32:nf=-38,"
                f"highpass=f={dolna},lowpass=f={horna},"
                f"volume='{room_expression(hlasitost, izba_udalosti, drift_period=izba_perioda)}'"
                f":eval=frame[izba];"
            )
            graf += "[hlas][izba][sum]amix=inputs=3:duration=first:dropout_transition=0"
        else:
            graf += "[hlas][sum]amix=inputs=2:duration=first:dropout_transition=0"
        graf += f",{chain}{dozvuk}[out]"

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-loglevel", "error", *vstupy,
                "-filter_complex", graf, "-map", "[out]",
                "-c:a", "libopus", "-b:a", bitrate, "-ar", "48000", "-ac", "1",
                "-f", "ogg", "pipe:1",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=120)
        except Exception as exc:  # noqa: BLE001 - radšej text než nič
            log.warning("Mix hlasovky zlyhal: %s", exc)
            return None
        if proc.returncode != 0 or not out:
            log.warning("ffmpeg pri mixe neprešiel: %s", (err or b"")[:200])
            return None
        return out


async def to_mp3(ogg: bytes) -> Optional[bytes]:
    """Prevod hotovej hlasovky do MP3 — LEN pre ukážky na webe.

    PREČO. Hlasovka sa mixuje do Opusu v OGG, lebo presne to Telegram vyžaduje,
    aby ju ukázal ako nahrávku a nie ako priložený súbor. Ten formát ale macOS
    natívne neprehrá a Fanvue ho ako hlasovku neprijme, takže stiahnutá ukážka
    bola Marekovi na nič.

    NA TELEGRAM TO NEMÁ ŽIADNY VPLYV. Odosielaná hlasovka ide ďalej ako OGG;
    toto vzniká navyše a používa sa výhradne na stiahnutie z dashboardu.

    192 kb/s je zámerne vysoko nad zdrojom: prekódovanie už raz stratového
    zvuku pridáva ďalšiu stratu a pri takomto strope je nepočuteľná.

    `None` = nepodarilo sa. Volajúci pokračuje s OGG, ukážka sa nezahodí.
    """
    if not ogg:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100",
            "-f", "mp3", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(ogg), timeout=60)
    except Exception as exc:  # noqa: BLE001 - MP3 je bonus, nie podmienka
        log.warning("Prevod ukážky do MP3 zlyhal: %s", exc)
        return None
    if proc.returncode != 0 or not out:
        log.warning("ffmpeg pri prevode do MP3 neprešiel: %s", (err or b"")[:200])
        return None
    return out


async def speak(
    text: str,
    api_key: str,
    voice_id: str,
    ambience_name: str = "home",
    strength: str = "rough",
    tempo: float = DEFAULT_TEMPO,
    level: float = DEFAULT_AMBIENCE_LEVEL,
    spoken: Optional[str] = None,
    volume_range: Optional[tuple] = None,
    lead_range: Optional[tuple] = None,
    tail_range: Optional[tuple] = None,
) -> Optional[bytes]:
    """Vyrobí hotovú hlasovku: reč + miestnosť + telefón. None = pošli text.

    `spoken` je text pripravený na prednes (s tagmi ako [laughs]). Keď chýba,
    prehovorí sa `text` tak, ako je — do chatu aj do pamäte však ide vždy
    `text`, lebo tagy nie sú slová.
    """
    import eleven

    if not (api_key and voice_id):
        return None
    # Zakaždým trochu inak: iné ticho na okrajoch, iná hlasitosť, iné tempo.
    # Bez toho vyzerá séria hlasoviek ako výstup zo stroja, aj keď je každá
    # o niečom inom.
    lead, tail = lead_tail(lead=lead_range, tail=tail_range)
    hlasitost = note_volume(rozsah=volume_range)
    rychlost = wobble_tempo(tempo)
    # Nastavená hlasitosť miestnosti je strop, nie pevná hodnota.
    izba_hlasitost = round(level * ambience_jitter(), 5)
    # Aj rytmus kolísania je zakaždým iný — pravidelná vlna je sama o sebe vzor.
    perioda = round(random.uniform(DRIFT_PERIOD_MIN, DRIFT_PERIOD_MAX), 2)

    # Tempo sa najprv skúsi priamo pri nahrávaní — tam ho hlas znesie bez ujmy.
    # atempo v mixe je až náhradné riešenie pre model, ktorý `speed` ignoruje.
    hlas, model = await eleven.speech(spoken or text, api_key, voice_id, speed=rychlost)
    if not hlas:
        return None
    if model in eleven.HONOURS_SPEED:
        log.info("Tempo %.2f zariadil priamo %s, atempo netreba", rychlost, model)
        rychlost = 1.0

    # Pozadie je bonus — keď sa nevyrobí, hlas ide sám a nikto to nezbadá.
    # Dĺžka sa odhaduje z textu a musí pokryť aj ticho na okrajoch, inak by
    # miestnosť v tom tichu vypadla a bolo by tam hluché miesto.
    sekundy = max(6.0, len(text.split()) / 2.4 + 3 + lead + tail)
    izba = (
        await eleven.ambience(ambience_name, api_key, sekundy)
        if ambience_name and ambience_name != "none"
        else None
    )
    log.info(
        "Hlasovka: %s, tempo %.2f, hlasitosť %.2f, izba %.4f, ticho %.1f/%.1f s",
        ambience_name, rychlost, hlasitost, izba_hlasitost, lead, tail,
    )
    return await _mix(
        hlas, izba, izba_hlasitost, strength, rychlost, ambience_name,
        lead=lead, tail=tail, volume=hlasitost, drift_period=perioda,
    )
