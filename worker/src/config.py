"""Načítanie a validácia konfigurácie z env premenných.

Multi-tenant verzia predlohy (`telegram/src/config.py`): tam bol jeden Config,
ktorý miešal globálne veci (Supabase, LLM kľúče) s per-model vecami (TG
session, bot token). Tu je to rozdelené na dve triedy:

- `Config` — globálne, jeden na worker proces (jeden Supabase projekt,
  jeden fallback LLM kľúč, atď.).
- `TenantConfig` — per-tenant, poskladaný z riadku `models` tabuľky +
  zdedených globálnych defaultov. Moduly portované z predlohy (userbot.py,
  control_bot.py, ...) čítajú `cfg.<atribút>` presne tak ako predtým — teraz
  im ale prde `TenantConfig`, takže musí niesť všetko, čo tie moduly čítajú.
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from crypto import decrypt

# Atlas Cloud — Marek ho už používa na obrázky/video, hostuje aj Grok.
# Endpoint je OpenAI-kompatibilný, takže rovnaký klient funguje aj pre OpenRouter či xAI.
_DEFAULT_BASE_URL = "https://api.atlascloud.ai/v1"
_DEFAULT_MODEL = "xai/grok-4.5"


class BadModelRow(ValueError):
    """Riadok `models`, z ktorého sa nedá poskladať beh — aj s názvom stĺpca.

    Existuje kvôli jednej vete v logu. Keď `TenantConfig.from_row` padne, pool
    model odstaví a doteraz o tom napísal len „neplatný riadok — odstavujem"
    plus traceback z `int(None)`. Z toho sa nedalo prečítať, KTORÝ stĺpec
    chýbal, takže sa to muselo dohľadávať ručne v databáze. `field` ide aj do
    `status_reason` (`bad_config:tg_api_id`), nech to klient aj admin vidia
    priamo v dashboarde.
    """

    def __init__(self, field: str, detail: str) -> None:
        super().__init__(f"models.{field}: {detail}")
        self.field = field


def _required(row: dict, field: str):
    value = row.get(field)
    if value in (None, ""):
        raise BadModelRow(field, "chýba, bez neho sa tenant nedá postaviť")
    return value


def _required_int(row: dict, field: str) -> int:
    value = row.get(field)
    if value in (None, ""):
        raise BadModelRow(field, "je prázdne — modelka sa nemá ako prihlásiť")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise BadModelRow(field, f"nie je číslo ({value!r})") from exc


def _req(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Chýba povinná env premenná: {name}")
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _ids(name: str) -> frozenset:
    """Zoznam Telegram id oddelený čiarkami. Prázdne = žiadne výnimky."""
    raw = os.getenv(name, "").replace(";", ",")
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return frozenset(out)


def _first(*names: str) -> str:
    """Prvá neprázdna z premenných — kvôli kompatibilite starších názvov."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    raise RuntimeError(f"Chýba aspoň jedna z env premenných: {', '.join(names)}")


@dataclass(frozen=True)
class Config:
    """Globálne env — jeden na worker proces, spoločné pre všetkých tenantov."""

    # Supabase — jeden projekt, zdieľaný všetkými tenantmi
    supabase_url: str
    supabase_key: str

    # LLM — akékoľvek OpenAI-kompatibilné API (Atlas Cloud, OpenRouter, xAI)
    llm_key: str
    llm_base_url: str
    model: str
    summary_model: str
    reasoning_effort: str
    vision_model: str

    # Chovanie — globálne defaulty, ktoré sa dedia do TenantConfig (model si
    # ich v budúcnosti môže prepísať cez behavior tabuľku, nie tu)
    context_messages: int
    summary_every: int
    skip_contacts: bool
    contact_exceptions: frozenset
    link_min_messages: int
    link_cooldown_hours: int
    link_max_pushes: int

    # Dešifrovací kľúč pre tg_session_enc / control_bot_token_enc v models
    encryption_key: str

    # Multi-tenant worker — koľko modelov naraz tento proces obsluhuje,
    # ako často claimuje nové, a čím sa identifikuje v `models.claimed_by`
    max_tenants: int
    replica_name: str
    claim_interval_s: int

    # Fallback cena za milión tokenov, keď LLM providera nepoznáme v cenníku
    fallback_price_per_mtok: float

    # Denný auto-sync cien z Atlas Billing API — koľko hodín medzi behmi.
    # 0 = vypnuté (žiadny background task v main.py run()).
    pricing_sync_hours: int = 24
    # Pod touto hranicou (USD) sa zostatok na Atlas účte považuje za nízky —
    # sync_pricing/check_atlas_balance zaloguje log.error, nech si to Marek všimne.
    atlas_balance_alert_usd: float = 50.0

    # Fanvue OAuth appka — spoločná pre všetky modelky (jedna appka, jeden
    # redirect URI). Worker ju potrebuje na OBNOVU prístupového tokenu; samotné
    # pripojenie účtu robí web (`/api/fanvue/start`). Prázdne = Fanvue sa
    # nespúšťa vôbec, Telegram beží ako doteraz.
    fanvue_client_id: str = ""
    fanvue_client_secret: str = ""

    # Ako často sa pozerá do fronty `tg_login_jobs` (Telegram login z webu).
    # Wizard čaká na odpoveď naživo, preto sekundy, nie minúty. 0 = vypnuté.
    login_jobs_poll_s: int = 2

    # Zvuk berie Gemini — vision model ani hlavný model ho neprijmú.
    audio_model: str = "google/gemini-3.5-flash"
    # Hlasovka na mieru z AI Modelka Web. Prázdne = vypnuté, posiela sa text.
    voice_api_url: str = ""
    voice_api_key: str = ""
    voice_ambience: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        _model = (
            os.getenv("LLM_MODEL", "").strip()
            or os.getenv("OPENROUTER_MODEL", "").strip()
            or _DEFAULT_MODEL
        )
        return cls(
            supabase_url=_req("SUPABASE_URL").rstrip("/"),
            supabase_key=_req("SUPABASE_SERVICE_KEY"),
            llm_key=_first("LLM_API_KEY", "ATLAS_API_KEY", "OPENROUTER_API_KEY"),
            llm_base_url=os.getenv("LLM_BASE_URL", _DEFAULT_BASE_URL),
            model=_model,
            summary_model=os.getenv("LLM_SUMMARY_MODEL", "").strip() or _model,
            reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "low").strip(),
            vision_model=os.getenv("LLM_VISION_MODEL", "qwen/qwen3-vl-235b-a22b-thinking"),
            # Zvuk berie Gemini, vision model ani hlavný model ho neprijmú.
            audio_model=os.getenv("LLM_AUDIO_MODEL", "google/gemini-3.5-flash"),
            voice_api_url=os.getenv("VOICE_API_URL", ""),
            voice_api_key=os.getenv("VOICE_API_KEY", ""),
            voice_ambience=os.getenv("VOICE_AMBIENCE", ""),
            context_messages=_int("CONTEXT_MESSAGES", 12),
            summary_every=_int("SUMMARY_EVERY", 15),
            skip_contacts=os.getenv("SKIP_CONTACTS", "true").lower() != "false",
            contact_exceptions=_ids("CONTACT_EXCEPTIONS"),
            link_min_messages=_int("LINK_MIN_MESSAGES", 6),
            link_cooldown_hours=_int("LINK_COOLDOWN_HOURS", 48),
            link_max_pushes=_int("LINK_MAX_PUSHES", 3),
            encryption_key=_req("ENCRYPTION_KEY"),
            max_tenants=_int("MAX_TENANTS", 25),
            replica_name=os.getenv("RAILWAY_REPLICA_ID")
            or f"{socket.gethostname()}-{os.getpid()}",
            claim_interval_s=_int("CLAIM_INTERVAL_S", 30),
            fallback_price_per_mtok=float(os.getenv("FALLBACK_PRICE_PER_MTOK", "5.0")),
            pricing_sync_hours=_int("PRICING_SYNC_HOURS", 24),
            atlas_balance_alert_usd=float(os.getenv("ATLAS_BALANCE_ALERT_USD", "50")),
            login_jobs_poll_s=_int("LOGIN_JOBS_POLL_S", 2),
            fanvue_client_id=os.getenv("FANVUE_CLIENT_ID", "").strip(),
            fanvue_client_secret=os.getenv("FANVUE_CLIENT_SECRET", "").strip(),
        )


@dataclass(frozen=True)
class TenantConfig:
    """Per-tenant konfigurácia — jeden riadok `models` + zdedené globálne
    defaulty z `Config`. Moduly portované z predlohy (userbot.py,
    control_bot.py, ...) na toto pristupujú presne tak, ako predtým na
    globálny Config — preto tu musí byť aj to, čo je "len" zdedené.
    """

    # Identita tenanta (v predlohe nebolo — jeden proces = jeden model)
    model_id: str
    account_id: str
    name: str

    # Telegram — userbot (účet modelky)
    tg_api_id: int
    tg_api_hash: str
    tg_session: str

    # Telegram — kontrolný bot
    control_bot_token: str
    owner_chat_id: int
    owner_as_client: bool = False

    # Účty, ktorým sa odpovedá výhradne hlasovkou — na testovanie hlasu.
    voice_only_ids: frozenset = frozenset()

    # POZOR: v predlohe `supabase_schema` nie je len názov DB schémy — čítajú
    # ho aj den.block_at()/behavior.activity_wave() (userbot.py:391,397,711)
    # ako SEED pre denný rozvrh a aktivitu, a userbot.py:1345 ako prefix
    # storage cesty. V Telepipe je DB spoločná (public, žiadne per-tenant
    # schémy), takže sem ide model_id — unikátne per tenant, deterministické
    # naprieč reštartami, vďaka čomu má každý model iný rozvrh/aktivitu aj
    # iný storage prefix. Konštanta ako "tgai" by spôsobila, že by všetci
    # tenanti mali identický denný rozvrh — nechceme.
    supabase_schema: str = ""

    # --- Zdedené globálne defaulty z Config (LLM, chovanie) ---
    llm_key: str = ""
    llm_base_url: str = ""
    model: str = ""
    summary_model: str = ""
    reasoning_effort: str = ""
    vision_model: str = ""
    audio_model: str = ""
    voice_api_url: str = ""
    voice_api_key: str = ""
    voice_ambience: str = ""

    context_messages: int = 12
    summary_every: int = 15
    skip_contacts: bool = True
    contact_exceptions: frozenset = frozenset()
    link_min_messages: int = 6
    link_cooldown_hours: int = 48
    link_max_pushes: int = 3

    @classmethod
    def from_row(cls, row: dict, g: Config) -> "TenantConfig":
        """Poskladá per-tenant config z riadku `models` + globálnych defaultov.

        PRAVIDLO PRE NULL. V `models` sú nullovateľné práve dva stĺpce,
        `tg_api_id` a `owner_chat_id`, a znamenajú úplne rozdielne veci:

          * `owner_chat_id` NULL = „kontrolný bot ešte nemá majiteľa". To je
            BEŽNÝ a povolený stav — modelka odpisuje fanúšikom aj bez neho a
            práve preto sľubujeme, že bot je nepovinný. Ide von ako 0.
          * `tg_api_id` NULL = „nie je čím sa prihlásiť". Bez neho Telethon
            klienta ani nepostaví, takže to je naozaj chyba — ale musí vyletieť
            ako `BadModelRow` s NÁZVOM stĺpca, nie ako holý `TypeError`.

        Prečo tak dôrazne: 2026-08-18 padol prvému platiacemu klientovi model
        práve na `int(None)` z `owner_chat_id`. `Pool.tick` to zachytil ako
        „neplatný riadok", nastavil `error`/`bad_config` a tenant sa nespustil
        — teda pravidlo „bot je nepovinný" bolo v produkte opakom pravdy a
        z logu sa nedalo prečítať, ktoré pole za to mohlo. Klient sa cez to
        dostal len náhodou, keď doplnil token bota.

        tg_session_enc/control_bot_token_enc sa dešifrujú `g.encryption_key`.
        Model v draft stave ich ešte nemusí mať — chýbajúca/prázdna hodnota
        znamená prázdny string, nie chybu. Ak dešifrovanie zlyhá (zlý kľúč,
        poškodené dáta), CryptoError sa pustí ďalej — o to sa postará volajúci.
        """
        session_enc = row.get("tg_session_enc") or ""
        token_enc = row.get("control_bot_token_enc") or ""
        tg_session = decrypt(session_enc, g.encryption_key) if session_enc else ""
        control_bot_token = decrypt(token_enc, g.encryption_key) if token_enc else ""

        return cls(
            model_id=_required(row, "id"),
            account_id=_required(row, "account_id"),
            # `name` má v DB `not null default ''` — prázdne meno beh nebráni.
            name=row.get("name") or "",
            tg_api_id=_required_int(row, "tg_api_id"),
            tg_api_hash=row.get("tg_api_hash") or "",
            tg_session=tg_session,
            control_bot_token=control_bot_token,
            # Nenastavený majiteľ je od migrácie 020 BEŽNÝ stav, nie chyba:
            # modelka sa páruje kódom až keď beží, takže do prvého spárovania
            # je stĺpec NULL. `int(None)` by hodilo TypeError, main.py by
            # riadok vyhodnotil ako `bad_config`, model by sa odstavil — a bot,
            # ktorý mal kód prijať, by sa vôbec nespustil. Nula znamená
            # „zatiaľ nikto"; `_is_owner` na ňu nikdy nesadne (Telegram chat id
            # nula nie je) a `notify()` ju len zaloguje.
            owner_chat_id=int(row.get("owner_chat_id") or 0),
            owner_as_client=bool(row.get("owner_as_client") or False),
            voice_only_ids=frozenset(row.get("voice_only_ids") or ()),
            # Seed pre denný rozvrh/aktivitu + prefix storage ciest (viď
            # komentár pri poli vyššie) — NIE názov DB schémy.
            supabase_schema=_required(row, "id"),
            # Zdedené z globálneho Config — predloha ich nastavuje z env,
            # tu ich model zatiaľ nemôže prepísať (bude riešiť behavior tabuľka).
            llm_key=g.llm_key,
            llm_base_url=g.llm_base_url,
            model=g.model,
            summary_model=g.summary_model,
            reasoning_effort=g.reasoning_effort,
            vision_model=g.vision_model,
            audio_model=g.audio_model,
            voice_api_url=g.voice_api_url,
            voice_api_key=g.voice_api_key,
            voice_ambience=g.voice_ambience,
            context_messages=g.context_messages,
            summary_every=g.summary_every,
            skip_contacts=g.skip_contacts,
            contact_exceptions=g.contact_exceptions,
            link_min_messages=g.link_min_messages,
            link_cooldown_hours=g.link_cooldown_hours,
            link_max_pushes=g.link_max_pushes,
        )
