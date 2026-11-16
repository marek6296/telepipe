"""Instagram agent — odpovedá na DM tou istou personou ako na Telegrame.

AKO TO BEŽÍ
-----------
Kolo za kolom ťahá konverzácie (`me/conversations`), nájde tie, kde je posledná
správa jeho a ešte sme na ňu neodpovedali, a odpovie. Webhooky by boli rýchlejšie,
ale vyžadujú Advanced Access aj overenie firmy — pollovanie stačí Standard Access
a funguje hneď.

Agent beží CELÝ ŽIVOT TENANTA, aj keď Instagram ešte nie je pripojený. Pripojenie
v dashboarde preto zaberie do pár minút bez reštartu modelky (reštart by znamenal
aj odpojenie Telethon session). Kým pripojený nie je, pozerá do databázy len raz
za `NECINNE_S`, nie každých 45 sekúnd.

REŽIMY
------
* `auto` — odpíše sám.
* `semi` — tri návrhy prídu majiteľovi do control bota ako schvaľovacia karta
  (tá istá ako pri Telegrame a Fanvue). Doručuje `deliver_text`, ktorý volá
  control bot po kliknutí. Časový fallback tu NIE JE: Instagram je verejný
  a nechcený automat je presne to, čo chce majiteľ v semi vylúčiť.
* `off` — mlčí.

KOMENTÁRE
---------
Keď je zapnuté `reply_comments` a režim je `auto`, raz za `KOMENTARE_KAZDE` kôl
pozrie komentáre pod poslednými príspevkami a krátko, verejne a bez flirtu
odpovie. V semi sa komentáre nevybavujú — karta v control bote je pre DM.

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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import humanize
import instagram_api as api
import instagram_pravidla as pravidla
import prehlad
import zadanie
from behavior import Behavior
from persona import build_system_prompt

log = logging.getLogger(__name__)

# Ako často sa pozerá na nové správy. Instagram DM nie je Telegram — nikto
# nečaká odpoveď do piatich sekúnd a častejšie pollovanie len míňa limity.
KOLO_S = 45.0

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
        """Jedno kolo. Vracia, či je Instagram aktívny (určuje tempo slučky)."""
        nastavenia = await self._db.settings()
        if not nastavenia.get("connected") or not nastavenia.get("enabled"):
            return False

        token = str(nastavenia.get("access_token") or "")
        if not token:
            log.info("Instagram: chýba token, kolo preskakujem")
            return False

        rezim = str(nastavenia.get("reply_mode") or "off")
        if rezim == "off":
            return False

        self._moje_id = str(nastavenia.get("ig_user_id") or "")
        if not self._moje_id:
            await self._db.save({"last_error": "Missing Instagram account ID. Please reconnect.", "connected": False})
            return False

        try:
            konverzacie = await asyncio.to_thread(api.konverzacie, token, account_id=self._moje_id)
        except api.InstagramError as exc:
            # Vypršaný token je bežná vec, nie porucha — klient to musí vidieť
            # na karte a agent má prestať skúšať dokola.
            log.warning("Instagram: konverzácie sa nepodarilo načítať (%s)", exc)
            if exc.kod == 190:
                await self._db.save({"connected": False, "last_error": "Instagram access was revoked. Please reconnect.", "poll_error": str(exc)[:400]})
                return False
            await self._db.save({"poll_error": str(exc)[:400]})
            return True

        await self._db.save(
            {"last_poll_at": datetime.now(timezone.utc).isoformat(), "poll_error": ""}
        )

        for surova in konverzacie:
            try:
                await self._konverzacia(surova, nastavenia, token, rezim)
            except Exception:  # noqa: BLE001 - jeden pokazený chat nezastaví ostatné
                log.exception("Instagram: konverzácia %s zlyhala", surova.get("id"))

        # Komentáre v každom n-tom kole (aj v prvom, nech sa dá hneď overiť).
        if self._kolo_c % KOMENTARE_KAZDE == 0:
            try:
                await self._komentare(token, nastavenia, rezim)
            except Exception:  # noqa: BLE001 - komentáre nesmú zhodiť DM
                log.exception("Instagram: komentáre zlyhali")
        self._kolo_c += 1
        return True

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

        # Kedy naposledy písal — podľa toho sa radí zoznam chatov v control bote.
        await self._db.update_user(
            igsid, {"last_incoming_at": datetime.now(timezone.utc).isoformat()}
        )

        # Okno na odpoveď. Po ňom Instagram odpoveď odmietne a jediná cesta von
        # je tag pre ľudského operátora — ten pre automat neplatí.
        if not api.v_okne(posledna.get("created_time")):
            log.info("Instagram %s: 24-hodinové okno vypršalo, neodpisujem", igsid)
            return

        if rezim == "semi":
            await self._na_schvalenie(user, chat, nastavenia)
            return

        text = await self._napis(user, igsid, nastavenia)
        if not text:
            return
        await self._posli(token, igsid, user, text, nastavenia)

    # ---------- prompt a odpoveď ----------

    async def _prompt(
        self, user: Dict[str, Any], igsid: str, nastavenia: Dict[str, Any]
    ) -> Tuple[str, List[Dict[str, str]], Behavior, str]:
        """Systémový prompt + história. Spoločné pre auto, semi aj Regenerate."""
        persona = await self._db.persona()
        behavior = Behavior.from_row(await self._db.behavior())
        historia = await self._db.history(igsid, KONTEXT)
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
        return system, historia, behavior, posledny_text

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
        text = UserBot._uprav_odpoved(
            surova or "",
            behavior,
            0.0,
            False,  # allow_link=False → prípadná adresa sa aj tak odstráni
            jej_nedavne,
            he_greeted=humanize.is_bare_greeting(posledny_text),
        )
        return api.orez(text)

    async def _napis(self, user: Dict[str, Any], igsid: str, nastavenia: Dict[str, Any]) -> str:
        system, historia, behavior, posledny = await self._prompt(user, igsid, nastavenia)
        surova = await self._llm.reply(system, historia)
        return self._ocisti(surova, behavior, historia, posledny)

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
        if brief:
            system += zadanie.do_promptu(brief)
        surove = await self._llm.suggest(
            system, historia, angles=UHLY_ZADANIE if brief else UHLY, seed=seed,
        )
        navrhy: List[str] = []
        for surova in surove or []:
            text = self._ocisti(surova, behavior, historia, posledny)
            if text and text not in navrhy:
                navrhy.append(text)
        return navrhy, historia

    async def _posli(
        self,
        token: str,
        igsid: str,
        user: Dict[str, Any],
        text: str,
        nastavenia: Dict[str, Any],
    ) -> bool:
        try:
            odpoved = await asyncio.to_thread(api.posli_text, token, igsid, text, account_id=str(nastavenia.get("ig_user_id") or ""))
        except api.InstagramError as exc:
            log.warning("Instagram %s: správa neodišla (%s)", igsid, exc)
            await self._db.save({"poll_error": str(exc)[:400]})
            return False

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
        return True

    # ---------- semi-auto ----------

    async def _na_schvalenie(
        self, user: Dict[str, Any], chat: Dict[str, Any], nastavenia: Dict[str, Any]
    ) -> bool:
        """Semi režim — tri návrhy idú majiteľovi ako schvaľovacia karta."""
        igsid = chat["igsid"]
        if not self._control:
            log.info("Instagram %s: semi režim, ale control bot nebeží", igsid)
            return False
        try:
            navrhy, historia = await self._navrhy(user, igsid, nastavenia)
        except Exception as exc:  # noqa: BLE001 - karta bez návrhov je lepšia než pád
            log.warning("Instagram %s: návrhy zlyhali (%s)", igsid, exc)
            return False
        if not navrhy:
            return False
        ok = await self._control.post_approval(
            channel="instagram",
            conv_key=igsid,
            display_name=chat.get("username") or str(user.get("username") or "") or igsid,
            incoming_preview=(
                prehlad.blok_rozhovoru(historia) or chat["spravy"][-1]["content"]
            ),
            suggestions=navrhy,
        )
        log.info("Instagram semi: karta pre %s %s", igsid, "poslaná" if ok else "NEposlaná")
        return bool(ok)

    # ---------- rozhranie pre control bota (kanál `instagram`) ----------

    async def deliver_text(self, conv_key: str, text: str) -> bool:
        """Schválený text z karty → Instagram. Okno sa overí znova: majiteľ
        mohol kartu nechať visieť dlhšie než 24 hodín."""
        nastavenia = await self._db.settings()
        token = str(nastavenia.get("access_token") or "")
        if not token or not nastavenia.get("connected"):
            return False
        historia = await self._db.history(conv_key, KONTEXT)
        posledny = next(
            (m["content"] for m in reversed(historia) if m["role"] == "user"), ""
        )
        behavior = Behavior.from_row(await self._db.behavior())
        cisty = self._ocisti(text, behavior, historia, posledny)
        if not cisty:
            return False
        user = await self._db.user(conv_key) or {}
        return await self._posli(token, conv_key, user, cisty, nastavenia)

    async def regenerate(
        self, conv_key: str, seed: str = "", brief: str = ""
    ) -> Dict[str, Any]:
        """Nové návrhy pre ten istý chat („Regenerate" / „Say this")."""
        user = await self._db.user(conv_key)
        if not user:
            return {}
        nastavenia = await self._db.settings()
        navrhy, _ = await self._navrhy(user, conv_key, nastavenia, seed=seed or "2", brief=brief)
        return {"suggestions": navrhy, "hint": ""}

    async def context_card(self, conv_key: str) -> str:
        """Kto to je a o čom si píšu. Nič sa negeneruje — len to, čo je v DB."""
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
        await self._db.update_user(conv_key, {"human_takeover": True})

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

    async def _komentare(self, token: str, nastavenia: Dict[str, Any], rezim: str) -> int:
        """Odpovie pod nové komentáre. Vracia počet odoslaných odpovedí."""
        if not nastavenia.get("reply_comments") or rezim != "auto":
            return 0

        try:
            prispevky = await asyncio.to_thread(api.prispevky_s_komentarmi, token, account_id=str(nastavenia.get("ig_user_id") or ""))
        except api.InstagramError as exc:
            log.warning("Instagram: komentáre sa nepodarilo načítať (%s)", exc)
            return 0

        komentare = api.rozober_komentare(
            prispevky, self._moje_id, str(nastavenia.get("username") or "")
        )
        hranica = datetime.now(timezone.utc) - timedelta(hours=KOMENTAR_MAX_H)
        komentare = [
            k for k in komentare
            if (cas := api._cas(k.get("created_time"))) is not None and cas >= hranica
        ]
        if not komentare:
            return 0

        vybavene = await self._db.handled_comments([k["comment_id"] for k in komentare])
        odoslane = 0
        for komentar in komentare:
            if odoslane >= KOMENTARE_NA_KOLO:
                break
            if komentar["comment_id"] in vybavene:
                continue
            text = await self._napis_komentar(komentar)
            if not text:
                await self._db.save_comment({**komentar, "status": "skipped"})
                continue
            try:
                await asyncio.to_thread(
                    api.odpovedz_na_komentar, token, komentar["comment_id"], text
                )
            except api.InstagramError as exc:
                log.warning("Instagram komentár %s: odpoveď neodišla (%s)",
                            komentar["comment_id"], exc)
                await self._db.save_comment({**komentar, "reply_text": text, "status": "failed"})
                continue
            await self._db.save_comment({**komentar, "reply_text": text, "status": "replied"})
            odoslane += 1
            log.info("Instagram: odpovedala pod komentár %s", komentar["comment_id"])
        return odoslane

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
        return _ocisti_komentar(surova)


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
