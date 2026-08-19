"""Jazyky modelky — katalóg a preklad nastavenia do promptu.

PREČO SAMOSTATNÝ MODUL
----------------------
Jazyk sa dotýka troch miest naraz: `persona.build_system_prompt` (Telegram),
`fanvue_agent.build_prompt` (Fanvue) a `humanize.looks_foreign` (detekcia, že
napísal inak). Kým to bolo rozsypané, Fanvue o vedľajších jazykoch nevedelo
vôbec a v jadre pravidiel svietilo natvrdo „ÚROVEŇ ANGLIČTINY: B1–B2" aj
modelke, ktorá po anglicky nemá písať.

Tu je jeden zdroj: katalóg, úrovne a text, ktorý z toho vznikne.

KATALÓG JE TU A V `web/lib/languages.ts`
---------------------------------------
Dve kópie, nie tri — databáza zoznam zámerne nepozná (stráži len tvar). Web ho
potrebuje na vykreslenie výberu, worker na preklad do promptu. Keď pribudne
jazyk, pribudne na oboch miestach; `tests/test_jazyky.py` stráži, že sa kódy
nerozišli.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Kód (ISO 639-1) -> ako sa jazyk volá v prompte. Anglické názvy zámerne: prompt
# je po slovensky, ale model rozumie „German" spoľahlivejšie než „nemčina", a
# hlavne to je jazyk, v ktorom má potom písať.
KATALOG: Dict[str, str] = {
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "cs": "Czech",
    "sk": "Slovak",
    "ru": "Russian",
    "uk": "Ukrainian",
    "tr": "Turkish",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "ro": "Romanian",
    "hu": "Hungarian",
    "el": "Greek",
    "ar": "Arabic",
    "ja": "Japanese",
}

UROVNE: Tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")

DEFAULT_PRIMARY = "en"

# Ako sa na danej úrovni PÍŠE. Toto je celý rozdiel medzi „vie po španielsky"
# a „naučila sa kedysi trochu po španielsky" — a presne to od nej chceme.
_STYL_UROVNE: Dict[str, str] = {
    "A1": (
        "vieš len pár slov. Zvládneš pozdrav a jednu krátku vetu, nič viac. "
        "Priznaj, že toho vieš málo, a vráť sa k hlavnému jazyku."
    ),
    "A2": (
        "vieš základy. Krátke jednoduché vety, prítomný čas, bežné slová. "
        "Robíš chyby a je to tak v poriadku. Keď je téma zložitejšia, povedz, "
        "že to po tvojom nedáš, a prejdi späť."
    ),
    "B1": (
        "dohovoríš sa, ale jednoducho. Krátke vety, bežné slová, žiadne idiomy "
        "ani slovné hračky. Raz za čas spravíš drobnú chybu (zlý rod, pád, "
        "predložka) — presne ako človek, ktorý sa jazyk kedysi učil. "
        "Nepredstieraj dokonalosť."
    ),
    "B2": (
        "hovoríš dobre, ale nie ako rodená. Zložitejšie vety zvládneš, občas "
        "siahneš po nie celkom presnom slove alebo po jednoduchšej väzbe. "
        "Idiomy skoro nepoužívaš."
    ),
    "C1": (
        "hovoríš veľmi dobre. Znie to prirodzene, len raz za čas presvitne, že "
        "to nie je tvoj rodný jazyk."
    ),
    "C2": (
        "hovoríš prakticky ako rodená. Píš úplne prirodzene."
    ),
}


def nazov(kod: str) -> str:
    """Kód -> názov jazyka. Neznámy kód vráti sám seba, nie výnimku: prompt sa
    kvôli jednému preklepu v databáze nesmie prestať skladať."""
    return KATALOG.get((kod or "").strip().lower(), (kod or "").strip().lower())


def _uroven(hodnota: Any) -> str:
    u = str(hodnota or "").strip().upper()
    return u if u in UROVNE else "B1"


def primarny(persona: Dict[str, Any]) -> str:
    kod = str(persona.get("lang_primary") or "").strip().lower()
    return kod if kod in KATALOG else DEFAULT_PRIMARY


def vedlajsie(persona: Dict[str, Any]) -> List[Tuple[str, str]]:
    """[(kód, úroveň)] — len známe jazyky, bez primárneho, najviac tri.

    Databáza tvar stráži, ale worker číta aj personu, ktorá mohla vzniknúť pred
    migráciou — a hlavne nesmie spadnúť na dátach, ktoré nečakal.
    """
    raw = persona.get("lang_extra")
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, list):
        return []

    hlavny = primarny(persona)
    out: List[Tuple[str, str]] = []
    videne = {hlavny}
    for polozka in raw:
        if not isinstance(polozka, dict):
            continue
        kod = str(polozka.get("code") or "").strip().lower()
        if kod not in KATALOG or kod in videne:
            continue
        videne.add(kod)
        out.append((kod, _uroven(polozka.get("level"))))
        if len(out) >= 3:
            break
    return out


def zoznam_kodov(persona: Dict[str, Any]) -> List[str]:
    """Všetky jazyky, ktoré ovláda — primárny prvý. Používa to detekcia."""
    return [primarny(persona)] + [kod for kod, _ in vedlajsie(persona)]


def uroven_primarneho(persona: Dict[str, Any]) -> str:
    """Úroveň hlavného jazyka.

    Zámerne NIE C2. Ona nie je rodená hovoriaca a nemá tak ani písať — jadro
    pravidiel to doteraz riešilo vetou „ÚROVEŇ ANGLIČTINY: B1–B2", ktorá platila
    aj pre modelku, čo po anglicky vôbec nepíše. Teraz je to vlastnosť jazyka,
    nie natvrdo napísaná angličtina.
    """
    return "B1-B2"


def pravidlo_hlavneho(persona: Dict[str, Any]) -> str:
    """Riadok do jadra pravidiel — nahrádza natvrdo napísanú angličtinu."""
    return (
        f"ÚROVEŇ JAZYKA ({nazov(primarny(persona))}): {uroven_primarneho(persona)}. "
        "Nie si rodená hovoriaca. Jednoduché časy, bežné slová, žiadne idiomy, "
        "žiadne kvetnaté výrazy. Občas malá chyba je v poriadku — znie to "
        "prirodzenejšie než dokonalý jazyk."
    )


def blok_znalosti(persona: Dict[str, Any], vlastnymi_slovami: str = "") -> str:
    """Sekcia „čo vieš za jazyky". Toto je to, čo odpovie, keď sa jej spýta."""
    hlavny = primarny(persona)
    extra = vedlajsie(persona)

    riadky = [
        "JAZYKY, KTORÉ VIEŠ (toto je pravda o tebe)",
        f"- {nazov(hlavny)} — tvoj hlavný jazyk. Píšeš ním prirodzene a takmer vždy.",
    ]
    for kod, uroven in extra:
        riadky.append(f"- {nazov(kod)} — úroveň {uroven}: {_STYL_UROVNE[uroven]}")

    if not extra:
        riadky.append(
            "- Iný jazyk NEVIEŠ. Netvár sa, že áno, ani zo zdvorilosti."
        )

    if vlastnymi_slovami:
        # Klientov voľný text ostáva — vie povedať nuansu, ktorú kód nezachytí
        # („s Nemcami radšej po anglicky, hanbí sa"). Ide POD štruktúru, aby
        # tvrdé fakty ostali tvrdé.
        riadky += ["", f"Ešte k tomu: {vlastnymi_slovami}"]

    riadky += [
        "",
        "Keď sa ťa spýta, akými jazykmi hovoríš, povedz to podľa tohto — normálne "
        "vo vete, nie ako zoznam a nie ako životopis. Pokojne s nadhľadom "
        "(„trochu po španielsky, ale fakt len trochu“). Nikdy netvrď, že "
        "vieš jazyk, ktorý tu nie je, a nikdy nezapieraj ten, ktorý tu je.",
    ]
    return "\n".join(riadky)


def blok_cudzia_sprava(persona: Dict[str, Any]) -> str:
    """Sekcia „napísal ti iným jazykom". Pridáva sa, len keď to naozaj nastalo."""
    hlavny = nazov(primarny(persona))
    extra = vedlajsie(persona)

    if not extra:
        return (
            "NAPÍSAL TI INÝM JAZYKOM\n"
            f"Nerozumieš mu — vieš len {hlavny}. Povedz to milo a s humorom a "
            f"nech to skúsi po {hlavny}. Buď roztomilá, nie odmeraná.\n"
            "NEPREKLADAJ jeho správu a nepredstieraj, že si rozumela."
        )

    zoznam = ", ".join(f"{nazov(k)} ({u})" for k, u in extra)
    return (
        "NAPÍSAL TI INÝM JAZYKOM\n"
        f"Okrem hlavného jazyka vieš: {zoznam}.\n"
        "Ak je to jeden z nich, odpovedz mu V ŇOM a presne na tej úrovni, ktorú "
        "tam máš — vrátane chýb a jednoduchosti. Nezlepši sa zrazu na rodenú, "
        "to je najväčší prezradzovač.\n"
        f"Ak je to jazyk, ktorý nevieš, povedz to milo a s humorom po {hlavny} a "
        "nech to skúsi tak. NEPREKLADAJ jeho správu a nepredstieraj, že si "
        "rozumela.\n"
        "ŠTÝL SA NEMENÍ. Aj v cudzom jazyku píšeš krátko, nedbalo, s tými istými "
        "emoji a bez typografických znakov — si tá istá osoba, len iným jazykom. "
        "A cieľ ostáva rovnaký: bavte sa ďalej.\n"
        "Keď sa vráti k tvojmu hlavnému jazyku, vráť sa aj ty."
    )


def pripomenutie(persona: Dict[str, Any]) -> str:
    """Krátka pripomienka na koniec promptu — jazyk sa inak stráca v dĺžke."""
    hlavny = nazov(primarny(persona))
    if vedlajsie(persona):
        return (
            f"PRIPOMENUTIE — píš po {hlavny}. Výnimka je len vtedy, keď ti "
            "napísal jazykom, ktorý ovládaš — vtedy mu odpovedz v ňom, na svojej "
            "úrovni."
        )
    return f"PRIPOMENUTIE — píš po {hlavny}."


__all__ = [
    "KATALOG",
    "UROVNE",
    "DEFAULT_PRIMARY",
    "nazov",
    "primarny",
    "vedlajsie",
    "zoznam_kodov",
    "pravidlo_hlavneho",
    "blok_znalosti",
    "blok_cudzia_sprava",
    "pripomenutie",
]
