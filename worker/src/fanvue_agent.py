"""Agent na Fanvue — tá istá osoba, iný register.

Na Telegrame ho niekam vedie. Tu ho už nikam viesť netreba: zaplatil, je vnútri.
Preto sa tu odkaz na Fanvue nespomína NIKDY — poslať človeku odkaz na miesto,
kde práve stojí, je najrýchlejší spôsob, ako sa prezradiť.

Rozhovor má dve fázy:

**Zoznamovanie.** Prvé správy nie sú na predaj ani na flirt naplno, ale na
jedinú otázku: kto to je a čo tu hľadá. Niekto chce sexting, niekto priateľku
na písanie, niekto konkrétny obsah. Kým to nevie, nemá podľa čoho sa
rozhodovať — a ponuka naslepo v druhej správe znie ako automat.

**Potom podľa neho.** Keď vie, čo chce, vedie rozhovor tým smerom a obsah
ponúka vtedy, keď to sedí. Nikdy nie natlačene a nikdy ako cenník.

Pamäť, miestny čas aj rozvrh dňa sú tie isté ako na Telegrame — je to tá istá
osoba a nesmie si protirečiť. Líši sa tempo, otvorenosť a to, že tu sa predáva.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import checkout
import den
import fanmatch
import fvflow
import fvmedia
import fvsync
import conversation_timing
import fvtah
import prezradenie
import fvvoice
import ludskost
import oznamy
import prehlad
import zadanie

log = logging.getLogger(__name__)

# Ako často sa pozerá do fronty. Webhook zapisuje do Supabase, agent si ju
# vyberá — priama cesta by znamenala písať odpoveď v tej istej požiadavke
# a Fanvue by ju medzitým vyhodnotil ako nedoručenú.
POLL_S = 5.0
NATIVE_SYNC_S = 30.0

# Ako dlho platí zistenie „v trezore niečo je". Klient obsah nahráva raz za
# čas, nie každú minútu.
_MEDIA_TTL_S = 300.0

ODPOVEDA_NA = "creator.message.received"
NATIVE_SENT = 'creator.message.sent'

# Tri ťahy, medzi ktorými si majiteľ vyberá v poloautomate na Fanvue.
#
# PREČO PRÁVE TIETO. Fanvue nie je Telegram: tu už zaplatil, píše sa horúcejšie
# a predáva sa obsah. Ale kupuje ďalej len ten, kto má pocit, že je s ňou
# v kontakte — takže jeden z troch ťahov musí vždy patriť JEMU, nie predaju.
# Keby boli všetky tri predajné, bola by z toho pokladňa s emoji.
# Uhly návrhov. TRI RÔZNE ŤAHY, nie tri nálady — a INÉ pre cudzieho než pre
# toho, kto už kupoval. Cudziemu je predajný ťah predčasný, kupujúcemu je
# zoznamovacia otázka strata ťahu.
#
# Predajné uhly nie sú vymyslené: sú to Marekove vlastné ťahy z chatov, ktoré
# naozaj predali (64,99 $ a 69,99 $). Postup, ktorý mu tam zabral, bol vždy
# rovnaký — zúž výber → zaváhaj → exkluzivita → fotka s príbehom.
UHLY_ZOZNAMOVANIE = [
    "choď s ním v tom, čo práve píše — ľahko a zvedavo, nič neponúkaj",
    "zisti, čo tu vlastne hľadá — jednou otázkou, nie výsluchom",
    "vráť loptičku jemu — daj najavo, že ťa teší, že je tu, a dostaň z neho "
    "niečo o ňom",
]

UHLY_PREDAJ = [
    # „choď s ním naplno" — bez predaja. Bez tohto by boli všetky tri ponuky.
    "choď priamo s ním v tom, čo práve chce — najhorúcejšia verzia, akú si "
    "dovolíš, bez akejkoľvek ponuky",
    # Naživo: „tell me what u wanna see first and maybe ill tease it" a
    # „You want me sitting or bent over?😈" — z odpovede potom vyplynie ponuka.
    "zúž to na výber — spýtaj sa PRESNE, čo chce vidieť, a to tak, aby sa "
    "z jeho odpovede dalo nadviazať na to, čo preňho máš",
    # Naživo: „but i dont sure if i want share this one 😅" → „never send this
    # one here 😜" → fotka s príbehom. Váhanie predáva lepšie než ponuka.
    "zaváhaj a zdvihni cenu záujmu — naznač, že práve toto nikam nedávaš a "
    "bolo by to len pre neho; ak to pokyn vyššie dovoľuje, sprav z toho ponuku "
    "s krátkym príbehom, inak to nechaj pri náznaku",
]

# Spätná kompatibilita pre volajúcich, ktorí uhly nevyberajú podľa fázy.
UHLY = UHLY_PREDAJ


def uhly_pre(row: Dict[str, Any], settings: Dict[str, Any]) -> List[str]:
    """Ktoré uhly použiť. Rozhoduje tá istá fáza ako v prompte."""
    return UHLY_ZOZNAMOVANIE if phase(row, settings) == "discovery" else UHLY_PREDAJ

# Uhly pre zadanie od majiteľa („napíš mu, že…"). Tému nemení ani jeden — mení
# sa len to, ako ju povie.
UHLY_ZADANIE = [
    "povedz to krátko a priamo",
    "povedz to hravejšie, s náznakom",
    "povedz to vrúcnejšie a osobnejšie",
]


@dataclass(frozen=True)
class Situacia:
    """Kontext jednej chvíle. Viď `FanvueAgent._situacia`."""

    persona: Dict[str, Any]
    behavior: Dict[str, Any]
    teraz: Optional[datetime]
    blok: Any
    kde: str
    pyta_fotku: bool
    pyta_ostre: bool
    moment: str
    foto_ok: bool
    dlzi: bool
    # Ktorý ťah sa práve ponúkol modelke. Zapisuje sa do registra po odoslaní,
    # nech ho ten istý človek nedostane znova.
    tah: Any
    prompt: str
    tip: str

NOVY_ODBERATEL = ("creator.subscription.activated", "subscription.activated")
PLATBA = ("creator.payment.succeeded", "payment.succeeded")


# ---------- čítanie udalostí ----------


def wants_reply(event: Dict[str, Any]) -> bool:
    """Má sa na túto udalosť vôbec odpisovať?

    Prijímame `fan` AJ `creator` odosielateľa: Fanvue značí `sender="creator"`
    vždy, keď píše z creator účtu — teda aj keď Simone napíše INÝ creator (ten
    je v jej chate bežný fanúšik). Sebe-slučku (Simonine vlastné odoslané
    správy majú tiež `sender="creator"`) NErieši toto pole, ale `_reconcile`/
    `stay_quiet` cez REÁLNY stav chatu: `role_of` porovná autora správy
    s `creator_uuid`, takže Simonina vlastná správa = „assistant" → mlčí, kým
    cudzí odosielateľ = „user" → odpovie. Automat na automat je slučka, preto
    `is_automated` filtrujeme vždy.
    """
    if event.get("type") != ODPOVEDA_NA:
        return False
    data = (event.get("payload") or {}).get("data") or {}
    if data.get("is_automated"):
        return False
    if data.get("sender") not in ("fan", "creator"):
        return False
    return bool((data.get("text") or "").strip())


def is_new_subscriber(event: Dict[str, Any]) -> bool:
    return event.get("type") in NOVY_ODBERATEL


def is_payment(event: Dict[str, Any]) -> bool:
    return event.get("type") in PLATBA


def fan_of(event: Dict[str, Any]) -> Dict[str, str]:
    """Kto je za udalosťou. Prázdne `uuid` = nevieme a nič sa nezaznamená.

    `purchaser` je tu draho zaplatená lekcia: pri platbe a pri odbere Fanvue
    fanúšika NEPOSIELA ako `fan`, ale ako `purchaser`. Kým tu ten kľúč chýbal,
    `_record_payment` skončil na prvom riadku a predplatné za 9,99 $ aj dva
    nákupy po ňom sa nezapísali nikde — modelka nevedela, že jej ten človek
    práve zaplatil, a ďalej sa k nemu správala ako k neplatiacemu.
    """
    data = (event.get("payload") or {}).get("data") or {}
    fan = (
        data.get("fan")
        or data.get("purchaser")
        or data.get("user")
        or data.get("subscriber")
        or {}
    )
    result = {
        "uuid": str(fan.get("uuid") or ""),
        "handle": str(fan.get("handle") or ""),
        "display_name": str(fan.get("display_name") or ""),
        "avatar_url": str(fan.get("avatar_url") or ""),
        "text": str(data.get("text") or "").strip() or ('(media)' if data.get('media_uuids') else ''),
    }
    # Only provider message time is trustworthy. Webhook arrival/import time
    # must not make an old message look new to the notification queue.
    times = fvsync.message_times([{**data, 'sentAt': data.get('created_at') or data.get('sentAt')}])
    message_uuid = str(data.get('uuid') or '')
    if message_uuid in times:
        result['_message_uuid'] = message_uuid
        result['_occurred_at'] = times[message_uuid]
    if event.get('type') == NATIVE_SENT:
        result['_source_role'] = 'assistant'
    return result


def paid_cents(event: Dict[str, Any]) -> int:
    """Koľko fanúšik zaplatil, v centoch.

    `gross` je prvé zámerne: to je suma, ktorú zaplatil ON. `net` (bez
    poplatkov Fanvue) je to, čo zostane modelke — ako miera toho, koľko je
    fanúšik ochotný minúť, by podhodnocovala o tretinu. Berie sa až keď nič
    iné nie je.
    """
    data = (event.get("payload") or {}).get("data") or {}
    for key in ("gross", "amount", "amount_cents", "price", "net"):
        try:
            value = int(data.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


# ---------- fázy a rozhodovanie ----------


def phase(row: Dict[str, Any], settings: Dict[str, Any]) -> str:
    """`discovery` = ešte nevie, kto to je. `known` = už vie a vedie podľa toho.

    Prejde sa ďalej, keď buď povedal, čo tu hľadá, alebo si už vymenili
    dosť správ na to, aby ďalšie vypytovanie pôsobilo ako výsluch.

    KTO UŽ KÚPIL, NIE JE CUDZÍ. Naostro mali VŠETCI traja platiaci fanúšikovia
    (30,99 / 64,99 / 69,99 $, tri nákupy každý) fázu `discovery` — a tá vetva
    promptu hovorí „nevieš o ňom nič" a „TERAZ NIČ NEPONÚKAJ A NIČ NEPREDÁVAJ".
    Modelka teda navrhovala zoznamovacie vety človeku, ktorý u nej práve minul
    70 dolárov, a `may_offer` mu nesmela ponúknuť nič. Peniaze sú silnejší
    dôkaz než počítadlo správ.
    """
    if str(row.get("stage") or "") == "known":
        return "known"
    if int(row.get("bought_count") or 0) > 0 or int(row.get("spent_cents") or 0) > 0:
        return "known"
    if str(row.get("wants") or "").strip():
        return "known"
    hranica = int(settings.get("discovery_msgs") or 4)
    return "known" if int(row.get("msg_count") or 0) >= hranica else "discovery"


def may_offer(
    settings: Dict[str, Any],
    row: Dict[str, Any],
    now: Optional[datetime] = None,
) -> bool:
    """Smie teraz ponúknuť platený obsah?

    Tri brzdy naraz: musí to byť zapnuté, musí byť po zoznamovaní a od
    poslednej ponuky musí prejsť odstup. Ponuka v každej druhej správe je
    to isté ako odkaz v každej druhej správe na Telegrame — reklama.
    """
    if not settings.get("sell_content"):
        return False
    if phase(row, settings) == "discovery":
        return False
    if int(row.get("msg_count") or 0) < int(settings.get("offer_after_msgs") or 0):
        return False

    posledna = _ts(row.get("last_offer_at"))
    if posledna:
        odstup = timedelta(hours=float(settings.get("offer_cooldown_h") or 0))
        if (now or datetime.now(timezone.utc)) - posledna < odstup:
            return False
    return True


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def within_hours(settings: Dict[str, Any], now_local: Optional[datetime]) -> bool:
    """Je teraz čas, kedy na Fanvue odpisuje? Rovnaké hranice = vždy."""
    start = int(settings.get("active_start_min") or 0)
    end = int(settings.get("active_end_min") or 0)
    if start == end or now_local is None:
        return True
    minuta = now_local.hour * 60 + now_local.minute
    # Okno cez polnoc (napr. 20:00–02:00) sa musí čítať naopak.
    return start <= minuta < end if start < end else (minuta >= start or minuta < end)


def local_now(behavior: Dict[str, Any]) -> Optional[datetime]:
    """Koľko je hodín tam, kde vraj žije. None = zóna sa nedá prečítať."""
    name = str(behavior.get("active_tz") or "").strip()
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(name))
    except Exception:  # noqa: BLE001 - bez času sa dá odpísať tiež
        return None


# ---------- pamäť ----------


def parse_facts(raw: Any) -> Dict[str, str]:
    """Fakty sú riadky `kľúč: hodnota`. Nečitateľné sa ticho preskočia."""
    out: Dict[str, str] = {}
    for line in str(raw or "").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and value.strip():
            out[key.strip().lower()] = value.strip()
    return out


def merge_facts(existing: Any, found: List[Dict[str, str]], limit: int = 25) -> str:
    """Nové fakty k starým. Novšia hodnota prepíše staršiu pri tom istom kľúči."""
    merged = parse_facts(existing)
    for item in found or []:
        key = str(item.get("key") or "").strip().lower()
        value = str(item.get("value") or "").strip()
        if key and value:
            merged[key] = value[:200]
    # Keď je toho priveľa, staré vypadnú — prompt má svoju kapacitu.
    riadky = [f"{k}: {v}" for k, v in merged.items()][-limit:]
    return "\n".join(riadky)


# ---------- prompt ----------


def build_prompt(
    persona: Dict[str, Any],
    settings: Dict[str, Any],
    fan: Dict[str, Any],
    row: Dict[str, Any],
    tg: Optional[Dict[str, Any]],
    now_local: Optional[datetime] = None,
    blok: Optional[Any] = None,
    pokyn_obsah: str = "",
    behavior: Optional[Dict[str, Any]] = None,
) -> str:
    """Systémový prompt pre Fanvue. Persona je tá istá OSOBA aj HLAS ako na
    Telegrame (rovnaké `CORE_RULES` písanie, štýl, ukážky a slang) — mení sa len
    OBSAH: tu už nikoho neťaháme na Fanvue (je tu), ideme sexting a predaj
    vault obsahu. Bez toho znela roboticky, lebo mala len holý msg_style."""
    import persona as persona_mod
    import jazyky

    meno = persona.get("name") or "ona"
    faza = phase(row, settings)
    behavior = behavior or {}
    riadky: List[str] = [
        f"Si {meno}. Toto je tvoj chat na Fanvue — s človekom, ktorý ti UŽ PLATÍ.",
        "",
        "KTO SI:",
        str(persona.get("backstory") or "").strip(),
        "",
        "AKO PÍŠEŠ (rovnako ľudsky ako v súkromnej správe, nie roboticky):",
        str(persona.get("msg_style") or "").strip(),
        str(persona.get("tone") or "").strip(),
        "",
        persona_mod.CORE_RULES,
        # Tá istá ľudská vrstva ako na Telegrame. Je to tá istá osoba a tie isté
        # situácie — smutná správa, test na bota či hrubosť nevyzerajú na Fanvue
        # inak, len by tam doteraz nemala povedané, čo s nimi.
        ludskost.blok(),
    ]

    # Slang podľa nastavenia modelky — ten istý zdroj ako Telegram.
    slang_rule = persona_mod.SLANG_RULES.get(str(behavior.get("slang") or ""))
    if slang_rule:
        riadky += ["", "SLANG:", slang_rule]
    if behavior.get("no_diacritics"):
        riadky += ["", "Píš BEZ diakritiky (ako sa bežne píše do mobilu)."]

    # Ukážky jej štýlu — najsilnejší anchor pre hlas. Na Telegrame ich má, tu
    # chýbali, a preto Fanvue znelo ako iná osoba.
    ukazky = str(persona.get("examples") or "").strip()
    if ukazky:
        riadky += [
            "",
            "TAKTO PÍŠEŠ (ukážky tvojho štýlu, neopisuj ich doslova):",
            ukazky,
        ]

    riadky += [
        "",
        "NA FANVUE NAVYŠE:",
        fvflow.STYLE,
        "",
        # Jazyky boli na Fanvue dieru: brala sa len voľná veta z `language`,
        # o vedľajších jazykoch prompt nevedel a na cudziu správu nemal pravidlo
        # vôbec. Fan, ktorý napísal po nemecky, tak dostal odpoveď po anglicky
        # od modelky, ktorá na Telegrame po nemecky vie. Teraz je to ten istý
        # zdroj aj tie isté vety ako tam.
        jazyky.pravidlo_hlavneho(persona),
        "",
        jazyky.blok_znalosti(persona, str(persona.get("languages") or "").strip()),
    ]

    # Cudzia správa sa tu nedeteguje priebežne ako na Telegrame — pravidlo preto
    # visí v prompte natrvalo. Je krátke a pre platiaceho fana je horšie, keď mu
    # neodpovie v jeho jazyku, než keď v prompte leží veta navyše.
    riadky += ["", jazyky.blok_cudzia_sprava(persona)]

    if now_local is not None:
        riadky += [
            "",
            "TERAZ:",
            f"U teba je {now_local.strftime('%H:%M')}, {_dnes(now_local)}.",
        ]
        kde = den.describe(blok) if blok is not None else ""
        if kde:
            riadky.append(f"Práve {kde}. Keď sa spýta, čo robíš, odpovedz podľa toho.")

    riadky += ["", "PRAVIDLÁ TOHTO MIESTA:"]
    riadky += [
        "- NIKDY neposielaj odkaz na Fanvue ani naň nepozývaj. Už tu je. "
        "Pozvať ho tam, kde stojí, je najrýchlejší spôsob, ako sa prezradiť.",
        "- Je platiaci zákazník. Správaj sa k nemu tak — má mať pocit, že si "
        "ho vážiš a že má niečo, čo iní nemajú.",
        # Bez tohto to skĺzne do „ďalšia ponuka, ďalšia ponuka". Kupuje ten,
        # kto má pocit, že je s ňou v kontakte — nie ten, komu sa lepšie
        # predáva. Vďačnosť je preto pravidlo, nie ozdoba.
        "- Teší ťa, že ťa podporuje. Nie ako fráza a nie v každej správe — "
        "raz za čas mu daj najavo, že to vidíš a že to niečo znamená, a hneď "
        "sa vráť k rozhovoru. Nikdy sa neponižuj a nikdy nežobri.",
        "- Chceš, aby tu ostal. To znamená aj rozhovor, nielen obsah: pamätaj "
        "si, čo ti povedal, a vráť sa k tomu.",
        "- Píš krátko, ako do chatu. Žiadne odstavce.",
    ]

    if str(settings.get("heat") or "hot") == "hot":
        riadky += ["", fvflow.HOT]

    if faza == "discovery":
        riadky += [
            "",
            "TERAZ SA IBA ZOZNAMUJETE:",
            "Nevieš o ňom nič. Prvé správy sú na to, aby si zistila, KTO to je "
            "a ČO TU HĽADÁ — niekto chce sex chat, niekto sa len rozprávať, "
            "niekto konkrétny obsah.",
            "Začni ľahko, v duchu „hey, what brings you here“ — zvedavo, nie "
            "ako výsluch a nie ako dotazník.",
            "Pýtaj sa po JEDNOM a vždy nadviaž na to, čo povedal.",
            "TERAZ NIČ NEPONÚKAJ A NIČ NEPREDÁVAJ. Kým nevieš, čo chce, "
            "je každá ponuka strela naslepo.",
        ]
        if not tg:
            riadky.append(
                "Nenápadne zisti, či ťa už nepozná odinakiaľ — možno ste už "
                "písali (napr. na Telegrame). Nepýtaj sa priamo, veď to "
                "prirodzene (v duchu „do we know each other?“ alebo „how'd you "
                "find me“), aby si odhalila, či je to niekto, koho už poznáš. "
                "Keď z odpovede pochopíš, že áno, tvár sa, že vieš kto je, nie "
                "že tápeš."
            )
    else:
        riadky += ["", "UŽ HO POZNÁŠ:"]
        chce = str(row.get("wants") or "").strip()
        if chce:
            riadky.append(f"Hľadá tu: {chce}. Veď rozhovor tým smerom.")
        else:
            riadky.append("Veď rozhovor podľa toho, na čo reaguje.")
        # Čo u nej UŽ minul. Doteraz o tom prompt nevedel nič a modelka písala
        # človeku, ktorý u nej nechal 70 dolárov, rovnako ako komukoľvek inému.
        # Sumu vie, ale nikdy ju nevysloví — to znie ako účtenka.
        kupil = int(row.get("bought_count") or 0)
        if kupil:
            riadky.append(
                f"UŽ U TEBA KUPOVAL, a to {kupil}×. Vie, čo za svoje peniaze "
                "dostane, takže ho nemusíš presviedčať — stačí mu dať dôvod "
                "chcieť ďalšie. Sumu ani počet nákupov NIKDY nespomeň nahlas."
            )
        if str(settings.get("heat") or "hot") == "hot" and settings.get("sell_content"):
            riadky += ["", fvflow.PREDAJ_AKO]

    if row:
        riadky += ["", "AKÝ JE TO ČLOVEK:", fvflow.CITANIE[fvflow.reads_as(row)]]

    if pokyn_obsah:
        riadky += ["", "ČO TERAZ S OBSAHOM:", pokyn_obsah]

    fakty = str(row.get("facts") or "").strip()
    if fakty:
        riadky += ["", "ČO O ŇOM VIEŠ:", fakty]

    zhrnutie = str(row.get("summary") or "").strip()
    if zhrnutie:
        riadky += ["", "AKO TO MEDZI VAMI IDE:", zhrnutie]

    hranice = str(persona.get("boundaries") or "").strip()
    if hranice:
        riadky += ["", "ČO NIKDY NEROBÍŠ:", hranice]

    extra = str(settings.get("extra_rules") or "").strip()
    if extra:
        riadky += ["", "ĎALŠIE POKYNY:", extra]

    if tg:
        riadky += ["", "TOHTO ČLOVEKA UŽ POZNÁŠ Z TELEGRAMU:"]
        user = tg.get("user") or {}
        if user.get("first_name"):
            riadky.append(f"- volá sa {user['first_name']}")
        if user.get("summary"):
            riadky.append(f"- ako to medzi vami išlo: {user['summary']}")
        for fact in (tg.get("facts") or [])[:15]:
            if fact.get("key") and fact.get("value"):
                riadky.append(f"- {fact['key']}: {fact['value']}")
        recent = tg.get("recent") or []
        if recent:
            riadky.append("- posledné, čo si písali:")
            for msg in recent[-6:]:
                kto = "on" if msg.get("role") == "user" else "ty"
                riadky.append(f"    {kto}: {str(msg.get('content') or '')[:120]}")
        riadky.append(
            "Nadväzuj na to. Nepýtaj sa znova, čo už vieš, a nehraj sa na cudziu."
        )
    elif fan.get("display_name") or fan.get("handle"):
        riadky += ["", f"Na Fanvue vystupuje ako {fan.get('display_name') or fan.get('handle')}."]

    riadky += [
        "",
        "Odpovedz JEDNOU správou. Bez úvodzoviek, bez podpisu, bez uvádzania mena.",
    ]
    return "\n".join(line for line in riadky if line)


DNI = ("v pondelok", "v utorok", "v stredu", "vo štvrtok", "v piatok", "v sobotu", "v nedeľu")


def _dnes(now_local: datetime) -> str:
    return DNI[now_local.weekday()]


GREETING_PROMPT = (
    "Napíš PRVÚ správu novému predplatiteľovi. Ešte o ňom nič nevieš.\n"
    "Krátko, vrelo a zvedavo — v duchu „hey, what brings you here“. Chceš "
    "zistiť, kto to je a čo tu hľadá.\n"
    "Nič neponúkaj, nič nepredávaj, nepýtaj sa viac než jednu vec.\n"
    "Jedna správa, bez úvodzoviek a bez podpisu."
)


# ---------- beh ----------


class ReplyDeferred(Exception):
    """Udalosť ostáva v trvalej fronte do otvorenia okna alebo zmeny režimu."""


class FanvueAgent:
    """Vyberá frontu udalostí a odpisuje na ne."""

    def __init__(self, db, api, llm, control=None) -> None:
        self._db = db
        self._api = api
        self._llm = llm
        from social_media import for_db
        self._incoming_media = for_db(db, llm)
        # Control bot pre semi-auto schvaľovanie (Fanvue karty chodia do toho
        # istého Telegram bota). Dopĺňa supervisor; bez neho semi len mlčí.
        self._control = control
        self._send_locks = {}
        self._sync_locks = {}
        self._sync_after = ''
        self._sync_pending_offset = 0
        self._sync_discovery_cursor = ''
        self._sync_creator = None
        # Je v trezore čo poslať? Zisťuje sa raz za `_MEDIA_TTL_S`. `-inf`
        # zámerne: `time.monotonic()` beží od štartu stroja, takže nula by
        # v čerstvom kontajneri znamenala, že prvé volanie uverí prednastavenej
        # hodnote namiesto toho, aby sa spýtalo databázy.
        self._media = True
        self._media_at = float("-inf")

    async def _auto_hours_open(self, settings: Dict[str, Any]) -> bool:
        """Spoločný lokálny deň + okno osoby, Fanvue okno je len ďalší limit."""
        try:
            behavior = await self._db.behavior()
            now = local_now(behavior)
            for limits in (behavior, settings):
                start, end = int(limits.get("active_start_min") or 0), int(limits.get("active_end_min") or 0)
                if start != end and (now is None or not within_hours(limits, now)):
                    return False
            if hub := getattr(self._db, "hub", None):
                if now is None:
                    return False
                block, _ = await hub.day(now, den.Rozvrh.from_row(await self._db.schedule()))
                if not block:
                    return False
            return True
        except Exception as exc:  # noqa: BLE001 - neznámy čas neotvára Auto
            log.warning("Fanvue rozvrh sa nedá overiť: %s", exc)
            return False

    async def _history_rows(self, conv_key: str) -> List[Dict[str, Any]]:
        # Legacy standalone adapter has no source timestamps; unknown stays
        # unknown. The tenant adapter preserves occurred_at from Fanvue.
        load = getattr(self._db, "history_rows", self._db.history)
        return await load(conv_key)

    async def _require_auto_hours(self, settings: Dict[str, Any]) -> None:
        if settings.get("reply_mode", "auto") != "auto" or not await self._auto_hours_open(settings):
            raise ReplyDeferred("waiting_for_schedule_or_approval")

    async def _send_checked(self, conv_key, text, *args, proactive=False, approved=False, source_message_id=None):
        lock = self._send_lock(conv_key)
        async with lock:
            return await self._send_checked_locked(conv_key, text, *args, proactive=proactive,
                                                   approved=approved, source_message_id=source_message_id)

    def _send_lock(self, conv_key):
        # Legacy adapters can initialise the agent without its tenant constructor.
        if not hasattr(self, '_send_locks'):
            self._send_locks = {}
        return self._send_locks.setdefault(conv_key, asyncio.Lock())

    async def _source_snapshot(self, conv_key):
        db = getattr(getattr(self, '_control', None), '_db', None)
        snapshot = getattr(db, 'source_snapshot', None)
        return await snapshot('fanvue', conv_key) if snapshot else None

    async def _send_checked_locked(self, conv_key, text, *args, proactive=False, approved=False, source_message_id=None):
        settings = await self._db.settings()
        if settings.get("reply_mode") == "off":
            return None
        hub = getattr(self._db, "hub", None)
        if hub:
            if not await hub.can_reply("fanvue", conv_key, proactive=proactive or bool(args and args[0])):
                return None
            preferences = await hub.restrictions("fanvue", conv_key)
            from instagram_interactions import URL
            if preferences.get("no_links") and URL.search(text or ""):
                return None
            row = await self._db.fan(conv_key) or {}
            if row.get("human_takeover") or not row.get("ai_enabled", True) or settings.get("reply_mode") == "off":
                return None
        if not approved:
            await self._require_auto_hours(settings)
        async def fresh_context():
            if not hasattr(self._api, 'sync_messages'):
                return True
            try:
                row = await self._db.fan(conv_key) or {}
                unanswered = await self._reconcile({'uuid': conv_key, 'text': ''}, row, sync_only=True, process_media=False)
                if source_message_id is not None and await self._source_snapshot(conv_key) != source_message_id:
                    if unanswered and not approved:
                        raise ReplyDeferred('context_changed')
                    return False
                if not proactive and not approved and not unanswered:
                    return False
                return True
            except ReplyDeferred:
                raise
            except Exception:
                if not approved:
                    raise ReplyDeferred('history_unavailable')
                return False
        if not await fresh_context():
            return None
        # Polling a návrhy zostávajú neprečítané. „Seen“ až po kontrolách,
        # bezprostredne pred provider send (aj po schválení v Semi).
        try:
            await self._api.chat_messages(conv_key, limit=1, mark_read=True)
        except Exception as exc:  # noqa: BLE001 - seen nesmie zhodiť odpoveď
            log.warning("Fanvue seen pre %s zlyhalo: %s", conv_key[:8], exc)
        current = await self._db.settings()
        if current.get("reply_mode") == "off":
            return None
        if not approved:
            await self._require_auto_hours(current)
        if not await fresh_context():
            return None
        return await self._api.send(conv_key, text, *args)

    async def run(self) -> None:
        log.info("Fanvue agent beží, kontroluje frontu každých %.0f s", POLL_S)
        sync = asyncio.create_task(self._native_sync_loop())
        try:
            while True:
                try:
                    await self.tick()
                except Exception as exc:  # noqa: BLE001 - slučka nesmie umrieť
                    log.exception("Kolo Fanvue zlyhalo: %s", exc)
                await asyncio.sleep(POLL_S)
        finally:
            sync.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sync

    async def _native_sync_loop(self):
        while True:
            try:
                await self.sync_native_chats()
            except Exception:
                log.warning('Fanvue native chat sync failed', exc_info=True)
            await asyncio.sleep(NATIVE_SYNC_S)

    async def sync_native_chats(self):
        """Five known + five pending chats per round, independently of webhooks."""
        cfg = await self._db.settings()
        if not cfg.get('connected') or not cfg.get('creator_uuid') or not hasattr(self._api, 'sync_messages'):
            return
        if self._sync_creator != cfg['creator_uuid']:
            self._api._sync_walks = {}
            self._sync_discovery_cursor = ''
            self._sync_after = ''
            self._sync_pending_offset = 0
            self._sync_creator = cfg['creator_uuid']
        discovered = []
        if hasattr(self._api, 'chat_page'):
            head = await self._api.chat_page()
            discovered.extend(head['data'])
            cursor = self._sync_discovery_cursor or head.get('nextCursor')
            if cursor:
                page = await self._api.chat_page(cursor)
                discovered.extend(page['data'])
                self._sync_discovery_cursor = page.get('nextCursor') or ''
            else:
                self._sync_discovery_cursor = ''
            current = await self._db.settings()
            if current.get('creator_uuid') != cfg['creator_uuid'] or not current.get('connected'):
                return
        discovered_keys = []
        for chat in discovered:
            person = chat.get('user') or {}
            if key := str(person.get('uuid') or ''):
                await self._ensure_fan({'uuid': key, 'handle': person.get('handle') or '',
                                       'display_name': person.get('displayName') or '',
                                       'avatar_url': person.get('avatarUrl') or ''})
                discovered_keys.append(key)
        rows = await self._db.sync_contacts(after=self._sync_after, limit=5)
        if not rows and self._sync_after:
            rows = await self._db.sync_contacts(limit=5)
        self._sync_after = rows[-1]['fan_uuid'] if len(rows) == 5 else ''
        pending = await self._db.pending_contacts(offset=self._sync_pending_offset, limit=5)
        self._sync_pending_offset = self._sync_pending_offset + len(pending) if len(pending) == 5 else 0
        keys = dict.fromkeys([r['conv_key'] for r in pending] + discovered_keys + [r['fan_uuid'] for r in rows])
        pending_ids = {r['conv_key']: r['id'] for r in pending if r.get('id')}
        for key in keys:
            try:
                row = await self._db.fan(key)
                if row:
                    if key in pending_ids:
                        row['_refresh_pending_id'] = pending_ids[key]
                    await self._reconcile({'uuid': key, 'text': ''}, row, sync_only=True)
                    await self._refresh_native_draft(key, row)
            except Exception:
                log.warning('Fanvue background history unavailable for %s', key[:8])
                if time.monotonic() < getattr(self._api, '_sync_retry_at', 0):
                    break

    async def _refresh_native_draft(self, key, row):
        """Only replace an existing Semi draft retired by this import."""
        state = row.get('history_sync_state') or {}
        pending_id = state.get('refresh_pending_id') or row.get('_refresh_pending_id')
        if not pending_id and (candidate := getattr(self._db, 'refresh_candidate', None)):
            pending_id = await candidate(key)
        if not pending_id:
            return
        cfg = await self._db.settings()
        current = await self._db.fan(key) or {}
        history = await self._history_rows(key)
        eligible = (cfg.get('enabled') and cfg.get('reply_mode') == 'semi'
                    and current.get('ai_enabled', True) and not current.get('human_takeover')
                    and history and history[-1]['role'] == 'user'
                    and await self._db.refreshable_pending(pending_id, key))
        if eligible:
            # This uses the normal fresh-history/generation/source-CAS path,
            # and only Semi. Backfill alone never creates a first proposal.
            await self._reply({'type': ODPOVEDA_NA, 'payload': {'data': {
                'fan': {'uuid': key}, 'sender': 'fan', 'text': history[-1]['content'],
            }}}, cfg)
            if await self._db.refreshable_pending(pending_id, key):
                return  # Generation failed; keep the durable request for retry.
        if state and state.get('complete'):
            await self._db.update_fan(key, {'history_sync_state': None})
            row['history_sync_state'] = None

    async def tick(self) -> None:
        settings = await self._db.settings()
        manual = not settings.get('enabled') or settings.get('reply_mode') == 'off'
        if not manual and fvmedia.due_to_post(settings, datetime.now(timezone.utc)):
            try:
                await self._post_to_feed(settings)
            except Exception as exc:  # noqa: BLE001 - feed nesmie zhodiť odpisovanie
                log.warning("Príspevok na feed zlyhal: %s", exc)

        include_deferred = (
            manual or str(settings.get("reply_mode") or "auto") != "auto"
            or await self._auto_hours_open(settings)
        )
        if include_deferred and settings.get("enabled") and settings.get("reply_mode") != "off":
            await self._retry_pending_thanks()
        events = await self._db.pending(include_deferred=include_deferred)
        if not events:
            return

        # Tri správy za sebou vyrobia tri udalosti. Keby sa odpovedalo na
        # každú, píše trikrát — odpovedá sa na STAV chatu, nie na udalosť.
        # Preto z každého chatu ide do spracovania len tá najnovšia a ostatné
        # sa označia za vybavené bez odpovede.
        posledna: Dict[str, Dict[str, Any]] = {}
        prebite: List[int] = []
        for event in events:
            # Outbound webhooks can arrive after a newer inbound. They refresh
            # history but must never consume that inbound's reply trigger.
            kto = fan_of(event)["uuid"] if event.get('type') == ODPOVEDA_NA else ""
            if not kto:
                continue
            if kto in posledna:
                prebite.append(int(posledna[kto]["id"]))
            posledna[kto] = event

        # Notifikácie idú PRED kontrolou `enabled`. Upozornenie nie je odpoveď:
        # kto si vypol automatické odpisovanie na Fanvue, stále chce vedieť, že
        # mu niekto zaplatil.
        bot_nastavenia = await self._db.control_bot_settings()
        for event in events:
            try:
                if not event.get("notified_at") and await self._db.claim_event_notification(int(event["id"])):
                    await self._oznam(event, bot_nastavenia)
            except Exception as exc:  # noqa: BLE001 — oznam nesmie zhodiť odpisovanie
                log.warning("Oznam k udalosti %s zlyhal: %s", event.get("id"), exc)

        for event in events:
            inbox_only = event.get('type') == NATIVE_SENT or (event.get('type') == ODPOVEDA_NA and (manual or not wants_reply(event)))
            try:
                if int(event["id"]) in prebite:
                    log.info("Udalosť %s prebitá novšou v tom istom chate", event["id"])
                elif inbox_only:
                    fan = fan_of(event)
                    if fan['uuid']:
                        row = await self._ensure_fan(fan)
                        await self._reconcile(fan, row, mark_read=False, sync_only=True)
                elif settings.get("enabled"):
                    await self._dispatch(event, settings)
            except ReplyDeferred:
                # Časové odloženie nie je vybavenie. Mimo okna sa táto
                # udalosť vynechá, aby nové owner notifikácie nehladovali.
                await self._db.defer_event(int(event["id"]))
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("Udalosť %s zlyhala: %s", event.get("id"), exc)
                if inbox_only:
                    continue  # A failed read/import is safe to retry, not handled.
            await self._db.mark_handled(int(event["id"]))

    async def _retry_pending_thanks(self) -> None:
        """Unlock zistený synchronizáciou dobehne aj bez ďalšieho webhooku."""
        for pending in await self._db.pending_thanks():
            try:
                uuid = pending["fan_uuid"]
                row = await self._db.fan(uuid) or {}
                if not row.get("pending_thanks"):
                    continue
                fan = {"uuid": uuid, "handle": row.get("handle") or "",
                       "display_name": row.get("display_name") or "", "text": ""}
                await self._thank(fan, row, await self._db.settings(), 0,
                                  int(row.get("bought_count") or 0))
            except ReplyDeferred:
                break
            except Exception as exc:  # noqa: BLE001 - trvalý príznak ostáva
                log.warning("Čakajúce poďakovanie sa nepodarilo dokončiť: %s", exc)

    async def _oznam(self, event: Dict[str, Any], nastavenia: Dict[str, Any]) -> None:
        """Pošle majiteľovi do control bota, že sa niečo stalo na Fanvue.

        Bez control bota sa ticho nerobí nič — nespárovaná modelka nie je
        porucha, len ešte nemá kam písať.
        """
        if not self._control:
            return

        fan = fan_of(event)
        meno = (fan.get("name") or fan.get("username") or "").strip()
        if meno and fan.get("username") and meno != fan["username"]:
            meno = f"{meno} (@{fan['username']})"
        elif fan.get("username") and not meno:
            meno = f"@{fan['username']}"

        suma = ""
        if is_payment(event):
            centy = paid_cents(event)
            if centy > 0:
                suma = f"${centy / 100:.2f}"

        text = oznamy.sprava_k_udalosti(event, nastavenia, meno_fana=meno, suma=suma)
        if not text:
            return
        # Prišiel z Telegramu? Vtedy je to jediné číslo, ktoré klient naozaj
        # chce vidieť — či sa to písanie vyplatilo. Odkaz si so sebou nesie,
        # komu bol poslaný (`checkout.attributed`), len sa to doteraz na druhej
        # strane nikdy nečítalo.
        odkial = await self._z_telegramu(event, fan)
        if odkial:
            text += f"\n\n💬 From your Telegram chat with {odkial}"
        await self._control.notify(text)

    async def _z_telegramu(self, event: Dict[str, Any], fan: Dict[str, str]) -> str:
        """Meno telegramového človeka za touto udalosťou. Prázdne = nevieme.

        Dve cesty, v poradí istoty: `client_reference_id` z checkout odkazu
        (to je dôkaz) a už spojený riadok fanúšika (to je predchádzajúci
        odhad). Hádať sa tu nesmie — zle spojená platba by klientovi ukázala,
        že mu zarába konverzácia, ktorá s tým nemá nič spoločné.
        """
        if hub := getattr(self._db, "hub", None):
            linked = await hub.linked("fanvue", fan["uuid"], "telegram")
            if not linked:
                return ""
            user = await self._db.get_user(int(linked[0]["external_id"]))
            return str((user or {}).get("first_name") or (user or {}).get("username") or linked[0]["external_id"])
        tg_id = checkout.z_udalosti(event)
        if tg_id is None and fan.get("uuid"):
            try:
                row = await self._db.fan(fan["uuid"])
            except Exception:  # noqa: BLE001 - notifikácia nesmie padnúť na DB
                row = None
            if row and row.get("tg_id"):
                tg_id = int(row["tg_id"])
        if tg_id is None:
            return ""

        try:
            user = await self._db.get_user(int(tg_id))
        except Exception:  # noqa: BLE001
            user = None
        if not user:
            return ""
        meno = (user.get("partner_name") or user.get("first_name") or "").strip()
        znacka = (user.get("username") or "").strip()
        if meno and znacka:
            return f"{meno} (@{znacka})"
        return meno or (f"@{znacka}" if znacka else str(tg_id))

    async def _dispatch(self, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        if is_payment(event):
            await self._record_payment(event, settings)
            return
        if is_new_subscriber(event) and settings.get("greet_new"):
            await self._greet(event, settings)
            return
        if wants_reply(event):
            await self._reply(event, settings)

    async def _post_to_feed(self, settings: Dict[str, Any]) -> None:
        """Pridá fotku na feed s popiskom v jej štýle.

        Feed nie je chat: príspevok ostáva navždy a vidia ho všetci naraz,
        takže popisok sa nepíše nikomu konkrétnemu a fotka sa nikdy neopakuje.
        """
        folders = await self._db.folders()
        zbierka: List[Dict[str, Any]] = []
        for folder in folders:
            if fvmedia.role_of(str(folder.get("name") or ""), folders) == "post":
                zbierka.extend(await self._db.media_in(str(folder.get("name"))))

        foto = fvmedia.next_post(zbierka)
        if not foto:
            log.info("Na feed nie je čo pridať")
            # Nech sa prázdny priečinok nekontroluje každých päť sekúnd.
            await self._db.save({"last_post_at": datetime.now(timezone.utc).isoformat()})
            return

        persona = await self._db.persona()
        popis = str(foto.get("caption") or "").strip()
        pokyn = (
            f"Napíš popisok k fotke na tvoj feed. Na fotke je: {popis or 'ty'}.\n"
            "Krátko, ako sa píše na sociálnu sieť — jedna veta, drzo a lákavo.\n"
            "Nepíšeš nikomu konkrétnemu, číta to veľa ľudí naraz.\n"
            "Bez úvodzoviek, bez hashtagov, bez podpisu."
        )
        try:
            text = (
                await self._llm.reply(
                    build_prompt(persona, settings, {}, {}, None),
                    [{"role": "user", "content": pokyn}],
                )
            ).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("Popisok sa nepodaril: %s", exc)
            return

        if not text or not self._safe(text):
            return

        audience = str(settings.get("post_audience") or "followers-and-subscribers")
        if audience not in fvmedia.AUDIENCES:
            audience = "followers-and-subscribers"

        if not await self._api.post(text, [foto["media_uuid"]], audience, 0):
            return

        teraz = datetime.now(timezone.utc).isoformat()
        await self._db.update_media(foto["media_uuid"], {"posted_at": teraz})
        await self._db.save({"last_post_at": teraz})
        log.info("Na feed pridaná fotka %s", foto["media_uuid"][:8])

    async def _record_payment(self, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        fan = fan_of(event)
        suma = paid_cents(event)
        if not fan["uuid"]:
            return
        row = await self._db.fan(fan["uuid"])
        if row is None:
            row = await self._ensure_fan(fan)

        # Toto je najlepší okamih na spojenie s Telegramom: človek pred pár
        # minútami klikol na SVOJ odkaz a hneď zaplatil. O hodinu už bude ten
        # klik len jeden z mnohých.
        if not row.get("tg_id"):
            await self._try_link(fan, row, klik_plati=True)

        row = await self._db.record_payment_once(int(event["id"]), fan["uuid"], suma)
        kupene = int(row.get("bought_count") or 0)
        log.info("Fanúšik %s zaplatil %s c (%s. nákup)", fan["uuid"][:8], suma, kupene)

        # Zaplatil → v Telegrame prestáva byť lead. Bez tohto by mu modelka
        # ďalej pripomínala stránku, ktorú si práve kúpil, a po skončení okna
        # by ho ešte aj odstrihla — hoci platiaci sa neutlmuje nikdy.
        await self._oznac_zaplateneho(event, fan)

        await self._thank(fan, row, settings, suma, kupene)

    async def _oznac_zaplateneho(self, event: Dict[str, Any], fan: Dict[str, str]) -> None:
        if hub := getattr(self._db, "hub", None):
            for identity in await hub.linked("fanvue", fan["uuid"], "telegram"):
                await self._db.update_user(int(identity["external_id"]), {"paid": True})
            return
        tg_id = checkout.z_udalosti(event)
        if tg_id is None and fan.get("uuid"):
            row = await self._db.fan(fan["uuid"])
            if row and row.get("tg_id"):
                tg_id = int(row["tg_id"])
        if tg_id is None:
            return
        try:
            await self._db.update_user(int(tg_id), {"paid": True})
            log.info("Telegram %s označený ako platiaci", tg_id)
        except Exception as exc:  # noqa: BLE001 - platba je zaznamenaná aj tak
            log.warning("Telegram %s sa nepodarilo označiť ako platiaci: %s", tg_id, exc)

    async def _thank(
        self,
        fan: Dict[str, Any],
        row: Dict[str, Any],
        settings: Dict[str, Any],
        cents: int,
        kolkykrat: int,
    ) -> None:
        """Poďakuje za nákup. Kto zaplatil, má cítiť, že si to niekto všimol.

        Ide to hneď z platby, nie až keď sa ozve — vďaka o dva dni neskôr
        už nie je vďaka.
        """
        if hub := getattr(self._db, "hub", None):
            if not await hub.can_reply("fanvue", fan["uuid"], proactive=True):
                return
        if not fvflow.may_thank(row, settings):
            log.info("Za nákup %s sa práve ďakovalo, druhý raz nie", fan["uuid"][:8])
            return
        if row.get("human_takeover") or not row.get("ai_enabled", True):
            return

        # POĎAKOVANIE JE TIEŽ ODPOVEĎ. Chodí z webhooku o platbe, nie
        # z prichádzajúcej správy, takže obchádzalo bránu `reply_mode` v
        # `_reply` — v režime `semi` odpisovala sama, hoci majiteľ schvaľuje
        # každú správu, a pri `off` písala, hoci mala mlčať.
        reply_mode = str(settings.get("reply_mode") or "auto")
        if reply_mode == "off":
            return
        if reply_mode == "auto":
            await self._require_auto_hours(settings)

        persona = await self._db.persona()
        behavior = await self._db.behavior()
        self._rezim(behavior)
        teraz_local = local_now(behavior)
        prompt = build_prompt(persona, settings, fan, row, None, teraz_local)
        history = (await self._history_rows(fan["uuid"])) + [
            {"role": "user", "content": fvflow.thanks_hint(cents, kolkykrat)}
        ]
        turn = conversation_timing.analyze(history, now_local=teraz_local)
        prompt = conversation_timing.prompt_with_timing(prompt, turn)

        if reply_mode == "semi":
            # Kartu si nechá schváliť ako každú inú odpoveď. Zapisuje sa až
            # po jej odoslaní, inak by sa pri ďalšom zosúladení chatu
            # ďakovalo znova a majiteľ by dostal druhú kartu za tú istú platbu.
            if await self._handoff_semi(
                fan, row, prompt, history,
                preview=fvflow.popis_nakupu(cents, kolkykrat),
            ):
                await self._db.update_fan(
                    fan["uuid"],
                    {
                        "last_thanks_at": datetime.now(timezone.utc).isoformat(),
                        "thanks_sent": int(row.get("thanks_sent") or 0) + 1,
                        "pending_thanks": False,
                    },
                )
            return

        try:
            text = (await self._llm.reply(prompt, turn.messages)).strip()
        except Exception as exc:  # noqa: BLE001 - vďaka je bonus, nie podmienka
            log.warning("Poďakovanie sa nepodarilo napísať: %s", exc)
            return
        text = self._clean(text)
        if not text or not self._safe(text):
            return

        poslana = await self._send_checked(fan["uuid"], text, proactive=True)
        if not poslana:
            return
        await self._db.add_message(
            fan["uuid"], "assistant", text, "" if poslana == "-" else poslana
        )
        await self._db.update_fan(
            fan["uuid"],
            {
                "last_thanks_at": datetime.now(timezone.utc).isoformat(),
                "thanks_sent": int(row.get("thanks_sent") or 0) + 1,
                "pending_thanks": False,
            },
        )
        log.info("Poďakované za nákup %s", fan["uuid"][:8])

    async def _ensure_fan(self, fan: Dict[str, str]) -> Dict[str, Any]:
        row = await self._db.fan(fan["uuid"])
        if row is None:
            # Cez `.get`, nie indexom: udalosť o platbe má iný tvar než
            # udalosť o správe a chýbajúci kľúč by zhodil celé spracovanie.
            await self._db.upsert_fan(
                fan["uuid"],
                {
                    "handle": fan.get("handle") or "",
                    "display_name": fan.get("display_name") or "",
                    "avatar_url": fan.get("avatar_url") or "",
                },
            )
            row = await self._db.fan(fan["uuid"]) or {}
        return row

    async def _greet(self, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        """Nový predplatiteľ — prihovorí sa prvá a rovno zisťuje, kto to je."""
        fan = fan_of(event)
        if not fan["uuid"]:
            return
        if hub := getattr(self._db, "hub", None):
            if not await hub.can_reply("fanvue", fan["uuid"], proactive=True):
                return
        row = await self._ensure_fan(fan)
        if row.get("greeted"):
            return
        # Vypnuté AI a prevzatý chat platia aj na privítanie. Doteraz sa
        # nekontrolovali vôbec — jediná brána bolo `greeted`.
        if row.get("human_takeover") or not row.get("ai_enabled", True):
            return

        # Aj privítanie je odpoveď. Chodí z webhooku o novom predplatiteľovi,
        # takže obchádzalo bránu `reply_mode` rovnako ako poďakovanie.
        reply_mode = str(settings.get("reply_mode") or "auto")
        if reply_mode == "off":
            return
        if reply_mode == "auto":
            await self._require_auto_hours(settings)

        persona = await self._db.persona()
        prompt = build_prompt(persona, settings, fan, row, None)
        history = [{"role": "user", "content": GREETING_PROMPT}]

        if reply_mode == "semi":
            # `greeted` až po odoslanej karte — inak by človek ostal bez
            # privítania aj bez karty a druhá šanca by už neprišla.
            if await self._handoff_semi(
                fan, row, prompt, history, preview=fvflow.POPIS_PREDPLATNEHO
            ):
                await self._db.update_fan(fan["uuid"], {"greeted": True})
            return

        text = (await self._llm.reply(prompt, history)).strip()
        text = self._clean(text)
        if not text or not self._safe(text):
            return
        poslana = await self._send_checked(fan["uuid"], text, proactive=True)
        if not poslana:
            return
        await self._db.add_message(
            fan["uuid"], "assistant", text, "" if poslana == "-" else poslana
        )
        await self._db.update_fan(fan["uuid"], {"greeted": True})
        log.info("Privítaný nový predplatiteľ %s", fan["uuid"][:8])

    async def _ma_media(self, settings: Dict[str, Any]) -> bool:
        """Je v trezore čo poslať? Vypnuté posielanie = to isté ako prázdny trezor.

        Chyba čítania vráti `True` — zbytočne potlačená ponuka nič nepokazí,
        ale zákaz odvodený z výpadku siete by modelke zakázal predávať obsah,
        ktorý naozaj má.
        """
        if not settings.get("send_photos"):
            return False
        teraz = time.monotonic()
        if teraz - self._media_at < _MEDIA_TTL_S:
            return self._media
        try:
            self._media = await self._db.has_media()
        except Exception as exc:  # noqa: BLE001
            log.warning("Trezor sa nepodarilo overiť: %s", exc)
            return True
        self._media_at = teraz
        return self._media

    def _rezim(self, behavior: Dict[str, Any]) -> None:
        """Lacnejší režim konverzácie podľa nastavenia modelky.

        Volá sa všade, kde sa načíta chovanie — nie na jednotlivých volaniach
        `reply`/`suggest`, tých je desať a na jedenáste by sa zabudlo.
        """
        # Režim persony si držíme pre `_safe` — poistka proti vypadnutiu z roly
        # potrebuje vedieť, či modelka smie priznať, že je AI.
        self._mode = str((behavior or {}).get("mode") or "real")
        try:
            self._llm.set_chat_tier(str((behavior or {}).get("chat_tier") or ""))
        except Exception:  # noqa: BLE001 - režim je voľba, nie podmienka
            log.debug("Režim konverzácie sa nepodarilo prepnúť", exc_info=True)

    async def _situacia(
        self, fan: Dict[str, Any], row: Dict[str, Any], settings: Dict[str, Any]
    ) -> "Situacia":
        """Celý kontext jednej chvíle: kde je, koľko je u nej, čo s obsahom.

        Je to na jednom mieste zámerne. Automat aj poloautomat aj tlačidlo
        „Regenerate" musia vidieť ten istý svet — dve kópie tohto výpočtu by sa
        rozišli a majiteľ by dostával návrhy podľa iných pravidiel, než podľa
        akých modelka píše sama.
        """
        persona = await self._db.persona()
        behavior = await self._db.behavior()
        self._rezim(behavior)
        teraz = local_now(behavior)

        # One persisted day across Telegram, Instagram and Fanvue.
        rozvrh = None
        try:
            rozvrh = den.Rozvrh.from_row(await self._db.schedule())
        except Exception as exc:  # noqa: BLE001 - bez rozvrhu platí šablóna
            log.warning("Rozvrh dňa sa nenačítal: %s", exc)
        blok = (
            den.block_at(teraz, seed=str(persona.get("name") or ""), rozvrh=rozvrh)
            if teraz
            else None
        )

        hub = getattr(self._db, "hub", None)
        shared_mood = ""
        if hub and teraz:
            blok, shared_mood = await hub.day(teraz, rozvrh)

        tg = None
        # Legacy tg_id is attribution, not ownership proof.
        verified_tg = await hub.linked("fanvue", fan["uuid"], "telegram") if hub else []
        if row.get("tg_id") and (not hub or any(str(r["external_id"]) == str(row["tg_id"]) for r in verified_tg)):
            try:
                tg = await self._db.telegram_context(int(row["tg_id"]))
            except Exception as exc:  # noqa: BLE001 - kontext je bonus
                log.warning("Kontext z Telegramu sa nenačítal: %s", exc)

        # O tom, ČI niečo odíde, rozhoduje kód. Model rieši len AKO to povie —
        # keby rozhodoval on, posielal by fotky v každej druhej správe.
        kde = den.where(blok) if blok is not None else "home"
        text = str(fan.get("text") or "")
        pyta_fotku = fvmedia.asked_for_photo(text)
        pyta_ostre = fvmedia.wants_spicy(text)
        # Nadrženie sa stupňuje naprieč správami, nie v jednej vete. Keď to
        # beží, ponuka doňho neskáče — a keď si o niečo povie, `asked` vyššie
        # to aj tak zachytí.
        horuco = fvmedia.rozohriaty(await self._db.history(fan["uuid"]))
        moment = fvflow.paid_moment(row, settings, pyta_ostre, rozohriaty=horuco)
        # Ktorým spôsobom to priniesť. Register drží odstup, aby ten istý
        # postup nedostal ten istý človek dvakrát krátko po sebe.
        tah = fvtah.vyber(fvtah.pouzite_z(row), moment)
        foto_ok = fvflow.free_photo_ok(row, settings, pyta_fotku, kde)
        dlzi = fvflow.owes_photo(row)

        prompt = build_prompt(
            persona,
            settings,
            fan,
            row,
            tg,
            teraz,
            blok,
            fvflow.guidance(
                row, settings, moment, foto_ok, pyta_fotku, kde, dlzi,
                ma_media=await self._ma_media(settings),
                rozohriaty=horuco,
                tah_hint=fvtah.blok(tah),
            ),
            behavior=behavior,
        )
        if hub:
            prompt += await hub.context("fanvue", fan["uuid"])
            prompt += hub.mood_prompt(shared_mood)
        return Situacia(
            persona=persona,
            behavior=behavior,
            teraz=teraz,
            blok=blok,
            kde=kde,
            pyta_fotku=pyta_fotku,
            pyta_ostre=pyta_ostre,
            moment=moment,
            foto_ok=foto_ok,
            dlzi=dlzi,
            tah=tah,
            prompt=prompt,
            tip=fvflow.tip(moment, foto_ok, pyta_fotku, dlzi, kde),
        )

    async def _reply(self, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        fan = fan_of(event)
        if not fan["uuid"]:
            return

        row = await self._ensure_fan(fan)
        if hub := getattr(self._db, "hub", None):
            await hub.observe("fanvue", fan["uuid"], fan.get("handle", ""), fan.get("display_name", ""), fan.get("text", ""))
        if not row.get("ai_enabled", True) or row.get("human_takeover"):
            await self._reconcile(fan, row, mark_read=False, sync_only=True)
            log.info("Fanúšik %s má odpisovanie vypnuté", fan["uuid"][:8])
            return

        # Režim (Off / Auto / Semi) — nezávislý od Telegramu. Off = ticho;
        # Semi = návrhy na schválenie (branch až po zostavení promptu nižšie).
        reply_mode = str(settings.get("reply_mode") or "auto")
        if reply_mode == "off":
            return
        semi = reply_mode == "semi"
        if not semi:
            await self._require_auto_hours(settings)

        if not row.get("tg_id"):
            # Prvá správa od neznámeho = práve prišiel, takže čerstvý klik
            # ukazuje na neho. Starý fanúšik mohol napísať hocikedy a klik
            # medzitým patrí niekomu inému.
            await self._try_link(fan, row, klik_plati=not int(row.get("msg_count") or 0))

        # ČÍTA SA VŽDY, „VIDENÉ" NIE. Fanvue má na to prepínač: `markAsRead`
        # na `GET /chats/{uuid}/messages`. Pri synchronizácii vždy `false`, takže
        # chat vidíme celý, ale fanúšikovi nesvieti videné skôr, než sa majiteľ
        # rozhodne odpovedať. Overené naostro: dve neprečítané správy ostali po
        # stiahnutí dvadsiatich naďalej neprečítané.
        #
        # Predtým sa v semi nečítalo vôbec a do pamäte šla len správa
        # z webhooku. Fanvue ale webhookom NEPOSIELA to, čo majiteľ odpíše
        # priamo z ich appky — a tak v karte aj v promptoch chýbala celá jedna
        # strana rozhovoru: 24 jeho správ za sebou a ani jedna jej.
        #
        # Skutočný stav chatu má prednosť pred frontou: doručenie sa mohlo
        # stratiť a poradie Fanvue nezaručuje.
        try:
            if not await self._reconcile(fan, row, mark_read=False):
                return
        except Exception as exc:
            raise ReplyDeferred('history_unavailable') from exc
        if hub := getattr(self._db, "hub", None):
            if not await hub.can_reply("fanvue", fan["uuid"]):
                return

        source_message_id = await self._source_snapshot(fan['uuid'])
        history = await self._history_rows(fan["uuid"])
        turn = conversation_timing.analyze(history, now_local=local_now(await self._db.behavior()))
        fan["text"] = turn.latest_text or fan.get("text", "")
        sit = await self._situacia(fan, row, settings)
        persona, behavior, teraz, blok = sit.persona, sit.behavior, sit.teraz, sit.blok
        kde, moment, foto_ok, dlzi = sit.kde, sit.moment, sit.foto_ok, sit.dlzi
        pyta_fotku, pyta_ostre, prompt = sit.pyta_fotku, sit.pyta_ostre, sit.prompt

        # V Semi riadi tempo majiteľ — návrh mu má prísť hneď, aj mimo aktívnych
        # hodín (rovnako ako na Telegrame). Auto naďalej rešpektuje rozvrh.
        if not semi and not within_hours(settings, teraz):
            log.info("Mimo času na Fanvue — %s ostáva bez odpovede", fan["uuid"][:8])
            raise ReplyDeferred("outside_fanvue_hours")

        prompt = conversation_timing.prompt_with_timing(prompt, turn)

        # Semi: namiesto odoslania vygeneruj návrhy a pošli majiteľovi kartu.
        if semi:
            if await self._handoff_semi(fan, row, prompt, history, sit.tip) and (
                sit.tah is not None
            ):
                # Karta odišla s týmto ťahom — zapíš ho, nech ho majiteľ
                # nedostane v návrhoch znova o dve správy neskôr.
                await self._db.update_fan(
                    fan["uuid"],
                    {
                        "used_moves": fvtah.zapis(
                            fvtah.pouzite_z(row),
                            sit.tah.key,
                            datetime.now(timezone.utc),
                        )
                    },
                )
            return

        text = (await self._llm.reply(prompt, turn.messages)).strip()
        text = self._clean(text)
        if not text or not self._safe(text):
            return

        # Ľudský rytmus odpovede (ako Telegram) — nie plochý random na každú
        # správu. Skutočný človek neodpíše každému rovnako rýchlo: tempo sa
        # riadi dňom (na fotení pomalšie, na gauči rýchlejšie) a občas telefón
        # odloží na pár minút. Vďaka tomu to nevyzerá, že „hneď videla a hneď
        # píše“ automaticky každému.
        low = float(settings.get("reply_min_s") or 0)
        high = max(low, float(settings.get("reply_max_s") or 0))
        delay = random.uniform(low, high)
        if blok is not None:
            delay *= den.pace(blok)  # 1.0 bežne, ~2.5+ keď je zaneprázdnená
        # Občas odloží telefón na dlhšie — nie na každú správu. Keď je práve
        # zaneprázdnená, šanca je vyššia a pauza dlhšia.
        pause_chance = 0.25 if den.busy(blok) else 0.12
        if random.random() < pause_chance:
            delay += random.uniform(180, 420)  # +3–7 min ticha
        await asyncio.sleep(min(delay, 900))  # strop 15 min, nech to niekde nevisí

        # Hlasovka má prednosť pred fotkou — obe naraz v jednej správe by
        # pôsobili ako balík z automatu.
        # Pozadie hlasovky sedí na to, kde práve je — miestnosť, ktorá
        # nesedí na jej vlastné slová, je horšia než žiadna.
        hlas = await self._voice(fan, row, settings, behavior, pyta_ostre, kde)
        if hlas:
            media, cena = [hlas["media_uuid"]], int(hlas["price_cents"])
            foto = None
        else:
            foto = await self._pick_photo(fan, row, settings, moment, foto_ok, kde, dlzi)
            media = [foto["media_uuid"]] if foto else None
            cena = int(foto["price_cents"]) if foto else 0

        poslana = await self._send_checked(fan["uuid"], text, media, cena,
                                          source_message_id=source_message_id)
        if not poslana:
            return

        teraz_iso = datetime.now(timezone.utc).isoformat()
        # Id sa ukladá spolu so správou — inak by sa nám vlastná odpoveď pri
        # ďalšom zosúladení javila ako cudzia a uložila by sa druhý raz.
        await self._db.add_message(
            fan["uuid"], "assistant", text, "" if poslana == "-" else poslana
        )
        patch: Dict[str, Any] = {"msg_count": int(row.get("msg_count") or 0) + 1}

        if hlas:
            patch["last_voice_at"] = teraz_iso
            patch["voices_sent"] = int(row.get("voices_sent") or 0) + 1
            await self._db.add_message(fan["uuid"], "assistant", f"(hlasovka) {hlas['prepis']}")
        if foto and cena == 0:
            patch["free_photos"] = int(row.get("free_photos") or 0) + 1
        if moment:
            patch["last_paid_ask_at"] = teraz_iso
        # Ťah sa zapisuje UŽ PRI POUŽITÍ, nie po overení, či ho model naozaj
        # využil — rovnako ako vtipy na Telegrame. Radšej ťah raz preskočiť
        # než ho tomu istému človeku zopakovať.
        if sit.tah is not None:
            patch["used_moves"] = fvtah.zapis(
                fvtah.pouzite_z(row), sit.tah.key, datetime.now(timezone.utc)
            )
        if cena > 0 or (moment and _offered(text)):
            patch["last_offer_at"] = teraz_iso
            patch["offers_sent"] = int(row.get("offers_sent") or 0) + 1
        if cena > 0:
            # Kým to neodomkne, ďalšia platená mu nechodí. Zruší sa to až
            # nákupom — o tom sa dozvieme z webhooku alebo z `purchasedAt`.
            patch["pending_offer_at"] = teraz_iso

        # Sľub sa buď práve splnil, alebo práve vznikol. Nesplnený sľub je
        # presne ten detail, na ktorom sa pozná automat.
        if foto:
            patch["promised_at"] = None
        elif pyta_fotku and not fvflow.can_take_photo(kde):
            patch["promised_at"] = teraz_iso
            patch["promised_what"] = "fotka, keď príde domov"

        await self._db.update_fan(fan["uuid"], patch)

        if foto:
            await self._db.record_send(foto["media_uuid"], fan["uuid"], cena)
            await self._db.update_media(
                foto["media_uuid"], {"sent_count": int(foto.get("sent_count") or 0) + 1}
            )
            log.info(
                "Fotka %s odišla %s za %s c", foto["media_uuid"][:8], fan["uuid"][:8], cena
            )

        # Pamäť sa dopĺňa NA POZADÍ — nesmie pridať sekundu do cesty odpovede.
        asyncio.create_task(self._remember(fan["uuid"], persona, settings))

    # ---------- semi-auto: handoff + doručovanie (volá control bot) ----------

    async def _handoff_semi(
        self, fan, row, prompt, history, tip: str = "", preview: str = ""
    ) -> bool:
        """Vygeneruj návrhy a pošli majiteľovi kartu (supersede rieši control).

        `preview` je pre karty, ktoré nevznikli z prichádzajúcej správy —
        poďakovanie za nákup a privítanie predplatiteľa. Bez neho by karta
        ukazovala vnútorný pokyn pre model namiesto dôvodu, prečo prišla.

        Vracia, či karta naozaj odišla: volajúci si podľa toho zapíše, že
        vybavené (`greeted`, `last_thanks_at`). Keby si to zapísal aj pri
        neúspechu, človek by ostal bez privítania aj bez karty.
        """
        if not self._control:
            log.warning("Fanvue semi: control bot nie je pripojený — %s bez karty", fan["uuid"][:8])
            return False
        source_message_id = await self._source_snapshot(fan['uuid'])
        if source_message_id is not None:
            current_history = await self._history_rows(fan['uuid'])
            if preview:
                history = current_history + history[-1:]
            elif [(r['role'], r['content']) for r in history] != [(r['role'], r['content']) for r in current_history]:
                raise ReplyDeferred('context_changed')
        now_local = local_now(await self._db.behavior())
        turn = conversation_timing.analyze(history, now_local=now_local)
        try:
            suggestions = await self._llm.suggest(
                conversation_timing.prompt_with_timing(prompt, turn), turn.messages,
                angles=uhly_pre(row, await self._db.settings()),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Fanvue návrhy zlyhali: %s", exc)
            return False
        if not suggestions:
            return False
        if hasattr(self._api, 'sync_messages'):
            try:
                unanswered = await self._reconcile(fan, row, sync_only=True, process_media=False)
                if await self._source_snapshot(fan['uuid']) != source_message_id:
                    if unanswered:
                        raise ReplyDeferred('context_changed')
                    return False
            except ReplyDeferred:
                raise
            except Exception as exc:
                raise ReplyDeferred('history_unavailable') from exc
            current_cfg = await self._db.settings()
            current_user = await self._db.fan(fan['uuid']) or {}
            if (not current_cfg.get('connected') or not current_cfg.get('enabled')
                    or current_cfg.get('reply_mode') != 'semi' or current_user.get('human_takeover')
                    or not current_user.get('ai_enabled', True)):
                return False
        name = row.get("display_name") or fan.get("name") or fan["uuid"][:8]
        # Všetko, na čo ešte neodpovedala — nielen posledná správa. Kým
        # majiteľ rozhoduje, fanúšik píše ďalej a karta sa má dopĺňať.
        ok = await self._control.post_approval(
            channel="fanvue",
            conv_key=fan["uuid"],
            display_name=name,
            incoming_preview=(
                preview or prehlad.blok_rozhovoru(history, now_local=now_local) or (fan.get("text") or "")
            ),
            suggestions=suggestions,
            hint=tip,
            **({'source_message_id': source_message_id} if source_message_id is not None else {}),
        )
        log.info("Fanvue semi: karta pre %s %s", fan["uuid"][:8], "poslaná" if ok else "NEposlaná")
        return bool(ok)

    async def regenerate(
        self, conv_key: str, seed: str = "", brief: str = ""
    ) -> Dict[str, Any]:
        """Nové návrhy pre ten istý chat. Volá control bot cez „Regenerate".

        `brief` je zadanie od majiteľa vlastnými slovami („poďakuj mu, že tu je,
        a opýtaj sa, kto to je"). Nie je to text na odoslanie — modelka ho
        povie po svojom a v jazyku, ktorým si s tým človekom píše. Majiteľ ho
        smie napísať po slovensky; na výstup to nemá vplyv.

        Stav sa počíta ODZNOVA, nie z toho, čo viselo na karte: kým sa majiteľ
        rozhodoval, mohol prísť čas na fotku, mohol niečo kúpiť alebo sa mohla
        zmeniť hodina u nej. Prepísať len text a nechať starý kontext by
        znamenalo ponúkať mu odpovede na svet, ktorý už nie je.
        """
        row = await self._db.fan(conv_key)
        if not row:
            return {}
        settings = await self._db.settings()
        if not await self._reconcile({"uuid": conv_key, "text": ""}, row,
                                     mark_read=False, sync_only=True, process_media=False):
            return {}
        history = await self._history_rows(conv_key)
        turn = conversation_timing.analyze(history, now_local=local_now(await self._db.behavior()))
        fan = {
            "uuid": conv_key,
            "handle": str(row.get("handle") or ""),
            "display_name": str(row.get("display_name") or ""),
            "avatar_url": str(row.get("avatar_url") or ""),
            "text": turn.latest_text,
        }
        sit = await self._situacia(fan, row, settings)
        prompt = conversation_timing.prompt_with_timing(sit.prompt, turn) + zadanie.do_promptu(brief)
        suggestions = await self._llm.suggest(
            prompt,
            turn.messages,
            angles=UHLY_ZADANIE if brief else uhly_pre(row, settings),
            seed=seed or "2",
        )
        return {"suggestions": suggestions, "hint": "" if brief else sit.tip}

    async def recent_chats(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Chaty pre menu control bota: kľúč, meno a krátky popis do tlačidla."""
        out: List[Dict[str, Any]] = []
        for row in await self._db.recent_chats(limit):
            meno = str(row.get("display_name") or row.get("handle") or "fan")
            minul = int(row.get("spent_cents") or 0)
            popis = f"{int(row.get('msg_count') or 0)} msgs"
            if minul:
                popis += f" · ${minul / 100:.0f}"
            if row.get("human_takeover"):
                popis += " · ✋"
            out.append(
                {"conv_key": str(row.get("fan_uuid") or ""), "name": meno, "hint": popis}
            )
        return [chat for chat in out if chat["conv_key"]]

    async def context_card(self, conv_key: str) -> str:
        """Kto je tento fanúšik a o čom si píšu. Volá control bot cez „Context".

        Skladá sa z toho, čo už v databáze je — nič sa negeneruje. Volanie
        modelu by stálo coiny aj sekundy a povedalo by to isté, len menej
        presne než zhrnutie, ktoré si modelka priebežne píše sama.
        """
        row = await self._db.fan(conv_key)
        if not row:
            return ""
        tg = None
        if row.get("tg_id"):
            try:
                tg = await self._db.telegram_context(int(row["tg_id"]))
            except Exception as exc:  # noqa: BLE001 - prehľad je pohodlie
                log.warning("Kontext z Telegramu sa nenačítal: %s", exc)
        history = await self._db.history(conv_key, limit=prehlad.SPRAV * 2)
        return prehlad.fanvue(row, history, tg)

    async def deliver_text(self, conv_key: str, text: str) -> bool:
        sent = await self._send_checked(conv_key, text, approved=True)
        if not sent:
            return False
        await self._db.add_message(conv_key, "assistant", text, "" if sent == "-" else sent)
        row = await self._db.fan(conv_key) or {}
        await self._db.update_fan(
            conv_key, {"msg_count": int(row.get("msg_count") or 0) + 1}
        )
        await self._dobehni(conv_key, row)
        return True

    async def deliver_operator(self, command, before_send):
        lock = self._send_lock(command['external_id'])
        async with lock:
            return await self._deliver_operator_locked(command, before_send)

    async def _deliver_operator_locked(self, command, before_send):
        from social_commands import DeliveryResult
        from instagram_interactions import URL
        key, text = command['external_id'], command['text']
        initial = await self._db.settings()
        creator = initial.get('creator_uuid')
        async def ready():
            settings = await self._db.settings()
            scope = 'fanvue:' + str(settings['creator_uuid']) if settings.get('creator_uuid') else 'primary'
            if not settings.get('connected') or command['account_scope'] != scope or settings.get('creator_uuid') != creator:
                return 'fanvue_disconnected'
            if not await self._db.fan(key):
                return 'unknown_contact'
            hub = getattr(self._db, 'hub', None)
            if hub:
                if not await hub.can_reply('fanvue', key):
                    return 'contact_opt_out'
                if (await hub.restrictions('fanvue', key)).get('no_links') and URL.search(text):
                    return 'links_not_allowed'
            return ''
        if reason := await ready():
            return DeliveryResult.blocked(reason)
        # Sync only, never seen or purchase thanks while preparing an owner action.
        row = await self._db.fan(key)
        try:
            await self._reconcile({'uuid': key, 'text': ''}, row, mark_read=False, sync_only=True, process_media=False)
        except Exception:
            return DeliveryResult.blocked('history_unavailable')
        if not await before_send():
            return DeliveryResult.blocked('stale_context')
        settings = await self._db.settings()
        if command['operation'] == 'send_text' and settings.get('reply_mode', 'auto') == 'auto':
            await self._db.update_fan(key, {'human_takeover': True})
            if self._control is not None:
                await self._control._db.supersede_open('fanvue', key)
        if reason := await ready():
            return DeliveryResult.blocked(reason)
        if not await before_send():
            return DeliveryResult.blocked('stale_context')
        await self._api.chat_messages(key, limit=1, mark_read=True)
        if not await before_send():
            return DeliveryResult.blocked('stale_context')
        async def fresh_before_send():
            if hasattr(self._api, 'sync_messages'):
                try:
                    await self._reconcile({'uuid': key, 'text': ''}, row, sync_only=True, process_media=False)
                except Exception:
                    return False
            return not await ready() and await before_send()
        outcome = await self._api.send_operator(key, text, before_send=fresh_before_send)
        if outcome.status == 'done':
            try:
                await self._db.add_message(key, 'assistant', text, outcome.result.get('provider_message_id') or '')
                await self._db.update_fan(key, {'msg_count': int(row.get('msg_count') or 0) + 1})
            except Exception:
                log.warning('Fanvue operator send succeeded; history update failed')
        return outcome

    async def take_over(self, conv_key: str) -> None:
        await self._db.update_fan(conv_key, {'human_takeover': True})

    async def _dobehni(self, conv_key: str, row: Dict[str, Any]) -> None:
        """Zosúladenie chatu AŽ TERAZ, keď už odpoveď odišla.

        Dotiahne správy písané ručne vo Fanvue, nákupy a počet správ.
        Synchronizácia nemení „videné“: nová správa mohla prísť až po našej
        odpovedi a má zostať neprečítaná do ďalšieho odosielania.

        Zlyhanie sa prehltne: odpoveď je odoslaná, to je to podstatné.
        """
        try:
            await self._reconcile({"uuid": conv_key, "text": ""}, dict(row or {}))
        except Exception as exc:  # noqa: BLE001 - dobiehanie je bonus
            log.warning("Dobehnutie chatu %s zlyhalo: %s", conv_key[:8], exc)

    async def photo_folders(self, conv_key: str) -> List[Dict[str, str]]:
        out = []
        for f in await self._db.folders():
            role = str(f.get("role") or "")
            if role == "ignore":
                continue
            name = str(f.get("name") or "")
            label = f"{name} · {role}" if role else name
            out.append({"id": name, "label": label})
        return out

    async def photo_items(self, conv_key: str, folder_id: str) -> List[Dict[str, Any]]:
        media = await self._db.media_in(folder_id)
        return [
            {
                "ref": m["media_uuid"],
                "caption": m.get("caption") or m.get("fits") or "",
                "price_cents": m.get("price_cents"),
            }
            for m in media
        ]

    async def suggest_caption(self, conv_key: str) -> List[str]:
        return ["just for you 🙈", "hope you like it 😏", "thinking of you 💋"]

    async def deliver_photo(
        self, conv_key: str, media_ref: str, caption: str, price_cents=None
    ) -> bool:
        price = int(price_cents or 0)
        sent = await self._send_checked(conv_key, caption or "", [media_ref], price, approved=True)
        if not sent:
            return False
        try:
            await self._db.record_send(media_ref, conv_key, price)
        except Exception:  # noqa: BLE001 - odoslané už je, záznam je bonus
            pass
        marker = (
            f"[poslala platenú fotku ${price // 100}: {caption}]"
            if price > 0
            else f"[poslala fotku: {caption or 'foto'}]"
        )
        await self._db.add_message(conv_key, "assistant", marker, "" if sent == "-" else sent)
        row = await self._db.fan(conv_key) or {}
        await self._db.update_fan(
            conv_key, {"msg_count": int(row.get("msg_count") or 0) + 1}
        )
        await self._dobehni(conv_key, row)
        return True

    async def generate_voice_preview(self, text: str):
        # Fanvue hlasovka cez schvaľovanie príde ako fast-follow (upload do
        # vaultu + odoslanie ako platené/free médium). Zatiaľ nedostupná —
        # tlačidlo to majiteľovi povie.
        return None

    async def deliver_voice(self, conv_key: str, text: str, ogg: bytes) -> bool:
        return False

    async def _reconcile(
        self, fan: Dict[str, Any], row: Dict[str, Any], mark_read: bool = False,
        *, sync_only: bool = False, process_media: bool = True,
    ) -> bool:
        if not hasattr(self, '_sync_locks'):
            self._sync_locks = {}
        lock = self._sync_locks.setdefault(fan['uuid'], asyncio.Lock())
        async with lock:
            result = await self._reconcile_locked(fan, row, mark_read, sync_only=sync_only, process_media=process_media)
        if row.get('pending_thanks') and not sync_only:
            # Delivery can itself refresh history; never hold the import lock
            # across generation/send or it would recursively acquire itself.
            await self._thank(fan, row, await self._db.settings(), 0,
                              int(row.get('bought_count') or 0))
        return result

    async def _reconcile_locked(
        self, fan: Dict[str, Any], row: Dict[str, Any], mark_read: bool = False,
        *, sync_only: bool = False, process_media: bool = True,
    ) -> bool:
        """Doplní, čo v pamäti chýba. False = teraz sa neodpisuje.

        Tenant reads fail closed. A provider failure or incomplete catch-up
        cannot authorise a generated reply; the legacy adapter keeps its
        historical fallback for standalone use.

        Predvolené `mark_read=False` načíta chat bez „videné“ v oboch
        režimoch. Potvrdenie prečítania patrí až do `_send_checked`.
        """
        creator = str((await self._db.settings()).get("creator_uuid") or "")
        known = None
        gap = None
        strict = hasattr(self._api, 'sync_messages')
        if strict:
            if getattr(self, '_sync_creator', None) != creator:
                self._api._sync_walks = {}
                self._sync_discovery_cursor = ''
                self._sync_creator = creator
            known = await self._db.known_message_uuids(fan['uuid'])
            checkpoint = row.get('history_sync_state')
            if checkpoint and checkpoint.get('account_scope') == 'fanvue:' + creator and not checkpoint.get('complete'):
                self._api._sync_walks[fan['uuid']] = {
                    'cursor': checkpoint.get('cursor') or '', 'anchors': checkpoint.get('anchors') or [],
                    'head_ids': checkpoint.get('head_ids') or [],
                }
            elif checkpoint and checkpoint.get('account_scope') != 'fanvue:' + creator:
                await self._db.update_fan(fan['uuid'], {'history_sync_state': None})
                row['history_sync_state'] = None
            from fanvue_api import FanvueHistoryGap
            try:
                skutocne = await self._api.sync_messages(fan['uuid'], known)
            except FanvueHistoryGap as exc:
                gap = exc
                skutocne = exc.messages
            current = await self._db.settings()
            if not current.get('connected') or current.get('creator_uuid') != creator:
                raise RuntimeError('Fanvue connection changed while reading history')
            if not skutocne and known:
                raise RuntimeError('Known Fanvue history is unavailable')
        else:
            skutocne = await self._api.chat_messages(fan["uuid"], mark_read=mark_read)
        if not skutocne:
            if fan.get("text"):
                message_uuid = fan.get('_message_uuid')
                if message_uuid and fan.get('_occurred_at'):
                    if message_uuid not in await self._db.known_message_uuids(fan['uuid']):
                        await self._db.add_messages(fan['uuid'], [{
                            'message_uuid': message_uuid, 'role': fan.get('_source_role', 'user'), 'content': fan['text'],
                            'occurred_at': fan['_occurred_at'],
                        }])
                else:
                    await self._db.add_message(fan["uuid"], "user", fan["text"])
            return True

        try:
            refresh_id = row.get('_refresh_pending_id') or (row.get('history_sync_state') or {}).get('refresh_pending_id')
            durable_checkpoint = hasattr(skutocne, 'previous_state') and (gap or row.get('history_sync_state') or refresh_id)
            if durable_checkpoint:
                # Write the BEFORE-page checkpoint first. A crash during import
                # then replays that page instead of treating its partial IDs as
                # a complete anchor after restart.
                state = {'account_scope': 'fanvue:' + creator, **skutocne.previous_state}
                if refresh_id:
                    state.update(refresh_draft=True, refresh_pending_id=refresh_id)
                await self._db.update_fan(fan['uuid'], {'history_sync_state': state})
                row['history_sync_state'] = state
            zname = known if known is not None else await self._db.known_message_uuids(fan["uuid"])
            if backfill := getattr(self._db, "backfill_message_times", None):
                await backfill(fan["uuid"], fvsync.message_times(skutocne))
            legacy_loader = getattr(self._db, 'unidentified_messages', None)
            chybajuce = fvsync.missing(
                zname, skutocne, creator,
                **({'legacy_rows': await legacy_loader(fan['uuid'])} if legacy_loader else
                   {'bez_uuid': await self._db.texty_bez_uuid(fan['uuid'])}),
            )
            if chybajuce:
                await self._db.add_messages(fan["uuid"], chybajuce)
                log.info(
                    "Doplnených %s správ do chatu %s", len(chybajuce), fan["uuid"][:8]
                )
            if process_media and getattr(self, '_incoming_media', None):
                # Includes already stored messages: recover accessible recent
                # attachments and retry bounded failures without a new fan turn.
                from social_media import fanvue_attachments
                media_messages = [m for m in skutocne if m.get('hasMedia')]
                budget = 3
                for message in media_messages:
                    parts = fanvue_attachments(message, self._api, fan['uuid'])
                    budget -= int(bool(await self._incoming_media.ingest('fanvue', fan['uuid'], 'fanvue:' + creator,
                        message['uuid'], parts)))
                    if budget <= 0:
                        break

            # POČÍTADLO SPRÁV PODĽA SKUTOČNÉHO CHATU. `msg_count` sa inak
            # zvyšuje LEN pri správach, ktoré prešli cez bota — kto píše priamo
            # vo Fanvue (a v režime `semi` je to majiteľ), ho nechá takmer na
            # nule. Naostro: 50 správ v chate a `msg_count` 6, 34 správ a 0.
            # Z toho počítadla pritom `phase` a `may_offer` odvodzujú, či sa
            # ešte len zoznamujú.
            skutocny_pocet = len(skutocne)
            if skutocny_pocet > int(row.get("msg_count") or 0):
                await self._db.update_fan(
                    fan["uuid"], {"msg_count": skutocny_pocet}
                )
                row["msg_count"] = skutocny_pocet

            # Nákup sa inak nedozvieme — webhook o odomknutí správy nechodí.
            kupil = fvsync.bought(skutocne)
            if kupil > int(row.get("bought_count") or 0):
                patch = {"bought_count": kupil, "pending_offer_at": None,
                         "pending_thanks": True}
                kedy = fvsync.last_bought_at(skutocne)
                if kedy:
                    patch["last_bought_at"] = kedy
                await self._db.update_fan(fan["uuid"], patch)
                row.update(patch)
                log.info("Fanúšik %s má kúpené: %s", fan["uuid"][:8], kupil)
            if durable_checkpoint:
                state = ({'account_scope': 'fanvue:' + creator, **skutocne.next_state}
                         if skutocne.next_state else None)
                if refresh_id:
                    state = state or {'account_scope': 'fanvue:' + creator, 'complete': True}
                    state.update(refresh_draft=True, refresh_pending_id=refresh_id)
                await self._db.update_fan(fan['uuid'], {'history_sync_state': state})
                row['history_sync_state'] = state
        except ReplyDeferred:
            raise
        except Exception as exc:  # noqa: BLE001 - zosúladenie je poistka, nie podmienka
            if sync_only or strict:
                raise  # Inbox import must keep its webhook pending on failure.
            log.warning("Zosúladenie chatu zlyhalo: %s", exc)

        if acknowledge := getattr(skutocne, 'acknowledge', None):
            acknowledge()
        if gap:
            raise gap

        if fvsync.stay_quiet(skutocne, creator):
            log.info("Na %s už niekto odpovedal — mlčím", fan["uuid"][:8])
            return False
        return True

    async def _voice(
        self,
        fan: Dict[str, Any],
        row: Dict[str, Any],
        settings: Dict[str, Any],
        behavior: Dict[str, Any],
        hot: bool,
        ambience: str = "home",
    ) -> Optional[Dict[str, Any]]:
        """Vyrobí hlasovku a nahrá ju na Fanvue. None = pôjde len text.

        Všetko je fail-open: keď sa čokoľvek nepodarí, odpoveď odíde ako
        text. Hlas je bonus, nie podmienka.
        """
        druh = fvvoice.should_speak(
            row, settings, fvvoice.asked_for_voice(fan["text"]), hot
        )
        if not druh:
            return None

        cena = int(settings.get("voice_price_cents") or 0) if druh == "paid" else 0
        persona = await self._db.persona()
        try:
            script = (
                await self._llm.reply(
                    build_prompt(persona, settings, fan, row, None),
                    [{"role": "user", "content": fvvoice.script_hint(druh, cena)}],
                )
            ).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("Text hlasovky sa nepodaril: %s", exc)
            return None
        if not script:
            return None

        data = await fvvoice.make(behavior, script, ambience)
        if not data:
            return None

        creator = str((await self._db.settings()).get("creator_uuid") or "")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        uuid = await self._api.upload(creator, data, f"voice-{stamp}.mp3", "audio")
        if not uuid:
            return None

        log.info("Hlasovka %s (%s) nahraná pre %s", uuid[:8], druh, fan["uuid"][:8])
        return {
            "media_uuid": uuid,
            "price_cents": cena,
            # Značky prednesu patria do nahrávky, nie do pamäte — inak by ich
            # model o týždeň videl v histórii a začal ich písať do správ.
            "prepis": fvvoice.spoken_only(script)[:400],
        }

    async def _pick_photo(
        self,
        fan: Dict[str, Any],
        row: Dict[str, Any],
        settings: Dict[str, Any],
        moment: str,
        foto_ok: bool,
        kde: str,
        dlzi: bool,
    ) -> Optional[Dict[str, Any]]:
        """Ktorá fotka pôjde s odpoveďou. None = žiadna.

        Platená odchádza, keď je na ňu ten správny moment. Bežná len na
        začiatku alebo na vyžiadanie — a nikdy odtiaľ, kde sa fotka nedá
        spraviť. Fotka z fitka by prezradila viac než akákoľvek veta.
        """
        if not settings.get("send_photos"):
            return None

        ostra = bool(moment)
        if not ostra and not (foto_ok or dlzi):
            return None
        if not ostra and not fvflow.can_take_photo(kde):
            return None

        try:
            folders = await self._db.folders()
            uz_videl = await self._db.sent_media(fan["uuid"])
        except Exception as exc:  # noqa: BLE001 - fotka je bonus, nie podmienka
            log.warning("Zbierka fotiek sa nenačítala: %s", exc)
            return None

        # ODKLON OD PREDLOHY (zámerný, viď `fvmedia.effective_spicy`).
        # Šablóna brala kandidátov len z priečinkov so sediacou rolou a potom
        # celému výberu prepísala `item["spicy"] = ostra` — per-fotkový príznak
        # „Explicit" z dashboardu tým nikdy nič neovplyvnil. Tu sa berú fotky
        # z OBOCH posielateľných rolí, každej sa dopočíta skutočná ostrosť
        # (priečinok = východisko, `spicy_override` na fotke ho prebíja)
        # a triedi až `fvmedia.pick(spicy=…)`. Bez toho by ostrá fotka
        # zaradená do sfw priečinka odišla zadarmo.
        zbierka: List[Dict[str, Any]] = []
        for folder in folders:
            meno = str(folder.get("name") or "")
            rola = fvmedia.role_of(meno, folders)
            if rola not in ("sfw", "nsfw"):
                continue
            for item in await self._db.media_in(meno):
                item["spicy"] = fvmedia.effective_spicy(item, rola)
                zbierka.append(item)

        vybrana = fvmedia.pick(
            zbierka, uz_videl, spicy=ostra, hint=fan["text"], paid=ostra
        )
        if not vybrana:
            return None
        vybrana["price_cents"] = fvmedia.price_for(vybrana) if ostra else 0
        return vybrana

    def _safe(self, text: str) -> bool:
        """Čo sa odtiaľto nesmie dostať von.

        Okrem odkazu na Fanvue aj odpoveď, ktorá vypadla z roly. Naostro sa
        pri teste stalo, že model uprostred konverzácie odpísal „I'm Grok,
        built by xAI, I'm not a real woman" — a nezachytilo to nič.
        """
        if "fanvue.com" in text.lower():
            log.warning("Odpoveď obsahovala odkaz na Fanvue, zahadzujem ju")
            return False
        dovod = prezradenie.unikol(text, getattr(self, "_mode", "real"))
        if dovod:
            log.error("Odpoveď vypadla z roly (%s), zahadzujem ju: %s", dovod, text[:160])
            return False
        return True

    @staticmethod
    def _clean(text: str) -> str:
        """Doladenie textu pred odoslaním.

        Na výkričníky prompt zabúda a jeden z nich prezradí správu rýchlejšie
        než celá zlá veta. Preto sa neriešia len pravidlom, ale aj tu.
        """
        import humanize

        return humanize.no_shouting(text or "").strip()

    async def _remember(
        self, fan_uuid: str, persona: Dict[str, Any], settings: Dict[str, Any]
    ) -> None:
        """Fakty a zhrnutie — aby si na Fanvue pamätala rovnako ako inde."""
        try:
            import facts

            row = await self._db.fan(fan_uuid) or {}
            rows = await self._db.history(fan_uuid, limit=20)
            if not rows:
                return

            found = await facts.extract(self._llm, rows, persona.get("name") or "Ona")
            patch: Dict[str, Any] = {}
            if found:
                patch["facts"] = merge_facts(row.get("facts"), found)
                # Čo tu hľadá, je najdôležitejší jediný fakt — podľa neho sa
                # rozhoduje, či sa ešte zoznamuje alebo už vedie rozhovor.
                for item in found:
                    if str(item.get("key") or "").lower() in ("wants", "chce", "hľadá", "hlada"):
                        patch["wants"] = str(item.get("value") or "")[:200]
                        patch["stage"] = "known"

            every = int(settings.get("summary_every") or 12)
            if every and len(rows) >= every:
                prepis = "\n".join(
                    f"{'on' if r['role'] == 'user' else 'ty'}: {r['content']}" for r in rows
                )
                patch["summary"] = (
                    await self._llm.summarize(str(row.get("facts") or ""), prepis)
                ).strip()[:2000]

            if patch:
                await self._db.update_fan(fan_uuid, patch)
        except Exception as exc:  # noqa: BLE001 - pamäť je bonus, nie podmienka
            log.warning("Pamäť sa nepodarilo doplniť: %s", exc)

    async def _try_link(
        self, fan: Dict[str, Any], row: Dict[str, Any], klik_plati: bool = False
    ) -> None:
        """Skúsi zistiť, či to nie je niekto, s kým si už písala.

        Checkout odkaz s Telegram id je istota, ale nie každý ňou prejde —
        odkaz sa dá otvoriť inokedy alebo z iného zariadenia. Vtedy ostáva
        meno, komu sme odkaz nedávno poslali, a čerstvý klik na krátky odkaz.
        Keď to nestačí na istotu, radšej sa nespojí nič: neznámemu sa prihovorí
        ako novému a nič sa nestane, ale zle spojenému by pripomínala cudzie
        zážitky.

        `klik_plati` zapína dôkaz z kliku — viď `fanmatch.best`.
        """
        if hub := getattr(self._db, "hub", None):
            await hub.observe("fanvue", fan["uuid"], fan.get("handle", ""), fan.get("display_name", ""), fan.get("text", ""))
            return
        try:
            chats = await self._db.link_candidates()
            taken = await self._db.linked_tg_ids()
        except Exception as exc:  # noqa: BLE001 - spojenie je bonus
            log.warning("Kandidátov sa nepodarilo načítať: %s", exc)
            return

        hit = fanmatch.best(fan, chats, taken=taken, klik_plati=klik_plati)
        if not hit:
            log.info("Fanúšik %s ostáva nespojený", fan["uuid"][:8])
            return

        await self._db.update_fan(fan["uuid"], {"tg_id": hit["tg_id"]})
        row["tg_id"] = hit["tg_id"]
        log.info(
            "Fanúšik %s spojený s Telegramom %s (%s, %s bodov)",
            fan["uuid"][:8], hit["tg_id"], hit["why"], hit["score"],
        )


# Slová, po ktorých to vyzerá, že ponuka naozaj odišla. Nie je to presné a
# nemusí byť — slúži len na odstup medzi ponukami, nie na účtovníctvo.
_PONUKA = ("$", "unlock", "send you", "for you if", "tip", "buy", "pay")


def _offered(text: str) -> bool:
    low = text.lower()
    return any(word in low for word in _PONUKA)
