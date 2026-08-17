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
_AMBIENCE_MIX = {
    # V posteli v noci nemá nič buchať. Zostáva len tlmené dunenie televízora
    # spoza steny — má sa tušiť, nie počuť.
    "bedroom":  {"gain": 0.30, "low": 55,  "high": 700},
    "home":     {"gain": 1.00, "low": 70,  "high": 1400},
    "kitchen":  {"gain": 1.10, "low": 80,  "high": 2200},  # chladnička, lyžička
    "bathroom": {"gain": 0.85, "low": 120, "high": 3000},  # kachličky nesú výšky
    "car":      {"gain": 1.60, "low": 40,  "high": 900},   # motor je dole
    # Na ulici je hluk okolo teba, nie za stenou — tam smie byť výrazný.
    "outside":  {"gain": 2.10, "low": 90,  "high": 3800},
    "cafe":     {"gain": 1.40, "low": 90,  "high": 2600},
    "gym":      {"gain": 1.70, "low": 60,  "high": 2800},  # činky aj hudba
    "none":     {"gain": 0.00, "low": 70,  "high": 1400},
}


def ambience_mix(name: str, level: float) -> tuple:
    """(hlasitosť, dolná hranica, horná hranica) pre danú miestnosť."""
    r = _AMBIENCE_MIX.get(name or "home", _AMBIENCE_MIX["home"])
    return round(max(0.0, level) * r["gain"], 4), r["low"], r["high"]


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
LEAD_MIN, LEAD_MAX = 0.5, 1.5
# Koniec je dlhší než začiatok. Človek dohovorí, chvíľu ešte drží tlačidlo a
# až potom nahrávanie zastaví — a v tom tichu dobehne miestnosť do stratena.
TAIL_MIN, TAIL_MAX = 1.0, 3.0

# Ako hlasno vyjde celá hlasovka. Rovnaká hlasitosť zakaždým znie ako výstup
# zo stroja; skutočné hlasovky sú raz tichšie, raz hlasnejšie podľa toho, ako
# ďaleko mal človek telefón od úst.
#
# Rozsah je polovičný oproti prvej verzii — hlasovky boli celkovo prehnane
# hlasné. Filter sedí až za kompresorom a pred limiterom, takže sa stíšenie
# neprežerie späť a prejde celé.
NOTE_MIN, NOTE_MAX = 0.20, 0.40

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

# Rozptyl tempa okolo nastavenej hodnoty. Skôr rýchlejšie než pomalšie —
# pomalý prednes je na hlasovke to prvé, čo prezradí, že ju nikto nehovoril.
TEMPO_UP = 0.18
TEMPO_DOWN = 0.06
FASTER_CHANCE = 0.72


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


def lead_tail(rng: Optional[random.Random] = None) -> tuple:
    """(ticho pred, ticho po) v sekundách. Zakaždým iné."""
    r = rng or random
    return round(r.uniform(LEAD_MIN, LEAD_MAX), 2), round(r.uniform(TAIL_MIN, TAIL_MAX), 2)


def note_volume(rng: Optional[random.Random] = None) -> float:
    """Hlasitosť celej hlasovky. Nikdy dvakrát rovnaká."""
    return round((rng or random).uniform(NOTE_MIN, NOTE_MAX), 3)


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

        # Keď dohovorí, miestnosť nemá ostať visieť na plnej hlasitosti až do
        # konca súboru — v skutočnej hlasovke sa zvuk stratí do ticha skôr, než
        # nahrávanie skončí. Stmievanie začne presne tam, kde končí reč, a trvá
        # celý chvost.
        stmavni = ""
        if trvanie and tail > 0:
            stmavni = f",afade=t=out:st={lead + trvanie / max(tempo, 0.1):.2f}:d={tail:.2f}"

        graf = f"[0:a]{_NORMALISE},{mic}{okraje}[hlas];"
        graf += f"[{sum_index}:a]volume={hiss}{stmavni}[sum];"
        if ambience:
            # Miestnosť je dunenie a vzdialené zvuky, nie sykot. Bez orezu
            # výšok znie generované pozadie ako biely šum pod hlasom.
            # afftdn zoberie zo vzorky široký šum a nechá v nej len to, čo má
            # štruktúru — auto, televízor, kvapku. Bez neho je pozadie sykot
            # bez ohľadu na to, o akú miestnosť sme požiadali.
            hlasitost, dolna, horna = ambience_mix(ambience_name, level)
            graf += (
                f"[1:a]{_NORMALISE},afftdn=nr=32:nf=-38,"
                f"highpass=f={dolna},lowpass=f={horna},"
                f"volume={hlasitost:.4f}{stmavni}[izba];"
            )
            graf += "[hlas][izba][sum]amix=inputs=3:duration=first:dropout_transition=0"
        else:
            graf += "[hlas][sum]amix=inputs=2:duration=first:dropout_transition=0"
        graf += f",{chain}[out]"

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


async def speak(
    text: str,
    api_key: str,
    voice_id: str,
    ambience_name: str = "home",
    strength: str = "rough",
    tempo: float = DEFAULT_TEMPO,
    level: float = DEFAULT_AMBIENCE_LEVEL,
    spoken: Optional[str] = None,
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
    lead, tail = lead_tail()
    hlasitost = note_volume()
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
