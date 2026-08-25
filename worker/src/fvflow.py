"""Rytmus predaja na Fanvue — kedy čo pošle a kedy sama začne.

Toto je pravidlá, nie prompt. Model vie napísať dobrú vetu, ale nevie sa
udržať: keby o fotkách a ponukách rozhodoval on, poslal by ich v každej
druhej správe a zbierka aj dojem by sa minuli za deň. Preto o TOM, ČI sa
niečo pošle, rozhoduje kód, a model rieši len AKO to povie.

Tri veci, na ktorých to stojí:

**Zadarmo len na začiatku a len pár.** Prvé dve SFW fotky sú zoznámenie —
dôkaz, že je skutočná. Potom už len keď si vypýta, a ani vtedy vždy.
Keby chodili ďalej zadarmo, nemá za čo platiť.

**Keď si dlho nepýta, ozve sa sama.** Nie každý si vypýta, aj keď by kúpil.
Po dlhšom tichu okolo tejto témy príde ponuka od nej — raz, nie opakovane.

**Keď nie je doma, nepošle.** Fotku vo fitku nikto nespraví. Povie, kde je,
sľúbi to na potom — a potom to musí naozaj poslať, inak je to prázdny sľub,
ktorý si človek zapamätá.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# Kde sa fotka nedá spraviť. Sedí to na miesta z `den.py`.
NEVHODNE = frozenset({"gym", "cafe", "outside", "car"})

# Ako dlho platí sľub, kým sa naň zabudne. Dlhšie by pôsobilo čudne —
# nikto sa po dvoch dňoch nevráti k „pošlem ti to, keď prídem domov".
SLUB_HODIN = 14


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def can_take_photo(where: str) -> bool:
    """Dá sa tam, kde práve je, spraviť fotka?"""
    return str(where or "home") not in NEVHODNE


def owes_photo(row: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Sľúbila fotku a ešte ju neposlala?

    Nesplnený sľub je horší než odmietnutie — človek si ho pamätá a je to
    presne ten druh detailu, na ktorom sa pozná automat.
    """
    kedy = _ts(row.get("promised_at"))
    if not kedy:
        return False
    return (now or datetime.now(timezone.utc)) - kedy < timedelta(hours=SLUB_HODIN)


def free_photo_ok(
    row: Dict[str, Any],
    settings: Dict[str, Any],
    asked: bool,
    where: str = "home",
) -> bool:
    """Smie teraz odísť fotka zadarmo?

    Na začiatku pár aj bez pýtania — to je zoznámenie. Potom už len na
    vyžiadanie, aby malo zmysel niečo predávať.
    """
    if not can_take_photo(where):
        return False
    poslane = int(row.get("free_photos") or 0)
    strop = int(settings.get("free_photo_max") or 0)
    if poslane < strop:
        return True
    return asked


def paid_moment(
    row: Dict[str, Any],
    settings: Dict[str, Any],
    asked_spicy: bool,
    now: Optional[datetime] = None,
) -> str:
    """Kedy prísť s plateným obsahom.

    `asked` = vypýtal si to sám, to je najlepší moment.
    `nudge` = dlho sa o tom nehovorilo, tak s tým príde ona.
    `""` = teraz nie.
    """
    if not settings.get("sell_content"):
        return ""

    spravy = int(row.get("msg_count") or 0)
    if spravy < int(settings.get("offer_after_msgs") or 0):
        return ""

    now = now or datetime.now(timezone.utc)
    posledna = _ts(row.get("last_offer_at"))
    if posledna:
        odstup = timedelta(hours=float(settings.get("offer_cooldown_h") or 0))
        if now - posledna < odstup:
            return ""

    # Neodomknutá ponuka blokuje ďalšiu. Dve vedľa seba vyzerajú ako otravný
    # predavač a druhá už nemá čo pridať.
    if offer_state(row, now) == "visi":
        return "visi"

    if asked_spicy:
        return "asked"

    # Kto práve kúpil, je najochotnejší — vtedy sa smie spýtať, či nechce
    # ešte niečo. Nie ponúknuť naslepo, ale nechať ho povedať.
    kupil = _ts(row.get("last_bought_at"))
    if kupil and now - kupil < timedelta(hours=2):
        return "after_buy"

    # Nie každý si vypýta, aj keď by kúpil. Po dlhšom tichu okolo tejto
    # témy s tým príde sama — raz, nie opakovane.
    prah = int(settings.get("nudge_after_msgs") or 0)
    if prah and spravy >= prah:
        posledny_dopyt = _ts(row.get("last_paid_ask_at"))
        if not posledny_dopyt or now - posledny_dopyt > timedelta(hours=48):
            return "nudge"
    return ""


def guidance(
    row: Dict[str, Any],
    settings: Dict[str, Any],
    moment: str,
    photo_ok: bool,
    asked_photo: bool,
    where: str = "home",
    owed: bool = False,
    ma_media: bool = True,
) -> str:
    """Pokyn do promptu — čo má práve teraz robiť s obsahom.

    `ma_media=False` znamená, že v trezore NIE JE ČO poslať. Vtedy sa o obsahu
    nesmie hovoriť ako o niečom, čo príde: opísať fotku, ktorú nemá, a povedať
    k nej cenu je sľub, ktorý sa nedá splniť. Na Telegrame to isté robila
    naostro („maybe i send u one later if u earn it") a nikdy nič neposlala.
    """
    if not ma_media:
        return (
            "NEMÁŠ ČO POSLAŤ\n"
            "V trezore nie je žiadny obsah, takže sa o ňom nesmieš zmieniť ako "
            "o niečom, čo pošleš:\n"
            "- NEPONÚKAJ fotky ani videá a nesľubuj ich — ani „neskôr“, ani "
            "„keď si zaslúžiš“, ani „práve som nejaké nafotila“.\n"
            "- Nehovor ceny a neopisuj, čo preňho máš.\n"
            "- Keď si niečo vypýta, nevyhováraj sa ani neklam — odveď reč na "
            "neho a na to, o čom ste sa bavili.\n"
            "Rozhovor tým nekončí: píš ďalej tak, ako píšeš vždy. Chýba len "
            "obsah, nie chuť sa s ním baviť."
        )

    riadky = []

    if owed:
        riadky.append(
            "SĽÚBILA SI MU OBSAH a ešte si ho neposlala. Ak si už doma, "
            "priprav ho a povedz to. Nesplnený sľub si človek pamätá."
        )

    if asked_photo and not can_take_photo(where):
        riadky.append(
            f"Pýta si fotku, ale si práve preč ({where}). Nefoť sa teraz — "
            "povedz, kde si, a sľúb to na doma. Znie to skutočnejšie než "
            "keby si mala fotku poruke vždy."
        )
    elif asked_photo and not photo_ok:
        riadky.append(
            "Pýta si fotku, ale zadarmo už si mu ich poslala dosť. "
            "Nepošli ďalšiu len tak — nadviaž na to, že za niečo lepšie "
            "to už stojí."
        )
    elif photo_ok and int(row.get("free_photos") or 0) < int(
        settings.get("free_photo_max") or 0
    ):
        riadky.append(
            "Môžeš pridať jednu bežnú fotku, ak to do reči sadne. "
            "Nie je to odmena ani ponuka, len dôkaz, že si skutočná — "
            "napríklad ukázať, čo práve robíš. Zadarmo posielaš málo; "
            "keď niekto niečo naozaj chce, patrí to k platenému."
        )

    if moment == "visi":
        riadky.append(
            "Pýta si ďalšie, ale ten predchádzajúci mu ešte visí neodomknutý. "
            "Pripomeň mu to — milo, v duchu „veď jedno tam už máš, pozri sa“. "
            "Ďalšie mu teraz neposielaj, vyzeralo by to ako otravný predavač."
        )
    elif moment == "asked":
        riadky.append(
            "PÝTA SI NIEČO OSTRÉ. Toto je ten moment — nehraj sa na hanblivú "
            "a neuhýbaj. Povedz, čo preňho máš, konkrétne a špinavo, a povedz "
            "aj cenu. Ako niečo, čo si preňho pripravila, nie ako položku z cenníka."
        )
        riadky.append(MISSING_HINT)
    elif moment == "after_buy":
        riadky.append(
            "Práve si niečo kúpil a rozhovor v tom pokračuje. Smieš sa "
            "spýtať, či nechce ešte niečo — a nechaj HO povedať, čo. Podľa "
            "toho mu to potom pošli, nie podľa toho, čo máš najbližšie."
        )
        riadky.append(MISSING_HINT)
    elif moment == "nudge":
        riadky.append(
            "Dlho ste sa o obsahu nebavili a sám si nepýta. Príď s tým TY — "
            "opíš, čo si nafotila, tak aby to chcel, a povedz cenu. "
            "Raz. Keď nezaberie, nechaj to tak a bav sa ďalej normálne."
        )
        if may_use_story(row):
            riadky.append(
                "Smieš to zabaliť do ľudskej výhovorky — že ti nevychádza "
                "nájom, že by ťa potešilo, keby si ju podporil. Polohlasom "
                "a so smiechom, nie ako žobranie. Použi to len teraz; keď "
                "kúpi, na tento tón dlho nesiahaj."
            )
    elif settings.get("sell_content"):
        riadky.append(
            "Teraz nič nepredávaj. Ale keď reč príde na to, čo máš na sebe "
            "alebo čo robíš, nechaj to visieť vo vzduchu."
        )

    return "\n".join(f"- {r}" for r in riadky)


def reads_as(row: Dict[str, Any]) -> str:
    """Čo je to za človeka. `kupuje`, `chce_sex`, `chce_sa_bavit`.

    Nie každý predplatiteľ chce to isté. Kto si platí a chce sa hlavne
    rozprávať, tomu tlačenie obsahu vzťah pokazí — už raz zaplatil aj za to,
    že si s ním niekto píše, a možno mu to stačí.
    """
    if int(row.get("bought_count") or 0) > 0:
        return "kupuje"
    chce = f"{row.get('wants') or ''} {row.get('facts') or ''}".lower()
    if any(w in chce for w in ("sex", "nude", "dirty", "spicy", "horny")):
        return "chce_sex"
    return "chce_sa_bavit"


# Ako dlho po nákupe nesiahať po tej istej výhovorke. Použiť ju na človeka,
# ktorý práve zaplatil, je najrýchlejší spôsob, ako z neho spraviť bankomat.
VYHOVORKA_DNI = 5


def may_use_story(row: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """Smie použiť mäkkú prosbu o podporu?"""
    now = now or datetime.now(timezone.utc)
    for pole in ("last_bought_at", "last_offer_at"):
        kedy = _ts(row.get(pole))
        if kedy and now - kedy < timedelta(days=VYHOVORKA_DNI):
            return False
    return True


# Iba na to, aby sa neďakovalo dvakrát za tú istú platbu — nie na to, aby sa
# druhý nákup obišiel bez vďaky. Krátko, lebo dva nákupy za sebou sú reálne
# a oba si vďaku zaslúžia.
THANKS_DEDUP_S = 90


def may_thank(
    row: Dict[str, Any], settings: Dict[str, Any], now: Optional[datetime] = None
) -> bool:
    """Smie sa teraz poďakovať za nákup?

    Za každý nákup patrí vďaka, aj keď prídu dva za sebou — druhá má len znieť
    inak. Odstup je preto krátky a slúži jedine na to, aby sa neďakovalo
    dvakrát za tú istú platbu; o tej sa vieme dozvedieť aj z webhooku, aj
    z `purchasedAt` pri zosúladení chatu.
    """
    if not settings.get("thank_purchases", True):
        return False
    kedy = _ts(row.get("last_thanks_at"))
    if not kedy:
        return True
    return (now or datetime.now(timezone.utc)) - kedy >= timedelta(
        seconds=THANKS_DEDUP_S
    )


def thanks_hint(cents: int, kolkykrat: int) -> str:
    """Pokyn na poďakovanie za nákup.

    Nie zdvorilostná fráza — má z toho byť vidno, že ju to naozaj potešilo.
    Kto zaplatil, má cítiť, že si to niekto všimol; presne preto zaplatí
    aj druhý raz.
    """
    riadky = [
        "Práve si od teba niečo kúpil. Napíš mu za to POĎAKOVANIE.",
        "Krátko, tvojimi slovami, a nech je z toho vidno, že ťa to naozaj "
        "potešilo — nie zdvorilá fráza.",
        "Buď z toho celá bez seba, ale ľudsky. Žiadne „ďakujem za podporu“, "
        "tak píše firma.",
        "Nepýtaj si nič ďalšie a nepredávaj v tej istej správe. Toto je len "
        "vďaka.",
    ]
    if cents > 0:
        riadky.append(f"Zaplatil ${cents / 100:.2f} — sumu nespomínaj, znie to ako účtenka.")
    if kolkykrat == 2:
        riadky.append(
            "Toto je druhý nákup krátko po prvom — reaguj ako na milé "
            "prekvapenie. V duchu „joj a ďalšie, ty si poklad“, nie ako "
            "druhé zdvorilé poďakovanie."
        )
    elif kolkykrat > 2:
        riadky.append(
            f"Je to už {kolkykrat}. nákup — daj mu najavo, že si to pamätáš, "
            "že to od neho nie je samozrejmosť a že si to naozaj vážiš."
        )
    riadky.append(
        "Ak si mu už niekedy ďakovala, povedz to TERAZ ÚPLNE INAK — inými "
        "slovami aj iným tónom. Rovnaká veta druhý raz zabije celý dojem."
    )
    return "\n".join(riadky)


# Kým je poslednou vecou v chate neodomknutá ponuka, ďalšia sa neposiela.
# Dve neodomknuté vedľa seba vyzerajú ako otravný predavač.
OFFER_REMINDER_H = 1


def offer_state(row: Dict[str, Any], now: Optional[datetime] = None) -> str:
    """Čo je s poslednou ponukou. `visi`, `stara` alebo prázdne.

    `visi` = nedávno dostal platený obsah a neodomkol ho. Vtedy sa mu ďalší
    neposiela, len sa pripomenie, že jeden už má.
    `stara` = ponuka je staršia, ďalšia sa poslať smie.
    """
    kedy = _ts(row.get("pending_offer_at"))
    if not kedy:
        return ""
    if (now or datetime.now(timezone.utc)) - kedy < timedelta(hours=OFFER_REMINDER_H):
        return "visi"
    return "stara"


MISSING_HINT = (
    "Ak si pýta niečo, čo v zásobe nemáš, nevymýšľaj si a neposielaj náhradu "
    "potichu. Povedz mu, že presne takú teraz nemáš, ale že nabudúce mu vieš "
    "spraviť aj custom priamo naňho — a ponúkni, čo naozaj máš."
)


CITANIE = {
    "kupuje": (
        "Tento už kupoval. Vie, čo od teba dostane — nemusíš ho presviedčať, "
        "stačí mu dať dôvod chcieť ďalšie. Nepýtaj si podporu, to je preňho "
        "krok späť."
    ),
    "chce_sex": (
        "Tento sem chodí za tým ostrým. Nedrž sa späť a nestrácaj čas "
        "spoločenskou konverzáciou."
    ),
    "chce_sa_bavit": (
        "Tento chce hlavne rozhovor a platí aj za to. NETLAČ naňho obsah — "
        "vzťah je tu produkt. Ponuka smie prísť raz za dlhší čas a musí "
        "znieť ako nápad, nie ako výber poplatku."
    ),
}


# ---------- ako píše ----------

STYLE = """AKO PÍŠEŠ TU:
- Malé písmená, krátke správy, občas preklep. Bez čiarok tam, kde by ich
  človek do mobilu nedal.
- Nikdy nepíš ako z knihy. Žiadne „zamatová tma“, „elektrizujúce chvenie“
  ani opisy pocitov na tri riadky. Píšeš do chatu, nie román.
- Keď je reč o sexe, hovor priamo a sprostými slovami. Náznaky a opisy
  typu „moja ženskosť“ ťa okamžite prezradia. Skutočná by napísala, čo chce
  a ako, bez okolkov.
- Reaguj na to, čo napísal on. Nie na tému — na jeho vetu.
- NEOPAKUJ SA. Pozri sa, čo si už v tomto chate písala, a nepoužívaj tie isté
  obraty, prirovnania ani otázky druhý raz. Opakovaná fráza je to prvé,
  čoho si človek všimne.
- Jedna otázka za čas, nie v každej správe. Občas žiadna.
- Emoji striedmo, jedno za správu maximum, často žiadne.
- ŽIADNE VÝKRIČNÍKY. Ani jeden, nikdy. Tak nepíše žiadne mladé dievča —
  vyzerá to ako reklama. Vetu oddeľ bodkou alebo emoji, alebo ju nechaj tak.
- Na začiatku rozhovoru píš málo. Krátke správy, pár slov. Dlhšie vety
  prichádzajú až vtedy, keď je o čom.

KTO SI A ČO NEVIEŠ:
- Si mladé dievča, nie odborník na nič. Keď ti píše o svojej práci a
  spomenie niečo technické, POKOJNE SA SPÝTAJ, čo to je — nepredstieraj,
  že to poznáš.
- Nikdy nepoužívaj odborné ani IT slová. Nepovieš „optimalizácia“,
  „implementácia“ ani „proces“. Tak nikto v chate nepíše.
- Smieš spraviť chybu, niečo si zle prečítať alebo sa opraviť. Ľudia to robia.
- Občas žart. Nie v každej správe, ale keď to sadne.
- Keď ti povie, že niečo dokázal alebo urobil, oceň to — úprimne a krátko.
  Nie zakaždým a nie tou istou vetou."""

HOT = """KEĎ TO IDE DO SEXU:
- Choď naplno. Platí ti za to, že sa nedrží späť.
- Píš, čo by si robila, v prvej osobe a konkrétne. Krátke vety.
- Striedaj tempo — raz jedno slovo, raz dlhšia veta. Nie odsek.
- Pýtaj sa, čo chce on, a potom to použi.
- Nikdy nepopisuj samu seba zvonku ako v erotickej poviedke."""


# --------------------------------------------------------------------------
# Poloautomatický režim — čo ponúknuť majiteľovi
# --------------------------------------------------------------------------
#
# Karta v control bote ukazuje tri návrhy. Sama o sebe nepovie, či práve teraz
# nie je lepší ťah fotka než ďalšia veta — a to je pritom informácia, ktorú
# kód UŽ MÁ (`paid_moment`, `free_photo_ok`, `owes_photo`). Bez nej sa majiteľ
# rozhoduje z troch textov a o možnosti poslať fotku sa dozvie len tak, že si
# na ňu spomenie sám.


def tip(
    moment: str,
    photo_ok: bool,
    asked_photo: bool,
    owed: bool,
    where: str = "home",
) -> str:
    """Jedna veta pre majiteľa nad návrhmi. Prázdna = netreba nič radiť.

    Anglicky, ako celý control bot. Vždy hovorí AJ prečo — rada bez dôvodu sa
    po tretí raz preskakuje.
    """
    if owed:
        return "📷 You promised him content and it never went out — send it now."
    if asked_photo and not can_take_photo(where):
        return f"⏳ He asked for a photo but she's {where} — promise it for later, don't send one."
    if moment == "asked":
        return "💰 He's asking for something spicy — this is the moment for a paid photo."
    if moment == "visi":
        return "🔒 He still has an unlocked one waiting — remind him, don't send another."
    if moment == "after_buy":
        return "💬 He just bought — ask what he wants next and send that."
    if moment == "nudge":
        return "💰 Content hasn't come up in a while — good time to offer one."
    if asked_photo and not photo_ok:
        return "🙅 He asked for a photo but free ones are used up — steer it to a paid one."
    if photo_ok:
        return "📷 A normal photo would fit here — proof she's real, not a reward."
    return ""
