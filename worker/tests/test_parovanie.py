"""Párovanie kontrolného bota kódom (migrácia 020).

Toto je jediné miesto, kde bot čokoľvek prijme od NEZNÁMEHO chatu, takže sa
tu netestuje len šťastná cesta. Zlý kód, cudzí kód, skupina, hrubá sila aj
nespárovaná modelka musia skončiť rovnako: ticho.
"""
import asyncio

import pytest
from config import TenantConfig as Config
from control_bot import ControlBot


def _cfg(owner_chat_id: int = 0, control_bot_token: str = "t") -> Config:
    return Config(
        model_id="test-model", account_id="acc-1", name="Lucia",
        tg_api_id=1, tg_api_hash="h", tg_session="s",
        control_bot_token=control_bot_token,
        owner_chat_id=owner_chat_id, owner_as_client=False,
        supabase_schema="test-model",
        llm_key="k", llm_base_url="https://x/v1", model="m", summary_model="m",
        reasoning_effort="low", vision_model="v", audio_model="a",
        context_messages=12, summary_every=15, skip_contacts=True,
        contact_exceptions=frozenset(), link_min_messages=6,
        link_cooldown_hours=48, link_max_pushes=3,
    )


class FakeDb:
    """Prijme práve jeden kód; všetko ostatné odmietne (ako RPC v 020)."""

    def __init__(self, platny: str = "TP-4F9K2X") -> None:
        self.platny = platny
        self.pokusy: list = []

    async def pair_control_bot(self, code: str, chat_id: int) -> bool:
        self.pokusy.append((code, chat_id))
        return code == self.platny

    # ---- to, čo potrebuje _send_main ----
    async def is_paused(self) -> bool:
        return False

    async def tg_reply_mode(self) -> dict:
        return {"mode": "auto", "fallback_minutes": None}

    async def fanvue_reply_mode(self) -> dict:
        return {"mode": "auto", "fallback_minutes": None, "connected": False}

    async def get_persona(self) -> dict:
        return {"name": "Lucia", "cta_link": ""}

    async def get_behavior(self) -> dict:
        return {"active_tz": "Europe/Bratislava"}


class FakeEvent:
    def __init__(self, chat_id: int, text: str, private: bool = True) -> None:
        self.chat_id = chat_id
        self.raw_text = text
        self.is_private = private
        self.odpovede: list = []

    async def reply(self, text, **_kw):
        self.odpovede.append(text)

    async def respond(self, text, **_kw):
        self.odpovede.append(text)


def _run(bot: ControlBot, event: FakeEvent):
    return asyncio.run(bot._on_value(event))


class TestSpravnyKod:
    def test_neznamy_chat_s_kodom_sa_spáruje(self):
        db = FakeDb()
        cfg = _cfg(0)
        bot = ControlBot(cfg, db, None)
        event = FakeEvent(777, "TP-4F9K2X")

        _run(bot, event)

        assert db.pokusy == [("TP-4F9K2X", 777)]
        assert cfg.owner_chat_id == 777, "chat id sa musí zapísať do configu"
        assert any("Paired" in t for t in event.odpovede)
        # Po potvrdení hneď menu — klient nemá hľadať, čo ďalej.
        assert any("Persona" in t or "running" in t for t in event.odpovede)

    def test_kod_prezije_male_pismena_aj_chybajuci_prefix(self):
        for napisane in ("tp-4f9k2x", "4F9K2X", "  TP 4f9k2x  ", "4f9k2x\n"):
            db = FakeDb()
            bot = ControlBot(_cfg(0), db, None)
            _run(bot, FakeEvent(777, napisane))
            assert db.pokusy == [("TP-4F9K2X", 777)], napisane

    def test_po_sparovani_prejde_vlastnicka_brana(self):
        cfg = _cfg(0)
        bot = ControlBot(cfg, FakeDb(), None)
        assert not bot._is_owner(777)

        _run(bot, FakeEvent(777, "TP-4F9K2X"))

        assert bot._is_owner(777)
        assert not bot._is_owner(778)


class TestTichoNaVsetkoOstatne:
    def test_zly_kod_neodpovie_ani_slovo(self):
        db = FakeDb()
        event = FakeEvent(777, "TP-ZZZZZZ")
        _run(ControlBot(_cfg(0), db, None), event)

        assert db.pokusy == [("TP-ZZZZZZ", 777)]
        assert event.odpovede == [], "neznámemu sa nesmie prezradiť, že kódy existujú"

    def test_bezna_sprava_sa_databazy_ani_nepyta(self):
        db = FakeDb()
        event = FakeEvent(777, "ahoj, kto si?")
        _run(ControlBot(_cfg(0), db, None), event)

        assert db.pokusy == []
        assert event.odpovede == []

    def test_v_skupine_sa_neparuje(self):
        db = FakeDb()
        event = FakeEvent(-100123, "TP-4F9K2X", private=False)
        _run(ControlBot(_cfg(0), db, None), event)

        assert db.pokusy == []
        assert event.odpovede == []

    def test_nula_nie_je_majitel(self):
        """`owner_chat_id = 0` znamená „zatiaľ nikto", nie chat číslo nula."""
        bot = ControlBot(_cfg(0), FakeDb(), None)
        assert not bot._is_owner(0)
        assert not bot._is_owner(None)


class TestHrubaSila:
    def test_siesty_pokus_za_minutu_sa_uz_neoveruje(self):
        db = FakeDb()
        bot = ControlBot(_cfg(0), db, None)
        for _ in range(8):
            _run(bot, FakeEvent(777, "TP-ZZZZZZ"))

        assert len(db.pokusy) == 5, "kódy sa nesmú dať prehľadávať hrubou silou"

    def test_strop_plati_na_chat_nie_na_bota(self):
        db = FakeDb()
        bot = ControlBot(_cfg(0), db, None)
        for _ in range(6):
            _run(bot, FakeEvent(777, "TP-ZZZZZZ"))
        _run(bot, FakeEvent(888, "TP-4F9K2X"))

        assert ("TP-4F9K2X", 888) in db.pokusy, "vyčerpaný chat nesmie zablokovať iný"

    def test_uspesne_sparovanie_zahodi_pocitadlo(self):
        db = FakeDb()
        bot = ControlBot(_cfg(0), db, None)
        for _ in range(3):
            _run(bot, FakeEvent(777, "TP-ZZZZZZ"))
        _run(bot, FakeEvent(777, "TP-4F9K2X"))

        assert bot._pair_tries.get(777) in (None, [])


class TestPadNezhodiBota:
    def test_chyba_databazy_sa_len_zaloguje(self):
        class Zlyhava(FakeDb):
            async def pair_control_bot(self, code, chat_id):
                raise RuntimeError("Supabase spadla")

        event = FakeEvent(777, "TP-4F9K2X")
        _run(ControlBot(_cfg(0), Zlyhava(), None), event)
        assert event.odpovede == []


def _global_cfg():
    from config import Config as GlobalConfig

    return GlobalConfig(
        supabase_url="https://x", supabase_key="k", llm_key="k",
        llm_base_url="https://x/v1", model="m", summary_model="m",
        reasoning_effort="low", vision_model="v",
        context_messages=12, summary_every=15, skip_contacts=True,
        contact_exceptions=frozenset(), link_min_messages=6,
        link_cooldown_hours=48, link_max_pushes=3,
        encryption_key="a" * 44, max_tenants=25, replica_name="r",
        claim_interval_s=30, fallback_price_per_mtok=5.0,
    )


def _row(**zmeny):
    row = {
        "id": "m1", "account_id": "a1", "name": "Lucia",
        "tg_api_id": 1, "tg_api_hash": "h",
        "tg_session_enc": "", "control_bot_token_enc": "",
        "owner_chat_id": None,
    }
    row.update(zmeny)
    return row


class TestConfigBezMajitela:
    """Modelka bez kontrolného bota MUSÍ bežať — inak je „nepovinný" lož.

    Presne toto padlo 2026-08-18 prvému platiacemu klientovi: Telegram login
    prešiel, o 20 sekúnd neskôr `int(None)` z `owner_chat_id`, pool to zapísal
    ako `bad_config` a tenant sa nespustil. Cez to sa dostal len náhodou, keď
    doplnil token bota.
    """

    def test_null_owner_chat_id_nezhodi_tenanta(self):
        from config import TenantConfig

        assert TenantConfig.from_row(_row(), _global_cfg()).owner_chat_id == 0

    def test_chybajuci_token_je_prazdny_string_nie_chyba(self):
        from config import TenantConfig

        row = _row()
        row.pop("control_bot_token_enc")
        cfg = TenantConfig.from_row(row, _global_cfg())
        assert cfg.control_bot_token == ""
        assert cfg.tg_session == ""

    def test_nullove_stlpce_z_006_maju_rozumne_defaulty(self):
        """`voice_only_ids`/`owner_as_client` chodia z PostgREST aj ako None."""
        from config import TenantConfig

        cfg = TenantConfig.from_row(
            _row(voice_only_ids=None, owner_as_client=None, name=None, tg_api_hash=None),
            _global_cfg(),
        )
        assert cfg.voice_only_ids == frozenset()
        assert cfg.owner_as_client is False
        assert cfg.name == "" and cfg.tg_api_hash == ""


class TestZlyRiadokPovieCoMuChyba:
    """Bez `api_id` sa naozaj bežať nedá — ale musí byť vidieť, čo chýbalo."""

    def test_chybajuce_api_id_nesie_nazov_stlpca(self):
        from config import BadModelRow, TenantConfig

        with pytest.raises(BadModelRow) as chyba:
            TenantConfig.from_row(_row(tg_api_id=None), _global_cfg())
        assert chyba.value.field == "tg_api_id"

    def test_necislo_v_api_id_tiez(self):
        from config import BadModelRow, TenantConfig

        with pytest.raises(BadModelRow) as chyba:
            TenantConfig.from_row(_row(tg_api_id="ehm"), _global_cfg())
        assert chyba.value.field == "tg_api_id"

    @pytest.mark.asyncio
    async def test_pool_zapise_ktore_pole_zlyhalo(self):
        """`status_reason` = `bad_config:tg_api_id`, nie holé `bad_config`."""
        from config import BadModelRow
        from main import Pool

        class FakeReg:
            def __init__(self):
                self.statuses = []

            async def claim(self, replica, capacity):
                return [{"id": "m-1", "model_type": "persona"}]

            async def model_row(self, mid):
                return None

            async def set_status(self, mid, status, reason=""):
                self.statuses.append((mid, status, reason))

            async def release(self, mid):
                pass

            async def heartbeat(self, replica):
                return None

            async def upsert_replica(self, *a, **kw):
                pass

        def zly(row, g):
            raise BadModelRow("tg_api_id", "je prázdne")

        reg = FakeReg()
        pool = Pool(
            registry=reg, transport=None, global_cfg=_global_cfg(),
            runner_factory=lambda *a: None, tenant_factory=zly,
        )
        await pool.tick()
        assert reg.statuses == [("m-1", "error", "bad_config:tg_api_id")]


class TestBezTokenaSaBotNespusta:
    """Nepovinný bot sa nemá o čo pokúšať — a nesmie to byť ERROR v logu."""

    @pytest.mark.asyncio
    async def test_prazdny_token_sa_ani_neskusa_prihlasit(self, monkeypatch):
        import runner as runner_mod
        from telethon.errors import AuthKeyUnregisteredError

        starty = []

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def start(self, bot_token=None):
                starty.append(bot_token)

            async def connect(self):
                pass

            async def is_user_authorized(self):
                return False  # ukončí `_run_once` hneď za štartom bota

            async def disconnect(self):
                pass

        monkeypatch.setattr(runner_mod, "TelegramClient", FakeClient)
        monkeypatch.setattr(runner_mod, "StringSession", lambda *a: None)

        r = runner_mod.TenantRunner(
            _cfg(0, control_bot_token=""), _global_cfg(), object(), object()
        )
        with pytest.raises(AuthKeyUnregisteredError):
            await r._run_once()

        assert starty == [], "bez tokenu sa `bot_client.start` nesmie ani zavolať"


@pytest.mark.asyncio
async def test_db_metoda_posiela_model_id(transport, http_calls):
    """RPC musí niesť `p_model` — inak by kód spároval cudziu modelku."""
    from db import TenantDb

    db = TenantDb(transport, "model-A")
    await db.pair_control_bot("TP-4F9K2X", 777)

    call = http_calls[-1]
    assert "/rpc/pair_control_bot" in call["url"]
    assert call["body"] == {"p_model": "model-A", "p_code": "TP-4F9K2X", "p_chat": 777}
