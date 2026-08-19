"""Userbot — číta DM na účte modelky a odpisuje cez LLM."""
from __future__ import annotations

import asyncio
import io
import logging
import random
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events
from telethon.tl.functions.contacts import GetBlockedRequest
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji, User

import behavior as bhv
import den
import facts
import funnel
import gags
import humanize
import judge
import limity
import memory
import photos
import recall
import speech
import taper as taper_mod
import livevoice
import outreach as outreach_mod
import topics
import voices as voices_mod
import weather as weather_mod
from behavior import Behavior
from config import TenantConfig as Config
from db import TenantDb as Db
from llm import Llm
import persona as persona_mod
from persona import build_system_prompt

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+|\b[\w-]+\.(com|net|org|io|co|vue|me|link)\b\S*", re.IGNORECASE)
_SWEEP_INTERVAL_S = 180
# Po restarte sa nečaká celý interval — nech nikto nevisí bez odpovede.
_SWEEP_FIRST_S = 45
# Koľkým ľuďom sa odpovedá naraz, keď fronta dobieha. Viac než pár naraz už
# vyzerá ako dávka; menej znamená, že jedna dlhá pauza drží celý rad.
_SWEEP_CONCURRENCY = 4
# Na koľko bublín sa odpoveď nanajvýš delí (humanize.split_message).
_MAX_CHUNKS = 3
# Ako často sa pozerá, či dashboard nepýta ukážku hlasovky. Je to tlačidlo
# v prehliadači, takže sa čaká v sekundách, nie v minútach.
_VOICE_JOB_POLL_S = 4

# Prečo ukážka nevznikla — KÓDY, nie vety.
#
# Stĺpec `voice_jobs.error` číta jediný človek: klient v dashboarde, a ten
# číta po anglicky. Worker hovorí po slovensky a nemá kde držať preklady,
# takže sem ide kód a vetu k nemu složí web (`web/lib/voice.ts`). Kód, ktorý
# web nepozná, sa ukáže tak, ako prišiel — surová chyba je vždy lepšia než
# „niečo sa pokazilo".
VOICE_JOB_NO_KEY = "no_eleven_key"
VOICE_JOB_NO_VOICE = "no_voice_selected"
VOICE_JOB_NO_AUDIO = "no_audio"
# Od koľkej správy smie sama od seba poslať hlasovku. Cudziemu človeku sa
# hlasovkou nezačína — kto ju dostane hneď, dostane skôr podozrenie než dôkaz.
# Neplatí, keď si ju vypýta alebo keď pochybuje, že je skutočná.
VOICE_MIN_MESSAGES = 6
# Pod koľko nevidených fotiek sa už oplatí ozvať, že knižnica dochádza.
PHOTO_LOW_MARK = 2
# Najnižší násobič oneskorenia, na aký sa smú vlna a rozvrh vynásobiť.
# Rýchle odpovede má na starosti pozorný režim, nie stohovanie násobičov.
MIN_FACTOR = 0.35

# Servisné účty Telegramu — 777000 posiela prihlasovacie kódy a oznamy.
# Nie sú označené ako bot, takže by prešli ako bežný klient.
SYSTEM_IDS = frozenset({777000, 42777, 4244000, 333000})

# „Koľko sa ešte zmestí", keď je strop vypnutý (0). Konkrétne číslo, nie
# `math.inf`: hodnota ide do `min()` a do `kto_ide_na_rad`, kde sa porovnáva
# s dĺžkami zoznamov a nekonečno by tam len robilo neporiadok v typoch.
_BEZ_LIMITU = 10_000

# Koľko posledných spracovaných správ si držíme, aby sme spoznali znovudoručenie.
# 500 je s rezervou viac, než čo Telegram po jednom reconnecte zopakuje, a v pamäti
# je to zopár kilobajtov.
_SEEN_LIMIT = 500

# Reakcia emoji na jeho TEXT — ako keď človek dá srdiečko na správu, ktorá ho
# potešila, aj keď na ňu odpovedá. Šanca je nízka a medzi reakciami je odstup
# zámerne: reakcia na každú druhú správu je rovnaký stroj ako žiadna.
TEXT_REACT_CHANCE = 0.15
TEXT_REACT_GAP_MIN = 45


def _is_system_account(entity: User) -> bool:
    return (
        entity.id in SYSTEM_IDS
        or bool(getattr(entity, "support", False))
        or bool(getattr(entity, "scam", False))
        or bool(getattr(entity, "fake", False))
    )

Notifier = Callable[[str], Awaitable[None]]


class UserBot:
    def __init__(
        self,
        cfg: Config,
        db: Db,
        llm: Llm,
        client: TelegramClient,
        notify: Notifier,
    ) -> None:
        self._cfg = cfg
        self._db = db
        self._llm = llm
        self._client = client
        self._notify = notify
        # Control bot pre semi-auto schvaľovanie. Dopĺňa runner cez set_control;
        # bez neho (bez tokenu bota) semi-auto len necháva správu čakať.
        self._control = None
        self._debounce: Dict[int, asyncio.Task] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._reply_times: Deque[datetime] = deque()
        # Koho Marek zablokoval — tomu sa neodpisuje za žiadnych okolností.
        self._blocked: frozenset = frozenset()
        self._blocked_at: Optional[datetime] = None
        # Kedy sa naposledy hlásilo, že niekomu dochádzajú fotky.
        self._library_warned: Dict[int, datetime] = {}
        # Fotka, ktorá čaká na reakciu — dá sa až keď si ju naozaj otvorí.
        self._photo_reaction: Dict[int, tuple] = {}
        # To isté pre text: (msg_id, emoji) pripravené v handleri, odpálené až
        # po prečítaní. Plus kedy naposledy — reakcie majú byť občas, nie vždy.
        self._text_reaction: Dict[int, tuple] = {}
        self._last_text_react: Dict[int, datetime] = {}
        # Dokedy mlčíme, lebo si to vypýtal sám Telegram (FloodWait).
        self._flood_until: Optional[datetime] = None
        # Kĺzavé okno flood chýb za hodinu + kedy sme naposledy varovali, nech
        # sa Marekovi neposiela tá istá správa každú minútu.
        self._flood_events: Deque[datetime] = deque(maxlen=64)
        self._flood_warned_at: Optional[datetime] = None
        # Kedy sme naposledy hlásili, že limity nevidia do DB (a preto mlčíme).
        self._slepota_warned_at: Optional[datetime] = None
        # Id správ, ktoré sme už spracovali. Telegram po reconnecte doručí
        # neodkvitované updaty ZNOVA — bez tohto sa tá istá otázka uloží
        # druhýkrát a modelka na ňu odpovie druhýkrát, iným textom.
        # Ohraničené: drží sa posledných `_SEEN_LIMIT`, staršie vypadávajú.
        self._seen: Deque[tuple] = deque(maxlen=_SEEN_LIMIT)
        self._seen_set: set = set()

    # ---------- registrácia ----------

    def register(self) -> None:
        self._client.add_event_handler(self._on_message, events.NewMessage(incoming=True))

    def start_sweeper(self) -> asyncio.Task:
        return asyncio.create_task(self._sweep_loop())

    def start_voice_jobs(self) -> asyncio.Task:
        """Obsluha ukážok z dashboardu. Vlastná slučka, lebo sweeper beží
        raz za tri minúty a to je na tlačidlo v prehliadači priveľa."""
        return asyncio.create_task(self._voice_jobs_loop())

    async def _voice_jobs_loop(self) -> None:
        while True:
            await asyncio.sleep(_VOICE_JOB_POLL_S)
            try:
                await self._voice_jobs_once()
            except Exception:  # noqa: BLE001 - slučka nesmie umrieť
                log.exception("Obsluha ukážok zlyhala")

    async def _behavior(self) -> Behavior:
        try:
            return Behavior.from_row(await self._db.get_behavior())
        except Exception as exc:  # noqa: BLE001 - defaulty sú bezpečné
            log.warning("Nepodarilo sa načítať chovanie, používam defaulty: %s", exc)
            return Behavior()

    async def _rozvrh(self):
        """Nastavený deň modelky (migrácia 022). `None` = platí šablóna z `den`.

        Fail-safe rovnako ako pri chovaní: keď sa riadok nedá načítať, beží
        napísaný deň. Modelka, ktorá zrazu nevie, kde je, by bola horšia než
        modelka s pôvodným rozvrhom.
        """
        try:
            return den.Rozvrh.from_row(await self._db.get_schedule())
        except Exception as exc:  # noqa: BLE001 - šablóna je bezpečná
            log.warning("Nepodarilo sa načítať rozvrh dňa, beží šablóna: %s", exc)
            return None

    # ---------- príjem správ ----------

    async def _on_message(self, event: events.NewMessage.Event) -> None:
        try:
            await self._handle(event)
        except Exception:  # noqa: BLE001 - handler nesmie zhodiť klienta
            log.exception("Chyba pri spracovaní správy")
            # Vodoznak sme mohli posunúť ešte pred pádom (`claim_message`), a to
            # je cena za to, že sa neodpisuje dvakrát: tú istú správu už znovu
            # neprijmeme a dobeh po štarte ju tiež preskočí. Aby z ochrany pred
            # duplicitou nevzniklo mlčanie, odovzdáme ju sweeperu.
            tg_id = getattr(event, "sender_id", 0) or 0
            if tg_id:
                try:
                    await self._db.update_user(tg_id, {"pending_reply": True})
                except Exception:  # noqa: BLE001 - viac sa už spraviť nedá
                    log.exception("%s: nepodarilo sa zaradiť na neskoršiu odpoveď", tg_id)

    async def _handle(self, event: events.NewMessage.Event) -> None:
        if not event.is_private:
            log.debug("Preskakujem: nie je privátny chat")
            return
        sender = await event.get_sender()
        if not isinstance(sender, User):
            log.debug("Preskakujem: odosielateľ nie je user (%s)", type(sender).__name__)
            return
        if sender.bot:
            log.info("Preskakujem: odosielateľ je bot (%s)", sender.id)
            return
        if _is_system_account(sender):
            log.info("Preskakujem %s: servisný účet Telegramu", sender.id)
            return
        await self._refresh_blocked()
        if sender.id in self._blocked:
            log.info("Preskakujem %s: je zablokovaný", sender.id)
            return
        if sender.is_self:
            log.debug("Preskakujem: vlastná správa")
            return

        tg_id = sender.id
        is_owner = tg_id == self._cfg.owner_chat_id

        # ZNOVUDORUČENIE. Telegram po reconnecte pošle updaty, ktoré mu klient
        # nestihol odkvitovať — tie isté správy druhýkrát. Bez tejto brány sa
        # otázka uloží dvakrát a modelka na ňu odpovie dvakrát, zakaždým iným
        # textom; presne to sa stalo 18. 8. o 6:53, keď sa štyri Marekove
        # správy vložili naraz mimo poradia a vznikla druhá odpoveď.
        #
        # Kontrola je TU, ešte pred stiahnutím fotky a prepisom hlasovky —
        # tie stoja peniaze a zopakovať sa nesmú ani raz.
        seen_key = (tg_id, getattr(event.message, "id", 0) or 0)
        if seen_key[1]:
            if seen_key in self._seen_set:
                log.info("Preskakujem %s: správa %s už bola spracovaná", tg_id, seen_key[1])
                return
            if len(self._seen) == self._seen.maxlen:
                self._seen_set.discard(self._seen[0])
            self._seen.append(seen_key)
            self._seen_set.add(seen_key)

        # Vlastníka neobsluhuj ako klienta. Kontrola ide PRED filtrom kontaktov,
        # inak by testovanie z vlastného účtu spadlo na tom, že je v kontaktoch.
        if is_owner and not self._cfg.owner_as_client:
            log.info("Preskakujem %s: je to vlastník (OWNER_AS_CLIENT=false)", tg_id)
            return
        # Kontakty sa preskakujú, aby AI nepísala jej rodine a známym. Výnimky
        # sú na testovanie s kamošmi, ktorí v kontaktoch sú.
        if (
            not is_owner
            and self._cfg.skip_contacts
            and getattr(sender, "contact", False)
            and tg_id not in self._cfg.contact_exceptions
        ):
            log.info("Preskakujem %s: je v kontaktoch (SKIP_CONTACTS=true)", tg_id)
            return

        text = (event.raw_text or "").strip()
        if event.photo:
            seen = await self._look_at_photo(event)
            text = f"{seen} {text}".strip() if text else seen
            # Srdiečko alebo plamienok priamo na fotku. Odloží sa na chvíľu,
            # keď si správu naozaj otvorí: reakcia na fotku, ktorá je v chate
            # stále neprečítaná, je presne naopak než ako sa správa človek.
            self._photo_reaction[tg_id] = (message_id_of(event), "EXPLICITNÚ" in seen)
        elif getattr(event, "voice", None) or getattr(event, "audio", None):
            # Hlasovku prepíšeme, nech vie, čo jej povedal, a nech to má aj
            # v pamäti ako text — inak by konverzácia stratila celý kúsok.
            povedal = await self._hear_voice(event)
            text = f"{povedal} {text}".strip() if text else povedal
        elif not text and event.media:
            text = "[poslal médium bez textu]"
        if not text:
            log.info("Preskakujem %s: prázdna správa bez média", tg_id)
            return

        log.info("Prijaté od %s (@%s): %r", tg_id, sender.username, text[:80])

        # Nová správa po dlhom tichu = predošlé sedenie sa práve uzavrelo.
        # Zapíšeme ho ako epizódu, kým je ešte v archíve celé.
        asyncio.create_task(self._close_session(tg_id))

        user = await self._db.ensure_user(
            tg_id, sender.username, sender.first_name, getattr(sender, "lang_code", None)
        )
        is_new = int(user.get("msg_count") or 0) == 0

        # Druhý zámok — ten, ktorý prežije reštart procesu aj súbeh dvoch replík.
        # Pamäťová brána vyššie po štarte nevie nič (a práve po štarte doručuje
        # Telegram zopakovaných updateov najviac) a dva procesy majú pamäť každý
        # svoju. `claim_message` je jeden podmienený zápis do vodoznaku, takže ho
        # môže vyhrať práve jeden — druhý mlčí. Id správ v súkromných chatoch
        # rastú v jednej postupnosti na celý účet, takže nižšie id vždy znamená
        # „toto sme už mali".
        message_id = seen_key[1]
        if message_id and not await self._db.claim_message(tg_id, message_id):
            log.info("Preskakujem %s: správu %s spracoval niekto iný", tg_id, message_id)
            return

        await self._db.add_message(tg_id, "user", text)

        # Občasná reakcia na jeho text. Až TU, za zámkom správy — reagovať na
        # správu, ktorú si zabrala iná replika, by znamenalo dve reakcie.
        # Fotky majú vlastnú vetvu vyššie a majú prednosť.
        if not event.photo and message_id:
            emoji = humanize.text_reaction(text)
            naposledy = self._last_text_react.get(tg_id)
            if (
                emoji
                and (naposledy is None
                     or datetime.now(timezone.utc) - naposledy
                     > timedelta(minutes=TEXT_REACT_GAP_MIN))
                and random.random() < TEXT_REACT_CHANCE
            ):
                self._text_reaction[tg_id] = (message_id, emoji)
                self._last_text_react[tg_id] = datetime.now(timezone.utc)

        user["msg_count"] = int(user.get("msg_count") or 0) + 1
        patch: Dict[str, Any] = {
            "msg_count": user["msg_count"],
            "last_incoming_at": _utc_iso(),
            # Odpovedal — ranné oslovenia sa môžu znova rátať od nuly.
            "outreach_silent": 0,
        }
        # `last_msg_id` tu už nie je — posunul ho `claim_message` vyššie. Zapísať
        # ho druhýkrát by nič nepokazilo, ale zahmlilo by, kde sa o správe
        # rozhoduje: vodoznak JE ten zámok, nie poznámka po práci.
        # Meno ukladáme hneď ako sa predstaví — do vlastného stĺpca, nie do
        # summary. Vďaka tomu sa naň už nikdy nespýta, ani o týždeň.
        if not (user.get("partner_name") or "").strip():
            found = funnel.extract_name(text)
            if found:
                patch["partner_name"] = found
                user["partner_name"] = found
                log.info("%s sa predstavil ako %s", tg_id, found)

        new_stage = funnel.next_stage(user, text)
        if new_stage != user.get("funnel_stage"):
            patch["funnel_stage"] = new_stage
            user["funnel_stage"] = new_stage
        await self._db.update_user(tg_id, patch)

        if is_new and not user.get("notified"):
            await self._db.update_user(tg_id, {"notified": True})
            await self._notify(
                f"🆕 Nová konverzácia\n{_who(user)} (`{tg_id}`)\n\n„{text[:200]}\""
            )
        if funnel.detect_paid_claim(text) and not user.get("paid"):
            await self._notify(
                f"💳 {_who(user)} (`{tg_id}`) tvrdí, že zaplatil.\nAk áno: `/paid {tg_id}`"
            )

        self._schedule_reply(tg_id)

    def _schedule_reply(self, tg_id: int) -> None:
        """Debounce — ak človek dopisuje ďalšie správy, timer sa reštartuje."""
        existing = self._debounce.get(tg_id)
        if existing and not existing.done():
            existing.cancel()
        self._debounce[tg_id] = asyncio.create_task(self._debounced_reply(tg_id))

    async def _debounced_reply(self, tg_id: int) -> None:
        try:
            behavior = await self._behavior()
            if self._is_test_account(tg_id):
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(bhv.debounce_delay(behavior))
            await self.reply_to(tg_id, behavior)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Chyba pri generovaní odpovede pre %s", tg_id)
        finally:
            self._debounce.pop(tg_id, None)

    # ---------- generovanie odpovede ----------

    async def reply_to(
        self, tg_id: int, behavior: Optional[Behavior] = None, morning: bool = False
    ) -> None:
        lock = self._locks.setdefault(tg_id, asyncio.Lock())
        async with lock:
            await self._reply_locked(
                tg_id, behavior or await self._behavior(), morning=morning
            )

    def _is_test_account(self, tg_id: int) -> bool:
        """Marekov vlastný účet pri testovaní — odpovedá vždy a hneď.

        Bez toho by musel čakať na aktívne okno a na minútové pauzy, a nevedel by
        si chovanie prakticky vyskúšať. Pre všetkých ostatných platia pravidlá.
        """
        return tg_id == self._cfg.owner_chat_id and self._cfg.owner_as_client

    async def _reply_locked(self, tg_id: int, behavior: Behavior, morning: bool = False) -> None:
        user = await self._db.get_user(tg_id)
        if not user:
            return
        testing = self._is_test_account(tg_id)
        await self._refresh_blocked()
        if tg_id in self._blocked:
            log.info("Preskakujem %s: je zablokovaný", tg_id)
            await self._db.update_user(tg_id, {"pending_reply": False, "ai_enabled": False})
            return
        if user.get("human_takeover") or not user.get("ai_enabled", True):
            log.info("Preskakujem %s (takeover/vypnuté)", tg_id)
            return

        # Režim odpovedania (Off / Auto / Semi). Off = nereaguje vôbec; Semi =
        # namiesto odoslania sa vygenerujú návrhy a pošlú majiteľovi na
        # schválenie. V Semi sa preskakuje rozvrh/časovanie (tempo riadi majiteľ,
        # viď spec §3) — ale tvrdé gates (blocked, pauza, flood) platia aj tam.
        mode_row = await self._db.tg_reply_mode()
        mode = mode_row.get("mode", "auto")
        if mode == "off":
            await self._db.update_user(tg_id, {"pending_reply": False})
            return
        semi = mode == "semi"

        if await self._db.is_paused():
            log.info("Odkladám %s: globálna pauza", tg_id)
            await self._db.update_user(tg_id, {"pending_reply": True})
            return

        # Odložená odpoveď (tá „zabudol som“ na 2–3 h) — ešte nie je čas.
        # Nočný zámok ráno prirodzene vypršal, takže sa mu netreba vyhýbať.
        # V Semi riadi tempo majiteľ — odložené odpovede aj aktívne okno sa
        # ignorujú (návrh mu má prísť hneď).
        wait_until = None if (testing or semi) else _parse_ts(user.get("reply_after"))
        if wait_until and wait_until > datetime.now(timezone.utc):
            mins = (wait_until - datetime.now(timezone.utc)).total_seconds() / 60
            log.info("%s: ešte čaká, odpoveď za %.0f min", tg_id, mins)
            return

        now_local = datetime.now(ZoneInfo(behavior.active_tz))
        if not testing and not semi and not bhv.in_active_window(
            now_local, behavior.active_start_min, behavior.active_end_min
        ):
            mins = bhv.minutes_until_active(
                now_local, behavior.active_start_min, behavior.active_end_min
            )
            log.info(
                "Odkladám %s: mimo aktívneho okna %s %s (do začiatku %s min)",
                tg_id,
                bhv.format_window(behavior.active_start_min, behavior.active_end_min),
                behavior.active_tz,
                mins,
            )
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        if not await self._flood_ok():
            log.warning("Odkladám %s: Telegram si vypýtal pauzu", tg_id)
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        # Rozbeh: čerstvé Telegram číslo jazdí na zlomku stropov. Pre Telegram
        # je deň starý účet na plnom výkone oveľa podozrivejší než ten istý
        # objem na účte, ktorý beží mesiace.
        podiel = self._rozbeh()
        if not testing and not semi and not await self._rate_ok(
            limity.s_rozbehom(behavior.max_replies_per_hour, podiel)
        ):
            log.warning("Odkladám %s: hodinový strop odpovedí (rozbeh %.0f %%)",
                        tg_id, podiel * 100)
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        if not testing and not semi and not await self._denny_strop_ok(behavior, podiel):
            log.warning("Odkladám %s: denný strop správ", tg_id)
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        # Koľko rozhovorov vedie naraz. Skutočný človek nevedie dvadsať — vedie
        # pár, tie dopíše, a keď utíchnu, pustí sa do ďalších. Kto sa nezmestí,
        # počká vo fronte a dobehne ho sweeper, len čo sa miesto uvoľní.
        # V Semi to neplatí — schvaľuje človek, nie automat.
        if not testing and not semi:
            aktivni = await self._aktivne_rozhovory(behavior)
            if aktivni is None:
                # Výpadok DB. Rozhovor, ktorý už beží, dopíšeme — prerušiť ho
                # v polovici je horšie než pokračovať. Nový ale nezačíname:
                # bez čísel nevieme, koľko ich beží, a hádať smerom „smie" je
                # presne ten druh tichého vypnutia brzdy, ktorý stojí účet.
                log.warning("Odkladám %s: neviem, koľko rozhovorov beží", tg_id)
                await self._db.update_user(tg_id, {"pending_reply": True})
                return
            if not limity.ma_miesto(tg_id, aktivni, behavior.max_active_chats):
                log.info(
                    "Odkladám %s: práve vedie %s rozhovorov z %s",
                    tg_id, len(aktivni), behavior.max_active_chats,
                )
                await self._db.update_user(tg_id, {"pending_reply": True})
                return

        rows = await self._db.recent_messages(tg_id, self._cfg.context_messages)
        if not rows:
            return
        # Ochrana proti dvojitej odpovedi: odpisuj len keď posledná správa je jeho.
        # Pri rannom oslovení to neplatí — tam píše prvá zámerne.
        if not morning and rows[-1].get("role") == "assistant":
            log.info("Preskakujem %s: na poslednú správu už bolo odpovedané", tg_id)
            await self._db.update_user(tg_id, {"pending_reply": False})
            return

        history = memory.to_chat_history(rows)
        last_user_text = next(
            (r["content"] for r in reversed(history) if r["role"] == "user"), ""
        )

        # Občas „zabudne“ odpovedať a vráti sa k tomu až za pár hodín.
        # Čas sa ukladá do DB, takže to prežije restart workera.
        deferred = 0.0 if (testing or semi) else bhv.should_defer_reply(
            behavior, int(user.get("msg_count") or 0), last_user_text
        )
        if deferred:
            until = datetime.now(timezone.utc) + timedelta(seconds=deferred)
            log.info("%s: odkladám odpoveď o %.1f h (na %s)", tg_id, deferred / 3600, until)
            await self._db.update_user(
                tg_id, {"pending_reply": True, "reply_after": until.isoformat()}
            )
            return

        gap = bhv.gap_hours(_parse_ts(user.get("last_reply_at")), datetime.now(timezone.utc))
        # Kde je podľa dnešného rozvrhu. Z toho vyplýva, ako rýchlo odpisuje,
        # odkiaľ znie hlasovka aj čo o sebe smie povedať.
        rozvrh = await self._rozvrh()
        dnesny_blok = den.block_at(now_local, self._cfg.supabase_schema, rozvrh)
        if testing:
            factor, wave = (0.0, "TEST — odpovedá hneď")
        elif behavior.activity_waves:
            # Seed je schéma modelky, rovnako ako pri rozvrhu. Predtým mali
            # všetky tri natvrdo „simona", takže mali aj rovnaké vlny.
            factor, wave = bhv.activity_wave(now_local, self._cfg.supabase_schema)
        else:
            factor, wave = 1.0, "vypnuté"
        # V posilňovni sa neodpisuje rovnako rýchlo ako z gauča a na fotení
        # telefón vôbec nedrží — to je na nej to najľudskejšie.
        if not testing:
            factor *= den.pace(dnesny_blok)
            # Podlaha na zrýchlenie. Vlna „burst" (×0.12) a gauč (×0.6) sa
            # vynásobia na ×0.072, čo znamená odpoveď za 2,5–28 sekundy — a to
            # je presne to, čo má robiť pozorný režim. Keď to isté robí aj
            # bežná cesta, rozdiel medzi „drží telefón v ruke" a „všimla si
            # neskôr" zmizne a všetko splynie do jednej rýchlosti.
            factor = max(factor, MIN_FACTOR)
        log.info(
            "%s: vlna %s (×%.2f) | %s",
            tg_id, wave, factor, den.describe(dnesny_blok) or "mimo rozvrhu",
        )

        # Občas je práve pri telefóne — vtedy odpovie do pár sekúnd a žiadne
        # pauzy sa neuplatnia. Bez toho by ľudia čakali vždy a to je tiež divné.
        # Pozorný režim odpovie do pár sekúnd a obchádza pritom vlnu aj rozvrh —
        # nečíta `factor` vôbec. Keď má podľa rozvrhu telefón odložený, je to
        # priamy protiklad toho, čo rozvrh hovorí: namerané 55 % odpovedí do
        # pol minúty aj z fotenia. Tam sa preto nespúšťa vôbec.
        quick = (
            None
            if testing or den.busy(dnesny_blok)
            else bhv.quick_reply(behavior, last_user_text)
        )
        if quick:
            log.info("%s: pozorný režim — videné za %.0f s, odpoveď za %.0f s", tg_id, *quick)

        # 1) chvíľu si správu „nevšimne“, potom ju prečíta.
        #    V Semi žiadne pauzy — návrh má prísť majiteľovi hneď.
        if semi:
            pass
        elif quick:
            await asyncio.sleep(quick[0])
        elif not testing:
            await asyncio.sleep(bhv.read_delay(behavior, factor=factor))
        await self._mark_read(tg_id)
        # Chat je od tejto chvíle prečítaný, takže reakcia už sedí. Fotka má
        # prednosť pred textom; obe sa vyberú, nech textová nevisí do budúcna.
        caka = self._photo_reaction.pop(tg_id, None)
        na_text = self._text_reaction.pop(tg_id, None)
        if caka:
            asyncio.create_task(self._react_to_photo(tg_id, *caka))
        elif na_text:
            asyncio.create_task(self._react(tg_id, na_text[0], na_text[1], "správu"))

        # 2) občas nechá len „videné“ a odpíše až po pár minútach
        seen_wait = 0.0 if (testing or semi or quick) else bhv.seen_only_delay(behavior)
        if seen_wait:
            log.info("%s: len videné, odpoveď za %.0f s", tg_id, seen_wait)
            await self._defer(tg_id, seen_wait)
            await asyncio.sleep(seen_wait)

        # 3) občas odíde od telefónu na dlhšie
        pause = 0.0 if (testing or semi or quick) else bhv.long_pause_delay(behavior)
        if pause:
            log.info("%s: dlhá pauza %.0f min", tg_id, pause / 60)
            await self._defer(tg_id, pause)
            await asyncio.sleep(pause)

        # Medzitým sa mohlo všeličo zmeniť — načítaj stav odznova.
        # V Semi sa nečakalo, takže nie je čo obnovovať.
        if not testing and not semi:
            obnovene = await self._refresh_after_wait(tg_id, morning)
            if obnovene is None:
                return
            user, rows, history, last_user_text = obnovene
            gap = bhv.gap_hours(
                _parse_ts(user.get("last_reply_at")), datetime.now(timezone.utc)
            )

        # Sám si pýta odkaz alebo chce explicitný obsah → nedrž mu ho pred nosom.
        wants_link = funnel.detect_link_request(last_user_text)
        explicit = funnel.detect_explicit_interest(last_user_text)
        allow_link = funnel.can_send_link(
            user,
            datetime.now(timezone.utc),
            self._cfg.link_min_messages,
            self._cfg.link_cooldown_hours,
            self._cfg.link_max_pushes,
            fast_track=wants_link or explicit,
        )
        if allow_link and not await self._link_quota_ok(behavior):
            log.info("%s: odkaz zablokovaný globálnym stropom %s/h", tg_id, behavior.max_links_per_hour)
            allow_link = False

        # Menom osloví len občas — v každej správe by to znelo ako predavač.
        # Raz za pätnásť až dvadsať správ, nie v každej štvrtej. Model ho
        # inak používal takmer vždy a znelo to ako predavač.
        use_name = bool((user.get("partner_name") or "").strip()) and random.random() < 0.06
        # Rozpísať sa smie len občas, inak sa z výnimky stane štandard.
        allow_long = random.random() < 0.3

        # Register tém: čo sa hodí spýtať teraz a na čo sa už pýtať nesmie.
        persona = await self._db.get_persona()
        asked = user.get("asked_topics") or {}
        try:
            fact_rows = await self._db.facts_for(tg_id)
        except Exception as exc:  # noqa: BLE001 - bez faktov sa dá odpovedať
            log.warning("Fakty sa nepodarilo načítať pre %s: %s", tg_id, exc)
            fact_rows = []
        fact_sheet = facts.sheet(fact_rows)

        # Dej, sľuby a relevantné kúsky archívu — pamäť, ktorá nemá horizont.
        episodes_block = loops_block = archive_block = claims_block = ""
        claim_rows = []
        try:
            episode_rows = await self._db.episodes_for(tg_id)
            loop_rows = await self._db.open_loops(tg_id)
            claim_rows = await self._db.self_claims(tg_id)
            claims_block = judge.claims_block(claim_rows)
            episodes_block = recall.episodes_block(episode_rows)
            loops_block = recall.loops_block(loop_rows)
            terms = recall.search_terms(last_user_text)
            if terms:
                hits = await self._db.search_archive(tg_id, terms)
                # z archívu vyhoď to, čo aj tak vidí v okne posledných správ
                recent_texts = {(r.get("content") or "")[:60] for r in rows}
                hits = [h for h in hits if (h.get("content") or "")[:60] not in recent_texts]
                archive_block = recall.archive_block(hits, persona.get("name") or "Ona")
        except Exception as exc:  # noqa: BLE001 - pamäť navyše nesmie blokovať
            log.warning("Rozšírenú pamäť sa nepodarilo načítať pre %s: %s", tg_id, exc)
        # Známe fakty vypnú príslušné témy — predtým sem chodilo len ["name"],
        # takže sa vedela znovu spýtať na prácu, ktorú už poznala.
        known = facts.known_keys(fact_rows)
        if (user.get("partner_name") or "").strip() and "name" not in known:
            known.append("name")
        part = bhv.part_of_day(now_local)
        fresh = topics.suggest(asked, now_local, part, known_facts=known, seed=str(tg_id))
        avoid = topics.recently_asked(asked)
        # V ranej fáze sa pýta výrazne častejšie. Namerané: otázku mala len
        # v 16 % správ, hoci nastavenie povoľuje 45 % — a prvých dvadsať správ
        # má byť čisté spoznávanie. Kto sa nepýta, ten sa nespoznáva.
        # Nula znamená nula: keď má vypnuté otázky, neprebíja to ani raná fáza.
        sanca_otazky = float(behavior.question_chance or 0)
        if sanca_otazky > 0 and int(user.get("msg_count") or 0) < persona_mod.EARLY_PHASE:
            sanca_otazky = max(sanca_otazky, 0.8)
        can_ask = random.random() < sanca_otazky
        gag = gags.maybe_pick(
            user.get("used_gags"), part, float(getattr(behavior, "gag_chance", 0.07) or 0)
        )
        if gag:
            log.info("%s: ponúkam drzý vtip %s", tg_id, gag.key)
        log.info(
            "%s: %s | navrhy: %s | vyhnut sa: %s",
            tg_id,
            "môže sa spýtať" if can_ask else "bez otázky",
            [t.key for t in fresh] or "-",
            [t.key for t in avoid] or "-",
        )

        # Koľkokrát už tvrdil, že je bot. Raz je bežné, tri razy je to človek,
        # ktorý si to nedá vyhovoriť — a s tým sa už nemá zmysel naťahovať.
        tlak_bot = humanize.ai_question_count(rows)
        # Hlasovka mu zanikla a pýta sa, čo povedala. Ďalšia nahrávka by
        # dopadla rovnako — zopakuje to textom a kratšie.
        nerozumel = humanize.asks_what_she_said(last_user_text)
        if tlak_bot >= 4 and not testing:
            log.info("%s: %s. obvinenie z bota — nechávam to tak", tg_id, tlak_bot)
            await self._db.update_user(tg_id, {"pending_reply": False})
            return

        # Kto má odkaz už pár dní a stále je len tu, dostáva postupne menej.
        utlm = taper_mod.level(user)
        if utlm:
            log.info("%s: útlm konverzácie — úroveň %s", tg_id, utlm)

        # --- hlasovka: len keď prepis naozaj sadne na rozhovor ---
        # Nahrávky sú v angličtine, takže do inojazyčnej konverzácie nepatria —
        # anglická hlasovka niekomu, kto píše po slovensky, je okamžite divná.
        chosen_voice = None
        len_hlasovka = False
        # Ranné oslovenie je ľahké šťuchnutie, nie zásielka. Fotka ani hlasovka
        # k nemu nepatria — vyzerá to ako rozposielanie, nie ako že si spomenula.
        media_ok = not morning
        cudzi_jazyk = humanize.looks_foreign(last_user_text)
        if cudzi_jazyk:
            log.info("%s: hlasovku nepošlem, píše iným jazykom", tg_id)
        # Hlasovku vyrábame na mieru. Stará knižnica nemá prednosť — nahratý
        # súbor povie vždy to isté a nikdy nesadne na to, čo sa práve povedalo,
        # kým generovaná hovorí presne tú vetu, ktorú by inak napísala.
        #
        # Knižnica ostáva ako záchrana pre modelku, ktorá ešte nemá vyrobený
        # hlas — Ayko je presne ten prípad. Pre tú je nahratý súbor jediná
        # možnosť, ako vôbec niečo povedať.
        vie_generovat = bool(
            behavior.voices_enabled
            and behavior.eleven_key
            and behavior.eleven_voice_id
            and not cudzi_jazyk
        )
        if (
            media_ok
            and behavior.voices_enabled
            and not vie_generovat
            and not cudzi_jazyk
            and voices_mod.cooldown_passed(user)
        ):
            # Koniec dňa: keď je nahratá hlasovka na dobrú noc, rozlúči sa ňou
            # a text sa už nepíše. Bez nej sa rozlúči normálne textom.
            if bhv.winding_down(now_local, behavior.active_start_min, behavior.active_end_min):
                try:
                    kniznica = await self._db.voice_library()
                    videne = await self._db.voices_sent_to(tg_id)
                    chosen_voice = voices_mod.night_voice(kniznica, videne)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Nočnú hlasovku sa nepodarilo načítať: %s", exc)
                if chosen_voice:
                    len_hlasovka = True
                    log.info("%s: na dobrú noc idem hlasovkou", tg_id)
            if not chosen_voice:
                # Nie len posledná správa: téma bežne padne o vetu skôr
                # („bol som v gyme“ → „a co ty“) a z jednej vety sa nedá
                # rozhodnúť, či nahrávka sadne.
                chosen_voice = await self._pick_voice(
                    tg_id,
                    " ".join(memory.his_samples(rows, 3)),
                    bhv.part_of_day(now_local),
                    # CTA hlasovka je reklama — musí platiť to isté, čo pre
                    # odkaz. Bez tejto podmienky odchádzala hneď pri prvom
                    # „can i see more" a potom znova a znova, lebo sa nikam
                    # nepočítala. Klient to pomenoval presne: „that sounds
                    # very robotic".
                    allow_link and (wants_link or explicit),
                )

        # --- fotka: len keď je zapnuté, je dôvod, a nikdy tá istá dvakrát ---
        chosen_photo = None
        # Gate `photos_enabled`: klient musí posielanie fotiek zapnúť na stránke
        # (a to sa dá až keď v albumoch fotky sú). Bez toho sa fotka nepošle
        # nikdy. Testovací účet dostáva výhradne hlasovky — ani fotku, inak sa
        # v ladení zvuku nedá rozoznať, čo pokryla nahrávka a čo prišlo popri nej.
        photo_reason = (
            photos.send_reason(last_user_text, user)
            if media_ok and behavior.photos_enabled
            and tg_id not in self._cfg.voice_only_ids
            else None
        )
        # Hlasovka a fotka naraz sú tri až štyri notifikácie za sebou od
        # niekoho, kto má vyzerať, že píše z mobilu medzi vecami. Jedno médium
        # na odpoveď stačí: keď si fotku vypýtal, má prednosť fotka, inak
        # vyhráva hlasovka a fotka počká na ďalšiu správu.
        if chosen_voice and photo_reason and photo_reason != "asked":
            log.info("%s: fotku (%s) odkladám, ide hlasovka", tg_id, photo_reason)
            photo_reason = None
        if photo_reason:
            # Album podľa toho, KDE práve je (jej harmonogram) + hodina.
            schedule_folder = photos.folder_for(den.where(dnesny_blok, ""), now_local.hour)
            chosen_photo = await self._pick_photo(
                user, now_local, explicit, photo_reason, schedule_folder
            )
        if chosen_photo and chosen_voice and not len_hlasovka:
            log.info("%s: hlasovku odkladám, ide vypýtaná fotka", tg_id)
            chosen_voice = None

        # Nočná rozlúčka hlasom: nahrávka JE tá správa. Predtým sa napriek tomu
        # vygenerovala celá odpoveď, prebehol sudca a hneď nato sa text zahodil
        # — dva behy modelu do koša pri každom večernom rozlúčení.
        if len_hlasovka and chosen_voice:
            if quick:
                await asyncio.sleep(quick[1])
            elif not testing:
                await asyncio.sleep(bhv.reply_delay(behavior, factor=factor))
            if await self._send_voice(tg_id, chosen_voice):
                self._reply_times.append(datetime.now(timezone.utc))
                await self._post_send_update(
                    user, persona, behavior, "", rows, now_local, None,
                    said_goodnight=True,
                )
                return
            # Nahrávka neodišla. Rozlúčiť sa musí aj tak — mlčanie namiesto
            # dobrej noci je horšie než obyčajný text, a nasledoval by po ňom
            # nočný zámok, takže by človek do rána nedostal vôbec nič.
            log.warning("%s: nočná hlasovka neodišla, lúčim sa textom", tg_id)
            chosen_voice, len_hlasovka = None, False

        # Skutočné počasie tam, kde býva. Zlyhanie = prázdny reťazec a sekcia
        # o počasí v prompte jednoducho nebude.
        try:
            weather_now = await weather_mod.current(persona.get("city") or "")
        except Exception as exc:  # noqa: BLE001 - počasie nesmie zablokovať odpoveď
            log.warning("%s: počasie sa nepodarilo zistiť: %s", tg_id, exc)
            weather_now = ""

        # Čím je jeho správa: holý pozdrav, alebo len prikývnutie bez obsahu.
        pozdravil = humanize.is_bare_greeting(last_user_text)
        prikyvol = humanize.is_filler(last_user_text)
        # Jej posledné správy. Idú pisateľovi ako zákaz opakovania, sudcovi
        # ako podklad na kontrolu a post-processingu na potlačenie otváračov.
        jej_nedavne = [
            r.get("content") or "" for r in rows if r.get("role") == "assistant"
        ][-8:]

        system = build_system_prompt(
            persona,
            user,
            allow_link,
            humanize.looks_like_ai_question(last_user_text),
            ai_pressure=tlak_bot,
            behavior=behavior,
            gap=gap,
            last_incoming=last_user_text,
            explicit=explicit or wants_link,
            now_local=now_local,
            weather=weather_now,
            use_name=use_name,
            can_ask=can_ask,
            fresh_topics=fresh,
            avoid_topics=avoid,
            recent_emoji=humanize.recent_emoji(rows),
            fact_sheet=fact_sheet,
            claims=claims_block,
            episodes=episodes_block,
            loops=loops_block,
            archive=archive_block,
            gag=gag,
            photo=chosen_photo,
            voice=chosen_voice,
            voice_wanted=voices_mod.wants_voice(last_user_text),
            # Hlas si model smie vypýtať len keď je naozaj čím hovoriť: zapnuté,
            # kľúč aj hlas nastavené a konverzácia beží po anglicky.
            situation=den.describe(dnesny_blok),
            # Práve sa presunula — človek to povie sám, nečaká na otázku.
            arrival=den.arrival(
                den.just_moved(now_local, self._cfg.supabase_schema, rozvrh=rozvrh)
            ),
            # Nepočul hlasovku — zopakuje to textom, nie ďalšou nahrávkou.
            misheard=nerozumel,
            # Urazil ju — namiesto chápavej asistentky odpovie hrdé dievča.
            hostile=humanize.is_hostile(last_user_text),
            busy=den.busy(dnesny_blok),
            # O hlasovke sa v prompte hovorí len vtedy, keď ju naozaj smie
            # poslať — inak by si ju pýtala a tichý kód by ju zakaždým zahodil.
            # Odkaz má, tlačí a nepohol sa — hlasovka smie byť poriadne horúca.
            hot_voice=funnel.hot_and_stuck(user, explicit) and behavior.voice_when_hot,
            can_speak=bool(
                behavior.voices_enabled
                and behavior.eleven_key
                and behavior.eleven_voice_id
                and not cudzi_jazyk
                and (
                    int(user.get("msg_count") or 0) >= VOICE_MIN_MESSAGES
                    or speech.exception_reason(
                        behavior,
                        asked_for_voice=voices_mod.wants_voice(last_user_text),
                        doubts_her=humanize.looks_like_ai_question(last_user_text),
                        he_voiced=speech.he_sent_voice(last_user_text),
                    )
                )
            ),
            photo_wanted=photo_reason == "asked",
            photo_reason=photo_reason or "",
            link_already_sent=int(user.get("link_push_count") or 0) > 0,
            # Bez tohto stropu spomenula odkaz v každej jednej odpovedi.
            remind_link=not funnel.recently_reminded(rows),
            allow_long=allow_long,
            foreign=humanize.looks_foreign(last_user_text),
            bare_greeting=humanize.is_bare_greeting(last_user_text),
            taper=utlm,
            morning=outreach_mod.guidance(user) if morning else "",
            his_question=humanize.last_question(last_user_text),
            # Na prikývnutí sa nedá priostriť — naživo z „Nice 😅" vytiahla,
            # že by mala postnúť niečo horúcejšie, a bolo to úplne mimo.
            lead_funnel=funnel.should_lead(user) and not prikyvol,
            filler=prikyvol,
            wants_call=funnel.wants_call(last_user_text),
            session_h=memory.session_hours(rows),
            his_samples=memory.his_samples(rows),
            # Zoznam toho, čo už povedala, dostával doteraz len sudca — a ten
            # potom prepisoval polovicu odpovedí. Pisateľ ho potrebuje viac.
            her_recent=jej_nedavne,
        )

        # Semi: namiesto odoslania vygeneruj návrhy a pošli majiteľovi na
        # schválenie. Prompt aj kontext sú tie isté ako pri Auto, takže návrhy
        # znejú presne ako ona. Odoslanie prebehne až po kliku (viď
        # `deliver_text`/`deliver_photo`/`deliver_voice`).
        if semi:
            await self._handoff_semi(tg_id, user, system, history, last_user_text)
            return

        try:
            raw = await self._llm.reply(system, history)
        except Exception as exc:  # noqa: BLE001 - správa nesmie zapadnúť
            log.error("%s: model zlyhal (%s) — nechávam na sweeper", tg_id, exc)
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        # Riadok [HLAS: ...] je súhlas modelu poslať odpoveď hlasom. Odchytáva
        # sa hneď z pôvodného znenia — do chatu sa nesmie dostať za žiadnych
        # okolností, ani keď je pokazený.
        hlas_pokyn, raw = speech.parse_directive(raw)
        if hlas_pokyn is not None:
            log.info("%s: model pýta hlasovku %s", tg_id, hlas_pokyn or "(bez detailov)")
        text = self._uprav_odpoved(
            raw, behavior, gap, allow_link, jej_nedavne, he_greeted=pozdravil
        )
        # Sudca — posledná kontrola pred odoslaním. Zlyháva otvorene:
        # keď sa čokoľvek pokazí, odchádza pôvodný návrh.
        # Dostane aj to, čo nedávno napísala — bez toho nemá ako rozoznať, že
        # tú istú vetu už raz použila, a opakovanie je z celého zoznamu chýb
        # tá najčastejšia.
        verdict = await judge.review(
            self._llm,
            text,
            last_user_text,
            fact_sheet,
            [c["claim"] for c in claim_rows],
            [t.label for t in avoid],
            jej_nedavne,
        )
        if verdict["changed"]:
            log.info("%s: sudca opravil odpoveď (%s)", tg_id, verdict["why"])
            text = self._uprav_odpoved(
                verdict["text"], behavior, gap, allow_link, jej_nedavne,
                he_greeted=pozdravil,
            )
            asyncio.create_task(
                self._log_judge(tg_id, verdict["text"], text, verdict["why"])
            )

        chunks = humanize.split_message(text)
        if not chunks:
            log.warning("%s: po vyčistení nezostal text — skúsim znova cez sweeper", tg_id)
            await self._db.update_user(tg_id, {"pending_reply": True})
            return

        # 4) pauza medzi prečítaním a začatím písania
        if quick:
            await asyncio.sleep(quick[1])
        elif not testing:
            await asyncio.sleep(bhv.reply_delay(behavior, factor=factor))

        sent: List[str] = []
        if chosen_photo:
            await self._send_photo(tg_id, chosen_photo)
        chunks = [humanize.strip_archive_marks(c) for c in chunks]
        # Oslovenie a čiarky rieši kód, nie prosba v prompte — model obe
        # pravidlá ignoroval, nech boli napísané akokoľvek dôrazne.
        meno = (user.get("partner_name") or "").strip()
        chunks = [humanize.thin_commas(humanize.enforce_name(c, meno, use_name)) for c in chunks]
        if chosen_voice:
            prepis = chosen_voice.get("transcript") or ""
            pred = len(chunks)
            chunks = [c for c in chunks if c and not humanize.repeats_voice(c, prepis)]
            if len(chunks) != pred:
                log.info("%s: zahodená správa, opakovala obsah hlasovky", tg_id)
        # Zvyšok po delení: v reálnom chate odišla správa, v ktorej bolo samotné
        # „w". Jedno-dve písmená nie sú správa, sú to odrezky.
        chunks = [c for c in chunks if len(c.strip()) > 2 or c.strip() in {"?", "!", "ok", "ye"}]

        # Hlasovka na mieru: prvú správu vie povedať vlastným hlasom, priamo
        # na to, čo napísal. Keď to nevyjde, odíde ako text — nikdy sa nečaká.
        #
        # Rozhoduje o tom model svojím [HLAS: ...]; náhoda je len poistka pre
        # prípad, že by riadok nikdy nenapísal. Zhoda slov, ktorá o hlasovkách
        # rozhodovala pri nahratých súboroch, sem už nepatrí — ten, kto píše
        # odpoveď, jediný vie, či sa hlas do tejto chvíle hodí.
        # Testovacie účty dostávajú výhradne hlasovky — bez ohľadu na to, ako
        # sa model rozhodol. Slúži to na ladenie hlasu, nie na prevádzku.
        len_hlasom = tg_id in self._cfg.voice_only_ids

        # Cudziemu človeku sa hlasovkou nezačína. Kto dostane nahrávku ako
        # jednu z prvých správ, dostane skôr podozrenie než dôkaz — normálne
        # dievča najprv napíše „heyy" a hlas príde až keď je o čom.
        #
        # Jediná výnimka je tá, kvôli ktorej hlasovky vôbec existujú: keď
        # pochybuje, že je skutočná, alebo si nahrávku priamo vypýta. Vtedy je
        # hlas najsilnejší argument, aký má, a čakať na šiestu správu by bola
        # premárnená chvíľa.
        # Výnimky z pravidiel o hlasovkách. Každá sa dá vypnúť v nastaveniach —
        # sú to chvíle, keď je hlas najsilnejší, ale stoja kredity.
        vynimka = speech.exception_reason(
            behavior,
            asked_for_voice=voices_mod.wants_voice(last_user_text),
            doubts_her=humanize.looks_like_ai_question(last_user_text),
            he_voiced=speech.he_sent_voice(last_user_text),
            away=den.busy(dnesny_blok),
            hot_stuck=funnel.hot_and_stuck(user, explicit),
            winding_down=bhv.winding_down(
                now_local, behavior.active_start_min, behavior.active_end_min
            ),
        )
        if vynimka:
            log.info("%s: hlasovka smie mimo pravidiel — %s", tg_id, vynimka)
        pyta_dokaz = bool(vynimka)
        dost_dlho = int(user.get("msg_count") or 0) >= VOICE_MIN_MESSAGES

        # Odstup medzi hlasovkami. Nahratá knižnica ho mala od začiatku, ale
        # generovaná cesta nekontrolovala nič — takže keď si niekto hlasovky
        # pýtal, výnimka `voice_when_asked` sa spustila pri KAŽDEJ odpovedi a
        # nahrávka odchádzala stále dokola. Vyzerá to ako automat a horí to
        # kredity.
        #
        # Jediná výnimka z odstupu je pochybnosť, že je skutočná: tam je hlas
        # jediný argument, aký má, a kázať človeku čakať tri štvrte hodiny by
        # znamenalo prísť oň.
        odstup_ok = voices_mod.generated_cooldown_passed(user) or (
            humanize.looks_like_ai_question(last_user_text)
            and behavior.voice_when_doubted
        )
        if not odstup_ok:
            log.info("%s: hlasovku nepošlem, nedávno jednu dostal", tg_id)

        if (
            chunks
            and media_ok
            and (behavior.voices_enabled or len_hlasom)
            and not cudzi_jazyk
            and not chosen_voice
            and (odstup_ok or len_hlasom)
            and behavior.eleven_key
            and behavior.eleven_voice_id
            and livevoice.worth_speaking(
                chunks[0],
                *(
                    (livevoice.TEST_MIN_CHARS, livevoice.TEST_MAX_CHARS)
                    if len_hlasom
                    else ()
                ),
            )
            # Práve mu jedna zanikla — druhá by dopadla rovnako.
            and not nerozumel
            and (len_hlasom or dost_dlho or pyta_dokaz)
            and (
                len_hlasom
                or pyta_dokaz
                or speech.wants_voice(hlas_pokyn)
                or livevoice.should_speak(
                    chunks[0], chance=float(behavior.voice_chance or 0)
                )
            )
        ):
            kde = speech.ambience_from(
                hlas_pokyn,
                her_recent=jej_nedavne,
                claims=[c["claim"] for c in claim_rows],
                schedule=den.where(dnesny_blok, ""),
                fallback=behavior.voice_ambience or "home",
            )
            # Písaná veta prečítaná nahlas znie čítane, preto sa najprv prepíše
            # do hovorenej podoby. Do chatu aj do pamäte ide pôvodné znenie —
            # tagy ako [laughs] nie sú slová.
            povedane = await speech.to_spoken(
                self._llm, chunks[0], (hlas_pokyn or {}).get("emocia", "")
            )
            nahravka = await livevoice.speak(
                chunks[0], behavior.eleven_key, behavior.eleven_voice_id,
                kde,
                behavior.voice_strength or "rough",
                tempo=speech.tempo_from(hlas_pokyn, float(behavior.voice_tempo or 1.12)),
                level=float(behavior.voice_ambience_level or 0.05),
                spoken=povedane,
                **_voice_ranges(behavior),
            )
            if nahravka:
                povedany_text = chunks[0]
                log.info(
                    "%s: odpoveď posielam hlasom z %s (%s bajtov)",
                    tg_id, kde, len(nahravka),
                )
                await self._send_generated_voice(tg_id, nahravka, povedany_text)
                # Testovaciemu účtu ide len hlas — zvyšok textu by testovanie
                # znejasnil, lebo by nebolo vidieť, čo hlasovka pokryla.
                chunks = [] if len_hlasom else chunks[1:]
                # Archív beží na pozadí — klientovi hlasovka už odišla a čakať
                # na uloženie do úložiska nemá načo.
                asyncio.create_task(
                    self._archive_voice(
                        tg_id, nahravka,
                        text=povedany_text, spoken=povedane,
                        ambience=kde, behavior=behavior,
                    )
                )

        for chunk in chunks:
            async with self._client.action(tg_id, "typing"):
                await asyncio.sleep(humanize.typing_delay(chunk))
            try:
                await self._client.send_message(tg_id, chunk)
            except Exception as exc:  # noqa: BLE001
                # Flood chyba sa nesmie stratiť v logu ako hocijaká iná —
                # z nej vyplýva, že sa má prestať posielať úplne.
                if await self._note_flood(exc, tg_id):
                    await self._db.update_user(tg_id, {"pending_reply": True})
                    return
                raise
            await self._db.add_message(tg_id, "assistant", chunk)
            sent.append(chunk)

        # Hlasovka až PO texte. Prompt jej hovorí napísať pred ňou krátke
        # „one sec“ — pri opačnom poradí pristála veta až za nahrávkou a
        # vyzeralo to ako porucha.
        if chosen_voice:
            await self._send_voice(tg_id, chosen_voice)

        self._reply_times.append(datetime.now(timezone.utc))
        await self._post_send_update(
            user, persona, behavior, " ".join(sent), rows, now_local,
            gag.key if gag else None,
            said_goodnight=len_hlasovka,
            cta_voice=bool(chosen_voice and chosen_voice.get("is_cta")),
        )

    @staticmethod
    def _uprav_odpoved(
        raw: str,
        behavior: Behavior,
        gap: Optional[float],
        allow_link: bool,
        jej_nedavne: List[str],
        he_greeted: bool = False,
    ) -> str:
        """Post-processing, ktorý platí rovnako na návrh aj na opravu sudcu.

        Bolo to napísané dvakrát, takže sa pri každom pridanom pravidle dalo
        zabudnúť na jednu z ciest — a odpoveď, ktorú sudca prepísal, potom
        odišla bez niektorej úpravy.
        """
        # Pozdrav sa odstrelí len v rozbehnutej konverzácii. Keď pozdraví ON,
        # musí sa smieť pozdraviť späť — inak z „hey you 🥰 missed that" ostane
        # klientovi „you 🥰 missed that" a celý rozhovor sa od toho zvrtne.
        text = humanize.sanitize(
            raw, bhv.greeting_allowed(behavior, gap) or he_greeted
        )
        text = humanize.soften_slang(text, behavior.slang)
        # Výkričník vie správu prezradiť rýchlejšie než celá zlá veta —
        # vyzerá ako reklama, nie ako niečo natrieskané do mobilu.
        text = humanize.no_shouting(text)
        # Emoji mala nameraných v 100 % správ, hoci prompt hovorí „občas žiadne“.
        text = humanize.thin_emoji(text, jej_nedavne)
        # Nezačínaj tretíkrát po sebe tým istým slovom („haha" malo 13 %).
        text = humanize.thin_openers(text, jej_nedavne)
        if behavior.no_diacritics:
            text = humanize.strip_diacritics(text)
        if not allow_link:
            text = _strip_urls(text)
        return text

    async def _refresh_after_wait(self, tg_id: int, morning: bool):
        """Znovu načíta stav po pauzách. None = odpoveď sa už nemá poslať.

        Medzi načítaním správ a odoslaním odpovede ubehne bežne pár minút a pri
        dlhej pauze aj tri štvrte hodiny. Za ten čas mohol napísať ďalšie správy,
        Marek mohol konverzáciu prevziať, alebo odpoveď medzitým odišla inou
        cestou. Bez tohto odpovedala na správu spred hodiny, novšie ignorovala —
        a hneď nato na ne poslala druhú odpoveď.

        V debounce ceste to nehrozí (nová správa bežiacu úlohu zruší), ale
        odpoveď zo sweepera nikto nezruší, a tá je práve tá pomalá.
        """
        user = await self._db.get_user(tg_id)
        if not user:
            return None
        if user.get("human_takeover") or not user.get("ai_enabled", True):
            log.info("%s: počas čakania prevzatá alebo vypnutá — nepíšem", tg_id)
            return None
        rows = await self._db.recent_messages(tg_id, self._cfg.context_messages)
        if not rows:
            return None
        if not morning and rows[-1].get("role") == "assistant":
            log.info("%s: počas čakania už odpoveď odišla — nepíšem druhú", tg_id)
            await self._db.update_user(tg_id, {"pending_reply": False})
            return None
        history = memory.to_chat_history(rows)
        last_user_text = next(
            (r["content"] for r in reversed(history) if r["role"] == "user"), ""
        )
        return user, rows, history, last_user_text

    async def _flood_ok(self) -> bool:
        """Smieme teraz vôbec niečo poslať?

        Pamäťové pole je len cache. Zdroj pravdy je `settings.flood_until`,
        lebo pauza musí prežiť deploy aj presun tenanta na inú repliku — inak
        by ju každý reštart zrušil a účet by sa rozbehol priamo do toho, pred
        čím ho pauza chránila. Na Railway sa deployuje často, takže to nie je
        teoretický prípad.
        """
        if self._flood_until is None:
            try:
                ulozene = _parse_ts(await self._db.flood_until())
            except Exception:  # noqa: BLE001 - výpadok DB nesmie umlčať odpovedanie
                log.warning("Flood pauzu sa nepodarilo načítať, beriem to ako bez pauzy")
                return True
            if ulozene is None:
                return True
            self._flood_until = ulozene

        if datetime.now(timezone.utc) >= self._flood_until:
            self._flood_until = None
            try:
                await self._db.set_flood_until(None)
            except Exception:  # noqa: BLE001
                log.warning("Vypršanú flood pauzu sa nepodarilo zmazať z DB")
            return True
        return False

    async def _note_flood(self, exc: Exception, tg_id: Optional[int] = None) -> bool:
        """Spracuje flood chybu od Telegramu. True = bola to ona.

        Telegram pri preťažení sám povie, koľko chce čakať, a to číslo sa má
        rešpektovať — ďalší pokus počas čakania ho len predlžuje. Doteraz tieto
        chyby padali do všeobecného `except`, zapísali sa do logu ako hocičo
        iné a sweeper to o tri minúty skúsil znova. To je presne ten postup,
        ktorým sa z dočasného obmedzenia stane trvalé.
        """
        sekund = limity.flood_pauza_s(exc)
        if sekund is None:
            return False
        teraz = datetime.now(timezone.utc)
        self._flood_until = teraz + timedelta(seconds=sekund)

        # Drobné floody sú včasné varovanie. Jeden nič neznamená, tri za hodinu
        # znamenajú, že účet je na hrane a ďalej ho tlačiť je hazard. Doteraz
        # ich Telethon odspal sám a nikto sa o nich nedozvedel.
        self._flood_events.append(teraz)
        hodina_dozadu = teraz - timedelta(hours=1)
        while self._flood_events and self._flood_events[0] < hodina_dozadu:
            self._flood_events.popleft()
        if len(self._flood_events) >= limity.FLOOD_VAROVANIE_ZA_HODINU:
            log.error(
                "%s: %d flood chýb za poslednú hodinu — účet je na hrane",
                tg_id, len(self._flood_events),
            )
            if self._flood_warned_at is None or self._flood_warned_at < hodina_dozadu:
                self._flood_warned_at = teraz
                await self._notify(
                    f"⚠️ *{len(self._flood_events)} flood chýb za hodinu.* Telegram "
                    "účet pribrzďuje. Zváž zníženie stropu odpovedí za hodinu — "
                    "ďalší krok býva PeerFlood, a ten už stojí 24 h ticha."
                )

        # Do DB, nie do pamäte: reštart ani presun tenanta pauzu nesmie zrušiť.
        # Zapisuje sa pri KAŽDEJ flood chybe, nielen pri spam príznaku —
        # päťsekundový FloodWait tesne pred deployom je inak stratený.
        try:
            await self._db.set_flood_until(self._flood_until.isoformat())
        except Exception:  # noqa: BLE001
            log.exception("Flood pauzu sa nepodarilo zapísať do DB")

        if limity.je_spam_priznak(exc):
            # Toto je najvážnejšia odpoveď, akú Telegram dá: účet je označený
            # za rozposielača. Písať ďalej znamená prísť oň.
            log.error("%s: PeerFloodError — účet je označený za spam, zastavujem", tg_id)
            await self._notify(
                "🚨 *Telegram označil účet za rozposielanie* (PeerFloodError).\n"
                "Zastavil som odpovedanie na 24 hodín. Túto pauzu nezruší ani "
                "prepnutie režimu — píš z účtu chvíľu ručne a len ľuďom, ktorí "
                "napísali prví."
            )
            return True
        log.warning("%s: FloodWait %s s — do %s nič neposielam",
                    tg_id, sekund, self._flood_until.strftime("%H:%M:%S"))
        if sekund >= limity.HLASIT_NAD_S:
            await self._notify(
                f"⏳ Telegram pýta pauzu {sekund // 60} min (FloodWait). "
                "Odpovede počkajú a dobehnú potom."
            )
        return True

    async def _link_quota_ok(self, behavior: Behavior) -> bool:
        """Globálny strop odkazov za hodinu — naprieč všetkými konverzáciami.

        Marek nechce, aby z účtu odchádzalo veľa odkazov: pár za hodinu, každý
        niekomu inému. Počíta sa z DB, takže to prežije restart.
        """
        if behavior.max_links_per_hour <= 0:
            return False
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        try:
            sent = await self._db.links_sent_since(since)
        except Exception as exc:  # noqa: BLE001 - pri chybe radšej nepošli
            log.warning("Nepodarilo sa zistiť počet odkazov za hodinu: %s", exc)
            return False
        return sent < behavior.max_links_per_hour

    async def _close_session(self, tg_id: int, force: bool = False) -> None:
        """Ak predošlé sedenie skončilo, zapíš ho ako epizódu.

        `force` používa nočné upratovanie: tam už o uzavretí sedenia rozhodla
        databáza podľa času poslednej správy, takže sa to nemusí zisťovať
        druhýkrát z okna správ.
        """
        try:
            rows = await self._db.recent_messages(tg_id, 60)
            if not force and not recall.session_closed(rows):
                return
            persona = await self._db.get_persona()
            zapisane = await recall.write_episode(
                self._llm, self._db, tg_id, rows, persona.get("name") or "Ona"
            )
            if zapisane:
                await self._db.update_user(tg_id, {"episode_at": _utc_iso()})
        except Exception as exc:  # noqa: BLE001
            log.warning("Epizóda pre %s zlyhala: %s", tg_id, exc)

    async def _close_stale_sessions(self) -> None:
        """Dopíše epizódy za sedenia, po ktorých sa už nikto neozval.

        `_close_session` visí na prijatej správe, takže sedenie sa zapísalo len
        vtedy, keď človek po dlhom tichu napísal znova. Kto sa neozval, o tom
        nebolo nič — a to je väčšina. Beží to mimo aktívneho okna, kde aj tak
        nikto nečaká na odpoveď.
        """
        try:
            cakaju = await self._db.sessions_to_close(
                gap_hours=recall.SESSION_GAP_H, limit=5
            )
        except Exception as exc:  # noqa: BLE001 - upratovanie nie je kritické
            log.warning("Nedokončené sedenia sa nepodarilo načítať: %s", exc)
            return
        for user in cakaju:
            tg_id = user["tg_id"]
            log.info("%s: dopisujem epizódu za doznené sedenie", tg_id)
            await self._close_session(tg_id, force=True)

    async def _log_judge(self, tg_id: int, draft: str, fixed: str, why: str) -> None:
        try:
            await self._db.log_judge(tg_id, draft, fixed, why)
        except Exception as exc:  # noqa: BLE001
            log.warning("Zápis zásahu sudcu zlyhal: %s", exc)

    async def _remember(self, tg_id: int, her_name: str) -> None:
        """Zápis do pamäte na pozadí: fakty, sľuby, a epizóda po sedení.

        Nikdy nesmie pridať latenciu do cesty odpovede ani ju zhodiť.
        """
        await self._extract_facts(tg_id, her_name)
        try:
            rows = await self._db.recent_messages(tg_id, 40)
            await recall.sync_loops(self._llm, self._db, tg_id, rows[-10:], her_name)
            await judge.sync_claims(self._llm, self._db, tg_id, rows[-12:], her_name)
        except Exception as exc:  # noqa: BLE001
            log.warning("Sľuby pre %s zlyhali: %s", tg_id, exc)

    async def _extract_facts(self, tg_id: int, her_name: str) -> None:
        """Vytiahne nové fakty z posledných správ. Zlyhá potichu."""
        try:
            rows = await self._db.recent_messages(tg_id, 8)
            found = await facts.extract(self._llm, rows, her_name)
            if not found:
                return
            existing = await self._db.facts_for(tg_id)
            plan = facts.merge_plan(existing, found)
            if plan["inserts"] or plan["confirms"] or plan["supersedes"]:
                await self._db.apply_facts(tg_id, plan)
                log.info(
                    "%s: fakty +%s ~%s ↓%s",
                    tg_id, len(plan["inserts"]), len(plan["confirms"]), len(plan["supersedes"]),
                )
        except Exception as exc:  # noqa: BLE001 - nikdy nesmie zhodiť odpoveď
            log.warning("Extrakcia faktov pre %s zlyhala: %s", tg_id, exc)

    async def _look_at_photo(self, event: events.NewMessage.Event) -> str:
        """Nechá vision model pozrieť sa na prijatú fotku.

        Hlavný model obrázky neprijíma, takže popis ide do histórie ako text
        a on naň reaguje v postave. Príznak explicitnosti riadi, či ho pošle
        na platformu.
        """
        try:
            data = await event.download_media(bytes)
        except Exception as exc:  # noqa: BLE001
            log.warning("Prijatú fotku sa nepodarilo stiahnuť: %s", exc)
            return "[poslal fotku]"
        if not data:
            return "[poslal fotku]"

        seen = await self._llm.describe_image(data)
        description = seen.get("description") or "fotku"
        if seen.get("explicit"):
            return f"[poslal EXPLICITNÚ fotku: {description}]"
        return f"[poslal fotku: {description}]"

    async def _pick_photo(
        self,
        user: Dict[str, Any],
        now_local: datetime,
        explicit: bool,
        reason: str,
        schedule_folder: str,
    ) -> Optional[Dict[str, Any]]:
        """Vyberie fotku podľa albumovej logiky. None = neposiela sa.

        Album sa v chate použije najviac raz; druhá fotka z toho istého smie
        odísť len do 30 min a len keď si ju vypýta alebo pochybuje.
        """
        tg_id = user["tg_id"]
        # Cooldown na VLASTNÚ iniciatívu (first). Vyžiadanú fotku (asked/proof)
        # neblokuje — na „pošli ešte jednu" sa čakať 45 min nedá.
        if reason == "first" and not photos.cooldown_passed(user, 45):
            log.info("%s: fotka (first) — nedávno jednu dostal", tg_id)
            return None
        try:
            library = await self._db.photo_library()
            seen = await self._db.photos_sent_to(tg_id)
        except Exception as exc:  # noqa: BLE001 - bez fotky sa dá odpovedať
            log.warning("Fotoknižnicu sa nepodarilo načítať: %s", exc)
            return None
        if not library:
            log.info("%s: fotka (%s) — žiadne albumy nie sú naplnené", tg_id, reason)
            return None

        # Knižnica sa vyčerpáva (každá fotka raz). Keď dôjde, `pick` ticho vráti
        # None — hlásime skôr, než sa tak stane.
        await self._warn_low_library(tg_id, photos.remaining(library, seen))

        photo = photos.pick(
            library,
            seen,
            schedule_folder,
            reason,
            open_folder=photos.last_folder(library, seen),
            can_reopen=photos.window_open(user),
            prefer_spicy=explicit,
        )
        if not photo:
            log.info(
                "%s: fotka (%s) — album %s prázdny/použitý alebo už všetko videl",
                tg_id, reason, schedule_folder,
            )
            return None
        log.info(
            "%s: posielam fotku #%s [%s] — dôvod %s",
            tg_id, photo["id"], photo.get("folder"), reason,
        )
        return photo

    async def _warn_low_library(self, tg_id: int, zostava: int) -> None:
        """Ozve sa, keď tomuto človeku dochádzajú nevidené fotky.

        Nie častejšie než raz za hodinu a len raz na prah — inak by z jednej
        prázdnej knižnice bola pri každej správe ďalšia notifikácia.
        """
        if zostava > PHOTO_LOW_MARK:
            return
        teraz = datetime.now(timezone.utc)
        naposledy = self._library_warned.get(tg_id)
        if naposledy and teraz - naposledy < timedelta(hours=1):
            return
        self._library_warned[tg_id] = teraz
        if zostava <= 0:
            log.warning("%s: videl už všetky fotky, ďalšie neprídu", tg_id)
            await self._notify(
                f"📷 `{tg_id}` už videl VŠETKY fotky — ďalšie mu neprídu. "
                "Doplň knižnicu v dashboarde."
            )
        else:
            log.info("%s: v knižnici zostávajú %s nevidené fotky", tg_id, zostava)
            await self._notify(
                f"📷 `{tg_id}` má už len {zostava} nevidené fotky. Doplň knižnicu."
            )

    async def _send_photo(self, tg_id: int, photo: Dict[str, Any]) -> None:
        data = await _download(photo["url"])
        if not data:
            return
        try:
            async with self._client.action(tg_id, "photo"):
                await asyncio.sleep(humanize.typing_delay("x" * 40))
            # Čisté bajty by Telethon poslal ako dokument bez názvu — príjemcovi
            # potom pristane súbor, ktorý sa ani nedá otvoriť. Meno s príponou
            # a force_document=False z toho urobia normálnu fotku v bubline.
            buffer = io.BytesIO(data)
            buffer.name = photo_filename(photo["url"])
            await self._client.send_file(tg_id, buffer, force_document=False)
            await self._db.record_photo_send(int(photo["id"]), tg_id)
            await self._db.update_user(tg_id, {"last_photo_at": _utc_iso()})
            await self._db.add_message(
                tg_id, "assistant", f"[poslala fotku: {photo.get('caption') or 'selfie'}]"
            )
            # Az TERAZ — fotka naozaj odisla. Ucet za nedorucenu fotku by bol
            # najhorsi druh polozky na fakture.
            await self._llm.charge_unit("photo", "photo_usd", 0.10)
        except Exception as exc:  # noqa: BLE001 - fotka nesmie zhodiť odpoveď
            # Flood MUSÍ prejsť cez `_note_flood`, inak by fotka do spam-flagu
            # ochranu vôbec nespustila a sweeper by to o tri minúty skúsil znova.
            await self._note_flood(exc, tg_id)
            log.warning("Fotku sa nepodarilo poslať %s: %s", tg_id, exc)

    async def _defer(self, tg_id: int, seconds: float) -> None:
        """Zapíše do DB, že odpoveď má prísť až za `seconds`.

        Bez `reply_after` by po restarte sweeper odpísal do troch minút, aj keď
        mala ešte pol hodiny mlčať. Takto ju restart nezrýchli ani nezruší —
        odpoveď dobehne presne vtedy, kedy mala.
        """
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        await self._db.update_user(
            tg_id, {"pending_reply": True, "reply_after": until.isoformat()}
        )

    async def _pick_voice(self, tg_id, text, part, wants_cta):
        try:
            library = await self._db.voice_library()
            if not library:
                return None
            seen = await self._db.voices_sent_to(tg_id)
        except Exception as exc:  # noqa: BLE001 - bez hlasovky sa dá odpovedať
            log.warning("Hlasovky sa nepodarilo načítať: %s", exc)
            return None
        voice = voices_mod.pick(library, seen, text, part, wants_cta=wants_cta)
        if voice:
            log.info("%s: posielam hlasovku #%s", tg_id, voice["id"])
        return voice

    async def _archive_voice(
        self,
        tg_id: Optional[int],
        data: bytes,
        text: str,
        spoken: str,
        ambience: str,
        behavior: Behavior,
        kind: str = "reply",
        strength: str = "",
        tempo: float = 0.0,
        voice_id: str = "",
    ) -> str:
        """Odloží vyrobenú hlasovku do úložiska a zapíše ju do archívu.

        Dnes preto, aby si ich Marek vedel v dashboarde vypočuť a doladiť
        podľa nich zvuk. Neskôr preto, že z nich bude zásoba — keď ich budú
        stovky, dá sa siahnuť po hotovej namiesto vyrábania novej.

        `strength`, `tempo` a `voice_id` sú tu preto, že ukážka z dashboardu
        smie mať iné nastavenie než uložené — klient si v štúdiu posunie
        posuvník a chce počuť práve to. Bez nich by sa do archívu zapísalo
        uložené nastavenie a v zozname ukážok by pri každej stálo to isté,
        hoci znejú inak. Prázdne = plati, čo je uložené (ostrá hlasovka).

        Zlyhanie sa ticho prehltne: hlasovka klientovi už odišla.
        """
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            cesta = f"{self._cfg.supabase_schema}/generated/{stamp}-{tg_id or 'ukazka'}.ogg"
            url = await self._db.upload_voice(cesta, data)
            await self._db.add_voice_clip(
                {
                    "tg_id": tg_id,
                    "text": text[:600],
                    "spoken": (spoken or "")[:600],
                    "ambience": ambience,
                    "strength": strength or behavior.voice_strength or "rough",
                    "tempo": float(tempo or behavior.voice_tempo or 1.12),
                    "voice_id": voice_id or behavior.eleven_voice_id or "",
                    "url": url,
                    "bytes": len(data),
                    "kind": kind,
                }
            )
            return url
        except Exception as exc:  # noqa: BLE001 - archív nikdy nesmie prekážať
            log.warning("Hlasovku sa nepodarilo archivovať: %s", exc)
            return ""

    async def _voice_jobs_once(self) -> None:
        """Vyrobí ukážku, o ktorú si požiadal dashboard.

        Worker na Railway nemá port, takže si dashboard nemá kam zavolať —
        požiadavka preto chodí riadkom v databáze. Ukážka ide tým istým
        reťazcom ako ostrá hlasovka, takže čo Marek počuje pri ladení, to
        presne dostane aj klient.

        UKÁŽKA SA NIKOMU NEPOSIELA. Nikde tu nie je `send_file` ani `tg_id` —
        hotový súbor pristane v úložisku a v archíve (`kind="preview"`,
        `tg_id=None`) a tam to končí. Fanúšik o nej nevie.
        """
        try:
            job = await self._db.pending_voice_job()
            if not job:
                return
            if not await self._db.claim_voice_job(int(job["id"])):
                return  # vzal si ju iný beh
        except Exception as exc:  # noqa: BLE001 - fronta je bonus
            log.warning("Frontu ukážok sa nepodarilo prečítať: %s", exc)
            return

        behavior = await self._behavior()
        text = (job.get("text") or "").strip()

        # Čo naozaj zaznie: hodnota z práce, inak uložená. Vypočíta sa RAZ a
        # použije sa dvakrát — pri výrobe aj pri zápise do archívu. Kým sa to
        # počítalo na dvoch miestach, do archívu šlo uložené nastavenie, aj
        # keď ukážka znela podľa posunutého posuvníka, a zoznam ukážok potom
        # o všetkých tvrdil to isté.
        kluc = job.get("eleven_key") or behavior.eleven_key
        hlas_id = job.get("voice_id") or behavior.eleven_voice_id
        izba = job.get("ambience") or behavior.voice_ambience or "home"
        sila = job.get("strength") or behavior.voice_strength or "rough"
        tempo = float(job.get("tempo") or behavior.voice_tempo or 1.12)
        hlasitost = float(
            job.get("ambience_level") or behavior.voice_ambience_level or 0.05
        )

        # Bez kľúča alebo bez hlasu `speak()` vráti prázdno hneď na prvom
        # riadku a nič viac sa nedozvieme. Rozlíšiť to treba TU, kým sú obe
        # hodnoty po ruke — inak dashboard ukáže „nepodarilo sa" na niečo,
        # čo je jeden preklik.
        if not kluc:
            await self._db.finish_voice_job(int(job["id"]), error=VOICE_JOB_NO_KEY)
            return
        if not hlas_id:
            await self._db.finish_voice_job(int(job["id"]), error=VOICE_JOB_NO_VOICE)
            return

        try:
            povedane = await speech.to_spoken(self._llm, text)
            # Rozsahy idú z uloženého chovania, nie z práce: ukážka má znieť
            # presne ako hlasovka, ktorá odíde fanúšikovi — vrátane ticha na
            # okrajoch a vylosovanej hlasitosti. Preto tu NIE JE nič pevné.
            data = await livevoice.speak(
                text, kluc, hlas_id, izba, sila,
                tempo=tempo, level=hlasitost, spoken=povedane,
                **_voice_ranges(behavior),
            )
            if not data:
                await self._db.finish_voice_job(
                    int(job["id"]), error=VOICE_JOB_NO_AUDIO
                )
                return
            url = await self._archive_voice(
                None, data, text=text, spoken=povedane, ambience=izba,
                behavior=behavior, kind="preview",
                strength=sila, tempo=tempo, voice_id=hlas_id,
            )
            await self._db.finish_voice_job(int(job["id"]), url=url)
            log.info("Ukážka hlasovky #%s hotová (%s bajtov)", job["id"], len(data))
        except Exception as exc:  # noqa: BLE001
            log.warning("Ukážka #%s zlyhala: %s", job.get("id"), exc)
            try:
                await self._db.finish_voice_job(int(job["id"]), error=str(exc))
            except Exception:  # noqa: BLE001
                pass

    async def _send_generated_voice(self, tg_id: int, data: bytes, text: str) -> None:
        """Pošle nahrávku vyrobenú na mieru a do pamäte ju uloží ako jej slová."""
        try:
            async with self._client.action(tg_id, "record-voice"):
                await asyncio.sleep(random.uniform(3, 10))
            prevedene = await _to_opus(data) or data
            buffer = io.BytesIO(prevedene)
            buffer.name = "voice.ogg"
            await self._client.send_file(tg_id, buffer, voice_note=True)
            await self._db.update_user(tg_id, {"last_voice_at": _utc_iso()})
            await self._db.add_message(tg_id, "assistant", f"(hlasovka) {text}".strip())
            # Cena zavisi od toho, ci sla cez NAS kluc (managed hlas) alebo
            # klientov — pri jeho kluci nam ElevenLabs nic neuctuje.
            managed = (await self._behavior()).voice_source == "managed"
            await self._llm.charge_unit(
                "voice",
                "voice_managed_usd" if managed else "voice_own_usd",
                0.50 if managed else 0.30,
            )
        except Exception as exc:  # noqa: BLE001 - odpoveď nesmie zapadnúť
            log.warning("Hlasovku na mieru sa nepodarilo poslať %s: %s", tg_id, exc)
            # Náhrada textom má zmysel pri pokazenom súbore či prevode. Pri
            # floode je to ale okamžitý opakovaný pokus na ten istý účet —
            # presne ten pohyb, ktorým sa z dočasného obmedzenia stane trvalé.
            # Text sa nestratí: človeku ostane `pending_reply` a dobehne, keď
            # pauza vyprší.
            if await self._note_flood(exc, tg_id):
                return
            await self._client.send_message(tg_id, text)
            await self._db.add_message(tg_id, "assistant", text)

    # ---------- semi-auto: handoff a doručovanie po schválení ----------

    def set_control(self, control) -> None:
        """Runner dopĺňa referenciu na control bota (schvaľovacie UI)."""
        self._control = control

    async def _handoff_semi(
        self,
        tg_id: int,
        user: Dict[str, Any],
        system: str,
        history: List[Dict[str, str]],
        last_user_text: str,
    ) -> None:
        """Semi: vygeneruj návrhy a pošli majiteľovi kartu na schválenie.
        Supersede starých kariet rieši `control.post_approval`."""
        if not self._control:
            # Bez kontrolného bota niet ako schvaľovať — nechaj čakať sweeperu.
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        try:
            suggestions = await self._llm.suggest(system, history)
        except Exception as exc:  # noqa: BLE001
            log.error("%s: návrhy zlyhali (%s) — nechávam na sweeper", tg_id, exc)
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        if not suggestions:
            await self._db.update_user(tg_id, {"pending_reply": True})
            return
        name = (user.get("partner_name") or "").strip() or str(tg_id)
        ok = await self._control.post_approval(
            channel="telegram",
            conv_key=str(tg_id),
            display_name=name,
            incoming_preview=last_user_text,
            suggestions=suggestions,
        )
        # Karta drží pending; dm_users.pending_reply nech sweeper znovu nespustí.
        await self._db.update_user(tg_id, {"pending_reply": not ok})

    async def _semi_post_update(self, tg_id: int, text: str) -> None:
        """Po schválenom odoslaní dorob plný kontext-update (pamäť, summary,
        funnel), nech persóna nadväzuje aj po prepnutí späť na Auto."""
        try:
            user = await self._db.get_user(tg_id)
            if not user:
                return
            persona = await self._db.get_persona()
            behavior = Behavior.from_row(await self._db.get_behavior())
            rows = await self._db.recent_messages(tg_id, self._cfg.context_messages)
            now_local = datetime.now(ZoneInfo(behavior.active_tz))
            await self._post_send_update(user, persona, behavior, text, rows, now_local)
        except Exception as exc:  # noqa: BLE001 - odoslané už je, stav dorovnaj aspoň hrubo
            log.warning("%s: semi post-update zlyhal (%s)", tg_id, exc)
            await self._db.update_user(
                tg_id, {"pending_reply": False, "last_reply_at": _utc_iso()}
            )

    async def deliver_text(self, conv_key: str, text: str) -> bool:
        """Odošle schválený text ako ona, uloží ho do pamäte, dorovná stav."""
        tg_id = int(conv_key)
        try:
            async with self._client.action(tg_id, "typing"):
                await asyncio.sleep(humanize.typing_delay(text))
            await self._client.send_message(tg_id, text)
        except Exception as exc:  # noqa: BLE001
            if await self._note_flood(exc, tg_id):
                return False
            log.warning("%s: schválený text neodišiel (%s)", tg_id, exc)
            return False
        await self._db.add_message(tg_id, "assistant", text)
        self._reply_times.append(datetime.now(timezone.utc))
        await self._semi_post_update(tg_id, text)
        return True

    async def photo_folders(self, conv_key: str) -> List[Dict[str, str]]:
        """Telegram nemá priečinky — jedna zložka so všetkými aktívnymi fotkami."""
        return [{"id": "all", "label": "Fotky"}]

    async def photo_items(self, conv_key: str, folder_id: str) -> List[Dict[str, Any]]:
        lib = await self._db.photo_library()
        return [
            {
                "ref": str(p["id"]),
                "url": p.get("url"),
                "caption": p.get("caption") or p.get("situation") or "",
            }
            for p in lib
            if p.get("active", True)
        ]

    async def suggest_caption(self, conv_key: str) -> List[str]:
        """Krátke popisy k fotke na výber. Bez ťažkého promptu — pár univerzálnych."""
        return ["just for you 🙈", "thinking of you 😏", "hope you like it 💋"]

    async def deliver_photo(
        self, conv_key: str, media_ref: str, caption: str, price_cents=None
    ) -> bool:
        """Odošle vybranú fotku (Telegram = vždy zadarmo) s popisom."""
        tg_id = int(conv_key)
        lib = await self._db.photo_library()
        photo = next((p for p in lib if str(p["id"]) == str(media_ref)), None)
        if not photo:
            return False
        data = await _download(photo["url"])
        if not data:
            return False
        try:
            buffer = io.BytesIO(data)
            buffer.name = photo_filename(photo["url"])
            async with self._client.action(tg_id, "photo"):
                await asyncio.sleep(humanize.typing_delay("x" * 40))
            await self._client.send_file(
                tg_id, buffer, caption=caption or "", force_document=False
            )
            await self._db.record_photo_send(int(photo["id"]), tg_id)
            await self._db.update_user(tg_id, {"last_photo_at": _utc_iso()})
            marker = f"[poslala fotku: {caption or photo.get('caption') or 'selfie'}]"
            await self._db.add_message(tg_id, "assistant", marker)
        except Exception as exc:  # noqa: BLE001
            if await self._note_flood(exc, tg_id):
                return False
            log.warning("%s: schválenú fotku sa nepodarilo poslať (%s)", tg_id, exc)
            return False
        await self._semi_post_update(tg_id, caption or "[fotka]")
        return True

    async def generate_voice_preview(self, text: str):
        """Vyrobí ogg na vypočutie majiteľovi. None = chýba kľúč/hlas alebo zlyhalo."""
        behavior = Behavior.from_row(await self._db.get_behavior())
        if not (behavior.eleven_key and behavior.eleven_voice_id):
            return None
        try:
            spoken = await speech.to_spoken(self._llm, text, "")
            return await livevoice.speak(
                text, behavior.eleven_key, behavior.eleven_voice_id,
                "home", behavior.voice_strength or "rough",
                tempo=float(behavior.voice_tempo or 1.12),
                level=float(behavior.voice_ambience_level or 0.05),
                spoken=spoken, **_voice_ranges(behavior),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Náhľad hlasovky zlyhal: %s", exc)
            return None

    async def deliver_voice(self, conv_key: str, text: str, ogg: bytes) -> bool:
        """Pošle už schválenú (vypočutú) hlasovku fanúšikovi."""
        tg_id = int(conv_key)
        await self._send_generated_voice(tg_id, ogg, text)
        await self._semi_post_update(tg_id, f"(hlasovka) {text}")
        return True

    async def _send_voice(self, tg_id: int, voice: Dict[str, Any]) -> bool:
        """Pošle nahrávku ako hlasovku, nie ako súbor s prílohou.

        Vracia, či naozaj odišla. Volajúci to potrebuje vedieť: pri nočnej
        rozlúčke je hlasovka celá správa, takže keď sa nepošle, musí odísť
        aspoň text — inak sa človeku namiesto rozlúčky ozve ticho.
        """
        data = await _download(voice.get("url") or "")
        if not data:
            log.warning(
                "%s: hlasovka #%s sa nedá stiahnuť (url %r) — preskakujem ju",
                tg_id, voice.get("id"), (voice.get("url") or "")[:60],
            )
            return False
        try:
            async with self._client.action(tg_id, "record-voice"):
                await asyncio.sleep(voices_mod.record_seconds(voice))
            if voices_mod.needs_conversion(voice["url"]):
                data = await _to_opus(data) or data
            buffer = io.BytesIO(data)
            buffer.name = "voice.ogg"
            await self._client.send_file(tg_id, buffer, voice_note=True)
            await self._db.record_voice_send(int(voice["id"]), tg_id)
            await self._db.update_user(tg_id, {"last_voice_at": _utc_iso()})
            # Do archívu ide ako jej vlastná reč. Vďaka tomu si o pár správ
            # nezopakuje textom to, čo už povedala hlasom — v histórii to vidí
            # ako svoju správu, len s poznámkou, že odznela hlasom.
            await self._db.add_message(
                tg_id,
                "assistant",
                f"(hlasovka) {voice.get('transcript') or ''}".strip(),
            )
            return True
        except Exception as exc:  # noqa: BLE001 - hlasovka nesmie zhodiť odpoveď
            await self._note_flood(exc, tg_id)
            log.warning("Hlasovku sa nepodarilo poslať %s: %s", tg_id, exc)
        return False

    async def _hear_voice(self, event: events.NewMessage.Event) -> str:
        """Prepis hlasovky od klienta. Pri zlyhaní aspoň povie, že nejaká prišla."""
        try:
            data = await event.download_media(bytes)
        except Exception as exc:  # noqa: BLE001
            log.warning("Hlasovku sa nepodarilo stiahnuť: %s", exc)
            return "[poslal hlasovku]"
        # Telegram posiela OGG/Opus, ale audio model berie mp3 — prevedieme.
        mp3 = await _to_mp3(data or b"")
        prepis = await self._llm.transcribe_voice(mp3 or data or b"", "mp3" if mp3 else "ogg")
        if not prepis:
            return "[poslal hlasovku, nebolo jej rozumieť]"
        log.info("Prepis jeho hlasovky: %r", prepis[:80])
        return f"[v hlasovke povedal] {prepis}"

    async def _react_to_photo(self, tg_id: int, msg_id: int, explicit: bool) -> None:
        """Srdiečko na bežnú fotku, plamienok na horúcu."""
        await self._react(tg_id, msg_id, "🔥" if explicit else "❤️", "fotku")

    async def _react(self, tg_id: int, msg_id: int, emoji: str, co: str) -> None:
        """Reakcia priamo na jeho správu — fotku aj text.

        Nie je to odpoveď, len emoji na jeho bubline — príde skôr než text
        a chat vďaka nej pôsobí živo. Zlyhanie sa ticho ignoruje, odpoveď
        odíde tak či tak.
        """
        if not msg_id:
            return
        try:
            await asyncio.sleep(random.uniform(3, 15))
            await self._client(
                SendReactionRequest(
                    peer=await self._client.get_input_entity(tg_id),
                    msg_id=msg_id,
                    reaction=[ReactionEmoji(emoticon=emoji)],
                )
            )
            log.info("%s: reakcia %s na %s", tg_id, emoji, co)
        except Exception as exc:  # noqa: BLE001 - reakcia je bonus, nie povinnosť
            log.warning("%s: reakciu na %s sa nepodarilo dať: %s", tg_id, co, exc)

    async def _refresh_blocked(self, force: bool = False) -> None:
        """Načíta zoznam zablokovaných z Telegramu.

        Blokovaný človek sa väčšinou k účtu vôbec nedostane, ale keď ho Marek
        zablokuje až po tom, čo napísal, správa už v databáze leží — a bez tejto
        kontroly by mu sweeper odpísal.
        """
        teraz = datetime.now(timezone.utc)
        if not force and self._blocked_at and teraz - self._blocked_at < timedelta(minutes=10):
            return
        try:
            result = await self._client(GetBlockedRequest(offset=0, limit=200))
            self._blocked = frozenset(u.id for u in getattr(result, "users", []))
            self._blocked_at = teraz
            if self._blocked:
                log.info("Zablokovaných účtov: %s", len(self._blocked))
        except Exception as exc:  # noqa: BLE001 - bez zoznamu radšej pokračuj
            log.warning("Zoznam zablokovaných sa nepodarilo načítať: %s", exc)

    async def _mark_read(self, tg_id: int) -> None:
        """Bez toho ostane v chate „neprečítané“ a vyzerá to mŕtvo."""
        try:
            await self._client.send_read_acknowledge(tg_id)
        except Exception as exc:  # noqa: BLE001 - nesmie zablokovať odpoveď
            log.warning("Nepodarilo sa označiť ako prečítané pre %s: %s", tg_id, exc)

    async def _post_send_update(
        self,
        user: Dict[str, Any],
        persona: Dict[str, Any],
        behavior: Behavior,
        sent_text: str,
        rows: List[Dict[str, Any]],
        now_local: datetime,
        gag_used: Optional[str] = None,
        said_goodnight: bool = False,
        cta_voice: bool = False,
    ) -> None:
        tg_id = user["tg_id"]
        patch: Dict[str, Any] = {
            "pending_reply": False,
            "last_reply_at": _utc_iso(),
            "reply_after": None,
        }

        # Povedala dobrú noc na konci dňa → mlčí do ďalšieho cyklu.
        # Rozlúčka mohla odznieť hlasovkou — vtedy je text prázdny a podľa neho
        # by sa nočný zámok nikdy nechytil.
        sleep_until = (
            None
            if self._is_test_account(tg_id)
            else bhv.should_sleep_until_morning(
                now_local, behavior, "good night" if said_goodnight else sent_text
            )
        )
        if sleep_until:
            patch["reply_after"] = sleep_until.astimezone(timezone.utc).isoformat()
            log.info(
                "%s: rozlúčila sa na noc, ďalšia odpoveď najskôr %s miestneho času",
                tg_id,
                sleep_until.strftime("%H:%M"),
            )

        if funnel.asks_for_name(sent_text) and not user.get("name_asked"):
            patch["name_asked"] = True

        if gag_used:
            patch["used_gags"] = gags.record(
                user.get("used_gags"), gag_used, datetime.now(timezone.utc)
            )

        opened = topics.detect_asked(sent_text)
        if opened:
            patch["asked_topics"] = topics.record(
                user.get("asked_topics"), opened, datetime.now(timezone.utc)
            )
            log.info("%s: zapísané témy %s", tg_id, opened)

        style_note = memory.describe_style(rows)
        if style_note and style_note != (user.get("style_note") or ""):
            patch["style_note"] = style_note

        link = persona.get("cta_link") or ""
        # Pozvánka hlasom je ten istý krok ako poslať odkaz — inak by
        # obchádzala cooldown aj strop pushov a chodila donekonečna.
        if cta_voice or (link and humanize.contains_link(sent_text, link)):
            patch["link_sent_at"] = _utc_iso()
            patch["link_push_count"] = int(user.get("link_push_count") or 0) + 1
            patch["funnel_stage"] = funnel.stage_after_link(user)
            await self._notify(
                f"🔗 Odkaz poslaný — {_who(user)} (`{tg_id}`), {patch['link_push_count']}. push"
            )
        await self._db.update_user(tg_id, patch)

        user.update(patch)
        # Extrakcia beží NA POZADÍ — nesmie pridať ani sekundu do cesty odpovede.
        asyncio.create_task(self._remember(tg_id, persona.get("name") or "Ona"))

        every = int(getattr(behavior, "summary_every", 0) or self._cfg.summary_every)
        if memory.needs_summary(user, every):
            try:
                sheet = facts.sheet(await self._db.facts_for(tg_id))
            except Exception:  # noqa: BLE001
                sheet = ""
            await memory.refresh_summary(
                self._db,
                self._llm,
                user,
                persona.get("name") or "Ona",
                every * 4,
                sheet,
            )

    # ---------- rate limit a sweeper ----------

    async def _rate_left(self, max_per_hour: int) -> int:
        """Koľko odpovedí ešte za túto hodinu smie odísť.

        Čítač v pamäti je presný (jedna odpoveď = jeden záznam), ale po deployi
        je prázdny — strop sa tak dal reštartom vynulovať a prekročiť násobne,
        a práve prekročený strop je to, na čo Telegram reaguje. Preto sa berie
        aj z archívu. Ten počíta odoslané SPRÁVY, a keďže sa odpoveď delí až na
        tri bubliny, má vlastný, voľnejší strop.
        """
        # 0 = strop vypnutý, rovnako ako pri `max_active_chats` a
        # `max_outreach_per_hour`. Doteraz tu nula znamenala pravý opak — účet
        # onemel navždy — a je to klientsky editovateľné tlačidlo v control
        # bote. Kto ho nastavil na nulu v domnení „bez limitu", umlčal modelku
        # a nemal ako zistiť prečo.
        if max_per_hour <= 0:
            return _BEZ_LIMITU

        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        while self._reply_times and self._reply_times[0] < cutoff:
            self._reply_times.popleft()
        volno = max_per_hour - len(self._reply_times)
        if volno <= 0:
            return 0
        try:
            odoslanych = await self._db.replies_since(cutoff.isoformat())
        except Exception as exc:  # noqa: BLE001
            # Pamäť je po deployi prázdna, takže „drž sa pamäte" znamenalo
            # pustiť plný hodinový strop bez overenia — a to práve vtedy, keď
            # je DB v problémoch, čiže typicky počas deployu. Radšej chvíľu
            # neodpisovať: `pending_reply` ostáva a sweeper to o tri minúty
            # skúsi znova. Aj tak by sa odpoveď nemala kam zapísať.
            log.warning("Počet odoslaných správ za hodinu sa nezistil (%s) — brzdím", exc)
            await self._varuj_o_slepote(exc)
            return 0
        z_archivu = max_per_hour * _MAX_CHUNKS - odoslanych
        return max(min(volno, z_archivu), 0)

    async def _rate_ok(self, max_per_hour: int) -> bool:
        return await self._rate_left(max_per_hour) > 0

    def _rozbeh(self) -> float:
        """Akú časť stropov smie tento účet dnes využiť (rozbeh nového čísla)."""
        pripojene = _parse_ts(self._cfg.tg_connected_at or None)
        if pripojene is None:
            return 1.0
        hodin = (datetime.now(timezone.utc) - pripojene).total_seconds() / 3600
        return limity.rozbeh_podiel(hodin)

    async def _denny_strop_ok(self, behavior: Behavior, podiel: float = 1.0) -> bool:
        """Zmestí sa ešte dnes ďalšia správa?

        Hodinový strop sám nestačí: pri 40/hod a 14-hodinovom okne prejde za deň
        až 560 správ, lebo kĺzavé okno sa stále obnovuje. Telegram ale nesleduje
        hodinu, sleduje účet. Preto druhý strop na 24 hodín.

        Počítajú sa ODOSLANÉ SPRÁVY, nie odpovede — jedna odpoveď sa delí až na
        tri bubliny a Telegram vidí každú zvlášť.
        """
        strop = limity.s_rozbehom(behavior.max_messages_per_day, podiel)
        if strop <= 0:
            return True  # 0 = strop vypnutý
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        try:
            odoslanych = await self._db.replies_since(cutoff)
        except Exception as exc:  # noqa: BLE001 - rovnako ako hodinový: radšej brzdi
            log.warning("Denný strop sa nedá overiť (%s) — brzdím", exc)
            await self._varuj_o_slepote(exc)
            return False
        if odoslanych >= strop:
            log.warning("Denný strop vyčerpaný: %s/%s správ za 24 h", odoslanych, strop)
            return False
        return True

    async def _varuj_o_slepote(self, exc: Exception) -> None:
        """Keď limity nevedia čítať z DB, modelka mlčí — a to musí byť vidieť.

        Zlyhávať zatvorene je správne, ale bez tohto by dlhší výpadok znamenal
        ticho, ktoré sa prejaví až tým, že nikto neodpisuje. Ozveme sa najviac
        raz za hodinu, nech z toho nie je vodopád správ.
        """
        teraz = datetime.now(timezone.utc)
        if (
            self._slepota_warned_at is not None
            and teraz - self._slepota_warned_at < timedelta(hours=1)
        ):
            return
        self._slepota_warned_at = teraz
        await self._notify(
            "⚠️ *Nedostanem sa k limitom v databáze*, takže radšej neodpisujem "
            f"(`{type(exc).__name__}`). Správy sa nestrácajú a dobehnú, len čo "
            "sa spojenie obnoví."
        )

    async def _oslovenych_za_obdobie(self, hodin: int) -> Optional[set]:
        """Komu za posledných `hodin` odišla správa. `None` = nevieme."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hodin)).isoformat()
        try:
            return limity.uz_oslovenych(await self._db.people_since(cutoff))
        except Exception as exc:  # noqa: BLE001
            log.warning("Nepodarilo sa zistiť, komu sa písalo za %s h: %s", hodin, exc)
            return None

    async def _oslovenych_za_hodinu(self) -> Optional[set]:
        """Komu za poslednú hodinu odišla správa. Počíta sa z archívu.

        Nie z pamäte procesu: po deployi je prázdna, a práve vtedy by sa strop
        dal obísť reštartom.

        `None` = nevieme. Prázdna množina by znamenala „nikomu sa nepísalo",
        čiže by strop ticho VYPLA — a to práve v momente výpadku DB, ktorý
        typicky nastane počas deployu, teda vtedy, keď je pohybu najviac.
        Volajúci má z `None` spraviť „nesmie", nie „smie".
        """
        return await self._oslovenych_za_obdobie(hodin=1)

    async def _aktivne_rozhovory(self, behavior: Behavior) -> Optional[set]:
        """Kto práve drží miesto. Počíta sa z DB, takže to prežije restart.

        `None` = nevieme (výpadok DB). Volajúci má vtedy nový rozhovor
        nezačínať — pozri komentár pri `_oslovenych_za_hodinu`.
        """
        if behavior.max_active_chats <= 0:
            return set()
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=behavior.chat_slot_min)
        ).isoformat()
        try:
            return {int(t) for t in await self._db.active_chats(cutoff)}
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Nepodarilo sa zistiť otvorené rozhovory (%s) — nové nezačínam", exc
            )
            return None

    async def _smie_oslovit(self, tg_id: int, behavior: Behavior) -> bool:
        oslovenych = await self._oslovenych_za_hodinu()
        if oslovenych is None:
            return False
        return limity.smie_oslovit(tg_id, oslovenych, behavior.max_outreach_per_hour)

    async def _reply_batch(
        self, tg_ids: List[int], behavior: Behavior, morning: bool = False
    ) -> None:
        """Odpovie viacerým naraz — ale nie všetkým, dávka je sama o sebe stopa.

        Sériový cyklus tu nestačil: `_reply_locked` spí vnútri zámku (kým
        „prečíta“, kým odpíše, občas 20–40 minút pauzy), takže jediný človek
        v dlhej pauze zablokoval celú frontu aj na tri štvrte hodiny. Po
        výpadku sa odpovede rozpúšťali po jednej namiesto toho, aby fronta
        dobehla.
        """
        if not tg_ids:
            return
        semafor = asyncio.Semaphore(_SWEEP_CONCURRENCY)

        async def jeden(tg_id: int) -> None:
            async with semafor:
                # Keď medzitým Telegram vypýtal pauzu, zvyšok dávky sa už
                # nepokúša — inak by každý ďalší pokus čakanie predlžoval.
                if not await self._flood_ok():
                    return
                try:
                    await self.reply_to(tg_id, behavior, morning=morning)
                except Exception as exc:  # noqa: BLE001 - jeden pád nesmie zhodiť frontu
                    if await self._note_flood(exc, tg_id):
                        return
                    log.exception("Odpoveď pre %s zlyhala", tg_id)

        await asyncio.gather(*(jeden(tg_id) for tg_id in tg_ids))

    async def _morning_round(self, behavior: Behavior, now_local: datetime) -> None:
        """Pozdrav na druhý deň — jediný raz, keď píše prvá (`outreach.deserves`).

        Beží len v prvých hodinách cyklu a každému padne jeho vlastný čas
        v rámci okna, aby dávka správ neodišla naraz. Každého pozdraví RAZ,
        deň po prvom kontakte; opakovanie stráži vodoznak `last_outreach_at`.
        Vypína to `morning_enabled` (prepínač v Telegram nastaveniach).
        """
        if not behavior.morning_enabled:
            return
        od_zaciatku = bhv.minutes_since_window_start(
            now_local, behavior.active_start_min, behavior.active_end_min
        )
        if od_zaciatku is None or od_zaciatku > outreach_mod.SPREAD_HOURS * 60:
            return

        try:
            kandidati = await self._db.outreach_candidates()
        except Exception as exc:  # noqa: BLE001 - ranné správy nie sú kritické
            log.warning("Ranných kandidátov sa nepodarilo načítať: %s", exc)
            return

        den = now_local.date().isoformat()
        uplynulo = od_zaciatku * 60
        # Strop sa berie DOPREDU. Keby sa zoznam skracoval až po zápise
        # `last_outreach_at`, odrezaní by mali zapísané, že im ráno odišla
        # správa, ktorá nikdy neodišla — a `deserves` by ich na 20 hodín
        # zablokovalo.
        volno = await self._rate_left(behavior.max_replies_per_hour)
        if volno <= 0:
            return
        # Ranné oslovenie je nevyžiadaná prvá správa, čiže presne to, čo vyzerá
        # ako rozposielanie. Strop na počet rôznych ľudí za hodinu preto platí
        # aj tu — ba práve tu najviac.
        # Denný strop na nových ľudí. Hodinový sám nestačí: šesť za hodinu počas
        # 2,5-hodinového okna je pätnásť, ale keby sa okno raz predĺžilo, rástlo
        # by to s ním. Nevyžiadaná prvá správa je pritom presne to, čo vyzerá
        # ako rozposielanie — tu má strop najväčší zmysel.
        oslovenych_dnes = await self._oslovenych_za_obdobie(hodin=24)
        if oslovenych_dnes is None:
            log.warning("Pozdrav na druhý deň preskočený: nemám denné čísla")
            return
        denny_strop_ludi = limity.s_rozbehom(
            behavior.max_new_people_per_day, self._rozbeh()
        )
        if not limity.smie_oslovit(0, oslovenych_dnes, denny_strop_ludi):
            log.info(
                "Pozdrav na druhý deň: denný strop %s nových ľudí je vyčerpaný",
                denny_strop_ludi,
            )
            return

        oslovenych = await self._oslovenych_za_hodinu()
        if oslovenych is None:
            # Bez čísel sa neoslovuje. Ranné „hey" je nevyžiadaná prvá správa —
            # to je presne tá riziková vec, a poslať ju naslepo je horšie než
            # ju vynechať. Nikto o nič nepríde: `last_outreach_at` sa nezapíše,
            # takže ju dostane v ďalšom cykle.
            log.warning("Pozdrav na druhý deň preskočený: nemám čísla o oslovených")
            return

        vybrati: List[int] = []
        for user in outreach_mod.due(kandidati, now_local, limit=behavior.morning_max_per_day):
            if len(vybrati) >= volno:
                log.info("Pozdrav na druhý deň: hodinový strop, zvyšok počká na ďalší cyklus")
                break
            if not limity.smie_oslovit(
                user["tg_id"], oslovenych, behavior.max_outreach_per_hour
            ):
                log.info(
                    "Pozdrav na druhý deň: za túto hodinu už oslovila %s ľudí, zvyšok počká",
                    behavior.max_outreach_per_hour,
                )
                break
            tg_id = user["tg_id"]
            if outreach_mod.delay_for(tg_id, den) > uplynulo:
                continue  # jeho čas dnes ešte nenastal
            log.info("%s: pozdrav na druhý deň", tg_id)
            # `last_outreach_at` je vodoznak: keď je nastavený, `deserves` už
            # tohto človeka nikdy nevyberie. Jeden pozdrav za celý život
            # konverzácie — preto sa `outreach_silent` už nesleduje.
            await self._db.update_user(tg_id, {"last_outreach_at": _utc_iso()})
            vybrati.append(tg_id)
            oslovenych.add(int(tg_id))
        await self._reply_batch(vybrati, behavior, morning=True)

    async def _tidy_up(self) -> None:
        """Nočné čistenie faktov. Soft-delete: staré sa označia, nikdy nemažú."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
        try:
            rows = await self._db.recent_conversations(50)
        except Exception as exc:  # noqa: BLE001
            log.warning("Nočné čistenie: konverzácie sa nenačítali: %s", exc)
            return
        for user in rows:
            if (user.get("tidied_at") or "") > cutoff:
                continue
            try:
                merged = await self._db.tidy_facts(user["tg_id"])
                if merged:
                    log.info("%s: nočné čistenie zlúčilo %s duplicitných faktov",
                             user["tg_id"], merged)
            except Exception as exc:  # noqa: BLE001
                log.warning("Čistenie %s zlyhalo: %s", user.get("tg_id"), exc)
            return  # jeden za cyklus, nech to nezaťaží databázu

    async def _sweep_loop(self) -> None:
        """Dobehne odložené odpovede (mimo okna, pauza, rate limit, dlhé pauzy)."""
        first = True
        while True:
            # Prvý priechod ide skôr, aby po restarte nikto nečakal tri minúty.
            # Zároveň nie hneď, nech Reconciler dobehne svoje.
            await asyncio.sleep(_SWEEP_FIRST_S if first else _SWEEP_INTERVAL_S)
            first = False
            try:
                await self._sweep_once()
            except Exception:  # noqa: BLE001
                log.exception("Sweeper zlyhal")

    async def _sweep_once(self) -> None:
        behavior = await self._behavior()
        now_local = datetime.now(ZoneInfo(behavior.active_tz))
        if not bhv.in_active_window(
            now_local, behavior.active_start_min, behavior.active_end_min
        ):
            # Mimo okna aj tak nikto nečaká — je to najlepší čas upratať.
            await self._tidy_up()
            await self._close_stale_sessions()
            return
        if await self._db.is_paused():
            return

        await self._morning_round(behavior, now_local)

        now_utc = datetime.now(timezone.utc)
        # Koľko je po otvorení okna. Podľa toho sa rozpúšťa nočný rad — kto
        # napísal, kým modelka spala, nedostane odpoveď v tej istej minúte ako
        # ostatní. Mimo prvej hodiny je `od_otvorenia` veľké a nebrzdí nič.
        od_otvorenia = bhv.minutes_since_window_start(
            now_local, behavior.active_start_min, behavior.active_end_min
        )
        dnes = now_local.date().isoformat()

        def rad_prisiel(tg_id: int) -> bool:
            if od_otvorenia is None or od_otvorenia > outreach_mod.BACKLOG_SPREAD_H * 60:
                return True
            return outreach_mod.backlog_ready(tg_id, dnes, od_otvorenia)

        done: set = set()
        caka: List[int] = []
        # Kto čaká najdlhšie, ide prvý. Bez toho by sa na posledného vo fronte
        # nedostalo nikdy — miesta by stále brali tí, čo prídu neskôr.
        cakajuci = sorted(
            await self._db.pending_users(),
            key=lambda u: u.get("last_incoming_at") or "",
        )
        for user in cakajuci:
            tg_id = user["tg_id"]
            done.add(tg_id)
            if user.get("human_takeover") or not user.get("ai_enabled", True):
                await self._db.update_user(tg_id, {"pending_reply": False})
                continue
            # Odložená odpoveď ešte nedozrela — nechaj ju čakať.
            wait_until = _parse_ts(user.get("reply_after"))
            if wait_until and wait_until > now_utc:
                continue
            if not rad_prisiel(tg_id):
                continue
            caka.append(tg_id)

        # Sieť pod tým: niekomu ostala správa bez odpovede, aj keď príznak
        # `pending_reply` nesedí. Napríklad worker padol presne medzi zápisom
        # správy a naplánovaním odpovede. Nikto nesmie ostať bez odpovede.
        # Rovnaká hranica ako v Reconcileri — inak by sieť pod tým prebila
        # jeho rozhodnutie, že na štyri dni starú správu sa už neodpisuje.
        for user in await self._db.unanswered_users(stale_hours=STALE_HOURS):
            tg_id = user["tg_id"]
            if tg_id in done:
                continue
            wait_until = _parse_ts(user.get("reply_after"))
            if wait_until and wait_until > now_utc:
                continue
            if not rad_prisiel(tg_id):
                continue
            log.info("%s: ostala správa bez odpovede, dobieham to", tg_id)
            caka.append(tg_id)

        # Odpovede brzdí len objem správ. Strop na počet ľudí sem NEPATRÍ:
        # odpovedať tomu, kto napísal prvý, nie je vzor, ktorý by komukoľvek
        # vadil — a s ním by sa trinásty človek odpovede nedočkal, kým beží
        # dvanásť rozhovorov.
        volno = await self._rate_left(behavior.max_replies_per_hour)
        aktivni = await self._aktivne_rozhovory(behavior)
        if aktivni is None:
            # Výpadok DB — sweeper tento cyklus vynechá. Nikto o odpoveď
            # nepríde, `pending_reply` ostáva a o tri minúty to skúsi znova.
            log.warning("Sweeper stojí: neviem, koľko rozhovorov beží")
            return
        pusteni = limity.kto_ide_na_rad(
            caka, aktivni, behavior.max_active_chats, volno
        )
        if len(pusteni) < len(caka):
            log.warning(
                "Čaká %s ľudí, teraz ide %s — vedie %s rozhovorov z %s, strop správ %s",
                len(caka), len(pusteni), len(aktivni),
                behavior.max_active_chats, volno,
            )
        await self._reply_batch(pusteni, behavior)


def _strip_urls(text: str) -> str:
    """Odstráni odkazy, ale zachová členenie na odstavce (to určuje delenie správ)."""
    out = _URL_RE.sub("", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([,.!?…])", r"\1", out)
    return "\n\n".join(part.strip() for part in re.split(r"\n{2,}", out) if part.strip())


def message_id_of(event) -> int:
    return int(getattr(getattr(event, "message", None), "id", 0) or 0)


def _voice_ranges(behavior) -> Dict[str, tuple]:
    """Rozsahy hlasovky z nastavení klienta (migrácia 029) pre `livevoice.speak`.

    Je to jedna funkcia pre obe cesty — ostrú odpoveď aj ukážku v štúdiu —
    schválne. Kým sa nastavenia skladali na dvoch miestach, ukážka znela inak
    než to, čo naozaj odišlo, a ladenie sluchom tým stratilo zmysel.
    """
    return {
        "volume_range": (behavior.voice_volume_min, behavior.voice_volume_max),
        "lead_range": (behavior.voice_lead_min, behavior.voice_lead_max),
        "tail_range": (behavior.voice_tail_min, behavior.voice_tail_max),
    }


def _who(user: Dict[str, Any]) -> str:
    username = user.get("username")
    name = user.get("first_name") or "neznámy"
    return f"{name} (@{username})" if username else name


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------- dobehnutie po výpadku ----------

# Staršie ako toto sa už neodpovedá. Odpísať na tri dni starú správu, akoby sa
# nič nedialo, pôsobí horšie než neodpísať vôbec — ak sa ozve znova, kontext
# aj tak máme uložený.
STALE_HOURS = 48
RECONCILE_DIALOGS = 60


class Reconciler:
    """Po štarte zistí, čo ušlo, kým worker nebežal.

    Nikomu nepíše sama od seba — len dotiahne správy, ktoré prišli počas
    výpadku, uloží ich a rozhodne, na ktoré sa ešte oplatí odpovedať.
    """

    def __init__(self, bot: "UserBot", cfg: Config, db: Db, client: TelegramClient) -> None:
        self._bot = bot
        self._cfg = cfg
        self._db = db
        self._client = client

    async def run(self) -> Dict[str, int]:
        stats = {"dialogov": 0, "dotiahnutych": 0, "na_odpoved": 0, "prestarnutych": 0}
        # Čerstvý účet nemá čo dobiehať — históriu nemá. Sťahovať mu hneď po
        # pripojení šesťdesiat dialógov je zbytočný náraz na API práve vtedy,
        # keď je účet najzraniteľnejší.
        limit = max(int(RECONCILE_DIALOGS * self._bot._rozbeh()), 10)
        try:
            async for dialog in self._client.iter_dialogs(limit=limit):
                entity = dialog.entity
                if not isinstance(entity, User) or entity.bot or entity.is_self:
                    continue
                if _is_system_account(entity):
                    continue
                if entity.id == self._cfg.owner_chat_id and not self._cfg.owner_as_client:
                    continue
                if self._cfg.skip_contacts and getattr(entity, "contact", False):
                    if (
                        entity.id != self._cfg.owner_chat_id
                        and entity.id not in self._cfg.contact_exceptions
                    ):
                        continue
                stats["dialogov"] += 1
                await self._catch_up(entity, stats)
        except Exception:  # noqa: BLE001 - štart nesmie padnúť na tomto
            log.exception("Dobehnutie po štarte zlyhalo")
        log.info(
            "Po štarte: %s dialógov, %s nových správ, %s na odpoveď, %s prestarnutých",
            stats["dialogov"], stats["dotiahnutych"], stats["na_odpoved"], stats["prestarnutych"],
        )
        return stats

    async def _catch_up(self, entity: User, stats: Dict[str, int]) -> None:
        tg_id = entity.id
        user = await self._db.get_user(tg_id)
        if not user:
            # Nikdy sme si nepísali a je tu správa → normálny nový kontakt.
            user = await self._db.ensure_user(
                tg_id, entity.username, entity.first_name, getattr(entity, "lang_code", None)
            )

        last_seen = int(user.get("last_msg_id") or 0)
        missed = []
        async for message in self._client.iter_messages(entity, min_id=last_seen, limit=30):
            if message.out or not (message.message or "").strip():
                continue
            missed.append(message)
        if not missed:
            return

        missed.reverse()  # chronologicky
        count = int(user.get("msg_count") or 0)
        for message in missed:
            await self._db.add_message(tg_id, "user", message.message.strip())
            count += 1
        stats["dotiahnutych"] += len(missed)

        newest = missed[-1]
        patch: Dict[str, Any] = {
            "msg_count": count,
            "last_msg_id": newest.id,
            "last_incoming_at": newest.date.astimezone(timezone.utc).isoformat(),
        }

        age_h = (datetime.now(timezone.utc) - newest.date.astimezone(timezone.utc)).total_seconds() / 3600
        if age_h > STALE_HOURS:
            # Uložíme kontext, ale neodpisujeme. Keď sa ozve, budeme vedieť všetko.
            patch["pending_reply"] = False
            stats["prestarnutych"] += 1
            log.info("%s: %s zmeškaných správ, ale najnovšia má %.0f h — neodpisujem",
                     tg_id, len(missed), age_h)
        else:
            patch["pending_reply"] = True
            stats["na_odpoved"] += 1
            log.info("%s: %s zmeškaných správ (%.1f h) — zaradené na odpoveď",
                     tg_id, len(missed), age_h)
        await self._db.update_user(tg_id, patch)


# ---------- fotky ----------

# Telegram berie ako fotku len jpg, png a webp. Čokoľvek iné (napr. heic
# z iPhonu) musí ísť ako dokument, inak to server odmietne.
_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def photo_filename(url: str) -> str:
    """Názov, pod ktorým fotka odchádza do Telegramu.

    Telethon podľa prípony rozhodne, či je to fotka alebo dokument. Bez názvu
    z toho vždy vyjde dokument, ktorý si príjemca ani nevie otvoriť.
    """
    tail = url.split("?")[0].rsplit("/", 1)[-1]
    extension = tail.rsplit(".", 1)[-1].lower() if "." in tail else ""
    if extension not in _PHOTO_EXTENSIONS:
        extension = "jpg"
    return f"photo.{extension}"


async def _to_mp3(data: bytes) -> Optional[bytes]:
    """Prevod na mp3 pre prepis. None = ffmpeg zlyhal, skúsi sa originál."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0", "-vn", "-c:a", "libmp3lame", "-b:a", "64k",
            "-ar", "24000", "-ac", "1", "-f", "mp3", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _err = await asyncio.wait_for(process.communicate(data), timeout=60)
    except Exception as exc:  # noqa: BLE001 - prepis nesmie zhodiť odpoveď
        log.warning("Prevod prijatej hlasovky zlyhal: %s", exc)
        return None
    return out if process.returncode == 0 and out else None


async def _to_opus(data: bytes) -> Optional[bytes]:
    """Prevedie nahrávku na OGG/Opus cez ffmpeg. None = nepodarilo sa.

    Beží bez dočasných súborov, dáta idú cez stdin a stdout. Keď ffmpeg
    v prostredí nie je, pošle sa originál — hlasovka síce pristane ako
    zvukový súbor, ale odpoveď to nezhodí.
    """
    # Bola tu ešte úprava na „autentickosť" (šum, orezy, pauzy). Výsledok mal
    # echo a nedalo sa to počúvať, takže je preč: čistý prevod je vždy lepší
    # než pokazený zvuk. Jediné, čo ostáva, je bitrate v pásme, v akom posiela
    # hlasovky Telegram z mobilu.
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0", "-vn", "-c:a", "libopus", "-b:a", "32k",
            "-ar", "48000", "-ac", "1", "-f", "ogg", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(process.communicate(data), timeout=60)
    except FileNotFoundError:
        log.warning("ffmpeg nie je k dispozícii — posielam nahrávku bez prevodu")
        return None
    except Exception as exc:  # noqa: BLE001 - prevod nesmie zhodiť odpoveď
        log.warning("Prevod hlasovky zlyhal: %s", exc)
        return None
    if process.returncode != 0 or not out:
        log.warning("ffmpeg neprešiel: %s", (err or b"")[:200])
        return None
    log.info("Hlasovka prevedená na opus (%s → %s bajtov)", len(data), len(out))
    return out


async def _download(url: str) -> Optional[bytes]:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content
    except Exception as exc:  # noqa: BLE001
        log.warning("Fotku sa nepodarilo stiahnuť (%s): %s", url, exc)
        return None
