"""Global config z env; TenantConfig z riadku models + dešifrovanie."""
import pytest

from config import Config, TenantConfig
from crypto import encrypt

KEY = "u" * 43 + "="

ENV = {
    "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "sk",
    "LLM_API_KEY": "ak", "ENCRYPTION_KEY": KEY,
}

# Kontrakt: atribúty, ktoré predloha (telegram/src) číta cez cfg./self._cfg.
# v moduloch, ktoré v Telepipe dostanú TenantConfig (userbot.py, control_bot.py) —
# NIE main.py-only veci ako supabase_url/supabase_key (tie zostávajú len na
# globálnom Config, lebo Supabase projekt je spoločný pre všetkých tenantov).
TEMPLATE_TENANT_ATTRS = [
    "audio_model",
    "contact_exceptions",
    "context_messages",
    "control_bot_token",
    "link_cooldown_hours",
    "link_max_pushes",
    "link_min_messages",
    "llm_base_url",
    "llm_key",
    "model",
    "owner_as_client",
    "owner_chat_id",
    "reasoning_effort",
    "skip_contacts",
    "summary_every",
    "summary_model",
    "supabase_schema",
    "tg_api_hash",
    "tg_api_id",
    "tg_session",
    "vision_model",
    "voice_only_ids",
]


def test_config_from_env(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    assert cfg.supabase_url == "https://x.supabase.co"
    assert cfg.max_tenants == 25          # default
    assert cfg.replica_name              # nikdy prázdne
    assert cfg.pricing_sync_hours == 24           # default
    assert cfg.atlas_balance_alert_usd == 50.0    # default


def test_config_pricing_sync_env_overrides(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PRICING_SYNC_HOURS", "0")
    monkeypatch.setenv("ATLAS_BALANCE_ALERT_USD", "12.5")
    cfg = Config.from_env()
    assert cfg.pricing_sync_hours == 0
    assert cfg.atlas_balance_alert_usd == 12.5


def test_config_fanvue_is_optional(monkeypatch):
    """Bez Fanvue appky musí worker nabehnúť presne ako doteraz."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("FANVUE_CLIENT_ID", raising=False)
    monkeypatch.delenv("FANVUE_CLIENT_SECRET", raising=False)
    cfg = Config.from_env()
    assert cfg.fanvue_client_id == "" and cfg.fanvue_client_secret == ""


def test_config_reads_fanvue_app(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("FANVUE_CLIENT_ID", " app-id ")
    monkeypatch.setenv("FANVUE_CLIENT_SECRET", "app-secret")
    cfg = Config.from_env()
    assert cfg.fanvue_client_id == "app-id"          # orezané medzery
    assert cfg.fanvue_client_secret == "app-secret"


def test_config_missing_required(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        Config.from_env()


def test_tenant_config_decrypts_session(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    row = {
        "id": "m-1", "account_id": "a-1", "name": "Lola",
        "tg_api_id": 12345, "tg_api_hash": "hash",
        "tg_session_enc": encrypt("SESSION", KEY),
        "control_bot_token_enc": encrypt("BOT:token", KEY),
        "owner_chat_id": 777,
    }
    t = TenantConfig.from_row(row, cfg)
    assert t.tg_session == "SESSION"
    assert t.control_bot_token == "BOT:token"
    assert t.model_id == "m-1"
    assert t.link_min_messages == 6       # zdedené globálne defaulty predlohy


def test_tenant_config_covers_template_attrs(monkeypatch):
    """TenantConfig musí mať všetko, čo predloha číta cez cfg./self._cfg. —
    inak moduly userbot.py/control_bot.py po porte crashnú na AttributeError."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    row = {
        "id": "m-1", "account_id": "a-1", "name": "Lola",
        "tg_api_id": 12345, "tg_api_hash": "hash",
        "tg_session_enc": encrypt("SESSION", KEY),
        "control_bot_token_enc": encrypt("BOT:token", KEY),
        "owner_chat_id": 777,
    }
    t = TenantConfig.from_row(row, cfg)
    missing = [a for a in TEMPLATE_TENANT_ATTRS if not hasattr(t, a)]
    assert not missing, f"TenantConfig chýbajú atribúty z predlohy: {missing}"
    # supabase_schema nie je názov DB schémy — v predlohe je to zároveň seed
    # pre denný rozvrh/aktivitu (den.block_at/behavior.activity_wave) a
    # prefix storage ciest. Musí byť per-tenant unikátne, inak majú všetci
    # tenanti identický denný rozvrh.
    assert t.supabase_schema == t.model_id


def test_tenant_config_reads_model_flags(monkeypatch):
    """owner_as_client + voice_only_ids sú stĺpce v `models` (migrácia 006) —
    from_row ich musí prebrať, nie ostať na defaultoch."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    row = {
        "id": "m-3", "account_id": "a-1", "name": "Lola",
        "tg_api_id": 1, "tg_api_hash": "hash", "owner_chat_id": 777,
        "owner_as_client": True,
        "voice_only_ids": [1, 2],           # bigint[] z PostgREST príde ako list
    }
    t = TenantConfig.from_row(row, cfg)
    assert t.owner_as_client is True
    assert t.voice_only_ids == frozenset({1, 2})


def test_tenant_config_model_flags_default_when_null(monkeypatch):
    """Chýbajúce/NULL hodnoty (starý riadok) = vypnuté, nie pád."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    row = {
        "id": "m-4", "account_id": "a-1", "name": "Lola",
        "tg_api_id": 1, "tg_api_hash": "hash", "owner_chat_id": 777,
        "owner_as_client": None, "voice_only_ids": None,
    }
    t = TenantConfig.from_row(row, cfg)
    assert t.owner_as_client is False
    assert t.voice_only_ids == frozenset()


class TestKontaktovyFilterZRiadku:
    """`skip_contacts` a `contact_exceptions` sú per modelka (migrácia 023b).

    Kým sa čítali z env, platila na celej replike jedna hodnota — a keďže na
    Railway nastavená nebola, default `true` ticho umlčal každého, koho má
    modelka v kontaktoch. Marekov kamarát tak napísal Simone a nedostal
    odpoveď. Zdroj pravdy je odteraz riadok; env je len záchranka.
    """

    @staticmethod
    def _cfg(monkeypatch, **env):
        for k, v in {**ENV, **env}.items():
            monkeypatch.setenv(k, v)
        return Config.from_env()

    @staticmethod
    def _row(**extra):
        return {
            "id": "m-c", "account_id": "a-1", "name": "Lola",
            "tg_api_id": 1, "tg_api_hash": "hash", "owner_chat_id": 777,
            **extra,
        }

    def test_riadok_prebije_env(self, monkeypatch):
        cfg = self._cfg(monkeypatch, SKIP_CONTACTS="false", CONTACT_EXCEPTIONS="1")
        t = TenantConfig.from_row(
            self._row(skip_contacts=True, contact_exceptions=[42, 43]), cfg
        )
        assert t.skip_contacts is True
        assert t.contact_exceptions == frozenset({42, 43})

    def test_false_v_riadku_nespadne_na_env(self, monkeypatch):
        """`False` je hodnota, nie „nič" — inak by env prebilo vypnutý filter."""
        cfg = self._cfg(monkeypatch, SKIP_CONTACTS="true")
        t = TenantConfig.from_row(self._row(skip_contacts=False), cfg)
        assert t.skip_contacts is False

    def test_prazdne_pole_je_hodnota(self, monkeypatch):
        """Prázdny zoznam výnimiek znamená „žiadne", nie „vezmi tie z env"."""
        cfg = self._cfg(monkeypatch, CONTACT_EXCEPTIONS="693039915")
        t = TenantConfig.from_row(self._row(contact_exceptions=[]), cfg)
        assert t.contact_exceptions == frozenset()

    def test_chybajuce_stlpce_padnu_na_env(self, monkeypatch):
        """Rollout: worker môže bežať skôr, než migrácia dobehne."""
        cfg = self._cfg(monkeypatch, SKIP_CONTACTS="false", CONTACT_EXCEPTIONS="7,8")
        t = TenantConfig.from_row(self._row(), cfg)
        assert t.skip_contacts is False
        assert t.contact_exceptions == frozenset({7, 8})

    def test_null_stlpce_padnu_na_env(self, monkeypatch):
        """PostgREST vie poslať aj explicitné null (starý riadok pred seedom)."""
        cfg = self._cfg(monkeypatch, SKIP_CONTACTS="true", CONTACT_EXCEPTIONS="9")
        t = TenantConfig.from_row(
            self._row(skip_contacts=None, contact_exceptions=None), cfg
        )
        assert t.skip_contacts is True
        assert t.contact_exceptions == frozenset({9})


def test_tenant_config_missing_enc_is_empty_string(monkeypatch):
    """Model v draft stave nemusí mať ešte session/token — nesmie to spadnúť."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    row = {
        "id": "m-2", "account_id": "a-1", "name": "Draft",
        "tg_api_id": 1, "tg_api_hash": "hash",
        "owner_chat_id": 1,
    }
    t = TenantConfig.from_row(row, cfg)
    assert t.tg_session == ""
    assert t.control_bot_token == ""
