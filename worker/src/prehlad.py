"""Kto je ten človek — zhrnutie chatu pre majiteľa v control bote.

PREČO TO EXISTUJE. V automatickom režime si modelka píše sama a majiteľ do
toho nevidí. Keď potom prepne na poloautomat, dostane kartu s návrhmi na
odpoveď človeku, ktorého v živote nevidel: nevie, ako sa volá, o čom sa
bavili, či už zaplatil ani či mu niečo sľúbila. Vybrať z troch návrhov sa
v takej chvíli nedá inak než naslepo.

NIČ SA TU NEGENERUJE. Všetko, čo tu je, už v databáze leží — zhrnutie, ktoré
si modelka píše sama, fakty, čísla lievika, posledné správy. Volanie modelu by
stálo coiny a sekundy navyše a povedalo by to isté, len menej presne.

Text je anglicky, ako celý control bot, a skladá sa zhora nadol podľa toho, čo
majiteľ potrebuje najskôr: KTO to je → AKO to medzi nimi ide → ČO o ňom vieme
→ ČO si naposledy písali.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Koľko posledných správ ukázať. Osem je asi obrazovka na telefóne — dosť na
# to, aby bolo vidieť tón aj tému, a málo na to, aby sa to dalo prečítať skôr,
# než človeka prejde chuť.
SPRAV = 8
# Telegram má strop 4096 znakov na správu; nechávame si rezervu na formátovanie.
MAX_ZNAKOV = 3500


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def odkedy(value: Any, teraz: Optional[datetime] = None) -> str:
    """„3 days" / „2 hours" / „" keď sa to nedá zistiť."""
    kedy = _ts(value)
    if not kedy:
        return ""
    sekundy = ((teraz or datetime.now(timezone.utc)) - kedy).total_seconds()
    if sekundy < 90:
        return "just now"
    if sekundy < 5400:
        return f"{int(sekundy // 60)} min"
    if sekundy < 172800:
        return f"{int(sekundy // 3600)} h"
    return f"{int(sekundy // 86400)} days"


def bez_znaciek(text: str) -> str:
    """Odoberie z CUDZIEHO textu značky, ktoré by rozhodili formátovanie karty.

    Správy fanúšikov a fakty sme nepísali my, takže dvojica `*` alebo backtick
    v ich texte spraví z kusu prehľadu tučné písmo či blok kódu. Nie je to pád,
    len zmätok — ale zmätok na obrazovke, ktorá má práve odpovedať na otázku
    „kto to je".

    `_` sa ZÁMERNE necháva: v týchto textoch je oveľa častejšie súčasťou mena
    (`simona_here`) alebo kľúča faktu (`how_found`) než párovou značkou, a
    odstránené by z prezývky spravilo nezmysel. Osamotená značka ostáva
    v Telethone obyčajným znakom.
    """
    return str(text or "").replace("*", "").replace("`", "")


def _prepis(spravy: List[Dict[str, Any]]) -> List[str]:
    """Posledné správy ako dialóg. `her:` / `him:` — nie role z databázy."""
    out = []
    for message in spravy[-SPRAV:]:
        kto = "her" if str(message.get("role")) == "assistant" else "him"
        text = " ".join(bez_znaciek(message.get("content")).split())
        if not text:
            continue
        out.append(f"*{kto}:* {text[:220]}")
    return out


def _fakty(polozky: List[Dict[str, Any]], limit: int = 12) -> List[str]:
    out = []
    for fact in polozky:
        kluc = bez_znaciek(fact.get("key")).strip().replace("_", " ")
        hodnota = bez_znaciek(fact.get("value")).strip()
        if kluc and hodnota:
            out.append(f"• {kluc}: {hodnota}")
        if len(out) >= limit:
            break
    return out


def _orez(text: str) -> str:
    if len(text) <= MAX_ZNAKOV:
        return text
    return text[: MAX_ZNAKOV - 1] + "…"


def telegram(
    user: Dict[str, Any],
    facts: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    teraz: Optional[datetime] = None,
) -> str:
    """Zhrnutie telegramového chatu."""
    # Meno z Telegramu je fakt; `partner_name` je to, ako ho oslovuje ONA — a
    # vytiahol ho z rozhovoru model, takže sa občas mýli (naostro sa z vety
    # „Definitely" stalo meno a modelka mu tak hovorila celý deň). Preto sa
    # ukazujú obe, keď sa líšia: majiteľ tak zároveň vidí, že sa má čo opraviť.
    meno = bez_znaciek(user.get("first_name")).strip()
    oslovuje = bez_znaciek(user.get("partner_name")).strip()
    znacka = bez_znaciek(user.get("username")).strip()
    hlavicka = meno or oslovuje or (f"@{znacka}" if znacka else str(user.get("tg_id") or "?"))
    if hlavicka and znacka and hlavicka != f"@{znacka}":
        hlavicka = f"{hlavicka} (@{znacka})"

    riadky = [f"🧠 *{hlavicka}*"]
    if oslovuje and oslovuje.lower() != meno.lower():
        riadky.append(f"_She calls him *{oslovuje}* in the chat._")

    stav = []
    pozname = odkedy(user.get("created_at"), teraz)
    if pozname:
        stav.append(f"talking for {pozname}")
    spravy = int(user.get("msg_count") or 0)
    if spravy:
        stav.append(f"{spravy} messages")
    if user.get("paid"):
        stav.append("💚 has paid")
    elif user.get("link_clicked_at"):
        stav.append("👀 opened the link")
    elif user.get("link_sent_at"):
        stav.append("🔗 got the link")
    faza = str(user.get("funnel_stage") or "").strip()
    if faza and not user.get("paid"):
        stav.append(faza)
    if stav:
        riadky.append(" · ".join(stav))

    # Rozlúčka je dôležitejšia než čokoľvek nižšie: modelka mu už povedala, že
    # sa presúva inam, a odpoveď na to je iná ako odpoveď do živého chatu.
    if user.get("farewell_at"):
        riadky.append("⚠️ _She already said goodbye in this chat._")
    if user.get("human_takeover"):
        riadky.append("✋ _You took this chat over — the AI stays quiet here._")

    zhrnutie = bez_znaciek(user.get("summary")).strip()
    if zhrnutie:
        riadky += ["", "*How it's going*", zhrnutie]

    polozky = _fakty(facts)
    if polozky:
        riadky += ["", "*What she knows about him*"] + polozky

    prepis = _prepis(messages)
    if prepis:
        riadky += ["", "*Last messages*"] + prepis

    return _orez("\n".join(riadky))


def fanvue(
    row: Dict[str, Any],
    messages: List[Dict[str, Any]],
    tg: Optional[Dict[str, Any]] = None,
    teraz: Optional[datetime] = None,
) -> str:
    """Zhrnutie fanvue chatu. `tg` je spojený telegramový človek, ak je známy."""
    meno = bez_znaciek(row.get("display_name") or row.get("handle")).strip() or "fan"
    riadky = [f"🧠 *{meno}*"]

    stav = []
    pozname = odkedy(row.get("first_seen"), teraz)
    if pozname:
        stav.append(f"subscriber for {pozname}")
    spravy = int(row.get("msg_count") or 0)
    if spravy:
        stav.append(f"{spravy} messages")
    minul = int(row.get("spent_cents") or 0)
    if minul:
        stav.append(f"💰 spent ${minul / 100:.2f} ({int(row.get('bought_count') or 0)}×)")
    else:
        stav.append("subscription only, nothing bought yet")
    if stav:
        riadky.append(" · ".join(stav))

    # Toto je najcennejší riadok v celom prehľade: majiteľ vidí, že to nie je
    # cudzí človek, ale ten, s ktorým si modelka mesiac písala na Telegrame.
    if tg:
        user = (tg.get("user") or {}) if isinstance(tg, dict) else {}
        tg_meno = bez_znaciek(user.get("first_name")).strip()
        riadky.append(
            f"🔗 _Same person as *{tg_meno}* on Telegram._"
            if tg_meno
            else "🔗 _Linked to one of her Telegram chats._"
        )

    chce = bez_znaciek(row.get("wants")).strip()
    if chce:
        riadky.append(f"🎯 wants: {chce}")

    # Nesplnený sľub a neodomknutá ponuka menia, čo sa má práve teraz napísať —
    # preto stoja vysoko, nie medzi faktami.
    if row.get("promised_at"):
        slub = bez_znaciek(row.get("promised_what") or "content").strip()
        riadky.append(f"⚠️ _She promised him {slub} and hasn't sent it._")
    if row.get("pending_offer_at"):
        riadky.append("🔒 _He has an offer waiting, still unlocked._")
    if row.get("human_takeover"):
        riadky.append("✋ _You took this chat over — the AI stays quiet here._")

    zhrnutie = bez_znaciek(row.get("summary")).strip()
    if zhrnutie:
        riadky += ["", "*How it's going*", zhrnutie]

    fakty = bez_znaciek(row.get("facts")).strip()
    if fakty:
        riadky += ["", "*What she knows about him*", fakty]

    # Fakty z Telegramu sú často bohatšie než fanvue — je to ten istý človek.
    if tg and (tg.get("facts") or []):
        riadky += ["", "*From the Telegram chat*"] + _fakty(tg.get("facts") or [], 8)

    prepis = _prepis(messages)
    if prepis:
        riadky += ["", "*Last messages*"] + prepis

    return _orez("\n".join(riadky))


# --------------------------------------------------------------------------
# Na čo ešte neodpovedala
# --------------------------------------------------------------------------
#
# Kým majiteľ nerozhodne, fanúšik píše ďalej. Doteraz každá nová správa
# nahradila kartu novou, ktorá ukazovala LEN tú poslednú — a predchádzajúce
# zmizli aj s tým, na čo sa pýtal. Majiteľ potom odpovedal na tretiu vetu bez
# prvých dvoch.
#
# Karta preto ukazuje CELÝ neodpovedaný blok: všetko, čo napísal odvtedy, čo
# naposledy odpísala ona.

# Koľko z nich sa vojde na kartu. Viac než päť už nikto nečíta a karta
# prestane byť prehľadná; koľko ich je celkovo, sa dopíše slovom.
MAX_NEODPOVEDANYCH = 5


def neodpovedane(history: List[Dict[str, Any]]) -> List[str]:
    """Súvislý chvost jeho správ za jej poslednou odpoveďou.

    Ide sa od konca a končí sa pri prvej JEJ správe — čokoľvek pred ňou už
    zodpovedané bolo. Prázdny zoznam znamená, že posledné slovo mala ona.
    """
    out: List[str] = []
    for message in reversed(history or []):
        if str(message.get("role")) == "assistant":
            break
        text = " ".join(str(message.get("content") or "").split())
        if text:
            out.append(text)
    out.reverse()
    return out


def blok_neodpovedanych(history: List[Dict[str, Any]]) -> str:
    """Neodpovedané správy do jedného textu pre kartu, po jednej na riadok.

    Ukladá sa aj do `pending_replies.incoming_preview`, takže po návrate
    z foto-wizardu sa karta poskladá rovnako — riadky sa len rozdelia späť.
    """
    spravy = neodpovedane(history)
    if not spravy:
        return ""
    if len(spravy) <= MAX_NEODPOVEDANYCH:
        return "\n".join(spravy)
    skryte = len(spravy) - MAX_NEODPOVEDANYCH
    posledne = spravy[-MAX_NEODPOVEDANYCH:]
    return "\n".join([f"(+{skryte} earlier)"] + posledne)


# Značka, ktorou sa v uloženom náhľade odlíši JEJ správa od jeho. Náhľad ide
# do `pending_replies.incoming_preview` ako jeden text a karta sa z neho po
# návrate z foto-wizardu skladá znova rozdelením na riadky — bez značky by sa
# po tej ceste stratilo, kto čo povedal.
JEJ = "\u21b3 "

# Koľko JEHO správ ukázať. Keď ich napíše dvadsať za sebou, na kartu patrí
# posledných desať — zvyšok sa zhrnie do „(+N earlier)". Jej odpovede, ktoré
# medzi nimi sedia, sa pridávajú NAVYŠE a do tohto počtu sa nerátajú.
JEHO_MAX = 10

# Keby v tom úseku jej odpoveď nebola vôbec (napísal desať viet za sebou),
# doberie sa ešte toľkoto riadkov dozadu, aby bolo na čo nadviazať.
DOBRAT_MAX = 10


def blok_rozhovoru(history: List[Dict[str, Any]]) -> str:
    """Posledné správy OBOCH strán tak, ako idú za sebou — ako v chate.

    PREČO. Karta doteraz ukazovala len JEHO neodpovedané správy pod sebou.
    Marek z nej videl päť jeho viet bez toho, čo im predchádzalo od nej —
    takže sa nemal na čo napojiť a musel si chat otvárať vedľa. Keď napíše
    dve za sebou, sú tu dve za sebou; keď medzi tým odpovedala ona, je tam
    aj jej odpoveď. Presne ako to vyzerá na Fanvue.

    Jej riadky nesú `JEJ` značku, jeho sú bez nej.
    """
    vsetko = [
        r for r in (history or [])
        if bez_znaciek(str((r or {}).get("content") or "")).strip()
    ]
    if not vsetko:
        return ""

    def jeho(row: Dict[str, Any]) -> bool:
        return str((row or {}).get("role") or "") != "assistant"

    # Odzadu, kým nemáme desať JEHO správ. Jej odpovede cestou beriem so
    # sebou — sú to práve tie, ktoré medzi jeho správami naozaj padli.
    vybrane: List[Dict[str, Any]] = []
    jeho_pocet = 0
    i = len(vsetko) - 1
    while i >= 0 and jeho_pocet < JEHO_MAX:
        if jeho(vsetko[i]):
            jeho_pocet += 1
        vybrane.append(vsetko[i])
        i -= 1

    # Keď v tom úseku nič jej nie je (napísal desať viet za sebou), doberie sa
    # UŽ LEN jej posledná odpoveď — nie jeho správy cestou k nej. Inak by
    # strop na desať jeho správ nič neznamenal.
    if all(jeho(r) for r in vybrane):
        for k in range(i, max(-1, i - DOBRAT_MAX), -1):
            if not jeho(vsetko[k]):
                vybrane.append(vsetko[k])
                break

    vybrane.reverse()
    riadky = [
        (JEJ if not jeho(r) else "") + bez_znaciek(str(r.get("content") or "")).strip()
        for r in vybrane
    ]
    # „(+N earlier)" hovorí, koľko toho je pred prvým zobrazeným riadkom —
    # nie koľko riadkov chýba celkovo. Jej dobratá odpoveď môže byť spred
    # niekoľkých jeho správ, ktoré sa nezobrazia, a to je v poriadku.
    prvy = vsetko.index(vybrane[0])
    skryte = prvy
    if skryte:
        riadky.insert(0, f"(+{skryte} earlier)")
    return "\n".join(riadky)


def pokyn_pre_model(history: List[Dict[str, Any]]) -> str:
    """Veta do promptu, keď čaká viac jeho správ naraz. Prázdna = jedna stačí.

    Model síce celý blok vidí v histórii, ale bez tejto vety odpovie na
    POSLEDNÚ vetu — a človek, ktorý napísal tri veci a dostal odpoveď na
    jednu, má pocit, že ho nikto nečíta.

    Používa sa len v poloautomate. V automate to isté rieši debounce, ktorý
    rýchlo idúce správy zlúči skôr, než sa vôbec začne odpovedať.
    """
    kolko = len(neodpovedane(history))
    if kolko < 2:
        return ""
    return (
        f"\n\n[ČAKÁ VIAC SPRÁV] Napísal ti {kolko} správy za sebou a ani na "
        "jednu si ešte neodpovedala. Odpovedz na ne AKO NA CELOK — JEDNOU "
        "správou, ktorá sedí na všetky, nie len na tú poslednú. Keď sa v nich "
        "pýta na niečo konkrétne, na to odpovedz najskôr.\n"
        "NEODPOVEDAJ NA KAŽDÚ ZVLÁŠŤ. Nie každá si odpoveď pýta — „ok“, "
        "smajlík alebo tvoje meno sú len prikývnutie a reagovať na ne "
        "osobitne vyzerá, akoby si odpisovala zoznamu. Vyber to, čo naozaj "
        "niečo hovorí, a na to odpovedz.\n"
        "A NEPÍŠ PRETO DLHŠIE. Tri jeho správy neznamenajú trikrát dlhšiu "
        "odpoveď — dĺžka ostáva rovnaká, ako keby napísal jednu."
    )
