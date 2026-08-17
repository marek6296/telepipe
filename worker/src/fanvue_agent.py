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
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import den
import fanmatch
import fvflow
import fvmedia
import fvsync
import fvvoice

log = logging.getLogger(__name__)

# Ako často sa pozerá do fronty. Webhook zapisuje do Supabase, agent si ju
# vyberá — priama cesta by znamenala písať odpoveď v tej istej požiadavke
# a Fanvue by ju medzitým vyhodnotil ako nedoručenú.
POLL_S = 5.0

ODPOVEDA_NA = "creator.message.received"
NOVY_ODBERATEL = ("creator.subscription.activated", "subscription.activated")
PLATBA = ("creator.payment.succeeded", "payment.succeeded")


# ---------- čítanie udalostí ----------


def wants_reply(event: Dict[str, Any]) -> bool:
    """Má sa na túto udalosť vôbec odpisovať?"""
    if event.get("type") != ODPOVEDA_NA:
        return False
    data = (event.get("payload") or {}).get("data") or {}
    # Vlastnú správu si nekomentuje a na automat odpovedať automatom je slučka.
    if data.get("sender") != "fan" or data.get("is_automated"):
        return False
    return bool((data.get("text") or "").strip())


def is_new_subscriber(event: Dict[str, Any]) -> bool:
    return event.get("type") in NOVY_ODBERATEL


def is_payment(event: Dict[str, Any]) -> bool:
    return event.get("type") in PLATBA


def fan_of(event: Dict[str, Any]) -> Dict[str, str]:
    data = (event.get("payload") or {}).get("data") or {}
    fan = data.get("fan") or data.get("user") or data.get("subscriber") or {}
    return {
        "uuid": str(fan.get("uuid") or ""),
        "handle": str(fan.get("handle") or ""),
        "display_name": str(fan.get("display_name") or ""),
        "avatar_url": str(fan.get("avatar_url") or ""),
        "text": str(data.get("text") or "").strip(),
    }


def paid_cents(event: Dict[str, Any]) -> int:
    data = (event.get("payload") or {}).get("data") or {}
    for key in ("amount", "amount_cents", "price"):
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
    """
    if str(row.get("stage") or "") == "known":
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
) -> str:
    """Systémový prompt pre Fanvue. Persona je tá istá osoba, pravidlá iné."""
    meno = persona.get("name") or "ona"
    faza = phase(row, settings)
    riadky: List[str] = [
        f"Si {meno}. Toto je tvoj chat na Fanvue — s človekom, ktorý ti UŽ PLATÍ.",
        "",
        "KTO SI:",
        str(persona.get("backstory") or "").strip(),
        "",
        "AKO PÍŠEŠ:",
        str(persona.get("msg_style") or "").strip(),
        str(persona.get("tone") or "").strip(),
        "",
        fvflow.STYLE,
        "",
        "JAZYK:",
        str(persona.get("language") or "").strip(),
    ]

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
    else:
        riadky += ["", "UŽ HO POZNÁŠ:"]
        chce = str(row.get("wants") or "").strip()
        if chce:
            riadky.append(f"Hľadá tu: {chce}. Veď rozhovor tým smerom.")
        else:
            riadky.append("Veď rozhovor podľa toho, na čo reaguje.")

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


class FanvueAgent:
    """Vyberá frontu udalostí a odpisuje na ne."""

    def __init__(self, db, api, llm) -> None:
        self._db = db
        self._api = api
        self._llm = llm

    async def run(self) -> None:
        log.info("Fanvue agent beží, kontroluje frontu každých %.0f s", POLL_S)
        while True:
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 - slučka nesmie umrieť
                log.exception("Kolo Fanvue zlyhalo: %s", exc)
            await asyncio.sleep(POLL_S)

    async def tick(self) -> None:
        settings = await self._db.settings()
        if fvmedia.due_to_post(settings, datetime.now(timezone.utc)):
            try:
                await self._post_to_feed(settings)
            except Exception as exc:  # noqa: BLE001 - feed nesmie zhodiť odpisovanie
                log.warning("Príspevok na feed zlyhal: %s", exc)

        events = await self._db.pending()
        if not events:
            return

        # Tri správy za sebou vyrobia tri udalosti. Keby sa odpovedalo na
        # každú, píše trikrát — odpovedá sa na STAV chatu, nie na udalosť.
        # Preto z každého chatu ide do spracovania len tá najnovšia a ostatné
        # sa označia za vybavené bez odpovede.
        posledna: Dict[str, Dict[str, Any]] = {}
        prebite: List[int] = []
        for event in events:
            kto = fan_of(event)["uuid"] if wants_reply(event) else ""
            if not kto:
                continue
            if kto in posledna:
                prebite.append(int(posledna[kto]["id"]))
            posledna[kto] = event

        for event in events:
            try:
                if int(event["id"]) in prebite:
                    log.info("Udalosť %s prebitá novšou v tom istom chate", event["id"])
                elif settings.get("enabled"):
                    await self._dispatch(event, settings)
            except Exception as exc:  # noqa: BLE001
                log.warning("Udalosť %s zlyhala: %s", event.get("id"), exc)
            finally:
                # Označí sa vždy, aj keď sa neodpisuje. Inak by tá istá
                # udalosť visela vo fronte donekonečna a blokovala novšie.
                await self._db.mark_handled(int(event["id"]))

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

        kupene = int(row.get("bought_count") or 0) + 1
        teraz = datetime.now(timezone.utc).isoformat()
        await self._db.update_fan(
            fan["uuid"],
            {
                "spent_cents": int(row.get("spent_cents") or 0) + suma,
                "bought_count": kupene,
                "last_bought_at": teraz,
                # Odomkol, takže už nič nevisí a ďalšia ponuka je v poriadku.
                "pending_offer_at": None,
            },
        )
        log.info("Fanúšik %s zaplatil %s c (%s. nákup)", fan["uuid"][:8], suma, kupene)
        await self._thank(fan, row, settings, suma, kupene)

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
        if not fvflow.may_thank(row, settings):
            log.info("Za nákup %s sa práve ďakovalo, druhý raz nie", fan["uuid"][:8])
            return
        if row.get("human_takeover") or not row.get("ai_enabled", True):
            return

        persona = await self._db.persona()
        behavior = await self._db.behavior()
        teraz_local = local_now(behavior)
        try:
            text = (
                await self._llm.reply(
                    build_prompt(persona, settings, fan, row, None, teraz_local),
                    (await self._db.history(fan["uuid"]))
                    + [{"role": "user", "content": fvflow.thanks_hint(cents, kolkykrat)}],
                )
            ).strip()
        except Exception as exc:  # noqa: BLE001 - vďaka je bonus, nie podmienka
            log.warning("Poďakovanie sa nepodarilo napísať: %s", exc)
            return
        text = self._clean(text)
        if not text or not self._safe(text):
            return

        poslana = await self._api.send(fan["uuid"], text)
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
        row = await self._ensure_fan(fan)
        if row.get("greeted"):
            return

        persona = await self._db.persona()
        text = (await self._llm.reply(
            build_prompt(persona, settings, fan, row, None), [
                {"role": "user", "content": GREETING_PROMPT}
            ]
        )).strip()
        text = self._clean(text)
        if not text or not self._safe(text):
            return
        poslana = await self._api.send(fan["uuid"], text)
        if not poslana:
            return
        await self._db.add_message(
            fan["uuid"], "assistant", text, "" if poslana == "-" else poslana
        )
        await self._db.update_fan(fan["uuid"], {"greeted": True})
        log.info("Privítaný nový predplatiteľ %s", fan["uuid"][:8])

    async def _reply(self, event: Dict[str, Any], settings: Dict[str, Any]) -> None:
        fan = fan_of(event)
        if not fan["uuid"]:
            return

        row = await self._ensure_fan(fan)
        if not row.get("ai_enabled", True) or row.get("human_takeover"):
            log.info("Fanúšik %s má odpisovanie vypnuté", fan["uuid"][:8])
            return

        if not row.get("tg_id"):
            await self._try_link(fan, row)

        # Skutočný stav chatu má prednosť pred frontou: Marek mohol odpísať
        # ručne, doručenie sa mohlo stratiť a poradie Fanvue nezaručuje.
        if not await self._reconcile(fan, row):
            return

        persona = await self._db.persona()
        behavior = await self._db.behavior()
        teraz = local_now(behavior)
        if not within_hours(settings, teraz):
            log.info("Mimo času na Fanvue — %s ostáva bez odpovede", fan["uuid"][:8])
            return

        blok = den.block_at(teraz, seed=str(persona.get("name") or "")) if teraz else None

        tg = None
        if row.get("tg_id"):
            try:
                tg = await self._db.telegram_context(int(row["tg_id"]))
            except Exception as exc:  # noqa: BLE001 - kontext je bonus
                log.warning("Kontext z Telegramu sa nenačítal: %s", exc)

        # O tom, ČI niečo odíde, rozhoduje kód. Model rieši len AKO to povie —
        # keby rozhodoval on, posielal by fotky v každej druhej správe.
        kde = den.where(blok) if blok is not None else "home"
        pyta_fotku = fvmedia.asked_for_photo(fan["text"])
        pyta_ostre = fvmedia.wants_spicy(fan["text"])
        moment = fvflow.paid_moment(row, settings, pyta_ostre)
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
                row, settings, moment, foto_ok, pyta_fotku, kde, dlzi
            ),
        )
        history = await self._db.history(fan["uuid"])
        text = (await self._llm.reply(prompt, history)).strip()
        text = self._clean(text)
        if not text or not self._safe(text):
            return

        await asyncio.sleep(
            random.uniform(
                float(settings.get("reply_min_s") or 0),
                max(
                    float(settings.get("reply_min_s") or 0),
                    float(settings.get("reply_max_s") or 0),
                ),
            )
        )

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

        poslana = await self._api.send(fan["uuid"], text, media, cena)
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

    async def _reconcile(self, fan: Dict[str, Any], row: Dict[str, Any]) -> bool:
        """Doplní, čo v pamäti chýba. False = teraz sa neodpisuje.

        Keď sa chat nedá prečítať, pokračuje sa aj tak — uložená správa
        z webhooku je lepšia než mlčanie. Fail-open všade.
        """
        creator = str((await self._db.settings()).get("creator_uuid") or "")
        skutocne = await self._api.chat_messages(fan["uuid"])
        if not skutocne:
            await self._db.add_message(fan["uuid"], "user", fan["text"])
            return True

        try:
            zname = await self._db.known_message_uuids(fan["uuid"])
            chybajuce = fvsync.missing(zname, skutocne, creator)
            if chybajuce:
                await self._db.add_messages(fan["uuid"], chybajuce)
                log.info(
                    "Doplnených %s správ do chatu %s", len(chybajuce), fan["uuid"][:8]
                )

            # Nákup sa inak nedozvieme — webhook o odomknutí správy nechodí.
            kupil = fvsync.bought(skutocne)
            if kupil > int(row.get("bought_count") or 0):
                patch = {"bought_count": kupil, "pending_offer_at": None}
                kedy = fvsync.last_bought_at(skutocne)
                if kedy:
                    patch["last_bought_at"] = kedy
                await self._db.update_fan(fan["uuid"], patch)
                row.update(patch)
                log.info("Fanúšik %s má kúpené: %s", fan["uuid"][:8], kupil)
                # Druhá cesta k vďake: keby sa udalosť o platbe stratila,
                # nákup by ostal bez poďakovania. Odstup v `may_thank`
                # zabráni tomu, aby sa ďakovalo dvakrát.
                await self._thank(
                    fan, row, await self._db.settings(), 0, kupil
                )
        except Exception as exc:  # noqa: BLE001 - zosúladenie je poistka, nie podmienka
            log.warning("Zosúladenie chatu zlyhalo: %s", exc)

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
        """Poistka nad promptom: odkaz na Fanvue sa odtiaľto nesmie dostať von."""
        if "fanvue.com" in text.lower():
            log.warning("Odpoveď obsahovala odkaz na Fanvue, zahadzujem ju")
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

    async def _try_link(self, fan: Dict[str, Any], row: Dict[str, Any]) -> None:
        """Skúsi zistiť, či to nie je niekto, s kým si už písala.

        Checkout odkaz s Telegram id je istota, ale nie každý ňou prejde —
        odkaz sa dá otvoriť inokedy alebo z iného zariadenia. Vtedy ostáva
        meno a to, komu sme odkaz nedávno poslali. Keď to nestačí na istotu,
        radšej sa nespojí nič: neznámemu sa prihovorí ako novému a nič sa
        nestane, ale zle spojenému by pripomínala cudzie zážitky.
        """
        try:
            chats = await self._db.link_candidates()
            taken = await self._db.linked_tg_ids()
        except Exception as exc:  # noqa: BLE001 - spojenie je bonus
            log.warning("Kandidátov sa nepodarilo načítať: %s", exc)
            return

        hit = fanmatch.best(fan, chats, taken=taken)
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
