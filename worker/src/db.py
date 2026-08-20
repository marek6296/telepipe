"""Async prístup k tenantovým tabuľkám cez `SupabaseTransport`.

Oproti šablóne (jedna modelka = jedna schéma) tu všetkých šestnásť tabuliek
žije v `public` a rozlišuje ich stĺpec `model_id`. Jediné, čo drží tenantov od
seba, je preto tento súbor: **každé** čítanie má filter `model_id=eq.…`, každý
zápis nesie `model_id` v tele a každý update/delete filtruje na oboje. Chýbajúci
filter = únik dát medzi modelkami, nie „len" zlý výsledok.

Spojenie vlastní `main` (jeden transport na proces); `TenantDb` je tenká vrstva
nad ním, takže sa dá pre každú modelku vyrobiť a zahodiť bez nákladov.

ŠIFROVACÍ SEAM (ElevenLabs)
---------------------------
Rovnaký nápad ako pri Fanvue tokenoch (`fanvue_tenant.py`): portované moduly
(`userbot`, `speech`, `voices`, `livevoice`, `fvvoice`) čítajú
`behavior["eleven_key"]` ako čistý text a nesmú sa kvôli šifrovaniu meniť.
Dešifruje sa preto presne na hranici čítania — v `get_behavior()`. Von ide
`eleven_key`, `eleven_key_enc` sa do výsledku nedostane vôbec.

KDE TEN KĽÚČ ODTERAZ JE (migrácia 017)
--------------------------------------
Na ÚČTE (`accounts.eleven_key_enc`), nie na modelke. Účet ElevenLabs je jeden
a fakturácia je jedna, takže ho majiteľ pripája raz v nastaveniach účtu; na
karte modelky sa vyberá už len hlas. `behavior.eleven_key_enc` a zastaraný
čistý text `behavior.eleven_key` ostávajú ako FALLBACK — vďaka tomu prežije
tento worker aj databázu, v ktorej presun ešte nebežal.

Kľúč účtu sa NEČÍTA pri každej odpovedi. `get_behavior()` beží pri každej
správe; ďalší dotaz do DB na hodnotu, ktorá sa mení raz za mesiace, by bol
čistá réžia. Drží ho `AccountKeyCache` s krátkym TTL (5 min): pripojenie
alebo prekľúčovanie v dashboarde sa prejaví do piatich minút a bez reštartu
tenanta — rovnaký sľub, aký má dozor nad Fanvue vypínačom.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from transport import SupabaseTransport

log = logging.getLogger(__name__)

PERSONA = "/persona"
USERS = "/dm_users"
MESSAGES = "/dm_messages"
SETTINGS = "/settings"
PHOTOS = "/photos"
PHOTO_SENDS = "/photo_sends"
VOICES = "/voices"
VOICE_SENDS = "/voice_sends"
FACTS = "/facts"
EPISODES = "/episodes"
LOOPS = "/open_loops"
CLAIMS = "/self_claims"
JUDGE_LOG = "/judge_log"
BEHAVIOR = "/behavior"
MANAGED_VOICES = "/managed_voices"
SCHEDULE = "/model_schedule"
VOICE_CLIPS = "/voice_clips"
VOICE_JOBS = "/voice_jobs"
PENDING = "/pending_replies"
ACCOUNTS = "/accounts"
CONTROL_BOT_SETTINGS = "/control_bot_settings"

# Ako dlho platí raz načítaný kľúč účtu. Päť minút je kompromis: v dashboarde
# to pôsobí okamžite (kým si človek otvorí kartu hlasu a klikne, je to vonku),
# a pri stovke tenantov je to dvadsať dotazov za hodinu, nie na každú správu.
ACCOUNT_KEY_TTL_S = 300.0

# Ako dlho platí raz načítaný rozvrh dňa (migrácia 022). Rovnaká úvaha ako pri
# kľúči účtu: číta sa pri KAŽDEJ odpovedi, ale mení sa vtedy, keď si klient
# otvorí kartu a niečo preklikne. Päť minút znamená, že úprava v dashboarde je
# vonku skôr, než sa človek stihne prepnúť do Telegramu, a pritom to nie je
# dotaz navyše ku každej správe.
SCHEDULE_TTL_S = 300.0

# Vyrobené hlasovky si necháme. Dnes preto, aby si ich majiteľ vedel v dashboarde
# vypočuť, a raz preto, že z nich bude zásoba, z ktorej sa dá siahnuť po
# hotovej, keď sadne do kontextu.
# Názov musí sedieť s bucketom v Supabase Storage (`voices`, public read) —
# v predlohe sa volal `model-voices`, v Telepipe je to `voices`.
VOICE_BUCKET = "voices"


def _ts(value: Optional[str]) -> Optional[datetime]:
    """Časová značka z PostgREST na datetime. Nečitateľnú radšej ignoruj."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _v_buducnosti(value: Optional[str]) -> bool:
    """Je táto značka ešte pred nami? Nečitateľná = nie.

    Pri pochybnosti sa NESPÍ: zle prečítaný dátum smie znamenať nanajvýš to, že
    modelka odpovie, keď nemusela — nie to, že onemie a nikto nevie prečo.
    """
    kedy = _ts(value)
    return bool(kedy and kedy > datetime.now(timezone.utc))


def unseal_eleven_key(
    row: Dict[str, Any],
    encryption_key: str,
    model_id: str = "",
    account_sealed: str = "",
) -> Dict[str, Any]:
    """Riadok `behavior` s ElevenLabs kľúčom v čistom texte.

    Vstup je surový riadok z DB (`eleven_key_enc` + zastaraný `eleven_key`) plus
    šifrovaný kľúč ÚČTU; výstup je ten istý riadok, len s jediným kľúčom, ktorý
    zvyšok workera pozná — `eleven_key`. `eleven_key_enc` sa z výsledku VŽDY
    odstráni, aj keď sa nepodarilo dešifrovať: šifrovaný text nie je použiteľná
    hodnota a nikto ho nemá omylom poslať do ElevenLabs ako kľúč.

    Poradie zdrojov:
      1. `account_sealed` (`accounts.eleven_key_enc`, migrácia 017) — kľúč
         pripojený v nastaveniach účtu, platí pre všetky jeho modelky;
      2. `eleven_key_enc` na modelke — cesta z 014, dnes už len fallback pre
         databázu, v ktorej presun na účet ešte nebežal;
      3. `eleven_key` — čistý text z jednomodelkovej éry (Simona).

    PREČO ÚČET VYHRÁVA A NIE MODELKA. Keby vyhrávala modelka, prepojenie
    v dashboarde by u Simony a Mio nespravilo nič (obe majú starú per-model
    hodnotu z 014) a Marek by hľadal, prečo prekľúčovanie nezabralo. Účet je
    to, čo dnes UI spravuje; per-model stĺpce sú pozostatok, nie override.

    Fail-open: pokazená šifra alebo zlý kľúč znamená prázdny `eleven_key`, teda
    „hlasovky dnes nie sú" — nie pád tenanta. Hlas je bonus, nie podmienka
    (rovnaký sľub má hlavička `eleven.py`).
    """
    out = dict(row)
    model_sealed = str(out.pop("eleven_key_enc", "") or "")

    sealed, kde = (account_sealed, "účtu") if account_sealed else (model_sealed, "modelky")
    if not sealed:
        # Ani jedna šifra — platí zastaraný čistý text (alebo nič).
        return out

    if not encryption_key:
        # Šifrovaný kľúč v DB a worker bez ENCRYPTION_KEY — to je chyba
        # nasadenia, nie dát. Fallback na starý stĺpec je aj tak lepší než nič.
        log.warning(
            "model %s: eleven_key_enc (%s) je v DB, ale worker nemá ENCRYPTION_KEY",
            model_id, kde,
        )
        return out
    from crypto import decrypt

    try:
        out["eleven_key"] = decrypt(sealed, encryption_key)
    except Exception:  # noqa: BLE001 - zlý kľúč nesmie zhodiť tenanta
        log.warning(
            "model %s: eleven_key_enc (%s) sa nedá dešifrovať — hlasovky vypnuté",
            model_id, kde,
        )
        # Pád na nižší zdroj by tu bol tichý downgrade: keď šifra existuje, je
        # to platný kľúč a poškodenú treba vidieť v logu, nie obísť staršou
        # hodnotou, ktorú medzitým mohol majiteľ zmeniť.
        out["eleven_key"] = ""
    return out


class AccountKeyCache:
    """`accounts.eleven_key_enc` jedného účtu — načítaný raz, osviežený po TTL.

    Šifra sa tu nedešifruje; von ide presne to, čo je v DB, a rozbaľuje to až
    `unseal_eleven_key()`. Dôvod je nudný, ale praktický: cache tak nemusí
    poznať `ENCRYPTION_KEY` a v pamäti procesu neleží čistý API kľúč dlhšie,
    než trvá jedno zloženie odpovede.

    Chyba siete NIE JE dôvod vypnúť hlasovky: vtedy platí posledná známa
    hodnota a čas sa neposunie, takže ďalšie volanie to skúsi znova.
    """

    def __init__(self, transport, account_id: str, ttl_s: float = ACCOUNT_KEY_TTL_S) -> None:
        self._t = transport
        self.account_id = account_id or ""
        self._ttl = ttl_s
        self._sealed = ""
        self._at = 0.0

    async def sealed(self) -> str:
        if not self.account_id or self._t is None:
            return ""
        now = time.monotonic()
        if self._at and now - self._at < self._ttl:
            return self._sealed
        try:
            rows = await self._t._get(
                ACCOUNTS, {"id": f"eq.{self.account_id}", "select": "eleven_key_enc"}
            )
        except Exception as exc:  # noqa: BLE001 - výpadok DB nesmie zhodiť odpoveď
            log.warning(
                "účet %s: kľúč ElevenLabs sa nepodarilo načítať (%s) — platí posledný známy",
                self.account_id, exc,
            )
            return self._sealed
        self._sealed = str((rows[0].get("eleven_key_enc") if rows else "") or "")
        self._at = now
        return self._sealed



class PlatformKeyCache:
    """ElevenLabs kľúč PLATFORMY — ten, ktorým hovoria naše managed hlasy.

    PREČO SA BERIE Z ÚČTU SUPERADMINA A NIE Z ENV. Je to ten istý kľúč, ktorý
    má Marek pripojený v nastaveniach účtu. Keby sa musel zapisovať aj do env
    premennej, boli by to dve pravdy — a po prvej výmene kľúča v dashboarde by
    sa rozišli a managed hlasy by ticho prestali fungovať. Takto ho vymení na
    jednom mieste a platí všade.

    Zdieľané cez všetkých tenantov (je to jeden globálny kľúč), preto je cache
    na úrovni modulu, nie inštancie.

    Env `PLATFORM_ELEVEN_KEY` ostáva ako OVERRIDE pre prípad, že by managed
    hlasy mali raz bežať na inom účte než Marekovom.
    """

    def __init__(self, ttl_s: float = ACCOUNT_KEY_TTL_S) -> None:
        self._ttl = ttl_s
        self._key = ""
        self._at = 0.0

    async def key(self, transport, encryption_key: str, override: str = "") -> str:
        if override:
            return override
        if transport is None or not encryption_key:
            return ""

        now = time.monotonic()
        if self._at and now - self._at < self._ttl:
            return self._key

        try:
            rows = await transport._get(
                ACCOUNTS,
                {"role": "eq.superadmin", "select": "eleven_key_enc", "limit": "1"},
            )
        except Exception as exc:  # noqa: BLE001 - výpadok nesmie zhodiť odpoveď
            log.warning("Platformový ElevenLabs kľúč sa nenačítal (%s) — platí posledný", exc)
            return self._key

        sealed = str((rows[0].get("eleven_key_enc") if rows else "") or "")
        if not sealed:
            self._key, self._at = "", now
            return ""

        from crypto import decrypt

        try:
            self._key = decrypt(sealed, encryption_key)
        except Exception as exc:  # noqa: BLE001 - pokazená šifra = hlasovky dnes nie sú
            log.warning("Platformový kľúč sa nepodarilo dešifrovať: %s", exc)
            self._key = ""
        self._at = now
        return self._key


_platform_key = PlatformKeyCache()


class ScheduleCache:
    """Riadok `model_schedule` jednej modelky — načítaný raz, osviežený po TTL.

    Von ide surový riadok, nie `den.Rozvrh`: prekladá ho až volajúci, rovnako
    ako `Behavior.from_row` prekladá riadok `behavior`. Vďaka tomu je toto
    naozaj len cache a `db.py` sa nemusí starať o tvar rozvrhu.

    PRÁZDNY SLOVNÍK ZNAMENÁ NIEČO INÉ NEŽ CHYBA. `{}` je platná odpoveď —
    „táto modelka rozvrh nemá" — a volajúci na ňu odpovie napísanou šablónou.
    Výpadok siete preto NESMIE vrátiť `{}`: vtedy platí posledný známy riadok
    a čas sa neposunie, takže ďalšie volanie to skúsi znova.
    """

    def __init__(self, transport, model_id: str, ttl_s: float = SCHEDULE_TTL_S) -> None:
        self._t = transport
        self.model_id = model_id or ""
        self._ttl = ttl_s
        self._row: Dict[str, Any] = {}
        self._at = 0.0

    async def row(self) -> Dict[str, Any]:
        if not self.model_id or self._t is None:
            return {}
        now = time.monotonic()
        if self._at and now - self._at < self._ttl:
            return self._row
        try:
            rows = await self._t._get(
                SCHEDULE, {"model_id": f"eq.{self.model_id}", "select": "*"}
            )
        except Exception as exc:  # noqa: BLE001 - výpadok DB nesmie zhodiť odpoveď
            log.warning(
                "model %s: rozvrh dňa sa nepodarilo načítať (%s) — platí posledný známy",
                self.model_id, exc,
            )
            return self._row
        self._row = dict(rows[0]) if rows else {}
        self._at = now
        return self._row


class TenantDb:
    def __init__(
        self,
        transport: SupabaseTransport,
        model_id: str,
        encryption_key: str = "",
        account_id: str = "",
        platform_eleven_key: str = "",
    ) -> None:
        self._t = transport
        self.model_id = model_id
        # OVERRIDE platformového kľúča (env `PLATFORM_ELEVEN_KEY`). Prázdne =
        # kľúč sa vezme z účtu superadmina, teda z toho, ktorý je pripojený
        # v dashboarde. Viď `PlatformKeyCache`.
        self._platform_eleven_key = platform_eleven_key
        # Prázdny kľúč je legitímny stav (testy, staré volania): vtedy sa nič
        # nedešifruje a platí zastaraný `eleven_key`.
        self._key = encryption_key
        # Prázdne `account_id` = cache mlčí a platí per-model kľúč. Staré
        # volania (testy) tak fungujú presne ako pred 017.
        self._account_key = AccountKeyCache(transport, account_id)
        # Účet, pod ktorý modelka patrí. Coiny sú spoločné pre všetky modelky
        # jedného klienta, takže zostatok sa číta odtiaľto, nie z modelky.
        self._account_id = account_id or ""
        self._schedule = ScheduleCache(transport, model_id)

    @property
    def _mine(self) -> str:
        """Hodnota filtra `model_id` — píše sa v každom dotaze, nech je to vidieť."""
        return f"eq.{self.model_id}"

    @property
    def _client(self) -> httpx.AsyncClient:
        """Surový klient transportu — pre dotazy s hlavičkami (count, upsert do
        úložiska), ktoré sa cez `_get/_patch/_post` vyjadriť nedajú."""
        return self._t._client

    async def _get(self, path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
        return await self._t._get(path, params)

    async def _patch(self, path: str, params: Dict[str, str], body: Dict[str, Any]) -> None:
        await self._t._patch(path, params, body)

    async def _post(self, path: str, body: Any, upsert: bool = False) -> List[Dict[str, Any]]:
        return await self._t._post(path, body, upsert=upsert)

    # ---------- účet ----------

    async def account_balance_usd(self) -> float:
        """Zostatok kreditu účtu v dolároch. Pri chybe vracia 0.

        Používa to control bot pri dobíjaní — je to informácia pre klienta, nie
        podklad na účtovanie, takže výpadok tu nesmie nič zhodiť. Skutočná
        kreditová brána je `credits.py` a tá si zostatok číta sama.
        """
        if not self._account_id:
            return 0.0
        try:
            rows = await self._get(
                ACCOUNTS,
                {"id": f"eq.{self._account_id}", "select": "credit_balance_usd"},
            )
        except Exception:  # noqa: BLE001
            log.exception("zostatok účtu sa nepodarilo načítať")
            return 0.0
        if not rows:
            return 0.0
        try:
            return float(rows[0].get("credit_balance_usd") or 0)
        except (TypeError, ValueError):
            return 0.0

    # ---------- nastavenia control bota ----------

    async def control_bot_settings(self) -> Dict[str, Any]:
        """Čo má bot hlásiť. Prázdny slovník = platia defaulty z `oznamy`.

        Chýbajúci riadok NIE JE chyba: modelka mohla vzniknúť pred migráciou,
        ktorá tabuľku pridala. Vtedy je lepšie hlásiť podľa rozumného základu
        než nehlásiť nič.
        """
        try:
            rows = await self._get(
                CONTROL_BOT_SETTINGS, {"model_id": self._mine, "select": "*"}
            )
        except Exception:  # noqa: BLE001 — notifikácie nesmú zhodiť odpisovanie
            log.exception("nastavenia control bota sa nepodarilo načítať")
            return {}
        return rows[0] if rows else {}

    async def mark_credits_warned(self, kedy) -> None:
        """Značka upozornenia na kredit. `None` ju zmaže — to je návrat do
        stavu, keď smie prísť ďalšie upozornenie po opätovnom minutí."""
        await self._patch(
            CONTROL_BOT_SETTINGS,
            {"model_id": self._mine},
            {"credits_warned_at": kedy, "updated_at": _now_iso()},
        )

    async def mark_daily_report_sent(self, kedy: str) -> None:
        """Zapíše, kedy report odišiel. Poistka proti dvom za jeden deň —
        bez nej by ho každý reštart workera v aktívnom okne poslal znova."""
        await self._patch(
            CONTROL_BOT_SETTINGS,
            {"model_id": self._mine},
            {"daily_report_sent_at": kedy, "updated_at": _now_iso()},
        )

    async def mark_weekly_report_sent(self, kedy: str) -> None:
        """To isté pre týždenný. Sweeper beží každé tri minúty, takže bez
        vodoznaku by v pondelok po konci okna odišiel tridsaťkrát."""
        await self._patch(
            CONTROL_BOT_SETTINGS,
            {"model_id": self._mine},
            {"weekly_report_sent_at": kedy, "updated_at": _now_iso()},
        )

    # ---------- persona ----------

    async def get_persona(self) -> Dict[str, Any]:
        rows = await self._get(PERSONA, {"model_id": self._mine, "select": "*"})
        return rows[0] if rows else {}

    async def set_persona_field(self, field: str, value: str) -> None:
        await self._patch(
            PERSONA, {"model_id": self._mine}, {field: value, "updated_at": _now_iso()}
        )

    # ---------- chovanie ----------

    async def get_behavior(self) -> Dict[str, Any]:
        """Riadok `behavior` s DEŠIFROVANÝM `eleven_key` (viď hlavičku súboru).

        Jediné miesto, kde sa riadok `behavior` v tomto súbore číta — takže
        seam netreba opakovať nikde inde. `Behavior.from_row()` aj kontrolný
        bot dostanú presne to, čo čakali pred šifrovaním.

        Kľúč účtu ide z cache, takže druhý dotaz do DB tu padne nanajvýš raz za
        `ACCOUNT_KEY_TTL_S`, nie pri každej správe.
        """
        rows = await self._get(BEHAVIOR, {"model_id": self._mine, "select": "*"})
        if not rows:
            return {}
        row = unseal_eleven_key(
            rows[0], self._key, self.model_id, await self._account_key.sealed()
        )
        return await self._apply_managed_voice(row)

    async def _apply_managed_voice(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Keď má modelka vybraný NÁŠ hlas, podstrčí náš kľúč a jeho voice id.

        PREČO TU A NIE PRI GENEROVANÍ. Kľúč aj hlas si zvyšok workera berie
        výhradne z `behavior.eleven_key` / `.eleven_voice_id` — a robí to na
        šiestich rôznych miestach (bežná odpoveď, ukážka, semi-auto, job…).
        Keby sa managed hlas riešil až tam, muselo by sa to ošetriť šesťkrát
        a siedme miesto by na to raz zabudlo. Takto o tom zvyšok kódu nemusí
        vedieť vôbec.

        Fail-safe: keď chýba náš kľúč (env `PLATFORM_ELEVEN_KEY`) alebo hlas
        v `managed_voices` nie je či je vypnutý, kľúč sa VYPRÁZDNI. To znamená
        „hlasovky dnes nie sú" a modelka pošle text — nie pád a nie ticho
        prepnutie späť na klientov kľúč, ktorý si pre tento hlas nevybral.
        """
        if str(row.get("voice_source") or "own") != "managed":
            return row

        row["eleven_key"] = ""
        row["eleven_voice_id"] = ""

        platform_key = await _platform_key.key(
            self._t, self._key, self._platform_eleven_key
        )
        if not platform_key:
            log.warning(
                "Managed hlas je vybraný, ale platformový ElevenLabs kľúč chýba "
                "— pripoj ho v nastaveniach účtu superadmina"
            )
            return row

        voice_id = row.get("managed_voice_id")
        if not voice_id:
            return row
        try:
            eleven_id = await self.managed_voice(str(voice_id))
        except Exception as exc:  # noqa: BLE001 - hlas je bonus, nie podmienka
            log.warning("Managed hlas sa nenačítal: %s", exc)
            return row

        if not eleven_id:
            log.warning("Managed hlas %s neexistuje alebo je vypnutý", voice_id)
            return row

        row["eleven_key"] = platform_key
        row["eleven_voice_id"] = eleven_id
        return row

    async def managed_voice(self, voice_id: str) -> str:
        """`eleven_voice_id` zapnutého hlasu z NÁŠHO katalógu, inak prázdne.

        `managed_voices` je globálny číselník našich hlasov — zámerne NIE je
        filtrovaný podľa `model_id`. Nie sú v ňom tenantské dáta; je to zoznam
        hlasov, ktoré ponúkame všetkým rovnako.
        """
        rows = await self._get(
            MANAGED_VOICES,
            {"id": f"eq.{voice_id}", "active": "is.true", "select": "eleven_voice_id"},
        )
        if not rows:
            return ""
        return str(rows[0].get("eleven_voice_id") or "")

    async def set_behavior_field(self, field: str, value: Any) -> None:
        await self._patch(
            BEHAVIOR, {"model_id": self._mine}, {field: value, "updated_at": _now_iso()}
        )

    # ---------- rozvrh dňa ----------

    async def get_schedule(self) -> Dict[str, Any]:
        """Riadok `model_schedule` (migrácia 022). `{}` = modelka rozvrh nemá.

        Prekladá ho `den.Rozvrh.from_row()`; `{}` tam znamená „platí napísaná
        šablóna", takže modelka bez riadku má presne ten deň, aký mala pred
        022. Ide z cache — pri každej odpovedi sa tak nepýtame na niečo, čo sa
        mení raz za týždeň.
        """
        return await self._schedule.row()

    # ---------- párovanie kontrolného bota ----------

    async def pair_control_bot(self, code: str, chat_id: int) -> bool:
        """Spotrebuje párovací kód a zapíše `models.owner_chat_id`.

        Vráti `True`, len ak kód pre TÚTO modelku existoval, nebol použitý a
        nevypršal. Všetko ostatné (neznámy kód, cudzí kód, druhé použitie) je
        `False` — volajúci na to musí odpovedať rovnako (mlčaním), inak by bot
        cudziemu chatu prezradil, ktoré kódy existujú.

        Je to jedno RPC (migrácia 020), nie dva PostgREST dotazy: označenie kódu
        za použitý a zápis majiteľa musia byť jedna transakcia, inak by pri páde
        medzi nimi ostal kód minutý a majiteľ nenastavený.
        """
        return bool(
            await self._t._rpc(
                "pair_control_bot",
                {"p_model": self.model_id, "p_code": code, "p_chat": int(chat_id)},
            )
        )

    # ---------- globálne nastavenia ----------

    async def is_paused(self) -> bool:
        """Spí modelka? Ručná pauza BEZ konca, alebo uspatie na pár hodín.

        Sú to dve polia, lebo sú to dve rozhodnutia. `ai_paused` platí, kým ju
        niekto nevypne — a presne na to sa zabúda. `paused_until` sa zobudí samo
        a je to jediné, čo klient chce, keď ide na tri hodiny preč.
        """
        rows = await self._get(
            SETTINGS, {"model_id": self._mine, "select": "ai_paused,paused_until"}
        )
        row = rows[0] if rows else {}
        if row.get("ai_paused"):
            return True
        return _v_buducnosti(row.get("paused_until"))

    async def set_paused(self, paused: bool) -> None:
        """Ručná pauza. Zapnutie ruší uspatie a naopak — dve pauzy naraz by
        znamenali, že zobudenie ticho nezaberie."""
        await self._patch(
            SETTINGS, {"model_id": self._mine}, {"ai_paused": paused, "paused_until": None}
        )

    async def sleep_until(self, until_iso: Optional[str]) -> None:
        """Uspí do daného času (alebo zobudí, keď príde None)."""
        await self._patch(
            SETTINGS,
            {"model_id": self._mine},
            {"paused_until": until_iso, "ai_paused": False},
        )

    async def sleeping_until(self) -> Optional[str]:
        """Do kedy spí. None = nespí (alebo je to ručná pauza bez konca)."""
        rows = await self._get(SETTINGS, {"model_id": self._mine, "select": "paused_until"})
        hodnota = (rows[0].get("paused_until") if rows else None) or None
        return hodnota if _v_buducnosti(hodnota) else None

    # ---------- flood pauza (oddelená od ručnej!) ----------

    async def flood_until(self) -> Optional[str]:
        """Do kedy si Telegram vypýtal ticho. None = neplatí žiadna pauza.

        ZÁMERNE to NIE JE `ai_paused`. Tá je ručná pauza majiteľa a prepnutie
        režimu odpovedania ju právom zhadzuje — lenže do nej doteraz padala aj
        24-hodinová ochrana po `PeerFloodError`. Klik v menu tak ticho rušil to
        najvážnejšie varovanie, aké Telegram dá.
        """
        rows = await self._get(SETTINGS, {"model_id": self._mine, "select": "flood_until"})
        return (rows[0].get("flood_until") if rows else None) or None

    async def set_flood_until(self, until_iso: Optional[str]) -> None:
        """Zapíše (alebo zruší) flood pauzu. Prežije reštart aj presun repliky."""
        await self._patch(SETTINGS, {"model_id": self._mine}, {"flood_until": until_iso})

    # ---------- režim odpovedania (Telegram) ----------

    async def tg_reply_mode(self) -> Dict[str, Any]:
        """Telegram režim + čas fallbacku. `mode` ∈ off|auto|semi (default auto),
        `fallback_minutes` = int alebo None (nikdy)."""
        rows = await self._get(
            SETTINGS,
            {"model_id": self._mine, "select": "tg_reply_mode,tg_fallback_minutes"},
        )
        row = rows[0] if rows else {}
        mins = row.get("tg_fallback_minutes")
        return {
            "mode": str(row.get("tg_reply_mode") or "auto"),
            "fallback_minutes": int(mins) if mins not in (None, "") else None,
        }

    async def set_tg_reply_mode(self, mode: str) -> None:
        """Nastaví Telegram režim. Pri auto/semi zároveň zhodí RUČNÚ pauzu
        (`ai_paused`) — majiteľ vedome zapína, takže jeho vlastná pauza
        z minulosti nesmie ticho blokovať.

        `flood_until` sa NEDOTÝKA a nikdy nesmie. To nie je pauza majiteľa, ale
        varovanie od Telegramu; zrušiť ho klikom v menu je najrýchlejšia cesta
        k zablokovaniu účtu."""
        body: Dict[str, Any] = {"tg_reply_mode": mode}
        if mode in ("auto", "semi"):
            body["ai_paused"] = False
        await self._patch(SETTINGS, {"model_id": self._mine}, body)

    async def set_tg_fallback_minutes(self, minutes: Optional[int]) -> None:
        await self._patch(
            SETTINGS, {"model_id": self._mine}, {"tg_fallback_minutes": minutes}
        )

    async def fanvue_reply_mode(self) -> Dict[str, Any]:
        """Fanvue režim + čas fallbacku (na poller a control bota). Riadok
        `fanvue` nemusí existovať (nepripojené) — vtedy default auto/None."""
        rows = await self._get(
            "/fanvue",
            {"model_id": self._mine, "select": "reply_mode,fallback_minutes,connected"},
        )
        row = rows[0] if rows else {}
        mins = row.get("fallback_minutes")
        return {
            "mode": str(row.get("reply_mode") or "auto"),
            "fallback_minutes": int(mins) if mins not in (None, "") else None,
            # Či je Fanvue vôbec pripojené — control bot podľa toho ukáže/skryje
            # prepínač (bez pripojenia nemá čo prepínať).
            "connected": bool(row.get("connected")) if rows else False,
        }

    async def set_fanvue_reply_mode(self, mode: str) -> None:
        await self._patch("/fanvue", {"model_id": self._mine}, {"reply_mode": mode})

    # ---------- schvaľovacia fronta (semi-auto) ----------

    async def create_pending(
        self,
        *,
        channel: str,
        conv_key: str,
        suggestions: List[str],
        incoming_preview: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Zapíše nový čakajúci návrh. Vráti riadok (s `id`) alebo None."""
        rows = await self._post(
            PENDING,
            {
                "model_id": self.model_id,
                "channel": channel,
                "conv_key": str(conv_key),
                "suggestions": suggestions,
                "incoming_preview": incoming_preview[:400],
            },
        )
        return rows[0] if rows else None

    async def get_pending(self, pending_id: str) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            PENDING, {"model_id": self._mine, "id": f"eq.{pending_id}", "select": "*"}
        )
        return rows[0] if rows else None

    async def claim_pending(self, pending_id: str) -> bool:
        """Atomicky zoberie awaiting návrh (→ sent). False = medzitým sa
        rozhodlo inak (klik vs. poller vs. supersede)."""
        r = await self._client.patch(
            PENDING,
            params={
                "model_id": self._mine,
                "id": f"eq.{pending_id}",
                "status": "eq.awaiting",
            },
            json={"status": "sent", "decided_at": _now_iso(), "updated_at": _now_iso()},
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        return bool(r.json())

    async def mark_pending(self, pending_id: str, status: str, **fields: Any) -> None:
        """Zapíše konečný stav (skipped/superseded) + prípadné detaily odoslania."""
        body: Dict[str, Any] = {"status": status, "updated_at": _now_iso()}
        if status in ("sent", "skipped", "superseded"):
            body["decided_at"] = _now_iso()
        body.update({k: v for k, v in fields.items() if v is not None})
        await self._patch(PENDING, {"model_id": self._mine, "id": f"eq.{pending_id}"}, body)

    async def supersede_open(self, channel: str, conv_key: str) -> List[Dict[str, Any]]:
        """Uzavrie všetky otvorené awaiting pre konverzáciu (→ superseded).
        Vráti uzavreté riadky (majú `control_msg_id` na zrušenie karty)."""
        r = await self._client.patch(
            PENDING,
            params={
                "model_id": self._mine,
                "channel": f"eq.{channel}",
                "conv_key": f"eq.{conv_key}",
                "status": "eq.awaiting",
            },
            json={"status": "superseded", "updated_at": _now_iso()},
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        return r.json() or []

    async def awaiting_pending(self, channel: str = "") -> List[Dict[str, Any]]:
        """Otvorené čakajúce návrhy modelky (na obnovu po štarte aj pre poller)."""
        params = {
            "model_id": self._mine,
            "status": "eq.awaiting",
            "select": "*",
            "order": "created_at.asc",
        }
        if channel:
            params["channel"] = f"eq.{channel}"
        return await self._get(PENDING, params)

    # ---------- užívatelia ----------

    async def get_user(self, tg_id: int) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            USERS, {"model_id": self._mine, "tg_id": f"eq.{tg_id}", "select": "*"}
        )
        return rows[0] if rows else None

    async def ensure_user(
        self,
        tg_id: int,
        username: Optional[str],
        first_name: Optional[str],
        lang: Optional[str],
    ) -> Dict[str, Any]:
        """Vytvorí užívateľa, ak neexistuje; inak osvieži meta údaje."""
        existing = await self.get_user(tg_id)
        meta = {"username": username, "first_name": first_name, "lang": lang}
        if existing:
            changed = {k: v for k, v in meta.items() if v and existing.get(k) != v}
            if changed:
                await self.update_user(tg_id, changed)
                existing.update(changed)
            return existing
        rows = await self._post(USERS, {"model_id": self.model_id, "tg_id": tg_id, **meta})
        return rows[0] if rows else {"model_id": self.model_id, "tg_id": tg_id, **meta}

    async def update_user(self, tg_id: int, patch: Dict[str, Any]) -> None:
        await self._patch(USERS, {"model_id": self._mine, "tg_id": f"eq.{tg_id}"}, patch)

    async def claim_message(self, tg_id: int, message_id: int) -> bool:
        """Zaberie správu na spracovanie. `False` = už ju má niekto iný.

        PREČO ZÁMOK A NIE KONTROLA. Vodoznak `last_msg_id` sa dal čítať a
        porovnať, lenže medzi čítaním a zápisom sa zmestí druhý proces —
        a práve pri výmene lease bežia dve repliky naraz až 30 s (`main._fence`
        zastaví tú starú až pri jej najbližšom heartbeate). Obe by porovnanie
        prešli a obe by odpovedali.

        Tu je to JEDEN príkaz: posuň vodoznak, ale len ak je nižší. Podmienku
        vyhodnocuje Postgres nad zamknutým riadkom, takže ju môže vyhrať práve
        jeden volajúci — druhý dostane prázdnu odpoveď a mlčí.

        `is.null` je v podmienke kvôli novým konverzáciám: `lt` na NULL nesedí,
        a bez tejto vetvy by prvá správa od nového človeka nikdy neprešla.
        """
        rows = await self._t._patch_returning(
            USERS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "or": f"(last_msg_id.is.null,last_msg_id.lt.{int(message_id)})",
                "select": "tg_id",
            },
            {"last_msg_id": int(message_id)},
        )
        return bool(rows)

    async def find_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "username": f"ilike.{username.lstrip('@')}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def wipe_conversation(self, tg_id: int) -> int:
        """Vymaže históriu a vynuluje stav jednej konverzácie.

        Slúži na testovanie: po tomto sa daný človek chová ako úplne nový.
        Vracia počet zmazaných správ.
        """
        before = await self.recent_messages(tg_id, 10_000)
        # Archív správ, záznamy o poslaných fotkách a hlasovkách — inak by po
        # vymazaní dostal iba tie, ktoré ešte nevidel, a testovať sa to nedá.
        #
        # A hlavne CELÁ pamäť. Kým sa mazali len správy, ostávali po nej fakty,
        # epizódy, sľuby aj tvrdenia — takže „úplne nový človek" si po prvej
        # správe pamätal, čím sa živí a čo si o sebe povedali. Na jednom
        # testovacom účte tak zostalo jedenásť tvrdení pri nula správach.
        for path in (MESSAGES, PHOTO_SENDS, VOICE_SENDS, FACTS, EPISODES, LOOPS, CLAIMS):
            r = await self._client.delete(
                path, params={"model_id": self._mine, "tg_id": f"eq.{tg_id}"}
            )
            r.raise_for_status()
        await self.update_user(
            tg_id,
            {
                "msg_count": 0,
                "funnel_stage": "cold",
                "summary": "",
                "summary_at_msg": 0,
                "style_note": "",
                "partner_name": "",
                "name_asked": False,
                "asked_topics": {},
                "used_gags": {},
                # `last_msg_id` sa NEVYNULUJE. Telegram si históriu drží aj po
                # vymazaní našej — a Reconciler by pri nule stiahol späť
                # posledných tridsať správ a odpovedal na ne, akoby prišli
                # teraz. Presne to sa stalo: po vyčistení chatu dorazilo dvanásť
                # starých správ naraz a vyzeralo to, že píše sama od seba.
                "link_sent_at": None,
                "link_push_count": 0,
                "paid": False,
                "human_takeover": False,
                "pending_reply": False,
                "reply_after": None,
                "notified": False,
                "last_incoming_at": None,
                "last_reply_at": None,
                "last_photo_at": None,
                "last_voice_at": None,
                "last_outreach_at": None,
                "outreach_silent": 0,
                "tidied_at": None,
                # Vyčistený chat začína odznova, vrátane okna konverzácie —
                # inak by na prvú novú správu prišla rovno rozlúčka.
                "farewell_at": None,
            },
        )
        return len(before)

    async def links_sent_since(self, since_iso: str) -> int:
        """Koľko odkazov išlo od daného času — naprieč všetkými konverzáciami.

        Počíta sa z DB, nie z pamäte procesu, aby to prežilo restart na Railway.
        """
        r = await self._client.get(
            USERS,
            params={
                "model_id": self._mine,
                "link_sent_at": f"gte.{since_iso}",
                "select": "tg_id",
            },
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    async def active_chats(self, since_iso: str, limit: int = 200) -> List[int]:
        """Kto má práve otvorený rozhovor — jeho alebo jej správa je čerstvá.

        Berie sa aj jej odpoveď, nielen jeho správa: keď odpísala pred piatimi
        minútami a on ešte nereagoval, rozhovor beží a miesto je obsadené.
        """
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "tg_id",
                "or": f"(last_incoming_at.gte.{since_iso},last_reply_at.gte.{since_iso})",
                "limit": str(limit),
            },
        )
        return [int(r["tg_id"]) for r in rows if r.get("tg_id") is not None]

    async def people_since(self, since_iso: str) -> List[int]:
        """Komu z účtu odišla správa od daného času — zoznam tg_id.

        Samotný počet správ nestačí: tridsať správ dvom ľuďom je človek, ktorý
        sa rozpísal, kým tridsať správ tridsiatim ľuďom je obchôdzka. Práve to
        druhé je vzor, na ktorý Telegram reaguje.
        """
        rows = await self._get(
            MESSAGES,
            {
                "model_id": self._mine,
                "role": "eq.assistant",
                "created_at": f"gte.{since_iso}",
                "select": "tg_id",
                "limit": "2000",
            },
        )
        return [int(r["tg_id"]) for r in rows if r.get("tg_id") is not None]

    async def replies_since(self, since_iso: str) -> int:
        """Koľko správ z účtu odišlo od daného času — naprieč konverzáciami.

        Čítač v pamäti procesu je po každom deployi prázdny, takže sa hodinový
        strop dal reštartom vynulovať. Toto to prežije, lebo sa počíta z
        archívu odoslaných správ.
        """
        r = await self._client.get(
            MESSAGES,
            params={
                "model_id": self._mine,
                "role": "eq.assistant",
                "created_at": f"gte.{since_iso}",
                "select": "id",
            },
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    async def recent_conversations(self, limit: int = 10) -> List[Dict[str, Any]]:
        return await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "order": "last_incoming_at.desc.nullslast",
                "limit": str(limit),
            },
        )

    async def sessions_to_close(
        self, gap_hours: int = 6, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Sedenia, ktoré dozneli a ešte nie sú zapísané ako epizóda.

        Epizóda sa doteraz písala len vtedy, keď človek po dlhom tichu napísal
        znova — takže kto sa neozval, o tom nebol záznam. Naživo z toho vyšlo
        pol epizódy na konverzáciu a celá vrstva pamäte, po ktorej má ostať
        pocit „ona si ma pamätá", bola prakticky prázdna.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=gap_hours)
        ).isoformat()
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "last_incoming_at": f"lt.{cutoff}",
                "order": "last_incoming_at.desc",
                "limit": str(limit * 6),
            },
        )
        cakaju = [
            r for r in rows
            if int(r.get("msg_count") or 0) >= 3
            and not (r.get("episode_at") or "") >= (r.get("last_incoming_at") or "")
        ]
        return cakaju[:limit]

    async def pending_users(self) -> List[Dict[str, Any]]:
        return await self._get(
            USERS,
            {"model_id": self._mine, "pending_reply": "is.true", "select": "*", "limit": "50"},
        )

    async def outreach_candidates(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Ľudia, ktorých sa ráno oplatí osloviť — filtrovanie robí `outreach`."""
        return await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "order": "last_incoming_at.desc",
                "limit": str(limit),
                "last_incoming_at": "not.is.null",
            },
        )

    async def unanswered_users(
        self, limit: int = 50, stale_hours: int = 48
    ) -> List[Dict[str, Any]]:
        """Ľudia, ktorých posledná správa ostala bez odpovede.

        Nezávisí to na príznaku `pending_reply` — ten sa dá stratiť (pád workera
        v nesprávnom momente, ručný zásah v DB). Toto je sieť pod tým: porovná
        sa čas jeho poslednej správy s časom jej poslednej odpovede, takže sa
        nikto nestratí ani po restarte.

        Staré správy sa ale nechávajú tak. Reconciler po štarte správne
        rozhodne, že na štyri dni starú správu sa už neodpisuje — a táto sieť
        ho potom prebila a odpísala aj tak. Odpoveď na štyri dni starý pozdrav
        vyzerá horšie než žiadna.
        """
        rows = await self._get(
            USERS,
            {
                "model_id": self._mine,
                "select": "*",
                "order": "last_incoming_at.desc",
                "limit": str(limit),
                "last_incoming_at": "not.is.null",
            },
        )
        hranica = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
        waiting = []
        for row in rows:
            if row.get("human_takeover") or not row.get("ai_enabled", True):
                continue
            incoming = _ts(row.get("last_incoming_at"))
            replied = _ts(row.get("last_reply_at"))
            if not incoming or incoming < hranica:
                continue
            if replied is None or replied < incoming:
                waiting.append(row)
        return waiting

    # ---------- správy ----------

    async def add_message(self, tg_id: int, role: str, content: str) -> None:
        await self._post(
            MESSAGES,
            {"model_id": self.model_id, "tg_id": tg_id, "role": role, "content": content},
        )

    async def recent_messages(self, tg_id: int, limit: int) -> List[Dict[str, Any]]:
        """Posledných `limit` správ v chronologickom poradí."""
        rows = await self._get(
            MESSAGES,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "role,content,created_at",
                "order": "id.desc",
                "limit": str(limit),
            },
        )
        return list(reversed(rows))

    # ---------- fakty ----------

    async def facts_for(self, tg_id: int) -> List[Dict[str, Any]]:
        return await self._get(
            FACTS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "*",
                "order": "id.asc",
                "limit": "200",
            },
        )

    async def apply_facts(self, tg_id: int, plan: Dict[str, Any]) -> None:
        """Append-only zápis: staré fakty sa neprepisujú, len odkladajú."""
        for fact_id in plan.get("confirms", []):
            await self._patch(
                FACTS,
                {"model_id": self._mine, "id": f"eq.{fact_id}"},
                {"last_confirmed": _now_iso()},
            )
        new_rows = [
            {"model_id": self.model_id, "tg_id": tg_id, "key": item["key"], "value": item["value"]}
            for item in plan.get("inserts", [])
        ]
        created = await self._post(FACTS, new_rows) if new_rows else []
        marker = created[0]["id"] if created else None
        for fact_id in plan.get("supersedes", []):
            await self._patch(
                FACTS, {"model_id": self._mine, "id": f"eq.{fact_id}"}, {"superseded_by": marker}
            )

    # ---------- epizódy a sľuby ----------

    async def add_episode(self, tg_id: int, episode: Dict[str, Any]) -> None:
        await self._post(EPISODES, {"model_id": self.model_id, "tg_id": tg_id, **episode})

    async def episodes_for(self, tg_id: int, limit: int = 4) -> List[Dict[str, Any]]:
        rows = await self._get(
            EPISODES,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "*",
                "order": "ended_at.desc",
                "limit": str(limit),
            },
        )
        return list(reversed(rows))

    async def open_loops(self, tg_id: int) -> List[Dict[str, Any]]:
        return await self._get(
            LOOPS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "closed_at": "is.null",
                "select": "*",
                "limit": "10",
            },
        )

    async def add_loop(self, tg_id: int, what: str) -> None:
        await self._post(LOOPS, {"model_id": self.model_id, "tg_id": tg_id, "what": what})

    async def close_loop(self, loop_id: int) -> None:
        await self._patch(
            LOOPS, {"model_id": self._mine, "id": f"eq.{loop_id}"}, {"closed_at": _now_iso()}
        )

    async def search_archive(self, tg_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fulltext nad celou históriou — archív prestáva byť mŕtvy náklad."""
        if not query.strip():
            return []
        rows = await self._t._rpc(
            "search_messages",
            {"p_model": self.model_id, "p_tg_id": tg_id, "p_query": query, "p_limit": limit},
        )
        return rows or []

    # ---------- čo o sebe natvrdila ----------

    async def self_claims(self, tg_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        return await self._get(
            CLAIMS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "*",
                "order": "said_at.desc",
                "limit": str(limit),
            },
        )

    async def add_self_claim(self, tg_id: int, claim: str) -> None:
        await self._post(CLAIMS, {"model_id": self.model_id, "tg_id": tg_id, "claim": claim})

    async def log_judge(self, tg_id: int, draft: str, fixed: str, reason: str) -> None:
        await self._post(JUDGE_LOG, {"model_id": self.model_id, "tg_id": tg_id,
                                     "draft": draft[:1000],
                                     "fixed": fixed[:1000], "reason": reason[:300]})

    async def tidy_facts(self, tg_id: int) -> int:
        """Nočné čistenie faktov. Soft-delete: staré sa označia, nikdy nemažú.

        Rieši to, čo sa do databázy dostalo predtým, než začali platiť uzavreté
        kľúče a zlučovanie podľa významu:

          * **okamihy uložené ako trvalé fakty** — „leží na gauči a pozerá
            seriál" bolo naživo zapísané pod štyrmi kľúčmi naraz. Ako fakt to
            neplatí ani o hodinu.
          * **tá istá vec pod dvoma kľúčmi** — `past_locations` aj
            `previous_locations` s rovnakou hodnotou. Zlučovanie porovnávalo
            kľúče, takže sa tie dva nikdy nestretli.
        """
        import facts as facts_mod
        import similar

        rows = await self.facts_for(tg_id)
        active = sorted(
            (f for f in rows if f.get("superseded_by") is None),
            key=lambda f: f["id"],
        )
        merged = 0
        ponechane: List[Dict[str, Any]] = []
        for fact in active:
            key, value = fact.get("key") or "", (fact.get("value") or "").strip()
            if not value or facts_mod.is_transient(key, value):
                # Okamih nemá čím nahradiť — odloží sa sám sebou, aby sa
                # zachovalo, že tam raz bol, ale do promptu už nešiel.
                await self._patch(
                    FACTS,
                    {"model_id": self._mine, "id": f"eq.{fact['id']}"},
                    {"superseded_by": fact["id"]},
                )
                merged += 1
                continue
            dvojnik = next(
                (f for f in ponechane if similar.same_idea(value, f["value"])), None
            )
            if dvojnik is not None:
                await self._patch(
                    FACTS,
                    {"model_id": self._mine, "id": f"eq.{dvojnik['id']}"},
                    {"superseded_by": fact["id"]},
                )
                ponechane.remove(dvojnik)
                merged += 1
            ponechane.append({"id": fact["id"], "value": value})
        await self.update_user(tg_id, {"tidied_at": _now_iso()})
        return merged

    # ---------- fotky ----------

    async def photo_library(self) -> List[Dict[str, Any]]:
        return await self._get(
            PHOTOS,
            {"model_id": self._mine, "select": "*", "active": "is.true", "order": "id.asc"},
        )

    async def photos_sent_to(self, tg_id: int) -> List[int]:
        """Fotky, ktoré už tento človek videl — od najnovšej.

        Na poradí záleží: podľa poslednej poslanej sa vyberá ďalšia z tej istej
        kolekcie, aby po fotke z postele neprišla fotka z párty.
        """
        rows = await self._get(
            PHOTO_SENDS,
            {
                "model_id": self._mine,
                "tg_id": f"eq.{tg_id}",
                "select": "photo_id,sent_at",
                "order": "sent_at.desc",
            },
        )
        return [int(r["photo_id"]) for r in rows]

    async def voice_library(self) -> List[Dict[str, Any]]:
        """Hlasovky pripravené na posielanie.

        Pevné políčka bez nahratého zvuku majú prázdne `url` — tie sa
        preskakujú, inak by sa modelka pokúsila poslať prázdnu nahrávku.
        """
        rows = await self._get(
            VOICES, {"model_id": self._mine, "active": "is.true", "select": "*", "order": "id"}
        )
        return [r for r in rows if (r.get("url") or "").strip()]

    async def voices_sent_to(self, tg_id: int) -> List[int]:
        rows = await self._get(
            VOICE_SENDS,
            {"model_id": self._mine, "tg_id": f"eq.{tg_id}", "select": "voice_id"},
        )
        return [int(r["voice_id"]) for r in rows]

    async def record_voice_send(self, voice_id: int, tg_id: int) -> None:
        """Zápis, že túto nahrávku už počul — druhýkrát ju nedostane."""
        # Zloženému PK (model_id, voice_id, tg_id) stačí PostgREST default —
        # `resolution=merge-duplicates` si konflikt odvodí z primárneho kľúča.
        await self._post(
            VOICE_SENDS,
            {"model_id": self.model_id, "voice_id": voice_id, "tg_id": tg_id},
            upsert=True,
        )
        await self._client.patch(
            VOICES,
            params={"model_id": self._mine, "id": f"eq.{voice_id}"},
            # Predtým sa sem zapisovala natvrdo jednotka, takže štatistika
            # hlasoviek ukazovala 1 aj po stovke odoslaní.
            json={"sent_count": await self._voice_count(voice_id)},
            headers={"Prefer": "return=minimal"},
        )

    async def _voice_count(self, voice_id: int) -> int:
        r = await self._client.get(
            VOICE_SENDS,
            params={"model_id": self._mine, "voice_id": f"eq.{voice_id}", "select": "tg_id"},
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    async def record_photo_send(self, photo_id: int, tg_id: int) -> None:
        """Zápis, že táto fotka už tomuto človeku odišla — druhýkrát nepôjde."""
        await self._post(
            PHOTO_SENDS,
            {"model_id": self.model_id, "photo_id": photo_id, "tg_id": tg_id},
            upsert=True,
        )
        await self._client.patch(
            PHOTOS,
            params={"model_id": self._mine, "id": f"eq.{photo_id}"},
            json={"sent_count": await self._photo_count(photo_id)},
        )

    async def _photo_count(self, photo_id: int) -> int:
        r = await self._client.get(
            PHOTO_SENDS,
            params={"model_id": self._mine, "photo_id": f"eq.{photo_id}", "select": "tg_id"},
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        r.raise_for_status()
        return int(r.headers.get("content-range", "*/0").split("/")[-1])

    # ---------- vyrobené hlasovky ----------

    async def upload_voice(self, path: str, data: bytes) -> str:
        """Uloží nahrávku do úložiska a vráti verejnú adresu.

        Prázdny reťazec = nepodarilo sa. Archív je bonus: keď zlyhá, hlasovka
        aj tak odíde klientovi, len ju majiteľ neuvidí v dashboarde.

        Cestu skladá volajúci a už je tenant-unikátna (`cfg.supabase_schema`
        == model_id), preto sa tu žiadna predpona nepridáva.
        """
        base = str(self._client.base_url).rsplit("/rest/v1", 1)[0]
        try:
            r = await self._client.post(
                f"{base}/storage/v1/object/{VOICE_BUCKET}/{path}",
                content=data,
                headers={"Content-Type": "audio/ogg", "x-upsert": "true"},
            )
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - archív nesmie zdržať odpoveď
            log.warning("Hlasovku sa nepodarilo uložiť (%s): %s", path, exc)
            return ""
        return f"{base}/storage/v1/object/public/{VOICE_BUCKET}/{path}"

    async def add_voice_clip(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            rows = await self._post(VOICE_CLIPS, {"model_id": self.model_id, **row})
        except Exception as exc:  # noqa: BLE001
            log.warning("Záznam o hlasovke sa nepodarilo zapísať: %s", exc)
            return None
        return rows[0] if rows else None

    async def voice_clips(self, limit: int = 60) -> List[Dict[str, Any]]:
        return await self._get(
            VOICE_CLIPS,
            {"model_id": self._mine, "select": "*", "order": "id.desc", "limit": str(limit)},
        )

    # ---------- fronta na ukážky z dashboardu ----------
    #
    # Worker na Railway nemá port — je to worker, nie web služba, takže HTTP
    # endpoint by znamenal prerobiť ju na web s doménou. Fronta v databáze to
    # celé obchádza: dashboard vloží riadok, worker ho spracuje a zapíše adresu
    # hotového súboru. Ako bonus je ukážka vyrobená presne tým istým reťazcom
    # ako ostrá hlasovka, takže sa nemôžu rozísť.

    async def pending_voice_job(self) -> Optional[Dict[str, Any]]:
        rows = await self._get(
            VOICE_JOBS,
            {
                "model_id": self._mine,
                "status": "eq.pending",
                "select": "*",
                "order": "id.asc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def claim_voice_job(self, job_id: int) -> bool:
        """Označí prácu za rozrobenú. False = medzitým ju vzal niekto iný."""
        r = await self._client.patch(
            VOICE_JOBS,
            params={"model_id": self._mine, "id": f"eq.{job_id}", "status": "eq.pending"},
            json={"status": "working"},
            headers={"Prefer": "return=representation"},
        )
        r.raise_for_status()
        return bool(r.json())

    async def finish_voice_job(self, job_id: int, url: str = "", error: str = "") -> None:
        await self._patch(
            VOICE_JOBS,
            {"model_id": self._mine, "id": f"eq.{job_id}"},
            {
                "status": "error" if error else "done",
                "url": url,
                "error": error[:300],
                "done_at": _now_iso(),
            },
        )

    async def add_voice_job(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self._post(VOICE_JOBS, {"model_id": self.model_id, **row})
        return rows[0] if rows else None

    # ---------- štatistika ----------

    async def stats(self) -> Dict[str, int]:
        async def count(params: Dict[str, str]) -> int:
            r = await self._client.get(
                USERS,
                params={"model_id": self._mine, **params, "select": "tg_id"},
                headers={"Prefer": "count=exact", "Range": "0-0"},
            )
            r.raise_for_status()
            return int(r.headers.get("content-range", "*/0").split("/")[-1])

        return {
            "users": await count({}),
            "warm": await count({"funnel_stage": "eq.warm"}),
            "link_sent": await count({"funnel_stage": "eq.link_sent"}),
            "converted": await count({"funnel_stage": "eq.converted"}),
            "takeover": await count({"human_takeover": "is.true"}),
        }

    async def stats_od(self, since_iso: str) -> Dict[str, int]:
        """Čísla za obdobie, nie za celý život účtu.

        Celkové čísla po pár mesiacoch prestanú hovoriť čokoľvek — rastú aj
        vtedy, keď sa posledný týždeň nedialo nič. Toto je to, čo sa naozaj
        stalo za dané obdobie.
        """
        async def count(params: Dict[str, str]) -> int:
            r = await self._client.get(
                USERS,
                params={"model_id": self._mine, **params, "select": "tg_id"},
                headers={"Prefer": "count=exact", "Range": "0-0"},
            )
            r.raise_for_status()
            return int(r.headers.get("content-range", "*/0").split("/")[-1])

        od = f"gte.{since_iso}"
        return {
            "novi": await count({"created_at": od}),
            "odkazy": await count({"link_sent_at": od}),
            "platiaci": await count({"paid": "is.true"}),
            "zavrete": await count({"farewell_at": od}),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
