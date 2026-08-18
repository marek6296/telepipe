"""Kontrolný bot — klikacie menu na nastavenie chovania a persony.

DIVERGENCIA OD PREDLOHY: párovanie kódom
----------------------------------------
V predlohe (jeden proces = jedna modelka) bolo `OWNER_CHAT_ID` v env a bot
neprijal od nikoho iného nič. Tu si ho klient nastavuje sám z dashboardu a
doteraz to znamenalo opísať číslo z @userinfobot. Preklep sa nedal odhaliť:
každý handler nižšie gatuje na `chat_id == cfg.owner_chat_id`, takže pri zlom
čísle bot MLČÍ aj na `/start` — najhorší možný spôsob, ako sa niečo pokazí.

Preto je tu jedna — a jediná — vec, ktorú bot prijme od neznámeho chatu:
jednorazový párovací kód vydaný dashboardom (`control_bot_links`, migrácia
020). Keď sedí, bot si zapíše chat id odosielateľa ako majiteľa a rovno ukáže
menu. Pravidlá, ktoré to držia bezpečné:

  * kód generuje databáza, nie klient, platí 15 minút a práve raz;
  * hľadá sa vždy v páre s `model_id`, takže cudzí kód túto modelku nespáruje;
  * pri NEsprávnom kóde sa mlčí presne tak, ako pri hocijakej inej správe —
    inak by bot cudziemu potvrdil, že tu nejaké kódy existujú;
  * skúšanie kódov je obmedzené na `_PAIR_MAX_TRIES` za `_PAIR_WINDOW_S` na
    chat, aby sa priestor kódov nedal prehľadať hrubou silou.

Bez spárovania modelka normálne odpisuje fanúšikom — majiteľ len nedostáva
notifikácie a nemá menu.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from telethon import Button, TelegramClient, events

import behavior as bhv
from behavior import Behavior
from config import TenantConfig as Config
from db import TenantDb as Db
from persona import PERSONA_FIELDS, PERSONA_LABELS

log = logging.getLogger(__name__)

# Ktoré polia chovania patria do ktorej obrazovky
_TIMING_FIELDS = (
    "debounce_min_s",
    "debounce_max_s",
    "read_delay_min_s",
    "read_delay_max_s",
    "reply_delay_min_s",
    "reply_delay_max_s",
)
_RANDOM_FIELDS = (
    "question_chance",
    "gag_chance",
    "quick_reply_chance",
    "quick_read_max_s",
    "quick_reply_min_s",
    "quick_reply_max_s",
    "seen_only_chance",
    "seen_only_min_s",
    "seen_only_max_s",
    "long_pause_chance",
    "long_pause_min_s",
    "long_pause_max_s",
    "defer_reply_chance",
    "defer_min_s",
    "defer_max_s",
    "greeting_gap_hours",
    "max_replies_per_hour",
    "max_links_per_hour",
)
_TIME_FIELDS = ("active_start_min", "active_end_min", "active_tz")

_SLANG_CYCLE = ("none", "light", "medium")
_HEAT_CYCLE = ("mild", "medium", "hot")

# Párovací kód: `TP-` + 6 znakov z abecedy bez 0/O a 1/I (migrácia 020).
# Predpona aj veľkosť písmen sú voliteľné — klient kód prepisuje ručne a
# odmietnuť ho kvôli malému písmenu by bola presne tá istá tichá porucha,
# ktorú párovanie odstraňuje.
_PAIR_RE = re.compile(r"^(?:TP[-\s]?)?([2-9A-HJ-NP-Z]{6})$", re.IGNORECASE)
_PAIR_MAX_TRIES = 5
_PAIR_WINDOW_S = 60.0
_HINT_MAX_CHATS = 200

# Miestnosť, z ktorej má hlasovka znieť. Je to len východisko — keď z rozhovoru
# vyplynie, kde práve je, prebije to nastavenie.
_AMBIENCE_LABEL = {
    "home": "doma", "bedroom": "spálňa", "kitchen": "kuchyňa",
    "bathroom": "kúpeľňa", "car": "auto", "outside": "vonku",
    "cafe": "kaviareň", "gym": "fitko", "none": "ticho",
}
_HEAT_LABEL = {"mild": "slušná", "medium": "pikantná", "hot": "veľmi otvorená"}


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_hhmm(text: str) -> Optional[int]:
    raw = text.strip().replace(".", ":")
    if ":" not in raw:
        return int(raw) if raw.isdigit() and 0 <= int(raw) <= 1439 else None
    hours, _, mins = raw.partition(":")
    if not (hours.strip().isdigit() and mins.strip().isdigit()):
        return None
    h, m = int(hours), int(mins)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _short(value: Any, limit: int = 28) -> str:
    text = "—" if value in (None, "") else str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class ControlBot:
    def __init__(self, cfg: Config, db: Db, client: TelegramClient) -> None:
        self._cfg = cfg
        self._db = db
        self._client = client
        # chat_id → ("persona"|"behavior"|"time"|"semi_custom"|"semi_price"|
        # "semi_caption", field) — čaká sa na hodnotu. Pri semi_* field nesie
        # message_id karty (str).
        self._awaiting: Dict[int, Tuple[str, str]] = {}
        # Semi-auto: doručovatelia odpovedí podľa kanála (dopĺňa runner).
        self._senders: Dict[str, Any] = {}
        # message_id karty → pending_id (in-memory; po reštarte sa obnoví z DB).
        self._cards: Dict[int, str] = {}
        # message_id karty → prechodný stav foto/hlas wizardu (media_ref, price…).
        self._wizard: Dict[int, Dict[str, Any]] = {}
        # chat_id → časy posledných pokusov o kód (monotónne). Slúži len na
        # obmedzenie skúšania; prázdne zoznamy sa pri každom pokuse upratujú,
        # takže slovník nerastie donekonečna.
        self._pair_tries: Dict[int, List[float]] = {}
        # Chaty, ktorým sme už povedali, že bot čaká na párovací kód (viď
        # `_hint_unpaired`). Raz stačí — opakovať by z bota spravilo ozvenu.
        self._hinted: set[int] = set()

    def register(self) -> None:
        self._client.add_event_handler(
            self._on_command, events.NewMessage(incoming=True, pattern=r"^/")
        )
        self._client.add_event_handler(self._on_value, events.NewMessage(incoming=True))
        self._client.add_event_handler(self._on_callback, events.CallbackQuery())

    async def notify(self, text: str) -> None:
        # Nespárovaná modelka nie je porucha, len ešte nemá kam písať. Bez tejto
        # vetvy by `send_message(0, ...)` pri každej notifikácii hodil výnimku a
        # do logu tiekla varovná hláška o zle nastavenom botovi — hoci majiteľ
        # len ešte nestihol poslať párovací kód.
        if not self._cfg.owner_chat_id:
            log.debug("model %s: notifikácia zahodená — bot ešte nie je spárovaný",
                      self._cfg.model_id)
            return
        try:
            await self._client.send_message(self._cfg.owner_chat_id, text, link_preview=False)
        except Exception as exc:  # noqa: BLE001 - notifikácia nesmie zhodiť tok
            log.warning(
                "Notifikácia sa neodoslala (dal si botovi START zo správneho účtu?): %s", exc
            )

    def _is_owner(self, chat_id: Optional[int]) -> bool:
        # Nula je „zatiaľ nikto" (modelka pred spárovaním, viď config.py) —
        # nesmie sa trafiť do žiadneho skutočného chatu.
        owner = self._cfg.owner_chat_id
        return bool(owner) and chat_id == owner

    # ---------- párovanie (viď hlavičku súboru) ----------

    def _pair_allowed(self, chat_id: int) -> bool:
        """Necháva `_PAIR_MAX_TRIES` pokusov za `_PAIR_WINDOW_S` na chat."""
        now = time.monotonic()
        for known in list(self._pair_tries):
            fresh = [t for t in self._pair_tries[known] if now - t < _PAIR_WINDOW_S]
            if fresh:
                self._pair_tries[known] = fresh
            else:
                del self._pair_tries[known]
        tries = self._pair_tries.setdefault(chat_id, [])
        if len(tries) >= _PAIR_MAX_TRIES:
            log.warning("párovanie: chat %s skúša kódy pridrsno — ignorujem", chat_id)
            return False
        tries.append(now)
        return True

    async def _try_pair(self, event: events.NewMessage.Event) -> bool:
        """Správa z neznámeho chatu: je to platný párovací kód?

        Vracia `True`, len keď párovanie prebehlo. Pri čomkoľvek inom `False`
        a NIČ sa neodpisuje — neznámy chat sa nesmie dozvedieť ani to, že bot
        na správy vôbec reaguje.
        """
        chat_id = event.chat_id
        if not chat_id or not getattr(event, "is_private", True):
            return False
        match = _PAIR_RE.match((event.raw_text or "").strip())
        if not match:
            return False
        if not self._pair_allowed(chat_id):
            return False
        code = f"TP-{match.group(1).upper()}"
        if not await self._db.pair_control_bot(code, chat_id):
            return False

        # Config je zdieľaný s userbotom (`owner_as_client`, mazanie testovacieho
        # chatu), takže nové id musí vidieť aj on — preto sa mení NA MIESTE, aj
        # keď je dataclass frozen, a nie cez `replace()`, ktorý by vyrobil kópiu
        # známu len tomuto botovi.
        object.__setattr__(self._cfg, "owner_chat_id", chat_id)
        self._pair_tries.pop(chat_id, None)
        log.info("model %s: kontrolný bot spárovaný s chatom %s", self._cfg.model_id, chat_id)

        await event.reply(
            "✅ *Spárované*\n\nOd teraz sem chodia upozornenia na nových "
            "fanúšikov a odtiaľto ju ovládaš. Menu máš vždy pod `/menu`.",
            link_preview=False,
        )
        await self._send_main(event)
        return True

    async def _hint_unpaired(self, event: events.NewMessage.Event) -> None:
        """`/start` do ešte nespárovaného bota → povedz, čo sem patrí.

        Toto je JEDINÁ vec, ktorú neznámy chat dostane okrem úspešného
        spárovania, a je to zámer: klient si bota práve vyrobil, otvoril ho cez
        odkaz od @BotFathera a stlačil Start — mlčanie v tej chvíli je presne tá
        tichá porucha, ktorú párovanie odstraňuje. Nič sa tým neprezradí:
        hláška platí rovnako, či nejaký kód existuje alebo nie, a bot patrí tomu,
        kto ho vyrobil (jeho meno nikto cudzí nepozná).

        Keď už majiteľ SPÁROVANÝ je, cudzí `/start` nedostane nič — vtedy je to
        naozaj cudzí človek.
        """
        chat_id = event.chat_id
        if self._cfg.owner_chat_id or not chat_id:
            return
        if not getattr(event, "is_private", True):
            return
        if (event.raw_text or "").split()[0].split("@")[0].lower() not in ("/start", "/help"):
            return
        # Raz na chat za beh procesu. Strop drží slovník malý aj keby bota našiel
        # spamer — po naplnení sa už len mlčí.
        if chat_id in self._hinted or len(self._hinted) >= _HINT_MAX_CHATS:
            return
        self._hinted.add(chat_id)
        await event.reply(
            "Tento bot patrí k tvojmu Telepipe účtu, ale ešte nie je spárovaný.\n\n"
            "V dashboarde otvor *Telegram → Settings*, klikni *Generate pairing code* "
            "a kód sem pošli ako správu. Vyzerá takto: `TP-4F9K2X`.",
            link_preview=False,
        )

    # ---------- príkazy ----------

    async def _on_command(self, event: events.NewMessage.Event) -> None:
        if not self._is_owner(event.chat_id):
            await self._hint_unpaired(event)
            return
        command = (event.raw_text or "").split()[0].split("@")[0].lower()
        try:
            if command in ("/start", "/menu", "/help"):
                self._awaiting.pop(event.chat_id, None)
                await self._send_main(event)
            elif command == "/cancel":
                self._awaiting.pop(event.chat_id, None)
                await event.reply("Zrušené.")
                await self._send_main(event)
            elif command == "/den":
                await self._send_day(event)
            else:
                await event.reply("Použi /menu — všetko sa nastavuje klikaním.")
        except Exception as exc:  # noqa: BLE001
            log.exception("Príkaz zlyhal")
            await event.reply(f"⚠️ {exc}")
        raise events.StopPropagation

    # ---------- prijatie hodnoty ----------

    async def _on_value(self, event: events.NewMessage.Event) -> None:
        chat_id = event.chat_id
        if not self._is_owner(chat_id):
            # Jediná výnimka z vlastníckej brány — párovací kód. Musí byť pred
            # ňou, inak by sa nový majiteľ nemal ako ohlásiť.
            try:
                await self._try_pair(event)
            except Exception:  # noqa: BLE001 — pokazené párovanie nezhodí bota
                log.exception("párovanie zlyhalo")
            return
        if chat_id not in self._awaiting:
            return
        kind, field = self._awaiting[chat_id]
        value = (event.raw_text or "").strip()
        if not value:
            return
        # Semi-auto free-text (vlastná správa, cena, popis, text hlasovky) —
        # nie je to nastavenie poľa, ale akcia nad čakajúcim návrhom.
        if kind.startswith("semi_"):
            try:
                await self._apply_semi(event, kind, field, value)
            except Exception as exc:  # noqa: BLE001
                log.exception("semi akcia %s zlyhala", kind)
                await event.reply(f"⚠️ {exc}"[:190])
            self._awaiting.pop(chat_id, None)
            return
        try:
            message = await self._apply_value(kind, field, value)
        except Exception as exc:  # noqa: BLE001
            log.exception("Nastavenie %s.%s zlyhalo", kind, field)
            await event.reply(f"⚠️ {exc}")
            return
        if message:
            await event.reply(message)
            return
        self._awaiting.pop(chat_id, None)
        label = PERSONA_LABELS.get(field) or bhv.FIELD_LABELS.get(field, field)
        await event.reply(f"✅ *{label}* nastavené. Platí od najbližšej odpovede.")
        if kind == "persona":
            await self._send_persona(event)
        elif kind == "time":
            await self._send_times(event)
        else:
            await self._send_behavior(event)

    async def _apply_value(self, kind: str, field: str, value: str) -> Optional[str]:
        """Vráti chybovú správu, ak hodnota nesedí; inak zapíše a vráti None."""
        if kind == "persona":
            if field == "age":
                if not value.isdigit():
                    return "Vek musí byť číslo. Pošli znova, alebo /cancel."
                await self._db.set_persona_field(field, int(value))
            else:
                await self._db.set_persona_field(field, value)
            return None

        if kind == "time":
            if field == "active_tz":
                try:
                    from zoneinfo import ZoneInfo

                    ZoneInfo(value)
                except Exception:  # noqa: BLE001
                    return "Neznáma zóna. Napr. `America/Los_Angeles`. Alebo /cancel."
                await self._db.set_behavior_field(field, value)
                return None
            minutes = _parse_hhmm(value)
            if minutes is None:
                return "Zadaj čas ako `12:12`. Alebo /cancel."
            await self._db.set_behavior_field(field, minutes)
            return None

        # numerické chovanie
        if field.endswith("_chance"):
            try:
                number = float(value.replace(",", ".").rstrip("%"))
            except ValueError:
                return "Zadaj číslo, napr. `0.15` alebo `15%`. Alebo /cancel."
            if number > 1:
                number /= 100
            if not 0 <= number <= 1:
                return "Šanca musí byť medzi 0 a 1 (alebo 0–100 %)."
            await self._db.set_behavior_field(field, round(number, 4))
            return None

        if not value.isdigit():
            return "Zadaj celé číslo. Alebo /cancel."
        await self._db.set_behavior_field(field, int(value))
        return None

    # ---------- callbacky ----------

    async def _on_callback(self, event: events.CallbackQuery.Event) -> None:
        if not self._is_owner(event.chat_id):
            return
        data = (event.data or b"").decode()
        try:
            await self._route(event, data)
        except Exception as exc:  # noqa: BLE001
            log.exception("Callback %s zlyhal", data)
            await event.answer(f"Chyba: {exc}"[:190], alert=True)

    _APPROVAL_HEADS = frozenset({
        "ap", "ac", "as", "ax", "af", "afd", "afi", "afree", "apaid",
        "acap", "acapn", "acapw", "av", "avc", "avok", "avno", "aback",
    })

    async def _route(self, event: events.CallbackQuery.Event, data: str) -> None:
        head, _, arg = data.partition(":")

        if head in self._APPROVAL_HEADS:
            await self._route_approval(event, head, arg)
        elif head == "rm":
            # Prepnutie Telegram režimu: off → auto → semi → off
            await self._cycle_reply_mode(event)
        elif head == "m":
            await self._send_main(event, edit=True)
        elif head == "pz":
            paused = await self._db.is_paused()
            await self._db.set_paused(not paused)
            await event.answer("AI zapnutá" if paused else "AI vypnutá")
            await self._send_main(event, edit=True)
        elif head == "pm":
            await self._send_persona(event, edit=True)
        elif head == "p":
            await self._ask_value(event, "persona", arg)
        elif head == "bm":
            await self._send_behavior(event, edit=True)
        elif head == "bt":
            await self._toggle(event, arg)
        elif head == "b":
            await self._ask_value(event, "behavior", arg)
        elif head == "tm":
            await self._send_times(event, edit=True)
        elif head == "t":
            await self._ask_value(event, "time", arg)
        elif head == "ti":
            await self._send_fields(event, "Časovanie", _TIMING_FIELDS, "b", "bm")
        elif head == "ra":
            await self._send_fields(event, "Náhodnosť", _RANDOM_FIELDS, "b", "bm")
        elif head == "sf":
            await self._send_safety(event, edit=True)
        elif head == "vx":
            await self._send_voice_exceptions(event, edit=True)
        elif head == "st":
            await self._send_stats(event)
        elif head == "cv":
            await self._send_conversations(event)
        elif head == "cd":
            await self._send_conversation(event, int(arg))
        elif head == "to":
            await self._toggle_takeover(event, int(arg))
        elif head == "pd":
            await self._toggle_paid(event, int(arg))
        elif head == "wq":
            await self._confirm_wipe(event, int(arg))
        elif head == "wy":
            await self._wipe(event, int(arg))
        else:
            await event.answer("Neznáma akcia")

    async def _ask_value(self, event: events.CallbackQuery.Event, kind: str, field: str) -> None:
        if kind == "persona":
            current = (await self._db.get_persona()).get(field)
            label = PERSONA_LABELS.get(field, field)
        else:
            row = await self._db.get_behavior()
            current = row.get(field)
            label = bhv.FIELD_LABELS.get(field, field)
            if kind == "time" and field != "active_tz" and current is not None:
                current = _hhmm(int(current))

        self._awaiting[event.chat_id] = (kind, field)
        hint = ""
        if kind == "time" and field != "active_tz":
            hint = "\n\nFormát `12:12` (24-hodinový)."
        elif field.endswith("_chance"):
            hint = "\n\nČíslo 0–1 alebo v procentách (`15%`)."

        await event.answer()
        await event.respond(
            f"✏️ *{label}*\n\nTeraz: `{current if current not in (None, '') else '—'}`"
            f"{hint}\n\nPošli novú hodnotu ako správu. /cancel zruší.",
            link_preview=False,
        )

    async def _toggle(self, event: events.CallbackQuery.Event, field: str) -> None:
        row = await self._db.get_behavior()
        if field == "mode":
            new_value: Any = bhv.AI if (row.get("mode") or bhv.REAL) == bhv.REAL else bhv.REAL
            answer = "Režim: skutočná" if new_value == bhv.REAL else "Režim: AI"
        elif field == "no_diacritics":
            new_value = not bool(row.get("no_diacritics"))
            answer = "Bez diakritiky" if new_value else "S diakritikou"
        elif field == "heat":
            current = row.get("heat") or "medium"
            index = (_HEAT_CYCLE.index(current) + 1) % len(_HEAT_CYCLE) if current in _HEAT_CYCLE else 1
            new_value = _HEAT_CYCLE[index]
            answer = f"Pikantnosť: {_HEAT_LABEL[new_value]}"
        elif field == "activity_waves":
            new_value = not bool(row.get("activity_waves"))
            answer = "Vlny aktivity zapnuté" if new_value else "Vlny vypnuté"
        elif field == "morning_enabled":
            new_value = not bool(row.get("morning_enabled", True))
            answer = "Ranné správy zapnuté" if new_value else "Ranné správy vypnuté"
        elif field == "voices_enabled":
            new_value = not bool(row.get("voices_enabled", True))
            answer = "Hlasovky zapnuté" if new_value else "Hlasovky vypnuté — bude len písať"
        elif field == "voice_ambience":
            current = row.get("voice_ambience") or "home"
            cyklus = bhv.AMBIENCE_CYCLE
            index = (cyklus.index(current) + 1) % len(cyklus) if current in cyklus else 0
            new_value = cyklus[index]
            answer = f"Miestnosť: {_AMBIENCE_LABEL.get(new_value, new_value)}"
        elif field in bhv.VOICE_EXCEPTIONS:
            new_value = not bool(row.get(field, True))
            popis = bhv.FIELD_LABELS.get(field, field)
            answer = f"{popis}: {'áno' if new_value else 'nie'}"
        elif field == "voice_strength":
            current = row.get("voice_strength") or "real"
            cyklus = bhv.STRENGTH_CYCLE
            index = (cyklus.index(current) + 1) % len(cyklus) if current in cyklus else 0
            new_value = cyklus[index]
            answer = f"Kvalita hlasovky: {new_value}"
        elif field == "slang":
            current = row.get("slang") or "light"
            index = (_SLANG_CYCLE.index(current) + 1) % len(_SLANG_CYCLE) if current in _SLANG_CYCLE else 1
            new_value = _SLANG_CYCLE[index]
            answer = f"Slang: {new_value}"
        else:
            await event.answer("Neznámy prepínač")
            return
        await self._db.set_behavior_field(field, new_value)
        await event.answer(answer)
        if field in bhv.VOICE_EXCEPTIONS:
            await self._send_voice_exceptions(event, edit=True)
        else:
            await self._send_behavior(event, edit=True)

    # ---------- obrazovky ----------

    async def _render(self, event, text: str, buttons, edit: bool) -> None:
        if edit and hasattr(event, "edit"):
            await event.edit(text, buttons=buttons, link_preview=False)
        else:
            await event.respond(text, buttons=buttons, link_preview=False)

    # ================= semi-auto: schvaľovacie karty =================

    def register_sender(self, channel: str, sender: Any) -> None:
        """Runner registruje doručovateľa odpovedí pre kanál (userbot/fanvue)."""
        self._senders[channel] = sender

    def start_fallback_poller(self) -> "asyncio.Task":
        """Poller: neschválené návrhy staršie ako per-kanálový `fallback_minutes`
        odošle prvým (AI-top) návrhom. Beží, aj keď je web/Telegram zavretý."""
        return asyncio.create_task(self._fallback_loop())

    async def _fallback_loop(self) -> None:
        while True:
            try:
                await self._fallback_tick()
            except Exception as exc:  # noqa: BLE001
                log.warning("fallback poller: %s", exc)
            await asyncio.sleep(30)

    async def _fallback_tick(self) -> None:
        rows = await self._db.awaiting_pending()
        if not rows:
            return
        tg = await self._db.tg_reply_mode()
        fv = await self._db.fanvue_reply_mode()
        now = datetime.now(timezone.utc)
        for row in rows:
            fb = tg["fallback_minutes"] if row.get("channel") == "telegram" else fv["fallback_minutes"]
            if not fb:
                continue
            created = _parse_iso(row.get("created_at"))
            if created and (now - created).total_seconds() >= fb * 60:
                await self._auto_send(row)

    async def _auto_send(self, row: Dict[str, Any]) -> None:
        sender = self._senders.get(row.get("channel"))
        sugg = row.get("suggestions") or []
        if not sender or not sugg:
            return
        pid = row["id"]
        if not await self._db.claim_pending(pid):
            return
        ok = await sender.deliver_text(row["conv_key"], sugg[0])
        cmid = row.get("control_msg_id")
        if ok:
            await self._db.mark_pending(pid, "sent", chosen_text=sugg[0], kind="text")
            self._cards.pop(int(cmid or 0), None)
            if cmid:
                await self._clear_card(int(cmid), "⏱ _Odoslané automaticky (uplynul čas)._")
        else:
            await self._db.mark_pending(pid, "awaiting")

    async def recover_cards(self) -> None:
        """Po štarte/prevzatí modelky obnov mapu kariet z DB, nech staré karty
        (s uloženým control_msg_id) po reštarte repliky stále reagujú na kliky."""
        try:
            for row in await self._db.awaiting_pending():
                cmid = row.get("control_msg_id")
                if cmid:
                    self._cards[int(cmid)] = row["id"]
        except Exception as exc:  # noqa: BLE001
            log.warning("Obnova schvaľovacích kariet zlyhala: %s", exc)

    async def post_approval(
        self, *, channel: str, conv_key: str, display_name: str,
        incoming_preview: str, suggestions: List[str],
    ) -> bool:
        """Založí pending, pošle kartu majiteľovi. True = poslané."""
        if not self._cfg.owner_chat_id:
            return False
        # Fanúšik mohol napísať znova, kým visela stará karta — zavri ju.
        for old in await self._db.supersede_open(channel, conv_key):
            cmid = old.get("control_msg_id")
            if cmid:
                await self.cancel_card(int(cmid))
        row = await self._db.create_pending(
            channel=channel, conv_key=conv_key,
            suggestions=suggestions, incoming_preview=incoming_preview,
        )
        if not row:
            return False
        pid = row["id"]
        plat = "Fanvue" if channel == "fanvue" else "Telegram"
        lines = [f"💬 *{plat} · {display_name}*"]
        if incoming_preview:
            lines.append(f"„{_short(incoming_preview, 220)}“")
        lines.append("")
        for i, sug in enumerate(suggestions):
            lines.append(f"*{i + 1}️⃣* {sug}")
        try:
            msg = await self._client.send_message(
                self._cfg.owner_chat_id, "\n".join(lines),
                buttons=self._approval_buttons(len(suggestions)), link_preview=False,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Schvaľovaciu kartu sa nepodarilo poslať: %s", exc)
            return False
        await self._db.mark_pending(pid, "awaiting", control_msg_id=int(msg.id))
        self._cards[int(msg.id)] = pid
        self._wizard.pop(int(msg.id), None)
        return True

    def _approval_buttons(self, n: int) -> List[List[Button]]:
        nums = [Button.inline(f"{i + 1}️⃣", f"ap:{i}".encode()) for i in range(n)]
        return [
            nums or [Button.inline("✍️ Napísať", b"ac")],
            [Button.inline("✍️ Napíšem vlastnú", b"ac")],
            [Button.inline("📷 Fotka", b"af"), Button.inline("🎤 Hlasovka", b"av")],
            [Button.inline("⏭️ Preskočiť", b"as"), Button.inline("✋ Prevziať", b"ax")],
        ]

    async def cancel_card(self, control_msg_id: int) -> None:
        """Zruší kartu (fanúšik napísal znova / prevzatie) — bez tlačidiel."""
        self._cards.pop(control_msg_id, None)
        self._wizard.pop(control_msg_id, None)
        try:
            await self._client.edit_message(
                self._cfg.owner_chat_id, control_msg_id,
                "⤵️ _(neaktuálne — prišla nová správa)_", buttons=None,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _pending_for(self, event) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        mid = int(event.message_id)
        pid = self._cards.get(mid)
        if not pid:
            for row in await self._db.awaiting_pending():
                if int(row.get("control_msg_id") or 0) == mid:
                    pid = row["id"]
                    self._cards[mid] = pid
                    break
        if not pid:
            return None, None
        return pid, await self._db.get_pending(pid)

    async def _route_approval(self, event, head: str, arg: str) -> None:
        mid = int(event.message_id)
        pid, row = await self._pending_for(event)
        if not row or row.get("status") != "awaiting":
            await event.answer("Táto správa už nie je aktuálna", alert=True)
            return
        channel, conv = row["channel"], row["conv_key"]
        sender = self._senders.get(channel)
        if not sender:
            await event.answer("Kanál nie je pripojený", alert=True)
            return
        suggestions = row.get("suggestions") or []

        if head == "ap":
            idx = int(arg or 0)
            text = suggestions[idx] if 0 <= idx < len(suggestions) else ""
            await self._finish_text(event, pid, sender, conv, channel, text)
        elif head == "ac":
            self._awaiting[event.chat_id] = ("semi_custom", str(mid))
            await event.answer()
            await event.respond("✍️ Napíš správu, ktorú mám poslať. /cancel zruší.")
        elif head == "as":
            await self._db.mark_pending(pid, "skipped")
            self._cards.pop(mid, None)
            self._wizard.pop(mid, None)
            await event.edit("⏭️ _Preskočené._", buttons=None)
        elif head == "ax":
            await self._db.mark_pending(pid, "skipped")
            if channel == "telegram":
                try:
                    await self._db.update_user(int(conv), {"human_takeover": True})
                except Exception:  # noqa: BLE001
                    pass
            self._cards.pop(mid, None)
            await event.edit("✋ _Chat si preberáš. AI sem už nepíše._", buttons=None)
        elif head == "af":
            await self._show_folders(event, sender, conv, mid)
        elif head == "afd":
            await self._show_items(event, sender, conv, mid, arg)
        elif head == "afi":
            await self._chosen_item(event, sender, channel, mid, int(arg or 0))
        elif head == "afree":
            self._wizard.setdefault(mid, {})["price_cents"] = None
            await self._ask_caption(event, sender, conv, mid)
        elif head == "apaid":
            self._awaiting[event.chat_id] = ("semi_price", str(mid))
            await event.answer()
            await event.respond("💰 Napíš cenu v $ (len číslo, napr. 50).")
        elif head == "acap":
            caps = (self._wizard.get(mid, {}) or {}).get("caps", [])
            idx = int(arg or 0)
            cap = caps[idx] if 0 <= idx < len(caps) else ""
            await self._finish_media(event, pid, sender, conv, mid, cap)
        elif head == "acapn":
            await self._finish_media(event, pid, sender, conv, mid, "")
        elif head == "acapw":
            self._awaiting[event.chat_id] = ("semi_caption", str(mid))
            await event.answer()
            await event.respond("✍️ Napíš popis k fotke. /cancel zruší.")
        elif head == "aback":
            await self._restore_card(event, row)
        elif head == "av":
            idx = int(arg or 0)
            text = suggestions[idx] if 0 <= idx < len(suggestions) else (suggestions[0] if suggestions else "")
            await self._voice_preview(event, pid, sender, mid, text)
        elif head == "avc":
            self._awaiting[event.chat_id] = ("semi_voice", str(mid))
            await event.answer()
            await event.respond("🎤 Napíš text, ktorý mám povedať hlasom.")
        elif head == "avok":
            await self._voice_send(event, pid, sender, conv, mid)
        elif head == "avno":
            st = self._wizard.get(mid, {})
            st.pop("voice_ogg", None)
            st.pop("voice_text", None)
            await event.answer("Hlasovka zahodená")

    async def _finish_text(self, event, pid, sender, conv, channel, text) -> None:
        if not (text or "").strip():
            await event.answer("Prázdny text")
            return
        if not await self._db.claim_pending(pid):
            await event.answer("Už vybavené", alert=True)
            return
        ok = await sender.deliver_text(conv, text)
        mid = int(event.message_id)
        self._cards.pop(mid, None)
        self._wizard.pop(mid, None)
        if ok:
            await self._db.mark_pending(pid, "sent", chosen_text=text, kind="text")
            await event.edit(f"✅ _Odoslané:_ {_short(text, 200)}", buttons=None)
        else:
            await self._db.mark_pending(pid, "awaiting")
            if channel == "telegram":
                try:
                    await self._db.update_user(int(conv), {"pending_reply": True})
                except Exception:  # noqa: BLE001
                    pass
            await event.answer("Odoslanie zlyhalo — skús znova", alert=True)

    async def _show_folders(self, event, sender, conv, mid) -> None:
        folders = await sender.photo_folders(conv)
        if not folders:
            await event.answer("Žiadne fotky", alert=True)
            return
        self._wizard.setdefault(mid, {})
        rows = [[Button.inline(f["label"], f"afd:{f['id']}".encode())] for f in folders[:8]]
        rows.append([Button.inline("« Späť", b"aback")])
        await event.edit("📷 *Vyber priečinok:*", buttons=rows)

    async def _show_items(self, event, sender, conv, mid, folder_id) -> None:
        items = await sender.photo_items(conv, folder_id)
        if not items:
            await event.answer("Priečinok je prázdny", alert=True)
            return
        items = items[:12]
        self._wizard.setdefault(mid, {})["items"] = items
        self._wizard[mid]["folder"] = folder_id
        rows = []
        for i, it in enumerate(items):
            label = _short(it.get("caption") or f"Fotka {i + 1}", 40)
            rows.append([Button.inline(f"{i + 1}. {label}", f"afi:{i}".encode())])
        rows.append([Button.inline("« Späť", b"af")])
        await event.edit("🖼 *Vyber fotku:*", buttons=rows)

    async def _chosen_item(self, event, sender, channel, mid, idx) -> None:
        st = self._wizard.setdefault(mid, {})
        items = st.get("items") or []
        if not (0 <= idx < len(items)):
            await event.answer("Neplatný výber")
            return
        st["media_ref"] = items[idx].get("ref")
        # Telegram nemá PPV — rovno popis. Fanvue: zadarmo / za peniaze.
        if channel == "fanvue":
            await event.edit(
                "💰 *Ako ju poslať?*",
                buttons=[[
                    Button.inline("💚 Zadarmo", b"afree"),
                    Button.inline("💰 Za peniaze", b"apaid"),
                ]],
            )
        else:
            st["price_cents"] = None
            await self._ask_caption_edit(event, sender, mid)

    async def _ask_caption(self, event, sender, conv, mid) -> None:
        await self._ask_caption_edit(event, sender, mid)

    async def _ask_caption_edit(self, event, sender, mid) -> None:
        caps = []
        try:
            caps = await sender.suggest_caption("")
        except Exception:  # noqa: BLE001
            caps = []
        self._wizard.setdefault(mid, {})["caps"] = caps
        rows = [[Button.inline(_short(c, 40), f"acap:{i}".encode())] for i, c in enumerate(caps[:3])]
        rows.append([Button.inline("✍️ Vlastný popis", b"acapw"), Button.inline("Bez popisu", b"acapn")])
        price = (self._wizard.get(mid, {}) or {}).get("price_cents")
        head = "📝 *Popis k fotke:*" + (f" (cena ${price // 100})" if price else "")
        await event.edit(head, buttons=rows)

    async def _finish_media(self, event, pid, sender, conv, mid, caption) -> None:
        st = self._wizard.get(mid, {}) or {}
        media_ref = st.get("media_ref")
        price = st.get("price_cents")
        if not media_ref:
            await event.answer("Chýba fotka", alert=True)
            return
        if not await self._db.claim_pending(pid):
            await event.answer("Už vybavené", alert=True)
            return
        ok = await sender.deliver_photo(conv, media_ref, caption, price)
        self._cards.pop(mid, None)
        self._wizard.pop(mid, None)
        if ok:
            await self._db.mark_pending(
                pid, "sent", chosen_text=caption, kind="photo",
                media_ref=str(media_ref), price_cents=price,
            )
            tag = f" za ${price // 100}" if price else ""
            await event.edit(f"✅ _Fotka odoslaná{tag}._", buttons=None)
        else:
            await self._db.mark_pending(pid, "awaiting")
            await event.answer("Fotku sa nepodarilo poslať", alert=True)

    async def _restore_card(self, event, row) -> None:
        """« Späť z foto-wizardu na pôvodnú kartu s návrhmi."""
        suggestions = row.get("suggestions") or []
        plat = "Fanvue" if row.get("channel") == "fanvue" else "Telegram"
        lines = [f"💬 *{plat} · {row.get('conv_key')}*"]
        if row.get("incoming_preview"):
            lines.append(f"„{_short(row['incoming_preview'], 220)}“")
        lines.append("")
        for i, sug in enumerate(suggestions):
            lines.append(f"*{i + 1}️⃣* {sug}")
        await event.edit("\n".join(lines), buttons=self._approval_buttons(len(suggestions)))

    async def _voice_preview(self, event, pid, sender, mid, text) -> None:
        if not (text or "").strip():
            await event.answer("Najprv vyber alebo napíš text")
            return
        await event.answer("Vyrábam hlasovku…")
        ogg = await sender.generate_voice_preview(text)
        if not ogg:
            await event.respond("⚠️ Hlasovka sa nedá vyrobiť (chýba ElevenLabs kľúč/hlas).")
            return
        import io as _io
        buf = _io.BytesIO(ogg)
        buf.name = "preview.ogg"
        msg = await self._client.send_file(
            self._cfg.owner_chat_id, buf, voice_note=True,
            buttons=[[
                Button.inline("✅ Poslať fanúšikovi", b"avok"),
                Button.inline("❌ Zahodiť", b"avno"),
            ]],
        )
        # Náhľad je NOVÁ správa s vlastným message_id — napoj ju na to isté
        # pending a prenes stav, nech avok/avno na náhľade fungujú.
        self._cards[int(msg.id)] = pid
        self._wizard[int(msg.id)] = {"voice_ogg": ogg, "voice_text": text}

    async def _cycle_reply_mode(self, event) -> None:
        cur = (await self._db.tg_reply_mode()).get("mode", "auto")
        nxt = {"off": "auto", "auto": "semi", "semi": "off"}.get(cur, "auto")
        await self._db.set_tg_reply_mode(nxt)
        await event.answer(
            {"off": "Vypnuté", "auto": "Automatické", "semi": "Poloautomatické"}[nxt]
        )
        await self._send_main(event, edit=True)

    async def _clear_card(self, mid: int, text: str) -> None:
        try:
            await self._client.edit_message(self._cfg.owner_chat_id, mid, text, buttons=None)
        except Exception:  # noqa: BLE001
            pass

    async def _apply_semi(self, event, kind: str, field: str, value: str) -> None:
        """Free-text kroky semi wizardu (vlastná správa / cena / popis / hlas)."""
        mid = int(field) if field.isdigit() else 0
        pid = self._cards.get(mid)
        row = await self._db.get_pending(pid) if pid else None
        if not row or row.get("status") != "awaiting":
            await event.reply("Táto správa už nie je aktuálna.")
            return
        channel, conv = row["channel"], row["conv_key"]
        sender = self._senders.get(channel)
        if not sender:
            await event.reply("Kanál nie je pripojený.")
            return
        st = self._wizard.setdefault(mid, {})

        if kind == "semi_custom":
            if not await self._db.claim_pending(pid):
                self._cards.pop(mid, None)
                await event.reply("Už vybavené.")
                return
            ok = await sender.deliver_text(conv, value)
            self._cards.pop(mid, None)
            self._wizard.pop(mid, None)
            if ok:
                await self._db.mark_pending(pid, "sent", chosen_text=value, kind="text")
                await self._clear_card(mid, f"✅ _Odoslané:_ {_short(value, 150)}")
                await event.reply("✅ Odoslané.")
            else:
                await self._db.mark_pending(pid, "awaiting")
                await event.reply("⚠️ Odoslanie zlyhalo, skús znova.")

        elif kind == "semi_price":
            digits = "".join(ch for ch in value if ch.isdigit())
            if not digits or int(digits) <= 0:
                self._awaiting[event.chat_id] = (kind, field)  # čakaj znova
                await event.reply("Zadaj cenu ako číslo, napr. 50.")
                return
            st["price_cents"] = int(digits) * 100
            await self._send_caption_prompt(event, sender, pid, mid)

        elif kind == "semi_caption":
            media_ref = st.get("media_ref")
            price = st.get("price_cents")
            if not media_ref:
                await event.reply("Chýba fotka.")
                return
            if not await self._db.claim_pending(pid):
                await event.reply("Už vybavené.")
                return
            ok = await sender.deliver_photo(conv, media_ref, value, price)
            self._cards.pop(mid, None)
            self._wizard.pop(mid, None)
            if ok:
                await self._db.mark_pending(
                    pid, "sent", chosen_text=value, kind="photo",
                    media_ref=str(media_ref), price_cents=price,
                )
                await self._clear_card(mid, "✅ _Fotka odoslaná._")
                await event.reply("✅ Fotka odoslaná.")
            else:
                await self._db.mark_pending(pid, "awaiting")
                await event.reply("⚠️ Fotku sa nepodarilo poslať.")

        elif kind == "semi_voice":
            ogg = await sender.generate_voice_preview(value)
            if not ogg:
                await event.reply("⚠️ Hlasovka sa nedá vyrobiť (chýba ElevenLabs kľúč/hlas).")
                return
            import io as _io
            buf = _io.BytesIO(ogg)
            buf.name = "preview.ogg"
            msg = await self._client.send_file(
                self._cfg.owner_chat_id, buf, voice_note=True,
                buttons=[[
                    Button.inline("✅ Poslať fanúšikovi", b"avok"),
                    Button.inline("❌ Zahodiť", b"avno"),
                ]],
            )
            self._cards[int(msg.id)] = pid
            self._wizard[int(msg.id)] = {"voice_ogg": ogg, "voice_text": value}

    async def _send_caption_prompt(self, event, sender, pid, mid) -> None:
        try:
            caps = await sender.suggest_caption("")
        except Exception:  # noqa: BLE001
            caps = []
        st = self._wizard.setdefault(mid, {})
        st["caps"] = caps
        rows = [[Button.inline(_short(c, 40), f"acap:{i}".encode())] for i, c in enumerate(caps[:3])]
        rows.append([Button.inline("✍️ Vlastný popis", b"acapw"), Button.inline("Bez popisu", b"acapn")])
        price = st.get("price_cents")
        head = "📝 *Popis k fotke:*" + (f" (cena ${price // 100})" if price else "")
        msg = await event.respond(head, buttons=rows)
        # Napoj follow-up správu na to isté pending a zdieľaj stav wizardu.
        self._cards[int(msg.id)] = pid
        self._wizard[int(msg.id)] = st

    async def _voice_send(self, event, pid, sender, conv, mid) -> None:
        st = self._wizard.get(mid, {}) or {}
        ogg, text = st.get("voice_ogg"), st.get("voice_text")
        if not ogg or not text:
            await event.answer("Hlasovka nie je pripravená", alert=True)
            return
        if not await self._db.claim_pending(pid):
            await event.answer("Už vybavené", alert=True)
            return
        ok = await sender.deliver_voice(conv, text, ogg)
        self._cards.pop(mid, None)
        self._wizard.pop(mid, None)
        if ok:
            await self._db.mark_pending(pid, "sent", chosen_text=text, kind="voice")
            await event.edit("✅ _Hlasovka odoslaná._", buttons=None)
        else:
            await self._db.mark_pending(pid, "awaiting")
            await event.answer("Hlasovku sa nepodarilo poslať", alert=True)

    async def _send_main(self, event, edit: bool = False) -> None:
        paused = await self._db.is_paused()
        persona = await self._db.get_persona()
        behavior = Behavior.from_row(await self._db.get_behavior())

        window = bhv.format_window(behavior.active_start_min, behavior.active_end_min)
        mode = "skutočná osoba" if behavior.mode == bhv.REAL else "priznaná AI"
        reply = await self._db.tg_reply_mode()
        rmode = reply.get("mode", "auto")
        rmode_label = {"off": "⛔️ Vypnuté", "auto": "🤖 Automatické", "semi": "✋ Poloautomatické"}.get(rmode, rmode)
        text = (
            f"*{persona.get('name') or 'Modelka'}* · {'⏸ PAUZA' if paused else '✅ beží'}\n\n"
            f"Odpisovanie (Telegram): *{rmode_label}*\n"
            f"Režim: *{mode}*\n"
            f"Aktívna: *{window}* ({behavior.active_tz})\n"
            f"Odkaz: {_short(persona.get('cta_link'), 40)}"
        )
        buttons = [
            [Button.inline(f"🔁 Odpisovanie: {rmode_label}", b"rm")],
            [Button.inline("▶️ Zapnúť AI" if paused else "⏸ Vypnúť AI", b"pz")],
            [Button.inline("👤 Persona", b"pm"), Button.inline("🎭 Chovanie", b"bm")],
            [Button.inline("⏰ Časy", b"tm"), Button.inline("📊 Štatistika", b"st")],
            [Button.inline("💬 Konverzácie", b"cv")],
            [
                Button.inline(
                    "🧹 Vymazať môj testovací chat",
                    f"wq:{self._cfg.owner_chat_id}".encode(),
                )
            ],
        ]
        await self._render(event, text, buttons, edit)

    async def _send_persona(self, event, edit: bool = False) -> None:
        persona = await self._db.get_persona()
        rows: List[List[Button]] = []
        pair: List[Button] = []
        for field in PERSONA_FIELDS:
            label = PERSONA_LABELS.get(field, field)
            pair.append(Button.inline(label, f"p:{field}".encode()))
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair)
        rows.append([Button.inline("← Späť", b"m")])

        lines = [f"*Persona* — klikni na pole a pošli novú hodnotu\n"]
        for field in PERSONA_FIELDS:
            lines.append(f"*{PERSONA_LABELS.get(field, field)}*: {_short(persona.get(field), 60)}")
        await self._render(event, "\n".join(lines), rows, edit)

    async def _send_behavior(self, event, edit: bool = False) -> None:
        behavior = Behavior.from_row(await self._db.get_behavior())
        mode_label = "skutočná osoba" if behavior.mode == bhv.REAL else "priznaná AI"
        text = (
            "*Chovanie*\n\n"
            f"Režim: *{mode_label}*\n"
            f"{'Nepriznáva, že je AI.' if behavior.mode == bhv.REAL else 'Na otázku prizná, že je AI.'}\n\n"
            f"Diakritika: *{'nepíše ju' if behavior.no_diacritics else 'píše ju'}*\n"
            f"Slang: *{behavior.slang}*\n\n"
            f"Rýchla odpoveď: {behavior.quick_reply_chance:.0%} "
            f"({behavior.quick_reply_min_s}–{behavior.quick_reply_max_s} s)\n"
            f"Prečíta po: {behavior.read_delay_min_s}–{behavior.read_delay_max_s} s\n"
            f"Odpíše po: {behavior.reply_delay_min_s}–{behavior.reply_delay_max_s} s\n"
            f"Len „videné“: {behavior.seen_only_chance:.0%} "
            f"({behavior.seen_only_min_s // 60}–{behavior.seen_only_max_s // 60} min)\n"
            f"Dlhá pauza: {behavior.long_pause_chance:.0%} "
            f"({behavior.long_pause_min_s // 60}–{behavior.long_pause_max_s // 60} min)\n"
            f"Odloží na hodiny: {behavior.defer_reply_chance:.0%} "
            f"({behavior.defer_min_s // 3600}–{behavior.defer_max_s // 3600} h)\n"
            f"Pozdraví po: {behavior.greeting_gap_hours} h\n"
            f"Odkazov max: {behavior.max_links_per_hour}/h\n"
            f"Vlny aktivity: {'áno' if behavior.activity_waves else 'nie'}\n"
            f"Hlasovky: {'áno' if behavior.voices_enabled else 'nie'}"
            f" ({behavior.voice_chance:.0%}, {behavior.voice_tempo:.2f}×"
            f"{', hlas nenastavený' if not behavior.eleven_voice_id else ''})\n"
            f"Ranné správy: {'áno' if behavior.morning_enabled else 'nie'}"
        )
        buttons = [
            [Button.inline(f"🎭 Režim: {mode_label}", b"bt:mode")],
            [Button.inline(f"🌡 Pikantnosť: {_HEAT_LABEL.get(behavior.heat, behavior.heat)}", b"bt:heat")],
            [
                Button.inline(
                    f"✍️ Diakritika: {'nie' if behavior.no_diacritics else 'áno'}",
                    b"bt:no_diacritics",
                ),
                Button.inline(f"🗣 Slang: {behavior.slang}", b"bt:slang"),
            ],
            [
                Button.inline(
                    f"🌊 Vlny: {'áno' if behavior.activity_waves else 'nie'}",
                    b"bt:activity_waves",
                ),
                Button.inline(
                    f"🎙 Hlasovky: {'áno' if behavior.voices_enabled else 'nie'}",
                    b"bt:voices_enabled",
                ),
            ],
            [
                Button.inline(
                    f"🌅 Ranné správy: {'áno' if behavior.morning_enabled else 'nie'}",
                    b"bt:morning_enabled",
                )
            ],
            # Hlas: miestnosť je len východisko, keď z rozhovoru nevyplynie,
            # kde práve je. Kľúč a výber hlasu sa nastavujú v dashboarde —
            # do tlačidiel sa dlhý kľúč rozumne nezmestí.
            [
                Button.inline(
                    f"🏠 Miestnosť: {_AMBIENCE_LABEL.get(behavior.voice_ambience, behavior.voice_ambience)}",
                    b"bt:voice_ambience",
                ),
                Button.inline(
                    f"📻 Kvalita: {behavior.voice_strength}",
                    b"bt:voice_strength",
                ),
            ],
            [Button.inline("🎙 Kedy smie hlasovku", b"vx")],
            [Button.inline("⏱ Časovanie", b"ti"), Button.inline("🎲 Náhodnosť", b"ra")],
            [Button.inline("🛡 Bezpečnosť Telegramu", b"sf")],
            [Button.inline("← Späť", b"m")],
        ]
        await self._render(event, text, buttons, edit)

    async def _send_fields(self, event, title: str, fields, prefix: str, back: str) -> None:
        row = await self._db.get_behavior()
        rows: List[List[Button]] = []
        pair: List[Button] = []
        lines = [f"*{title}* — klikni a pošli novú hodnotu\n"]
        for field in fields:
            value = row.get(field)
            if field.endswith("_chance") and value is not None:
                shown = f"{float(value):.0%}"
            else:
                shown = str(value)
            lines.append(f"*{bhv.FIELD_LABELS.get(field, field)}*: {shown}")
            pair.append(Button.inline(bhv.FIELD_LABELS.get(field, field), f"{prefix}:{field}".encode()))
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair)
        rows.append([Button.inline("← Späť", back.encode())])
        await self._render(event, "\n".join(lines), rows, True)

    async def _send_times(self, event, edit: bool = False) -> None:
        behavior = Behavior.from_row(await self._db.get_behavior())
        text = (
            "*Časy*\n\n"
            f"Aktívna od *{_hhmm(behavior.active_start_min)}* "
            f"do *{_hhmm(behavior.active_end_min)}*\n"
            f"Zóna: *{behavior.active_tz}*\n\n"
            "Mimo tohto okna neodpisuje — správy sa odložia a dobehnú, "
            "keď sa okno otvorí."
        )
        buttons = [
            [
                Button.inline(f"⏰ Od {_hhmm(behavior.active_start_min)}", b"t:active_start_min"),
                Button.inline(f"🌙 Do {_hhmm(behavior.active_end_min)}", b"t:active_end_min"),
            ],
            [Button.inline(f"🌍 {behavior.active_tz}", b"t:active_tz")],
            [Button.inline("← Späť", b"m")],
        ]
        await self._render(event, text, buttons, edit)

    async def _send_safety(self, event, edit: bool = False) -> None:
        """Všetko, čo drží účet mimo dohľadu Telegramu, na jednej obrazovke.

        Nie sú to len čísla — pri každom je napísané, čo sa stane, keď ho
        zdvihneš. Bez toho sa nedá rozumne rozhodnúť, čo je ešte bezpečné.
        """
        b = Behavior.from_row(await self._db.get_behavior())
        naraz = (
            f"*{b.max_active_chats}* naraz" if b.max_active_chats > 0
            else "*bez obmedzenia*"
        )
        text = (
            "*Bezpečnosť Telegramu*\n\n"
            f"Rozhovorov naraz: {naraz}\n"
            f"Miesto sa uvoľní po *{b.chat_slot_min} min* ticha\n\n"
            "Keď píše veľa ľudí, baví sa len s toľkými naraz. Ostatní počkajú "
            "a prídu na rad, keď niektorý z rozhovorov utíchne. Nič sa "
            "nestratí — každý má odpoveď odloženú, nie zahodenú.\n\n"
            f"Max odpovedí: *{b.max_replies_per_hour}/h*\n"
            f"Sama osloví max *{b.max_outreach_per_hour}* ľudí/h, "
            f"*{b.morning_max_per_day}* za deň\n"
            f"Odkazov max: *{b.max_links_per_hour}/h*\n\n"
            "_Odpovedať tomu, kto napísal prvý, je bezpečné. Riziko je v tom, "
            "keď účet sám oslovuje ľudí — preto sú tie dva stropy oddelené._\n\n"
            "Ak Telegram pošle FloodWait, počká presne toľko, koľko si vypýtal. "
            "Ak označí účet za rozposielanie, všetko sa zastaví a napíšem ti."
        )
        rows: List[List[Button]] = []
        pair: List[Button] = []
        for field in bhv.SAFETY_FIELDS:
            pair.append(
                Button.inline(
                    f"{bhv.FIELD_LABELS.get(field, field)}", f"b:{field}".encode()
                )
            )
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair)
        rows.append([Button.inline("← Späť", b"bm")])
        await self._render(event, text, rows, edit)

    async def _send_voice_exceptions(self, event, edit: bool = False) -> None:
        """Kedy smie hlasovka odísť aj mimo bežných pravidiel.

        Bežne sa hlasovkou nezačína a chodí len občas podľa šance. Toto sú
        chvíle, keď je hlas najsilnejší — každá stojí kredity, tak sa dajú
        vypínať zvlášť.
        """
        row = await self._db.get_behavior()
        behavior = bhv.Behavior.from_row(row)
        text = (
            "*Kedy smie hlasovku* — mimo bežných pravidiel\n\n"
            f"Bežne: až od {6}. správy a so šancou {behavior.voice_chance:.0%}.\n"
            "Zapnuté výnimky to obchádzajú — vtedy odíde hneď.\n\n"
            f"Hlasovky celkovo: {'zapnuté' if behavior.voices_enabled else '*VYPNUTÉ*'}"
        )
        buttons = [
            [
                Button.inline(
                    f"{'✅' if getattr(behavior, pole) else '❌'} "
                    f"{bhv.FIELD_LABELS.get(pole, pole)}",
                    f"bt:{pole}".encode(),
                )
            ]
            for pole in bhv.VOICE_EXCEPTIONS
        ]
        buttons.append([Button.inline("← Späť", b"bm")])
        await self._render(event, text, buttons, edit)

    async def _send_day(self, event) -> None:
        """Rozvrh na dnes — z neho vyplýva, ako rýchlo odpisuje aj odkiaľ
        znie hlasovka. Je stabilný, takže si o pol hodiny neprotirečí."""
        import den as den_mod
        from datetime import datetime
        from zoneinfo import ZoneInfo

        behavior = bhv.Behavior.from_row(await self._db.get_behavior())
        teraz = datetime.now(ZoneInfo(behavior.active_tz))
        # Rozvrh si klient nastavuje v dashboarde (migrácia 022); keď ho nemá
        # alebo sa nedá načítať, platí napísaná šablóna a výpis vyzerá ako
        # doteraz. Starý `FakeDb` v testoch metódu `get_schedule` nemá — to je
        # legitímne „bez rozvrhu", nie chyba.
        rozvrh = None
        try:
            rozvrh = den_mod.Rozvrh.from_row(await self._db.get_schedule())
        except Exception:  # noqa: BLE001 - výpis dňa nesmie padnúť na rozvrhu
            pass
        blok = den_mod.block_at(teraz, self._cfg.supabase_schema, rozvrh)
        riadky = den_mod.summary(teraz.date(), self._cfg.supabase_schema, rozvrh)
        text = (
            f"*Dnešok* — {teraz.strftime('%A %d.%m.')} u nej {teraz.strftime('%H:%M')}\n\n"
            + "\n".join(f"`{r}`" for r in riadky)
            + f"\n\n*Práve:* {den_mod.describe(blok) or 'mimo rozvrhu (spí)'}"
            + f"\n*Odpovede:* ×{den_mod.pace(blok):.1f}"
            + (" — zaneprázdnená" if den_mod.busy(blok) else "")
        )
        await event.reply(text, link_preview=False)

    async def _send_stats(self, event) -> None:
        stats = await self._db.stats()
        total = max(stats["users"], 1)
        text = (
            "*Funnel*\n\n"
            f"Konverzácie: {stats['users']}\n"
            f"Warm: {stats['warm']}\n"
            f"Odkaz poslaný: {stats['link_sent']}\n"
            f"Predplatitelia: {stats['converted']}\n"
            f"Prevzaté tebou: {stats['takeover']}\n\n"
            f"Konverzia: *{stats['converted'] / total * 100:.1f} %*"
        )
        await self._render(event, text, [[Button.inline("← Späť", b"m")]], True)

    async def _send_conversations(self, event) -> None:
        rows = await self._db.recent_conversations(10)
        if not rows:
            await self._render(
                event, "Ešte nikto nenapísal.", [[Button.inline("← Späť", b"m")]], True
            )
            return
        buttons = [
            [
                Button.inline(
                    f"{r.get('first_name') or r['tg_id']} · {r.get('funnel_stage')} "
                    f"· {r.get('msg_count')}",
                    f"cd:{r['tg_id']}".encode(),
                )
            ]
            for r in rows
        ]
        buttons.append([Button.inline("← Späť", b"m")])
        await self._render(event, "*Konverzácie*", buttons, True)

    async def _send_conversation(self, event, tg_id: int) -> None:
        user = await self._db.get_user(tg_id)
        if not user:
            await event.answer("Nenašiel som to", alert=True)
            return
        messages = await self._db.recent_messages(tg_id, 14)
        lines = [
            f"*{user.get('first_name') or tg_id}*"
            + (f" · @{user['username']}" if user.get("username") else ""),
            f"stage: {user.get('funnel_stage')} · správ: {user.get('msg_count')} "
            f"· odkaz {user.get('link_push_count')}×",
        ]
        if user.get("style_note"):
            lines.append(f"_píše: {user['style_note']}_")
        if user.get("summary"):
            lines.append(f"\n*Pamätá si:*\n{user['summary']}")
        lines.append("\n*Posledné správy:*")
        for message in messages:
            who = "🩷" if message["role"] == "assistant" else "👤"
            lines.append(f"{who} {message['content'][:160]}")

        buttons = [
            [
                Button.inline(
                    "↩️ Vrátiť AI" if user.get("human_takeover") else "✋ Prevziať",
                    f"to:{tg_id}".encode(),
                ),
                Button.inline(
                    "❌ Neplatí" if user.get("paid") else "💚 Platí",
                    f"pd:{tg_id}".encode(),
                ),
            ],
            [Button.inline("← Konverzácie", b"cv"), Button.inline("Menu", b"m")],
        ]
        # Mazanie ponúkam len pre vlastný účet — aby si omylom nezmazal
        # históriu skutočnému klientovi.
        if tg_id == self._cfg.owner_chat_id:
            buttons.insert(
                1, [Button.inline("🧹 Vymazať pamäť tejto konverzácie", f"wq:{tg_id}".encode())]
            )
        await self._render(event, "\n".join(lines)[:4000], buttons, True)

    async def _confirm_wipe(self, event, tg_id: int) -> None:
        if tg_id != self._cfg.owner_chat_id:
            await event.answer("Mazať sa dá len tvoj testovací chat", alert=True)
            return
        user = await self._db.get_user(tg_id)
        count = (user or {}).get("msg_count") or 0
        await event.answer()
        await self._render(
            event,
            f"*Vymazať pamäť testovacieho chatu?*\n\n"
            f"Zmaže sa história ({count} správ), zhrnutie, štýl aj funnel stav.\n"
            f"Bude sa chovať, akoby ste si nikdy nepísali.\n\n"
            f"Ostatných konverzácií sa to netýka.",
            [
                [Button.inline("🧹 Áno, vymazať", f"wy:{tg_id}".encode())],
                [Button.inline("← Nie, späť", b"m")],
            ],
            True,
        )

    async def _wipe(self, event, tg_id: int) -> None:
        if tg_id != self._cfg.owner_chat_id:
            await event.answer("Mazať sa dá len tvoj testovací chat", alert=True)
            return
        deleted = await self._db.wipe_conversation(tg_id)
        log.info("Vymazaná pamäť konverzácie %s (%s správ)", tg_id, deleted)
        await event.answer(f"Vymazané ({deleted} správ)")
        await self._render(
            event,
            f"✅ *Pamäť vymazaná* — {deleted} správ.\n\n"
            f"Napíš jej z testovacieho účtu a začne od nuly.",
            [[Button.inline("← Menu", b"m")]],
            True,
        )

    async def _toggle_takeover(self, event, tg_id: int) -> None:
        user = await self._db.get_user(tg_id)
        if not user:
            await event.answer("Nenašiel som to", alert=True)
            return
        value = not bool(user.get("human_takeover"))
        await self._db.update_user(tg_id, {"human_takeover": value})
        await event.answer("Píšeš ty" if value else "AI pokračuje")
        await self._send_conversation(event, tg_id)

    async def _toggle_paid(self, event, tg_id: int) -> None:
        user = await self._db.get_user(tg_id)
        if not user:
            await event.answer("Nenašiel som to", alert=True)
            return
        paid = not bool(user.get("paid"))
        await self._db.update_user(
            tg_id, {"paid": paid, "funnel_stage": "converted" if paid else "warm"}
        )
        await event.answer("Označený ako predplatiteľ" if paid else "Zrušené")
        await self._send_conversation(event, tg_id)
