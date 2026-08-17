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
