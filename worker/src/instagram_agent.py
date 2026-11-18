"""Instagram persona adapter. Durable ingest, approvals and send gates live in
instagram_delivery; this module shares Telegram's established voice and cleaner.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import humanize
import conversation_timing
import instagram_api as api
import instagram_pravidla as pravidla
import prehlad
import zadanie
from behavior import Behavior
from persona import build_system_prompt

log = logging.getLogger(__name__)

# Ako často sa pozerá na nové správy. Instagram DM nie je Telegram — nikto
# nečaká odpoveď do piatich sekúnd a častejšie pollovanie len míňa limity.
KOLO_S = 90.0

# Kým Instagram nie je pripojený, zapnutý alebo má režim `off`, stačí sa
# pozrieť raz za päť minút. Toľko najviac čaká klient po pripojení.
NECINNE_S = 300.0

# Komentáre sa pozerajú len v každom n-tom kole (~7,5 min). Limit API je
# spoločný s konverzáciami a komentár nikto nečaká vybavený do minúty.
KOMENTARE_KAZDE = 10

# Najviac toľko odpovedí pod komentáre za jedno kolo — keď príspevok vystrelí,
# dvadsať odpovedí za sekundu je presne vzorec, ktorý Instagram trestá.
KOMENTARE_NA_KOLO = 3

# Starší komentár sa už nedobieha.
KOMENTAR_MAX_H = 48

# Koľko správ z histórie ide do promptu.
KONTEXT = 16

# Tri ťahy pre návrhy v semi. Na Instagrame sa nepredáva — ťahy sú
# zoznamovacie, nie predajné ako na Fanvue.
UHLY = [
    "nadviaž priamo na to, čo napísal — ľahko a zvedavo",
    "vráť loptičku jemu — jednou otázkou, nech povie viac o sebe",
    "buď hravejšia a o krok smelšia, ale stále slušne (je to Instagram)",
]

# Uhly pre zadanie od majiteľa („napíš mu, že…") — tému nemení ani jeden.
UHLY_ZADANIE = [
    "povedz to krátko a priamo",
    "povedz to hravejšie, s náznakom",
    "povedz to vrúcnejšie a osobnejšie",
]


class InstagramAgent:
    """Jedno kolo = pozri konverzácie, odpovedz tým, čo čakajú.

    Zároveň je to „sender" pre control bota (kanál `instagram`): vie doručiť
    schválený text, pregenerovať návrhy, ukázať kontext a prevziať chat.
    """

    def __init__(
        self,
        db,
        llm,
        control=None,
        poll_s: float = KOLO_S,
        idle_s: float = NECINNE_S,
    ) -> None:
        self._db = db
        self._llm = llm
        self._control = control
        self._poll_s = poll_s
        self._idle_s = idle_s
        self._moje_id = ""
        self._kolo_c = 0
        from instagram_delivery import InstagramDelivery
        self._delivery = InstagramDelivery(db, self)

    def set_control(self, control) -> None:
        self._control = control

    async def run(self) -> None:
        log.info("Instagram agent beží, konverzácie sa kontrolujú každých %.0f s", self._poll_s)
        while True:
            aktivny = False
            try:
                aktivny = await self._kolo()
            except Exception:  # noqa: BLE001 - kolo nesmie zabiť slučku
                log.exception("Kolo Instagramu zlyhalo")
            await asyncio.sleep(self._poll_s if aktivny else self._idle_s)

    # ---------- jedno kolo ----------

    async def _kolo(self) -> bool:
        return await self._delivery.poll()

    # ---------- prompt a odpoveď ----------

    async def _prompt(
        self, user: Dict[str, Any], igsid: str, nastavenia: Dict[str, Any]
    ) -> Tuple[str, List[Dict[str, str]], Behavior, str]:
        """Systémový prompt + história. Spoločné pre auto, semi aj Regenerate."""
        persona = await self._db.persona()
        behavior = Behavior.from_row(await self._db.behavior())
        historia = await self._db.history(igsid, KONTEXT)

        # Pikantnosť z karty Instagramu prebíja telegramovú — je to iná
        # platforma s inými pravidlami a `hot` tu neexistuje. `Behavior` je
        # frozen, takže vzniká nová inštancia; nastavenie v databáze ostáva
        # klientovo, mení sa len to, s čím pracuje tento agent.
        behavior = replace(behavior, heat=str(nastavenia.get("heat") or "mild"))

        offer = await self._delivery.offer_state(nastavenia, {**user, 'igsid': igsid})
        from zoneinfo import ZoneInfo
        import den
        local = datetime.now(timezone.utc).astimezone(ZoneInfo(behavior.active_tz))
        turn = conversation_timing.analyze(historia, now_local=local)
        posledny_text = turn.latest_text
        sent = next((m for m in reversed(historia) if m['role'] == 'assistant'), None)
        sent_at = conversation_timing.message_time(sent) if sent else None
        gap = max(0.0, (local - sent_at).total_seconds() / 3600) if sent_at else (
            0.0 if sent or int(user.get('msg_count') or 0) > 0 else None
        )
        block, mood = await self._db.hub.day(local, den.Rozvrh.from_row(await self._db.schedule()))
        system = build_system_prompt(
            persona,
            {
                "tg_id": 0,
                "msg_count": int(user.get("msg_count") or 0),
                "funnel_stage": str(user.get("funnel_stage") or "cold"),
                "partner_name": str(user.get("name") or ""),
                "summary": str(user.get("summary") or ""),
            },
            # Odkaz na platenú platformu sa na Instagrame neposiela NIKDY —
            # ani keď oň priamo pýta. Toto je ten vypínač.
            allow_link=False,
            gap=gap,
            asked_if_ai=humanize.looks_like_ai_question(posledny_text),
            behavior=behavior,
            foreign=humanize.looks_foreign(posledny_text),
            bare_greeting=turn.greeting_only,
            his_question=humanize.last_question(posledny_text),
            # Na Instagrame neodchádza žiadne médium (viď `instagram_pravidla`),
            # takže sľúbená fotka je sľub, ktorý sa nedá splniť ani omylom.
            no_photos=True,
            now_local=local,
            situation=den.describe(block),
            her_recent=[m['content'] for m in historia if m['role'] == 'assistant'][-8:],
        )
        system += "\n\n" + pravidla.blok(nastavenia, offer=offer)
        system += await self._db.hub.context('instagram', igsid, nastavenia['ig_user_id'])
        system += self._db.hub.mood_prompt(mood)
        if user.get('last_typo'):
            import json
            system += '\nIf asked about your last typo, correct it briefly in your voice: ' + json.dumps(user['last_typo'])
        return conversation_timing.prompt_with_timing(system, turn), historia, behavior, posledny_text

    def _ocisti(
        self,
        surova: str,
        behavior: Behavior,
        historia: List[Dict[str, str]],
        posledny_text: str,
    ) -> str:
        """To isté čistenie ako na Telegrame — vrátane potláčania otváračov."""
        from userbot import UserBot

        jej_nedavne = [m["content"] for m in historia if m["role"] == "assistant"][-6:]
        from instagram_interactions import TAGS, URL
        markers = TAGS.findall(surova or '')
        # Reject generated URLs rather than silently turning an unsafe invitation into another one.
        if URL.search(surova or ''):
            return ''
        prose = TAGS.sub('', surova or '')
        text = UserBot._uprav_odpoved(
            prose,
            behavior,
            0.0,
            False,  # allow_link=False → prípadná adresa sa aj tak odstráni
            jej_nedavne,
            he_greeted=conversation_timing.analyze(historia).has_greeting,
        )
        if len(markers) > 1:
            return ''
        if markers:
            marker = markers[0]
            return ('[[PHOTO]]' if marker == 'PHOTO' else
                    (api.orez(text, 550) + ' [[' + marker + ']]' if marker in ('LINK', 'TELEGRAM', 'LINKPAGE') else '[[' + marker + ']] ' + api.orez(text, 950)))
        return api.orez(text)

    async def _napis(self, user: Dict[str, Any], igsid: str, nastavenia: Dict[str, Any]) -> str:
        system, historia, behavior, posledny = await self._prompt(user, igsid, nastavenia)
        from zoneinfo import ZoneInfo
        messages = conversation_timing.analyze(historia, now_local=datetime.now(timezone.utc).astimezone(ZoneInfo(behavior.active_tz))).messages
        surova = await self._llm.reply(system, messages)
        text = self._ocisti(surova, behavior, historia, posledny)
        from conversation_policy import normalise
        previous = {normalise(m['content']) for m in historia if m['role'] == 'assistant'}
        if text and normalise(text) in previous:
            surova = await self._llm.reply(system + '\nDo not repeat a previous response; answer the current turn.', messages)
            text = self._ocisti(surova, behavior, historia, posledny)
            if normalise(text) in previous:
                return ''
        return text

    async def _navrhy(
        self,
        user: Dict[str, Any],
        igsid: str,
        nastavenia: Dict[str, Any],
        seed: str = "",
        brief: str = "",
    ) -> Tuple[List[str], List[Dict[str, str]]]:
        """Tri očistené návrhy pre semi kartu (alebo Regenerate / Say this)."""
        system, historia, behavior, posledny = await self._prompt(user, igsid, nastavenia)
        system += prehlad.pokyn_pre_model(historia)
        from zoneinfo import ZoneInfo
        messages = conversation_timing.analyze(historia, now_local=datetime.now(timezone.utc).astimezone(ZoneInfo(behavior.active_tz))).messages
        if brief:
            system += zadanie.do_promptu(brief)
        surove = await self._llm.suggest(
            system, messages, angles=UHLY_ZADANIE if brief else UHLY, seed=seed,
        )
        navrhy: List[str] = []
        offer = await self._delivery.offer_state(nastavenia, user)
        for surova in surove or []:
            text = self._ocisti(surova, behavior, historia, posledny)
            if any(marker in text for marker in ('[[LINK]]', '[[TELEGRAM]]', '[[LINKPAGE]]')):
                from instagram_interactions import prepare_response
                text = prepare_response(text, nastavenia, offer)['text']
            if text and text not in navrhy:
                navrhy.append(text)
        return navrhy, historia

    # ---------- rozhranie pre control bota (kanál `instagram`) ----------

    async def deliver_text(self, conv_key: str, text: str) -> bool:
        """Approve this exact durable action. Sending happens after current gates."""
        return await self._delivery.approve(conv_key, text)

    async def deliver_operator(self, command, before_send):
        return await self._delivery.deliver_operator(command, before_send)

    async def approval_state(self, conv_key: str) -> str:
        return await self._delivery.approval_state(conv_key)

    async def regenerate(
        self, conv_key: str, seed: str = "", brief: str = ""
    ) -> Dict[str, Any]:
        """Nové návrhy pre ten istý chat („Regenerate" / „Say this")."""
        from instagram_delivery import contact_key
        key = conv_key
        conv_key = contact_key(key)
        user = await self._db.user(conv_key)
        if not user:
            return {}
        nastavenia = await self._db.settings()
        if not await self._delivery.refresh_regeneration(nastavenia, key):
            return {}
        user = await self._db.user(conv_key) or user
        navrhy, _ = await self._navrhy(user, conv_key, nastavenia, seed=seed or "2", brief=brief)
        if not await self._delivery.refresh_regeneration(nastavenia, key):
            return {}
        return {"suggestions": navrhy, "hint": ""}

    async def context_card(self, conv_key: str) -> str:
        """Kto to je a o čom si píšu. Nič sa negeneruje — len to, čo je v DB."""
        from instagram_delivery import contact_key
        conv_key = contact_key(conv_key)
        user = await self._db.user(conv_key)
        if not user:
            return ""
        meno = str(user.get("username") or conv_key)
        riadky = [f"📸 *Instagram · @{meno}*"]
        riadky.append(
            f"{int(user.get('msg_count') or 0)} replies from her"
            + (f" · told him where to find her {int(user.get('pointed_count') or 0)}×"
               if user.get("pointed_count") else "")
        )
        if user.get("summary"):
            riadky.append(f"\n_{str(user['summary'])[:600]}_")
        historia = await self._db.history(conv_key, prehlad.SPOLU)
        blok = prehlad.blok_rozhovoru(historia)
        if blok:
            riadky.append("\n" + blok.replace(prehlad.JEJ, "↳ "))
        return "\n".join(riadky)

    async def recent_chats(self, limit: int = 10) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in await self._db.recent_chats(limit):
            igsid = str(row.get("igsid") or "")
            if not igsid:
                continue
            popis = f"{int(row.get('msg_count') or 0)} msgs"
            if row.get("human_takeover"):
                popis += " · ✋"
            out.append(
                {"conv_key": igsid, "name": str(row.get("username") or igsid), "hint": popis}
            )
        return out

    async def take_over(self, conv_key: str) -> None:
        """„Take over" na karte — AI do tohto chatu už nepíše."""
        from instagram_delivery import contact_key
        conv_key = contact_key(conv_key)
        await self._db.update_user(conv_key, {"human_takeover": True})
        await self._db.cancel_actions(conv_key, "takeover")

    # Médiá Instagram agent neposiela (viď hlavičku). Tlačidlá na ne sa pri
    # kanáli `instagram` ani nezobrazia; toto je poistka pre staré karty.
    async def photo_folders(self, conv_key: str) -> List[Dict[str, str]]:
        return []

    async def photo_items(self, conv_key: str, folder_id: str) -> List[Dict[str, Any]]:
        return []

    async def suggest_caption(self, conv_key: str) -> List[str]:
        return []

    async def deliver_photo(self, conv_key, media_ref, caption, price_cents=None) -> bool:
        return False

    async def generate_voice_preview(self, text: str) -> Optional[bytes]:
        return None

    async def deliver_voice(self, conv_key, text, ogg) -> bool:
        return False

    # ---------- komentáre ----------

    async def _napis_komentar(self, komentar: Dict[str, Any]) -> str:
        """Krátka verejná odpoveď. Prázdna = nechať tak (spam, urážka, nič)."""
        persona = await self._db.persona()
        behavior = replace(Behavior.from_row(await self._db.behavior()), heat="mild")
        system = build_system_prompt(
            persona,
            {"tg_id": 0, "msg_count": 0, "funnel_stage": "cold",
             "partner_name": "", "summary": ""},
            allow_link=False,
            asked_if_ai=humanize.looks_like_ai_question(str(komentar.get("text") or "")),
            behavior=behavior,
            no_photos=True,
        )
        system += "\n\n" + pravidla.KOMENTAR
        surova = await self._llm.reply(
            system, [{"role": "user", "content": pravidla.komentar_zadanie(komentar)}]
        )
        return _ocisti_komentar(self._ocisti(surova, behavior, [], str(komentar.get("text") or "")))


def _ocisti_komentar(surova: Optional[str]) -> str:
    """Verejná odpoveď: bez odkazov, @mien a hashtagov, krátka. SKIP = nič."""
    text = (surova or "").strip().strip('"“”')
    if not text or text.upper().startswith("SKIP"):
        return ""
    slova = []
    for slovo in text.split():
        nizke = slovo.lower()
        if slovo.startswith(("@", "#")) or "http" in nizke or "www." in nizke or ".com" in nizke:
            continue
        if any(z in nizke for z in ("fanvue", "onlyfans", "telegram", "t.me")):
            continue
        slova.append(slovo)
    return api.orez(" ".join(slova), api.MAX_BAJTOV_KOMENTAR)


def _pozvala(text: str, nastavenia: Dict[str, Any]) -> bool:
    """Objavilo sa v odpovedi pozvanie inam?"""
    nizky = (text or "").lower()
    handle = str(nastavenia.get("telegram_handle") or "").strip().lstrip("@").lower()
    if handle and handle in nizky:
        return True
    return any(slovo in nizky for slovo in ("bio", "link in my", "profile"))
