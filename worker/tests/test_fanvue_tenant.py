"""Fanvue seam — šifrovanie tokenov, izolácia tenantov, spustenie agenta.

Toto je jediné miesto, kde plaintext token prechádza medzi `fanvue_api` a DB,
takže testy stoja hlavne na dvoch veciach: von z DB ide dešifrované, do DB ide
zašifrované — a nikdy naopak.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from crypto import encrypt
from fanvue_tenant import FanvueSupervisor, TenantFanvueDb, start_fanvue
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
        calls.append({
            "method": req.method,
            "url": str(req.url),
            "body": body,
            # `Prefer` rozhoduje o insert vs. upsert — bez neho by sa testom
            # zápisov dalo veriť len na polovicu.
            "headers": dict(req.headers),
        })
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
        # Ďaleko od konca platnosti: dozor obnovuje token dopredu (viď
        # `TestObnovaTokenu`), takže pevný dátum v minulosti by z každého
        # tick-u urobil pokus o volanie na auth.fanvue.com.
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
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


def _zrus(cleanup):
    """Zruší všetko z cleanupu — presne ako `runner._drain_cleanup`.

    Dozor drží dve deti (vault + agent) a nezrušený `while True` by v testoch
    prežil svoj test a zamiešal sa do ďalšieho.
    """
    for item in cleanup:
        if isinstance(item, asyncio.Task):
            item.cancel()
        elif hasattr(item, "vault_task"):        # FanvueSupervisor
            for dieta in (item.vault_task, item.agent_task):
                if dieta is not None:
                    dieta.cancel()


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
# Fanúšikovia (fv_users)
# ---------------------------------------------------------------------------


class TestFanusikovia:
    async def test_fan_filtruje_na_modelku_aj_uuid(self):
        calls = []
        db = _db({"/fv_users": [{"fan_uuid": "f1", "msg_count": 3}]}, calls)
        row = await db.fan("f1")
        assert row["msg_count"] == 3
        assert "fan_uuid=eq.f1" in calls[-1]["url"]
        assert f"model_id=eq.{MODEL}" in calls[-1]["url"]

    async def test_neznamy_fanusik_je_none(self):
        """`_ensure_fan` na tom stojí — None znamená „založ ho"."""
        assert await _db({"/fv_users": []}, []).fan("f1") is None

    async def test_upsert_fan_pribali_model_id_do_tela(self):
        calls = []
        await _db({}, calls).upsert_fan("f1", {"handle": "joe"})
        body = calls[-1]["body"]
        assert body == {"model_id": MODEL, "fan_uuid": "f1", "handle": "joe"}
        assert "merge-duplicates" in calls[-1]["headers"]["prefer"]

    async def test_update_fan_nikdy_nepustí_patch_bez_modelky(self):
        calls = []
        await _db({}, calls).update_fan("f1", {"greeted": True})
        assert f"model_id=eq.{MODEL}" in calls[-1]["url"]
        assert "fan_uuid=eq.f1" in calls[-1]["url"]
        assert calls[-1]["body"] == {"greeted": True}

    async def test_linked_tg_ids_vracia_cisla(self):
        db = _db({"/fv_users": [{"tg_id": 11}, {"tg_id": "22"}, {"tg_id": None}]}, [])
        assert await db.linked_tg_ids() == {11, 22}

    async def test_bez_fanusikov_nie_je_sparovany_nikto(self):
        assert await _db({"/fv_users": []}, []).linked_tg_ids() == set()


# ---------------------------------------------------------------------------
# Správy (fv_messages)
# ---------------------------------------------------------------------------


class TestSpravy:
    async def test_add_message_zapise_riadok_s_modelkou(self):
        calls = []
        await _db({}, calls).add_message("f1", "assistant", "ahoj")
        assert calls[-1]["body"] == {
            "model_id": MODEL, "fan_uuid": "f1", "role": "assistant", "content": "ahoj",
        }

    async def test_bez_message_uuid_sa_stlpec_neposiela(self):
        """Prázdny reťazec by v DB vyzeral ako id správy, ktoré neexistuje."""
        calls = []
        await _db({}, calls).add_message("f1", "user", "hej")
        assert "message_uuid" not in calls[-1]["body"]

    async def test_add_message_je_insert_nie_upsert(self):
        """PK je `id` — merge-duplicates by aj tak len vložil. Duplicity rieši
        `known_message_uuids`, nie databáza."""
        calls = []
        await _db({}, calls).add_message("f1", "user", "hej", "m-9")
        assert calls[-1]["body"]["message_uuid"] == "m-9"
        assert "merge-duplicates" not in calls[-1]["headers"]["prefer"]

    async def test_add_messages_prilepi_fanusika_ku_kazdemu_riadku(self):
        calls = []
        await _db({}, calls).add_messages(
            "f1", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        )
        assert all(r["fan_uuid"] == "f1" and r["model_id"] == MODEL for r in calls[-1]["body"])

    async def test_prazdna_davka_nezavola_nic(self):
        calls = []
        await _db({}, calls).add_messages("f1", [])
        assert calls == []

    async def test_known_message_uuids_zahodi_prazdne(self):
        db = _db({"/fv_messages": [{"message_uuid": "a"}, {"message_uuid": None}]}, [])
        assert await db.known_message_uuids("f1") == {"a"}

    async def test_history_vracia_od_najstarsej(self):
        """DB dáva `id.desc` (najnovšie), prompt chce chronológiu."""
        rows = [
            {"role": "assistant", "content": "nova"},
            {"role": "user", "content": "stara"},
        ]
        calls = []
        db = _db({"/fv_messages": rows}, calls)
        assert await db.history("f1", limit=2) == [
            {"role": "user", "content": "stara"},
            {"role": "assistant", "content": "nova"},
        ]
        assert "order=id.desc" in calls[-1]["url"] and "limit=2" in calls[-1]["url"]


# ---------------------------------------------------------------------------
# Vault (fv_folders / fv_media / fv_media_sends)
# ---------------------------------------------------------------------------


class TestVault:
    async def test_folders_su_zoradene_podla_mena(self):
        calls = []
        await _db({"/fv_folders": []}, calls).folders()
        assert "order=name.asc" in calls[-1]["url"]

    async def test_save_folder_upsertuje_na_meno(self):
        calls = []
        await _db({}, calls).save_folder("Posts", {"role": "post"})
        assert calls[-1]["body"] == {"model_id": MODEL, "name": "Posts", "role": "post"}
        assert "merge-duplicates" in calls[-1]["headers"]["prefer"]

    async def test_upsert_media_oznaci_kazdy_riadok_modelkou(self):
        calls = []
        await _db({}, calls).upsert_media([{"media_uuid": "m1"}, {"media_uuid": "m2"}])
        assert [r["model_id"] for r in calls[-1]["body"]] == [MODEL, MODEL]

    async def test_prazdny_sync_nezapisuje(self):
        calls = []
        await _db({}, calls).upsert_media([])
        assert calls == []

    async def test_media_in_berie_len_aktivne_z_priecinka(self):
        calls = []
        await _db({"/fv_media": []}, calls).media_in("Clients NSFW")
        url = calls[-1]["url"]
        assert "active=is.true" in url and "folder=eq.Clients" in url

    async def test_update_media_filtruje_na_modelku(self):
        calls = []
        await _db({}, calls).update_media("m1", {"posted_at": "2026-08-17T00:00:00Z"})
        assert f"model_id=eq.{MODEL}" in calls[-1]["url"]
        assert "media_uuid=eq.m1" in calls[-1]["url"]

    async def test_sent_media_je_mnozina_uuid(self):
        db = _db({"/fv_media_sends": [{"media_uuid": "m1"}, {"media_uuid": "m2"}]}, [])
        assert await db.sent_media("f1") == {"m1", "m2"}

    async def test_record_send_upsertuje_prirodzeny_kluc(self):
        """PK je (model_id, media_uuid, fan_uuid) — druhé poslanie riadok
        neprimnoží."""
        calls = []
        await _db({}, calls).record_send("m1", "f1", 900)
        assert calls[-1]["body"] == {
            "model_id": MODEL, "media_uuid": "m1", "fan_uuid": "f1", "price_cents": 900,
        }
        assert "merge-duplicates" in calls[-1]["headers"]["prefer"]


# ---------------------------------------------------------------------------
# Izolácia dátovej vrstvy — každá metóda zvlášť
# ---------------------------------------------------------------------------


class TestIzolaciaFvTabuliek:
    @pytest.mark.parametrize(
        "call",
        [
            lambda db: db.fan("f1"),
            lambda db: db.upsert_fan("f1", {"handle": "j"}),
            lambda db: db.update_fan("f1", {"greeted": True}),
            lambda db: db.linked_tg_ids(),
            lambda db: db.add_message("f1", "user", "a"),
            lambda db: db.add_messages("f1", [{"role": "user", "content": "a"}]),
            lambda db: db.known_message_uuids("f1"),
            lambda db: db.history("f1"),
            lambda db: db.folders(),
            lambda db: db.save_folder("F", {"role": "post"}),
            lambda db: db.upsert_media([{"media_uuid": "m1"}]),
            lambda db: db.media_in("F"),
            lambda db: db.all_media(),
            lambda db: db.update_media("m1", {"active": False}),
            lambda db: db.sent_media("f1"),
            lambda db: db.record_send("m1", "f1", 100),
        ],
    )
    async def test_model_id_je_v_kazdom_volani(self, call):
        """Zapisuje sa service kľúčom, RLS teda neplatí — `model_id` v dotaze
        alebo v tele je JEDINÉ, čo drží modelky oddelené."""
        calls = []
        rows = {p: [] for p in ("/fv_users", "/fv_messages", "/fv_folders",
                                "/fv_media", "/fv_media_sends")}
        await call(_db(rows, calls))
        assert calls, "metóda nesiahla do DB vôbec"
        for c in calls:
            in_url = f"model_id=eq.{MODEL}" in c["url"]
            body = c["body"] if isinstance(c["body"], list) else [c["body"]]
            in_body = bool(body) and all(
                isinstance(r, dict) and r.get("model_id") == MODEL for r in body
            )
            assert in_url or in_body, c

    async def test_dvaja_tenanti_nevidia_do_toho_isteho_chatu(self):
        calls = []
        t = _transport({"/fv_messages": []}, calls)
        await TenantFanvueDb(t, "model-A", KEY).history("spolocny-fan")
        await TenantFanvueDb(t, "model-B", KEY).history("spolocny-fan")
        assert "model_id=eq.model-A" in calls[0]["url"]
        assert "model_id=eq.model-B" in calls[1]["url"]


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
    async def test_nepripojeny_ucet_nespusti_ziadnu_pracu(self, fake_agent):
        """Nič sa nerozbehne — ale DOZOR beží ďalej, viď `TestDozor`."""
        cleanup = []
        sup = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row(connected=False)]}, []), None, cleanup
        )
        try:
            assert sup is not None
            assert sup.vault_task is None and sup.agent_task is None
            assert fake_agent.made == []
        finally:
            _zrus(cleanup)

    async def test_vypnute_odpisovanie_agenta_nespusti(self, fake_agent):
        """`enabled` je vypínač ODPISOVANIA — účet môže byť pripojený a ticho."""
        cleanup = []
        sup = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row(enabled=False)]}, []), None, cleanup
        )
        try:
            assert sup.agent_task is None
            # Vault sa načítava aj tak: priradiť priečinkom rolu musí ísť SKÔR,
            # než sa agent zapne.
            assert sup.vault_task is not None
            assert fake_agent.made == [], "agent sa nesmel spustiť"
        finally:
            _zrus(cleanup)

    async def test_pripojeny_ucet_pusti_aj_nacitanie_vaultu(self, fake_agent):
        cleanup = []
        sup = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row()]}, []), object(), cleanup
        )
        try:
            assert sup.vault_task is not None and sup.agent_task is not None
        finally:
            _zrus(cleanup)

    async def test_bez_appky_sa_do_db_ani_nepozera(self):
        calls = []
        sup = await start_fanvue(
            _Cfg(),
            _globals(fanvue_client_id="", fanvue_client_secret=""),
            _transport({"/fanvue": [_row()]}, calls),
            None,
            [],
        )
        assert sup is None and calls == []

    async def test_chybajuci_riadok_nevadi(self, fake_agent):
        cleanup = []
        sup = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": []}, []), None, cleanup
        )
        try:
            assert sup.vault_task is None and sup.agent_task is None
        finally:
            _zrus(cleanup)

    async def test_dozor_a_upratovanie_idu_do_cleanupu_v_poradi(self, fake_agent):
        """Runner ide cleanupom odpredu: najprv sa zruší slučka dozoru a až
        potom sa `close()`-om pozatvárajú jej deti (klient, ktorý používajú)."""
        cleanup = []
        sup = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row()]}, []), object(), cleanup
        )
        try:
            assert isinstance(cleanup[0], asyncio.Task)
            assert cleanup[1] is sup
            assert hasattr(sup, "close")
        finally:
            _zrus(cleanup)

    async def test_pripojeny_a_zapnuty_agent_bezi(self, fake_agent):
        cleanup = []
        sup = await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row()]}, []), object(), cleanup
        )
        try:
            assert sup.agent_task is not None
            await fake_agent.wait()
        finally:
            _zrus(cleanup)

    async def test_agent_dostane_ten_isty_metered_llm(self, fake_agent):
        """Fanvue musí platiť z toho istého kreditu ako Telegram."""
        llm = object()
        cleanup = []
        await start_fanvue(
            _Cfg(), _globals(), _transport({"/fanvue": [_row()]}, []), llm, cleanup
        )
        try:
            await fake_agent.wait()
            agent = fake_agent.made[-1]
            assert agent.llm is llm
            assert isinstance(agent.db, TenantFanvueDb) and agent.db.model_id == MODEL
        finally:
            _zrus(cleanup)


# ---------------------------------------------------------------------------
# Dozor nad prepínačmi za behu
# ---------------------------------------------------------------------------
#
# Kto pripojil Fanvue až po štarte workera, nedostal doteraz ani agenta, ani
# načítanie vaultu — a nedozvedel sa prečo, lebo v dashboarde bolo všetko
# „pripojené". Ožilo to až reštartom modelky, čo znamená aj odpojenie Telethonu.
# Tá cena za prepnutie jedného vypínača je príliš vysoká.


class _MenlivyRiadok:
    """Transport, ktorého riadok `fanvue` sa dá medzi tickami meniť."""

    def __init__(self, row):
        self.row = row
        self.calls = []

    def transport(self):
        return _transport_z_callable(lambda: [self.row] if self.row else [], self.calls)


def _transport_z_callable(rows_fn, calls):
    def handler(req):
        path = str(req.url.path).replace("/rest/v1", "")
        try:
            body = json.loads(req.content) if req.content else None
        except ValueError:
            body = None
        calls.append({"method": req.method, "url": str(req.url), "body": body})
        if req.method != "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=rows_fn() if path == "/fanvue" else [])

    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://x.supabase.co/rest/v1"
    )
    return t


class TestDozor:
    async def test_pripojenie_za_behu_rozbehne_vault_aj_agenta(self, fake_agent):
        """Náprava nálezu: pripojenie po štarte workera si doteraz vyžiadalo
        reštart celej modelky."""
        zdroj = _MenlivyRiadok(_row(connected=False))
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
        try:
            await sup.tick()
            assert sup.vault_task is None and sup.agent_task is None

            zdroj.row = _row()               # majiteľ práve pripojil a zapol
            await sup.tick()
            assert sup.vault_task is not None
            assert sup.agent_task is not None
            await fake_agent.wait()
        finally:
            await sup.close()

    async def test_vypnutie_za_behu_zastavi_agenta_a_vault_necha(self, fake_agent):
        """Vypínač je len o odpisovaní — vault sa načítava aj potichu."""
        zdroj = _MenlivyRiadok(_row())
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
        try:
            await sup.tick()
            agent = sup.agent_task
            assert agent is not None

            zdroj.row = _row(enabled=False)
            await sup.tick()
            assert sup.agent_task is None
            assert agent.cancelled() or agent.done()
            assert sup.vault_task is not None
        finally:
            await sup.close()

    async def test_odpojenie_zastavi_vsetko(self, fake_agent):
        zdroj = _MenlivyRiadok(_row())
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
        try:
            await sup.tick()
            vault, agent = sup.vault_task, sup.agent_task

            zdroj.row = _row(connected=False)
            await sup.tick()
            assert sup.vault_task is None and sup.agent_task is None
            assert vault.done() and agent.done()
        finally:
            await sup.close()

    async def test_opakovane_ticky_nespustia_druhu_kopiu(self, fake_agent):
        """Dva agenti na jednom účte by odpísali dvakrát na tú istú správu."""
        zdroj = _MenlivyRiadok(_row())
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
        try:
            for _ in range(4):
                await sup.tick()
            assert len(fake_agent.made) == 1
        finally:
            await sup.close()

    async def test_opakovane_ticky_drzia_tie_iste_ulohy(self, fake_agent):
        zdroj = _MenlivyRiadok(_row())
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
        try:
            await sup.tick()
            vault, agent = sup.vault_task, sup.agent_task
            await sup.tick()
            assert sup.vault_task is vault and sup.agent_task is agent
        finally:
            await sup.close()

    async def test_vypnutie_a_zapnutie_agenta_zopakuje(self, fake_agent):
        zdroj = _MenlivyRiadok(_row())
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
        try:
            await sup.tick()
            zdroj.row = _row(enabled=False)
            await sup.tick()
            zdroj.row = _row()
            await sup.tick()
            assert sup.agent_task is not None
            assert len(fake_agent.made) == 2
        finally:
            await sup.close()

    async def test_vypadok_db_nic_nevypina(self, fake_agent):
        """Nedostupná Supabase neznamená, že niekto Fanvue odpojil."""
        stav = {"padaj": False}

        def rows():
            if stav["padaj"]:
                raise httpx.ConnectError("supabase down")
            return [_row()]

        t = _transport_z_callable(rows, [])
        sup = FanvueSupervisor(_Cfg(), _globals(), t, object())
        try:
            await sup.tick()
            vault, agent = sup.vault_task, sup.agent_task
            stav["padaj"] = True
            await sup.tick()                 # nesmie vyhodiť ani nič zrušiť
            assert sup.vault_task is vault and sup.agent_task is agent
        finally:
            await sup.close()

    async def test_close_uprace_vsetko(self, fake_agent):
        zdroj = _MenlivyRiadok(_row())
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
        await sup.tick()
        vault, agent = sup.vault_task, sup.agent_task
        await sup.close()
        assert vault.done() and agent.done()
        assert sup.vault_task is None and sup.agent_task is None

    async def test_zlyhany_tick_slucku_nezhodi(self, fake_agent, monkeypatch):
        zdroj = _MenlivyRiadok(_row())
        sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object(), poll_s=0)
        volania = {"n": 0}

        async def obcas_padne():
            volania["n"] += 1
            if volania["n"] == 1:
                raise RuntimeError("bum")

        monkeypatch.setattr(sup, "tick", obcas_padne)
        task = asyncio.create_task(sup.run())
        for _ in range(30):
            await asyncio.sleep(0)
            if volania["n"] >= 3:
                break
        task.cancel()
        assert volania["n"] >= 3, "slučka sa zastavila po prvej chybe"


# ---------------------------------------------------------------------------
# Fronta „načítaj vault"
# ---------------------------------------------------------------------------


class TestFrontaSync:
    async def test_pending_sync_berie_nedokoncenu_od_najstarsej(self):
        calls = []
        db = _db({"/fanvue_sync_requests": []}, calls)
        assert await db.pending_sync() is None
        url = calls[-1]["url"]
        assert "finished_at=is.null" in url
        assert "order=id.asc" in url and "limit=1" in url
        assert f"model_id=eq.{MODEL}" in url

    async def test_start_sync_zapise_cas_a_filtruje_na_riadok(self):
        calls = []
        await _db({}, calls).start_sync(4)
        assert "id=eq.4" in calls[-1]["url"]
        assert f"model_id=eq.{MODEL}" in calls[-1]["url"]
        assert calls[-1]["body"]["started_at"]

    async def test_finish_sync_zapise_vysledok(self):
        calls = []
        await _db({}, calls).finish_sync(4, ok=True, folders=3, media_new=7, media_seen=40)
        body = calls[-1]["body"]
        assert body["ok"] is True and body["folders"] == 3
        assert body["media_new"] == 7 and body["media_seen"] == 40
        assert body["finished_at"] and body["error"] == ""

    async def test_neuspech_riadok_tiez_uzavrie(self):
        """`finished_at is null` je zámok — otvorená požiadavka by zablokovala
        tlačidlo aj pre ďalšie pokusy."""
        calls = []
        await _db({}, calls).finish_sync(4, ok=False, error="401 Unauthorized")
        body = calls[-1]["body"]
        assert body["ok"] is False and body["finished_at"]
        assert body["error"] == "401 Unauthorized"

    async def test_dlha_chyba_sa_skrati(self):
        calls = []
        await _db({}, calls).finish_sync(4, ok=False, error="x" * 900)
        assert len(calls[-1]["body"]["error"]) == 400

    async def test_mark_vault_synced_pise_do_fanvue(self):
        calls = []
        await _db({}, calls).mark_vault_synced()
        assert calls[-1]["url"].split("?")[0].endswith("/fanvue")
        assert f"model_id=eq.{MODEL}" in calls[-1]["url"]
        assert calls[-1]["body"]["media_synced_at"]

    async def test_prune_maze_len_dobehnute_a_stare(self):
        """Fronta je krátkodobá pracovná pamäť — dashboard z nej číta výsledok
        POSLEDNÉHO kliku. Nikto ju doteraz nemazal a pri dennej synchronizácii
        rástla donekonečna."""
        calls = []
        await _db({}, calls).prune_sync(24)
        posledny = calls[-1]
        assert posledny["method"] == "DELETE"
        assert posledny["url"].split("?")[0].endswith("/fanvue_sync_requests")
        assert f"model_id=eq.{MODEL}" in posledny["url"]
        assert "finished_at=lt." in posledny["url"]

    async def test_prune_nesiaha_na_nedokoncene(self):
        """`finished_at is null` je zámok tlačidla — jeho tiché zmiznutie by
        zamaskovalo zaseknutú synchronizáciu."""
        calls = []
        await _db({}, calls).prune_sync(24)
        assert "finished_at=is.null" not in calls[-1]["url"]

    async def test_prune_hranica_je_v_minulosti(self):
        from urllib.parse import parse_qs, urlparse

        calls = []
        await _db({}, calls).prune_sync(24)
        hranica = parse_qs(urlparse(calls[-1]["url"]).query)["finished_at"][0]
        kedy = datetime.fromisoformat(hranica.removeprefix("lt."))
        odstup = datetime.now(timezone.utc) - kedy
        assert 23.9 * 3600 < odstup.total_seconds() < 24.1 * 3600

    async def test_prune_nikdy_nemaze_cerstve(self):
        """Nezmyselný vstup (0 h) by inak zmazal aj to, na čo sa práve pozerá
        dashboard — dolná hranica je hodina."""
        from urllib.parse import parse_qs, urlparse

        calls = []
        await _db({}, calls).prune_sync(0)
        hranica = parse_qs(urlparse(calls[-1]["url"]).query)["finished_at"][0]
        kedy = datetime.fromisoformat(hranica.removeprefix("lt."))
        assert (datetime.now(timezone.utc) - kedy).total_seconds() > 3500

    async def test_delete_bez_filtra_je_chyba(self):
        """PostgREST bez filtra zmaže tabuľku. Poistka v transporte."""
        t = _transport({}, [])
        with pytest.raises(ValueError):
            await t._delete("/fanvue_sync_requests", {})

    @pytest.mark.parametrize(
        "call",
        [
            lambda db: db.pending_sync(),
            lambda db: db.start_sync(1),
            lambda db: db.finish_sync(1, ok=True),
            lambda db: db.mark_vault_synced(),
            lambda db: db.prune_sync(24),
        ],
    )
    async def test_model_id_je_v_kazdom_volani(self, call):
        calls = []
        await call(_db({"/fanvue_sync_requests": []}, calls))
        assert calls
        for c in calls:
            assert f"model_id=eq.{MODEL}" in c["url"], c["url"]


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


# ---------------------------------------------------------------------------
# Obnova prístupového tokenu dopredu
# ---------------------------------------------------------------------------
#
# Nález z produkcie: Simona mala Fanvue pripojenú, ale agenta vypnutého. Token
# žije hodinu a `fanvue_api._access_token` ho obnovuje až vtedy, keď sa niečo
# volá — pri vypnutom agentovi teda nikdy. V dashboarde potom svietilo „vypršal
# pred hodinou", hoci pripojenie bolo zdravé, a opätovné pripojenie to riešilo
# presne na jednu hodinu.


class _FakeApi:
    """Falošné Fanvue API — počíta pokusy o obnovu, volať sa nikam nechodí."""

    def __init__(self, error: Exception | None = None):
        self.calls = 0
        self.error = error

    async def ensure_token(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return "fresh-token"

    async def close(self):
        pass


def _sup_s_api(row, api):
    """Dozor s podvrhnutým API. `_ensure_api` by inak postavil skutočné."""
    zdroj = _MenlivyRiadok(row)
    sup = FanvueSupervisor(_Cfg(), _globals(), zdroj.transport(), object())
    sup._ensure_api = lambda: setattr(sup, "_api", api)
    return sup, zdroj


def _o(**over):
    """Riadok s vlastným časom vypršania."""
    return _row(**over)


def _za(sekundy):
    return (datetime.now(timezone.utc) + timedelta(seconds=sekundy)).isoformat()


class TestObnovaTokenu:
    async def test_vyprsany_token_sa_obnovi_aj_ked_agent_nebezi(self, fake_agent):
        api = _FakeApi()
        sup, _ = _sup_s_api(_o(enabled=False, expires_at=_za(-60)), api)
        try:
            await sup.tick()
            assert api.calls == 1
            assert sup.agent_task is None      # vypínač sa tým nezaplo
        finally:
            await sup.close()

    async def test_tesne_pred_vyprsanim_sa_obnovi(self, fake_agent):
        api = _FakeApi()
        sup, _ = _sup_s_api(_o(enabled=False, expires_at=_za(120)), api)
        try:
            await sup.tick()
            assert api.calls == 1
        finally:
            await sup.close()

    async def test_cerstvy_token_sa_neobnovuje(self, fake_agent):
        api = _FakeApi()
        sup, _ = _sup_s_api(_o(enabled=False, expires_at=_za(3600)), api)
        try:
            await sup.tick()
            await sup.tick()
            assert api.calls == 0
        finally:
            await sup.close()

    async def test_odpojeny_ucet_sa_neobnovuje(self, fake_agent):
        api = _FakeApi()
        sup, _ = _sup_s_api(_o(connected=False, expires_at=_za(-60)), api)
        try:
            await sup.tick()
            assert api.calls == 0
        finally:
            await sup.close()

    async def test_bez_obnovovacieho_tokenu_sa_neskusa(self, fake_agent):
        """Bez refresh tokenu nemá čo obnovovať — účet treba pripojiť znova."""
        api = _FakeApi()
        sup, _ = _sup_s_api(_o(enabled=False, refresh_token_enc="", expires_at=_za(-60)), api)
        try:
            await sup.tick()
            assert api.calls == 0
        finally:
            await sup.close()

    async def test_zlyhanie_sa_neopakuje_dokola(self, fake_agent):
        """Neplatný refresh token by inak búchal na Fanvue každých 30 sekúnd."""
        api = _FakeApi(RuntimeError("Obnova tokenu zlyhala: 400"))
        sup, _ = _sup_s_api(_o(enabled=False, expires_at=_za(-60)), api)
        try:
            for _ in range(5):
                await sup.tick()
            assert api.calls == 1
        finally:
            await sup.close()

    async def test_zlyhanie_nezhodi_dozor_ani_vault(self, fake_agent):
        api = _FakeApi(RuntimeError("Obnova tokenu zlyhala: 400"))
        sup, _ = _sup_s_api(_o(enabled=True, expires_at=_za(-60)), api)
        try:
            await sup.tick()                   # nesmie hodiť
            assert sup.vault_task is not None
            assert sup.agent_task is not None
        finally:
            await sup.close()

    async def test_nove_pripojenie_odblokuje_dalsi_pokus(self, fake_agent):
        """Po opätovnom pripojení je v riadku INÝ refresh token — vtedy sa skúša
        znova. Bez toho by oprava v dashboarde ostala bez účinku až do reštartu."""
        api = _FakeApi(RuntimeError("Obnova tokenu zlyhala: 400"))
        sup, zdroj = _sup_s_api(_o(enabled=False, expires_at=_za(-60)), api)
        try:
            await sup.tick()
            await sup.tick()
            assert api.calls == 1

            api.error = None
            zdroj.row = _o(
                enabled=False,
                expires_at=_za(-60),
                refresh_token_enc=encrypt("refresh-novy", KEY),
            )
            await sup.tick()
            assert api.calls == 2
        finally:
            await sup.close()

    async def test_chybajuci_cas_vyprsania_je_dovod_na_obnovu(self, fake_agent):
        """Prázdny `expires_at` znamená „nevieme" — bezpečnejšie je obnoviť."""
        api = _FakeApi()
        sup, _ = _sup_s_api(_o(enabled=False, expires_at=None), api)
        try:
            await sup.tick()
            assert api.calls == 1
        finally:
            await sup.close()
