"""Fanvue seam — šifrovanie tokenov, izolácia tenantov, spustenie agenta.

Toto je jediné miesto, kde plaintext token prechádza medzi `fanvue_api` a DB,
takže testy stoja hlavne na dvoch veciach: von z DB ide dešifrované, do DB ide
zašifrované — a nikdy naopak.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from crypto import encrypt
from fanvue_tenant import TenantFanvueDb, start_fanvue
from transport import SupabaseTransport

KEY = "JoFAPhHkY+0QClNlXm2VoUanwKdZuNJFxrU1qTN0iPY="
MODEL = "model-A"


def _transport(rows, calls):
    """Transport, ktorý na GET vracia `rows` (dict path → riadky) a všetko píše
    do `calls`."""

    def handler(req):
        try:
            body = json.loads(req.content) if req.content else None
        except ValueError:
            body = None
        calls.append({"method": req.method, "url": str(req.url), "body": body})
        path = req.url.path.replace("/rest/v1", "")
        return httpx.Response(200, json=rows.get(path, []))

    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://x.supabase.co/rest/v1"
    )
    return t


def _row(**over):
    row = {
        "model_id": MODEL,
        "connected": True,
        "enabled": True,
        "access_token_enc": encrypt("access-plain", KEY),
        "refresh_token_enc": encrypt("refresh-plain", KEY),
        "expires_at": "2026-08-17T13:00:00+00:00",
        "scope": "openid read:chat",
        "creator_uuid": "creator-1",
        "handle": "lena",
        "display_name": "Lena",
        "last_error": "",
    }
    row.update(over)
    return row


def _db(rows, calls):
    return TenantFanvueDb(_transport(rows, calls), MODEL, KEY)


# ---------------------------------------------------------------------------
# Šifrovací seam
# ---------------------------------------------------------------------------


class TestTokeny:
    async def test_settings_vracia_desifrovane_tokeny(self):
        db = _db({"/fanvue": [_row()]}, [])
        row = await db.settings()
        assert row["access_token"] == "access-plain"
        assert row["refresh_token"] == "refresh-plain"

    async def test_settings_zahodi_enc_stlpce(self):
        """Šifrovaná podoba sa nesmie vydávať za použiteľnú hodnotu."""
        db = _db({"/fanvue": [_row()]}, [])
        row = await db.settings()
        assert "access_token_enc" not in row and "refresh_token_enc" not in row

    async def test_prazdny_token_ostane_prazdny(self):
        db = _db({"/fanvue": [_row(access_token_enc="", refresh_token_enc="")]}, [])
        row = await db.settings()
        assert row["access_token"] == "" and row["refresh_token"] == ""

    async def test_poskodeny_token_nezhodi_agenta(self):
        """Zlý kľúč znamená „nemáme token", nie pád v strede kola."""
        db = _db({"/fanvue": [_row(access_token_enc="nezmysel")]}, [])
        row = await db.settings()
        assert row["access_token"] == ""

    async def test_bez_riadku_je_prazdny_dict(self):
        db = _db({"/fanvue": []}, [])
        assert await db.settings() == {}

    async def test_save_zasifruje_a_nikdy_neposle_plaintext(self):
        calls = []
        db = _db({}, calls)
        await db.save({"access_token": "novy", "refresh_token": "novy-r", "last_error": ""})
        body = calls[-1]["body"]
        assert "access_token" not in body and "refresh_token" not in body
        assert body["access_token_enc"] and body["access_token_enc"] != "novy"
        assert body["refresh_token_enc"] and body["refresh_token_enc"] != "novy-r"
        assert body["last_error"] == "" and body["updated_at"]

    async def test_save_a_settings_su_navzajom_inverzne(self):
        """Zápis workera musí byť čitateľný jeho vlastným čítaním."""
        calls = []
        db = _db({}, calls)
        await db.save({"access_token": "kolobeh"})
        sealed = calls[-1]["body"]["access_token_enc"]
        db2 = _db({"/fanvue": [_row(access_token_enc=sealed)]}, [])
        assert (await db2.settings())["access_token"] == "kolobeh"

    async def test_prazdny_token_sa_nesifruje(self):
        calls = []
        db = _db({}, calls)
        await db.save({"refresh_token": ""})
        assert calls[-1]["body"]["refresh_token_enc"] == ""


# ---------------------------------------------------------------------------
# Izolácia tenantov
# ---------------------------------------------------------------------------


class TestIzolacia:
    async def test_kazdy_dotaz_nesie_model_id(self):
        calls = []
        db = _db({"/fanvue": [_row()], "/dm_users": [], "/facts": [], "/dm_messages": []}, calls)
        await db.settings()
        await db.save({"last_error": "x"})
        await db.pending()
        await db.mark_handled(7)
        await db.persona()
        await db.behavior()
        await db.link_candidates()
        await db.telegram_context(42)
        assert calls
        for call in calls:
            assert f"model_id=eq.{MODEL}" in call["url"], call["url"]

    async def test_dvaja_tenanti_si_nevidia_do_fronty(self):
        calls = []
        t = _transport({"/fanvue_events": []}, calls)
        await TenantFanvueDb(t, "model-A", KEY).pending()
        await TenantFanvueDb(t, "model-B", KEY).pending()
        assert "model_id=eq.model-A" in calls[0]["url"]
        assert "model_id=eq.model-B" in calls[1]["url"]


# ---------------------------------------------------------------------------
# Fronta udalostí
# ---------------------------------------------------------------------------


class TestFronta:
    async def test_pending_berie_len_nespracovane_od_najstarsich(self):
        calls = []
        db = _db({"/fanvue_events": []}, calls)
        await db.pending(limit=5)
        url = calls[-1]["url"]
        assert "processed_at=is.null" in url
        assert "order=id.asc" in url
        assert "limit=5" in url

    async def test_pending_premenuje_event_type_na_type(self):
        """`fanvue_agent` číta `event["type"]` — stĺpec sa volá inak."""
        calls = []
        db = _db({"/fanvue_events": []}, calls)
        await db.pending()
        assert "type%3Aevent_type" in calls[-1]["url"] or "type:event_type" in calls[-1]["url"]

    async def test_agent_rozumie_tvaru_z_fronty(self):
        """Poistka proti driftu: riadok z DB musí prejsť rozhodovaním agenta."""
        import fanvue_agent as fa

        rows = [
            {
                "id": 1,
                "type": "creator.message.received",
                "payload": {"data": {"object": "message", "sender": "fan", "text": "ahoj"}},
            }
        ]
        db = _db({"/fanvue_events": rows}, [])
        events = await db.pending()
        assert fa.wants_reply(events[0]) is True

    async def test_mark_handled_zapise_cas_a_filtruje_na_id(self):
        calls = []
        db = _db({}, calls)
        await db.mark_handled(11)
        assert "id=eq.11" in calls[-1]["url"]
        assert calls[-1]["body"]["processed_at"]


# ---------------------------------------------------------------------------
# Fáza 3.2 — čo ešte nie je
# ---------------------------------------------------------------------------


class TestNeskorsiaFaza:
    @pytest.mark.parametrize(
        "call",
        [
            lambda db: db.fan("f"),
            lambda db: db.upsert_fan("f", {}),
            lambda db: db.history("f"),
            lambda db: db.folders(),
            lambda db: db.media_in("x"),
            lambda db: db.sent_media("f"),
            lambda db: db.record_send("m", "f", 100),
        ],
    )
    async def test_chybajuca_tabulka_kricci(self, call):
        """Ticho vrátené prázdno by znamenalo odpisovať do prázdna."""
        with pytest.raises(NotImplementedError):
            await call(_db({}, []))

    async def test_bez_fv_users_nie_je_sparovany_nikto(self):
        assert await _db({}, []).linked_tg_ids() == set()


# ---------------------------------------------------------------------------
# Spustenie agenta
# ---------------------------------------------------------------------------


class _Cfg:
    model_id = MODEL


class _Global:
    encryption_key = KEY
    fanvue_client_id = "app-id"
    fanvue_client_secret = "app-secret"


def _globals(**over):
    g = _Global()
    for k, v in over.items():
        setattr(g, k, v)
    return g


class _Spy:
    """Čo agent dostal + kedy sa rozbehol."""

    def __init__(self):
        self.started = asyncio.Event()
        self.made = []

    async def wait(self):
        await asyncio.wait_for(self.started.wait(), 1)


@pytest.fixture
def fake_agent(monkeypatch):
    """FanvueAgent, ktorý len oznámi, že beží, a čaká na zrušenie."""
    spy = _Spy()

    class Fake:
        def __init__(self, db, api, llm):
            self.db, self.api, self.llm = db, api, llm
            spy.made.append(self)

        async def run(self):
            spy.started.set()
            await asyncio.sleep(3600)

    import fanvue_agent

    monkeypatch.setattr(fanvue_agent, "FanvueAgent", Fake)
    return spy


class TestStart:
    async def test_nepripojeny_ucet_agenta_nespusti(self):
        cleanup = []
        task = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row(connected=False)]}, []), None, cleanup
        )
        assert task is None and cleanup == []

    async def test_vypnute_odpisovanie_agenta_nespusti(self):
        """Kým fáza 3.2 nepribudne, `enabled` je false a fronta sa len plní."""
        cleanup = []
        task = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row(enabled=False)]}, []), None, cleanup
        )
        assert task is None and cleanup == []

    async def test_bez_appky_sa_do_db_ani_nepozera(self):
        calls = []
        task = await start_fanvue(
            _Cfg(),
            _globals(fanvue_client_id="", fanvue_client_secret=""),
            _transport({"/fanvue": [_row()]}, calls),
            None,
            [],
        )
        assert task is None and calls == []

    async def test_chybajuci_riadok_nevadi(self):
        assert await start_fanvue(_Cfg(), _globals(), _transport({"/fanvue": []}, []), None, []) is None

    async def test_pripojeny_a_zapnuty_agent_bezi(self, fake_agent):
        cleanup = []
        llm = object()
        task = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row()]}, []), llm, cleanup
        )
        try:
            assert task is not None
            await fake_agent.wait()
            # Úloha musí ísť do cleanupu PRED klientom, inak by sa zatvoril
            # skôr, než ho agent prestane používať.
            assert cleanup[0] is task
            assert hasattr(cleanup[1], "close")
        finally:
            task.cancel()

    async def test_agent_dostane_ten_isty_metered_llm(self, fake_agent):
        """Fanvue musí platiť z toho istého kreditu ako Telegram."""
        llm = object()
        task = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row()]}, []), llm, []
        )
        try:
            await fake_agent.wait()
            agent = fake_agent.made[-1]
            assert agent.llm is llm
            assert isinstance(agent.db, TenantFanvueDb) and agent.db.model_id == MODEL
        finally:
            task.cancel()


# ---------------------------------------------------------------------------
# Runner — Fanvue nesmie zhodiť Telegram
# ---------------------------------------------------------------------------


class TestRunnerSeam:
    async def test_pad_fanvue_nezhodi_telegram(self, monkeypatch):
        from runner import TenantRunner

        import fanvue_tenant

        async def boom(*a, **kw):
            raise RuntimeError("Supabase je dole")

        monkeypatch.setattr(fanvue_tenant, "start_fanvue", boom)
        r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=None, transport=None)
        # Nesmie hodiť — presne ako pri kontrolnom bote.
        await r._start_fanvue(_Cfg(), _globals(), None)

    async def test_uspesny_start_ide_do_cleanupu(self, monkeypatch, fake_agent):
        from runner import TenantRunner

        r = TenantRunner(
            tenant_cfg=None,
            global_cfg=None,
            registry=None,
            transport=_transport({"/fanvue": [_row()]}, []),
        )
        await r._start_fanvue(_Cfg(), _globals(), object())
        try:
            await fake_agent.wait()
            assert r._cleanup and isinstance(r._cleanup[0], asyncio.Task)
        finally:
            await r._drain_cleanup()
