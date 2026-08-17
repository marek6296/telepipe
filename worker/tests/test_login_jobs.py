"""Telegram login cez DB frontu — stavový automat pollera `login_jobs.py`.

Telethon sa nikdy nevolá naozaj: `poll_once` dostane `client_factory`, ktorá
vracia `FakeTelethonClient` s naskriptovaným správaním (kód OK / zlý kód / 2FA
/ flood wait). Supabase je `httpx.MockTransport`, takže testy vidia presné URL
aj telá requestov — pri zápise session do `models` je to podstata kontraktu.
"""
import asyncio
import datetime
import json
from types import SimpleNamespace

import httpx
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

import login_jobs
from crypto import decrypt, encrypt
from login_jobs import poll_once
from transport import SupabaseTransport

KEY = "u" * 43 + "="
MODEL_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT_ID = "22222222-2222-2222-2222-222222222222"
API_HASH = "0123456789abcdef0123456789abcdef"


# ---------- fake Telethon ----------

class FakeSession:
    def __init__(self, value: str) -> None:
        self.value = value

    def save(self) -> str:
        return self.value


class FakeTelethonClient:
    """Len tie metódy, ktoré `login_jobs` naozaj volá."""

    def __init__(self, session, api_id, api_hash, script) -> None:
        self.init_session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = FakeSession(session or "")
        self.connected = False
        self.disconnected = False
        self.sent_phone = None
        self.sign_in_calls = []
        self._script = script

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def send_code_request(self, phone):
        self.sent_phone = phone
        if self._script.get("send_error"):
            raise self._script["send_error"]
        self.session.value = self._script.get("session_after_send", "TMP-SESSION")
        return SimpleNamespace(phone_code_hash=self._script.get("phone_code_hash", "HASH-1"))

    async def sign_in(self, phone=None, code=None, phone_code_hash=None, password=None):
        self.sign_in_calls.append(
            {"phone": phone, "code": code, "phone_code_hash": phone_code_hash,
             "password": password}
        )
        err = self._script.get("password_error") if password else self._script.get("code_error")
        if err:
            raise err
        self.session.value = self._script.get("session_after_login", "SESSION-FINAL")
        return SimpleNamespace(id=42, username="modelka")


def make_factory(script=None, created=None):
    """Sync factory ako skutočný `TelegramClient(...)` konštruktor."""
    script = script or {}
    created = created if created is not None else []

    def factory(session, api_id, api_hash):
        client = FakeTelethonClient(session, api_id, api_hash, script)
        created.append(client)
        return client

    return factory, created


# ---------- fake Supabase ----------

def make_transport(calls, jobs=None, model_rows=None):
    jobs = jobs or []
    model_rows = [{"tg_api_id": None, "status": "draft", "status_reason": ""}] \
        if model_rows is None else model_rows

    def handler(req):
        body = json.loads(req.content) if req.content else None
        calls.append({"method": req.method, "url": str(req.url), "path": req.url.path,
                      "params": dict(req.url.params), "body": body})
        if req.method == "GET" and req.url.path.endswith("/tg_login_jobs"):
            return httpx.Response(200, json=jobs)
        if req.method == "GET" and req.url.path.endswith("/models"):
            return httpx.Response(200, json=model_rows)
        return httpx.Response(200, json=[])

    t = SupabaseTransport("https://test.supabase.co", "test-key")
    t._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://test.supabase.co/rest/v1",
    )
    return t


def _in(minutes):
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=minutes)).isoformat()


def job_row(**over):
    row = {
        "id": 7,
        "model_id": MODEL_ID,
        "account_id": ACCOUNT_ID,
        "phase": "send_code",
        "phone": "+421900123456",
        "api_id": 12345,
        "api_hash_enc": encrypt(API_HASH, KEY),
        "code_enc": "",
        "password_enc": "",
        "phone_code_hash": "",
        "tmp_session_enc": "",
        "error": "",
        "expires_at": _in(9),
    }
    row.update(over)
    return row


def code_job(**over):
    return job_row(
        phase="verify_code",
        code_enc=encrypt("12345", KEY),
        phone_code_hash="HASH-1",
        tmp_session_enc=encrypt("TMP-SESSION", KEY),
        **over,
    )


def password_job(**over):
    return job_row(
        phase="verify_password",
        password_enc=encrypt("tajne2fa", KEY),
        phone_code_hash="HASH-1",
        tmp_session_enc=encrypt("TMP-SESSION", KEY),
        **over,
    )


def patches(calls, table):
    return [c for c in calls if c["method"] == "PATCH" and c["path"].endswith(table)]


def job_patch(calls, index=-1):
    return patches(calls, "/tg_login_jobs")[index]["body"]


# ---------- výber jobov ----------

async def test_poll_selects_only_unfinished_jobs():
    calls = []
    t = make_transport(calls)
    factory, _ = make_factory()
    await poll_once(t, KEY, client_factory=factory)

    get = calls[0]
    assert get["method"] == "GET" and get["path"].endswith("/tg_login_jobs")
    phases = get["params"]["phase"]
    assert phases.startswith("in.(") and phases.endswith(")")
    assert set(phases[4:-1].split(",")) == {
        "send_code", "code_sent", "verify_code", "need_password", "verify_password"
    }
    assert get["params"]["order"] == "id.asc"


async def test_waiting_job_is_left_alone():
    """`code_sent` čaká na používateľa — worker doň nesmie hrabať."""
    calls = []
    t = make_transport(calls, jobs=[job_row(phase="code_sent")])
    factory, created = make_factory()
    handled = await poll_once(t, KEY, client_factory=factory)
    assert handled == 0
    assert not created                       # žiadny Telethon klient
    assert not patches(calls, "/tg_login_jobs")


# ---------- send_code ----------

async def test_send_code_stores_hash_and_tmp_session():
    calls = []
    t = make_transport(calls, jobs=[job_row()])
    factory, created = make_factory({"phone_code_hash": "HASH-XY",
                                     "session_after_send": "TMP-42"})
    await poll_once(t, KEY, client_factory=factory)

    patch = patches(calls, "/tg_login_jobs")[-1]
    assert patch["params"] == {"id": "eq.7"}
    body = patch["body"]
    assert body["phase"] == "code_sent"
    assert body["phone_code_hash"] == "HASH-XY"
    assert decrypt(body["tmp_session_enc"], KEY) == "TMP-42"
    assert body["error"] == ""
    assert body["updated_at"]
    assert created[0].sent_phone == "+421900123456"


async def test_send_code_uses_decrypted_api_credentials():
    calls = []
    t = make_transport(calls, jobs=[job_row()])
    factory, created = make_factory()
    await poll_once(t, KEY, client_factory=factory)

    client = created[0]
    assert client.init_session == ""          # nový klient, prázdna session
    assert client.api_id == 12345
    assert client.api_hash == API_HASH        # dešifrované, nie ciphertext
    assert client.connected and client.disconnected


async def test_send_code_wipes_secrets_after_attempt():
    calls = []
    t = make_transport(calls, jobs=[job_row(code_enc=encrypt("old", KEY))])
    factory, _ = make_factory()
    await poll_once(t, KEY, client_factory=factory)
    body = job_patch(calls)
    assert body["code_enc"] == "" and body["password_enc"] == ""


# ---------- verify_code → done ----------

async def test_verify_code_writes_session_to_models():
    calls = []
    t = make_transport(calls, jobs=[code_job()])
    factory, created = make_factory({"session_after_login": "SESSION-OK"})
    await poll_once(t, KEY, client_factory=factory)

    model_patch = patches(calls, "/models")[-1]
    assert model_patch["url"] == \
        "https://test.supabase.co/rest/v1/models?id=eq.11111111-1111-1111-1111-111111111111"
    body = model_patch["body"]
    assert decrypt(body["tg_session_enc"], KEY) == "SESSION-OK"
    assert body["tg_api_hash"] == API_HASH    # plaintext — TenantConfig ho číta priamo
    assert body["tg_api_id"] == 12345         # models.tg_api_id ešte nebolo nastavené
    assert body["updated_at"]

    client = created[0]
    assert client.init_session == "TMP-SESSION"
    assert client.sign_in_calls == [
        {"phone": "+421900123456", "code": "12345", "phone_code_hash": "HASH-1",
         "password": None}
    ]


async def test_verify_code_keeps_existing_api_id():
    calls = []
    t = make_transport(calls, jobs=[code_job()],
                       model_rows=[{"tg_api_id": 12345, "status": "draft",
                                    "status_reason": ""}])
    factory, _ = make_factory()
    await poll_once(t, KEY, client_factory=factory)
    assert "tg_api_id" not in patches(calls, "/models")[-1]["body"]


async def test_done_job_wipes_every_secret():
    calls = []
    t = make_transport(calls, jobs=[code_job()])
    factory, _ = make_factory()
    await poll_once(t, KEY, client_factory=factory)

    body = job_patch(calls)
    assert body["phase"] == "done" and body["error"] == ""
    for column in ("code_enc", "password_enc", "tmp_session_enc",
                   "phone_code_hash", "api_hash_enc"):
        assert body[column] == "", column


async def test_relogin_clears_session_revoked_block():
    """Model v `error/session_revoked` sa cez RPC nedá aktivovať — odblokuj ho."""
    calls = []
    t = make_transport(calls, jobs=[code_job()],
                       model_rows=[{"tg_api_id": 12345, "status": "error",
                                    "status_reason": "session_revoked"}])
    factory, _ = make_factory()
    await poll_once(t, KEY, client_factory=factory)

    body = patches(calls, "/models")[-1]["body"]
    assert body["status"] == "draft" and body["status_reason"] == ""


async def test_healthy_model_status_untouched():
    calls = []
    t = make_transport(calls, jobs=[code_job()],
                       model_rows=[{"tg_api_id": 12345, "status": "paused",
                                    "status_reason": ""}])
    factory, _ = make_factory()
    await poll_once(t, KEY, client_factory=factory)
    body = patches(calls, "/models")[-1]["body"]
    assert "status" not in body


# ---------- verify_code → 2FA / zlý kód ----------

async def test_verify_code_needs_password():
    calls = []
    t = make_transport(calls, jobs=[code_job()])
    factory, _ = make_factory({"code_error": SessionPasswordNeededError(None),
                               "session_after_send": "x"})
    await poll_once(t, KEY, client_factory=factory)

    body = job_patch(calls)
    assert body["phase"] == "need_password"
    assert body["error"] == ""
    assert body["code_enc"] == "" and body["password_enc"] == ""
    assert decrypt(body["tmp_session_enc"], KEY) == "TMP-SESSION"
    assert not patches(calls, "/models")      # session ešte nie je hotová


async def test_invalid_code_goes_back_to_code_sent():
    calls = []
    t = make_transport(calls, jobs=[code_job()])
    factory, _ = make_factory({"code_error": PhoneCodeInvalidError(None)})
    await poll_once(t, KEY, client_factory=factory)

    body = job_patch(calls)
    assert body["phase"] == "code_sent"       # používateľ skúsi kód znova
    assert body["error"] == "invalid_code"
    assert body["code_enc"] == ""
    # medzistav sa NEMAŽE — inak by sa musel posielať nový kód
    assert "tmp_session_enc" not in body and "phone_code_hash" not in body


async def test_expired_code_is_terminal():
    calls = []
    t = make_transport(calls, jobs=[code_job()])
    factory, _ = make_factory({"code_error": PhoneCodeExpiredError(None)})
    await poll_once(t, KEY, client_factory=factory)

    body = job_patch(calls)
    assert body["phase"] == "error"
    assert body["error"] == "phone_code_expired"
    assert body["tmp_session_enc"] == "" and body["api_hash_enc"] == ""


# ---------- verify_password ----------

async def test_verify_password_finishes_login():
    calls = []
    t = make_transport(calls, jobs=[password_job()])
    factory, created = make_factory({"session_after_login": "SESSION-2FA"})
    await poll_once(t, KEY, client_factory=factory)

    assert created[0].sign_in_calls[0]["password"] == "tajne2fa"
    assert decrypt(patches(calls, "/models")[-1]["body"]["tg_session_enc"], KEY) \
        == "SESSION-2FA"
    assert job_patch(calls)["phase"] == "done"


async def test_invalid_password_goes_back_to_need_password():
    calls = []
    t = make_transport(calls, jobs=[password_job()])
    factory, _ = make_factory({"password_error": PasswordHashInvalidError(None)})
    await poll_once(t, KEY, client_factory=factory)

    body = job_patch(calls)
    assert body["phase"] == "need_password"
    assert body["error"] == "invalid_password"
    assert body["password_enc"] == ""
    assert "tmp_session_enc" not in body
    assert not patches(calls, "/models")


# ---------- chyby a upratovanie ----------

async def test_expired_job_is_cleaned_without_telethon():
    calls = []
    t = make_transport(calls, jobs=[code_job(expires_at=_in(-1))])
    factory, created = make_factory()
    handled = await poll_once(t, KEY, client_factory=factory)

    assert handled == 1
    assert not created                        # expirovaný job sa už nespracúva
    body = job_patch(calls)
    assert body["phase"] == "error" and body["error"] == "expired"
    for column in ("code_enc", "password_enc", "tmp_session_enc",
                   "phone_code_hash", "api_hash_enc"):
        assert body[column] == "", column


async def test_expired_waiting_job_is_cleaned_too():
    """Aj job čakajúci na používateľa musí po TTL prísť o tajomstvá."""
    calls = []
    t = make_transport(calls, jobs=[job_row(phase="need_password",
                                            password_enc=encrypt("x", KEY),
                                            expires_at=_in(-5))])
    factory, _ = make_factory()
    await poll_once(t, KEY, client_factory=factory)
    body = job_patch(calls)
    assert body["phase"] == "error" and body["error"] == "expired"
    assert body["password_enc"] == ""


async def test_flood_wait_records_seconds():
    calls = []
    t = make_transport(calls, jobs=[job_row()])
    factory, _ = make_factory({"send_error": FloodWaitError(None, capture=86400)})
    await poll_once(t, KEY, client_factory=factory)

    body = job_patch(calls)
    assert body["phase"] == "error"
    assert body["error"] == "flood_wait_86400"
    assert body["api_hash_enc"] == "" and body["tmp_session_enc"] == ""


async def test_rpc_error_marks_job_error():
    calls = []
    t = make_transport(calls, jobs=[job_row()])
    factory, _ = make_factory({"send_error": ApiIdInvalidError(None)})
    await poll_once(t, KEY, client_factory=factory)

    body = job_patch(calls)
    assert body["phase"] == "error" and body["error"] == "api_id_invalid"
    assert body["code_enc"] == "" and body["password_enc"] == ""


async def test_broken_ciphertext_marks_job_error():
    calls = []
    t = make_transport(calls, jobs=[job_row(api_hash_enc="nie-je-token")])
    factory, created = make_factory()
    await poll_once(t, KEY, client_factory=factory)

    assert not created
    assert job_patch(calls)["error"] == "decrypt_failed"


async def test_client_disconnects_even_on_error():
    calls = []
    t = make_transport(calls, jobs=[job_row()])
    factory, created = make_factory({"send_error": ApiIdInvalidError(None)})
    await poll_once(t, KEY, client_factory=factory)
    assert created[0].disconnected


async def test_transient_failure_leaves_job_for_next_round():
    """Sieťový výpadok nesmie job zabiť — TTL ho aj tak uprace."""
    calls = []
    t = make_transport(calls, jobs=[job_row()])
    factory, _ = make_factory({"send_error": httpx.ConnectError("bum")})
    handled = await poll_once(t, KEY, client_factory=factory)

    assert handled == 0
    assert not patches(calls, "/tg_login_jobs")


async def test_one_broken_job_does_not_stop_the_others():
    calls = []
    broken = job_row(id=1)
    good_a = job_row(id=2, model_id=MODEL_ID)
    good_b = code_job(id=3)
    t = make_transport(calls, jobs=[broken, good_a, good_b])

    created = []

    def factory(session, api_id, api_hash):
        if not created:                       # prvý job spadne na neznámej chybe
            created.append(None)
            raise RuntimeError("rozbitý job")
        client = FakeTelethonClient(session, api_id, api_hash, {})
        created.append(client)
        return client

    handled = await poll_once(t, KEY, client_factory=factory)

    assert handled == 2                       # prvý neprešiel, ďalšie dva áno
    ids = [p["params"]["id"] for p in patches(calls, "/tg_login_jobs")]
    assert ids == ["eq.2", "eq.3"]


# ---------- config + main wiring ----------

def test_config_login_jobs_poll_default(monkeypatch):
    from config import Config

    for k, v in {"SUPABASE_URL": "https://x.supabase.co",
                 "SUPABASE_SERVICE_KEY": "sk", "LLM_API_KEY": "ak",
                 "ENCRYPTION_KEY": KEY}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LOGIN_JOBS_POLL_S", raising=False)
    assert Config.from_env().login_jobs_poll_s == 2
    monkeypatch.setenv("LOGIN_JOBS_POLL_S", "0")
    assert Config.from_env().login_jobs_poll_s == 0


class _Cfg:
    def __init__(self, poll_s):
        self.login_jobs_poll_s = poll_s
        self.encryption_key = KEY


async def test_main_loop_polls_until_stop(monkeypatch):
    import main

    seen = []
    stop = asyncio.Event()

    async def fake_poll(transport, key, **kw):
        seen.append(key)
        if len(seen) >= 2:
            stop.set()
        return 0

    monkeypatch.setattr(login_jobs, "poll_once", fake_poll)
    await asyncio.wait_for(main._login_jobs_loop(_Cfg(0.01), object(), stop), 3)
    assert seen == [KEY, KEY]


async def test_main_loop_survives_poll_failure(monkeypatch):
    import main

    seen = []
    stop = asyncio.Event()

    async def boom(transport, key, **kw):
        seen.append(key)
        if len(seen) >= 2:
            stop.set()
        raise RuntimeError("Supabase down")

    monkeypatch.setattr(login_jobs, "poll_once", boom)
    await asyncio.wait_for(main._login_jobs_loop(_Cfg(0.01), object(), stop), 3)
    assert len(seen) == 2


async def test_main_loop_disabled_by_zero(monkeypatch):
    import main

    async def never(*a, **kw):
        raise AssertionError("poller mal byť vypnutý")

    monkeypatch.setattr(login_jobs, "poll_once", never)
    await asyncio.wait_for(main._login_jobs_loop(_Cfg(0), object(), asyncio.Event()), 1)
