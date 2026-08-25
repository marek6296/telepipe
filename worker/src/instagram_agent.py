"""Instagram agent — odpovedá na DM tou istou personou ako na Telegrame.

AKO TO BEŽÍ
-----------
Kolo za kolom ťahá konverzácie (`me/conversations`), nájde tie, kde je posledná
správa jeho a ešte sme na ňu neodpovedali, a odpovie. Webhooky by boli rýchlejšie,
ale vyžadujú Advanced Access aj overenie firmy — pollovanie stačí Standard Access
a funguje hneď.

ČO SI TENTO SÚBOR NEROBÍ SÁM
----------------------------
Prompt stavia `persona.build_system_prompt`, teda to isté, čo Telegram: tá istá
osoba, tá istá ľudská vrstva, tie isté jazyky. Odlišnosti Instagramu pridáva
`instagram_pravidla` ako poslednú sekciu. Čistenie odpovede ide cez `humanize`.
Keby si tu agent písal vlastný prompt, o týždeň by to bola iná žena.

ČO TU ZÁMERNE NIE JE
--------------------
Fotky, hlasovky, ranné oslovenie, okno konverzácie ani útlm. Na Instagrame
modelka nepíše prvá (Instagram to ani neumožňuje: „Conversations only begin when
an Instagram user sends a message"), neposiela médiá a nemá čo utlmovať —
konverzácia sa skončí tým, že prestane písať on.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, List

import humanize
import instagram_api as api
import instagram_pravidla as pravidla
from behavior import Behavior
from persona import build_system_prompt

log = logging.getLogger(__name__)

# Ako často sa pozerá na nové správy. Instagram DM nie je Telegram — nikto
# nečaká odpoveď do piatich sekúnd a častejšie pollovanie len míňa limity.
KOLO_S = 45.0

# Koľko správ z histórie ide do promptu.
KONTEXT = 16


class InstagramAgent:
    """Jedno kolo = pozri konverzácie, odpovedz tým, čo čakajú."""

    def __init__(self, db, llm, control=None, poll_s: float = KOLO_S) -> None:
        self._db = db
        self._llm = llm
        self._control = control
        self._poll_s = poll_s
        self._moje_id = ""

    async def run(self) -> None:
        log.info("Instagram agent beží, konverzácie sa kontrolujú každých %.0f s", self._poll_s)
        while True:
            try:
                await self._kolo()
            except Exception:  # noqa: BLE001 - kolo nesmie zabiť slučku
                log.exception("Kolo Instagramu zlyhalo")
            await asyncio.sleep(self._poll_s)

    # ---------- jedno kolo ----------

    async def _kolo(self) -> None:
        nastavenia = await self._db.settings()
        if not nastavenia.get("connected") or not nastavenia.get("enabled"):
            return

        token = str(nastavenia.get("access_token") or "")
        if not token:
            log.info("Instagram: chýba token, kolo preskakujem")
            return

        rezim = str(nastavenia.get("reply_mode") or "off")
        if rezim == "off":
            return

        self._moje_id = str(nastavenia.get("ig_user_id") or "")

        try:
            konverzacie = await asyncio.to_thread(api.konverzacie, token)
        except api.InstagramError as exc:
            # Vypršaný token je bežná vec, nie porucha — klient to musí vidieť
            # na karte a agent má prestať skúšať dokola.
            log.warning("Instagram: konverzácie sa nepodarilo načítať (%s)", exc)
            await self._db.save({"poll_error": str(exc)[:400]})
            return

        await self._db.save(
            {"last_poll_at": datetime.now(timezone.utc).isoformat(), "poll_error": ""}
        )

        for surova in konverzacie:
            try:
                await self._konverzacia(surova, nastavenia, token, rezim)
            except Exception:  # noqa: BLE001 - jeden pokazený chat nezastaví ostatné
                log.exception("Instagram: konverzácia %s zlyhala", surova.get("id"))

    async def _konverzacia(
        self,
        surova: Dict[str, Any],
        nastavenia: Dict[str, Any],
        token: str,
        rezim: str,
    ) -> None:
        chat = api.rozober(surova, self._moje_id)
        igsid = chat["igsid"]
        if not igsid or not chat["spravy"]:
            return

        user = await self._db.ensure_user(igsid, chat["username"])
        if user.get("human_takeover") or not user.get("ai_enabled", True):
            return

        # Nové správy = tie, ktoré ešte nie sú v našej histórii.
        znama = await self._db.known_mids(igsid)
        nove = [s for s in chat["spravy"] if s["mid"] and s["mid"] not in znama]
        for sprava in nove:
            await self._db.add_message(igsid, sprava["role"], sprava["content"], sprava["mid"])

        posledna = chat["spravy"][-1]
        if posledna["role"] != "user":
            return  # posledné slovo je jej, niet na čo odpovedať
        if not nove:
            return  # nič nové, len sme to už videli

        # Okno na odpoveď. Po ňom Instagram odpoveď odmietne a jediná cesta von
        # je tag pre ľudského operátora — ten pre automat neplatí.
        if not api.v_okne(posledna.get("created_time")):
            log.info("Instagram %s: 24-hodinové okno vypršalo, neodpisujem", igsid)
            return

        text = await self._napis(user, chat, nastavenia)
        if not text:
            return

        if rezim == "semi":
            await self._na_schvalenie(user, chat, text)
            return

        await self._posli(token, igsid, user, text, nastavenia)

    # ---------- odpoveď ----------

    async def _napis(
        self, user: Dict[str, Any], chat: Dict[str, Any], nastavenia: Dict[str, Any]
    ) -> str:
        persona = await self._db.persona()
        behavior = Behavior.from_row(await self._db.behavior())
        historia = await self._db.history(chat["igsid"], KONTEXT)
        posledny_text = next(
            (m["content"] for m in reversed(historia) if m["role"] == "user"), ""
        )

        # Pikantnosť z karty Instagramu prebíja telegramovú — je to iná
        # platforma s inými pravidlami a `hot` tu neexistuje. `Behavior` je
        # frozen, takže vzniká nová inštancia; nastavenie v databáze ostáva
        # klientovo, mení sa len to, s čím pracuje tento agent.
        behavior = replace(behavior, heat=str(nastavenia.get("heat") or "mild"))

        smie_pozvat = pravidla.smie_pozvat(user, int(user.get("msg_count") or 0))
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
            asked_if_ai=humanize.looks_like_ai_question(posledny_text),
            behavior=behavior,
            foreign=humanize.looks_foreign(posledny_text),
            bare_greeting=humanize.is_bare_greeting(posledny_text),
            his_question=humanize.last_question(posledny_text),
            # Na Instagrame neodchádza žiadne médium (viď `instagram_pravidla`),
            # takže sľúbená fotka je sľub, ktorý sa nedá splniť ani omylom.
            no_photos=True,
        )
        system += "\n\n" + pravidla.blok(
            nastavenia,
            pozvala_uz=0 if smie_pozvat else pravidla.MAX_POZVANI,
        )

        surova = await self._llm.reply(system, historia)
        jej_nedavne = [m["content"] for m in historia if m["role"] == "assistant"][-6:]

        # To isté čistenie ako na Telegrame — vrátane potláčania otváračov.
        from userbot import UserBot

        text = UserBot._uprav_odpoved(
            surova or "",
            behavior,
            0.0,
            False,  # allow_link=False → prípadná adresa sa aj tak odstráni
            jej_nedavne,
            he_greeted=humanize.is_bare_greeting(posledny_text),
        )
        return api.orez(text)

    async def _posli(
        self,
        token: str,
        igsid: str,
        user: Dict[str, Any],
        text: str,
        nastavenia: Dict[str, Any],
    ) -> None:
        try:
            odpoved = await asyncio.to_thread(api.posli_text, token, igsid, text)
        except api.InstagramError as exc:
            log.warning("Instagram %s: správa neodišla (%s)", igsid, exc)
            await self._db.save({"poll_error": str(exc)[:400]})
            return

        mid = str(odpoved.get("message_id") or "")
        await self._db.add_message(igsid, "assistant", text, mid)

        patch: Dict[str, Any] = {
            "msg_count": int(user.get("msg_count") or 0) + 1,
            "last_reply_at": datetime.now(timezone.utc).isoformat(),
        }
        # Povedala mu, kde ju nájde? Poznáme to podľa toho, či sa v odpovedi
        # objavilo telegramové meno alebo zmienka o biu — na Instagrame nie je
        # čo iné merať, odkaz sa tu neposiela.
        if _pozvala(text, nastavenia):
            patch["pointed_at"] = datetime.now(timezone.utc).isoformat()
            patch["pointed_count"] = int(user.get("pointed_count") or 0) + 1
            log.info("Instagram %s: povedala, kde ju nájde (%s×)", igsid, patch["pointed_count"])

        await self._db.update_user(igsid, patch)
        log.info("Instagram %s: odpoveď odoslaná", igsid)

    async def _na_schvalenie(
        self, user: Dict[str, Any], chat: Dict[str, Any], text: str
    ) -> None:
        """Semi režim — návrh ide majiteľovi do control bota."""
        if not self._control:
            log.info("Instagram %s: semi režim, ale control bot nebeží", chat["igsid"])
            return
        kto = chat["username"] or chat["igsid"]
        await self._control.notify(
            f"📸 *Instagram — {kto}*\n\n"
            f"_{(chat['spravy'][-1]['content'])[:300]}_\n\n"
            f"Navrhujem:\n{text}"
        )


def _pozvala(text: str, nastavenia: Dict[str, Any]) -> bool:
    """Objavilo sa v odpovedi pozvanie inam?"""
    nizky = (text or "").lower()
    handle = str(nastavenia.get("telegram_handle") or "").strip().lstrip("@").lower()
    if handle and handle in nizky:
        return True
    return any(slovo in nizky for slovo in ("bio", "link in my", "profile"))
