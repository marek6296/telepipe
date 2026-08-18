"""TenantDb — každý dotaz nesie model_id; izolácia tenantov."""
import inspect
import json
import sys
import types

import httpx
import pytest
from db import TenantDb
from transport import SupabaseTransport

MODEL = "model-A"


def _capture(store):
    def handler(req):
        try:
            body = json.loads(req.content) if req.content else None
        except ValueError:
            body = None  # binárny obsah — upload do úložiska
        store.append({"method": req.method, "url": str(req.url), "body": body})
        return httpx.Response(200, json=[])
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")
    return t


async def test_every_get_filters_by_model_id():
    seen = []
    db = TenantDb(_capture(seen), "model-A")
    await db.get_persona()
    await db.recent_messages(42, limit=10)
    await db.photo_library()
    for call in seen:
        assert "model_id=eq.model-A" in call["url"], call["url"]


async def test_writes_carry_model_id():
    seen = []
    db = TenantDb(_capture(seen), "model-A")
    await db.add_message(42, "user", "ahoj")
    body = seen[-1]["body"]
    assert body["model_id"] == "model-A" and body["tg_id"] == 42


async def test_two_tenants_never_share_transport_state():
    seen = []
    t = _capture(seen)
    a, b = TenantDb(t, "model-A"), TenantDb(t, "model-B")
    await a.get_behavior(); await b.get_behavior()
    assert "model_id=eq.model-A" in seen[0]["url"]
    assert "model_id=eq.model-B" in seen[1]["url"]


# ---------------------------------------------------------------------------
# Vyčerpávajúca sieť: KAŽDÁ verejná metóda sa zavolá a každý HTTP dotaz, ktorý
# z nej vypadne, musí byť pripnutý na model_id. Toto je skutočná poistka proti
# úniku medzi tenantmi — nová metóda bez filtra tu spadne.
# ---------------------------------------------------------------------------

SINCE = "2026-01-01T00:00:00+00:00"

# metóda -> (args, kwargs)
CALLS = {
    "get_persona": ((), {}),
    "set_persona_field": (("name", "Eva"), {}),
    "get_behavior": ((), {}),
    "set_behavior_field": (("heat", "hot"), {}),
    "get_schedule": ((), {}),
    "pair_control_bot": (("TP-4F9K2X", 777), {}),
    "is_paused": ((), {}),
    "set_paused": ((True,), {}),
    "get_user": ((42,), {}),
    "ensure_user": ((42, "user", "Eva", "sk"), {}),
    "update_user": ((42, {"msg_count": 3}), {}),
    "find_user_by_username": (("@user",), {}),
    "wipe_conversation": ((42,), {}),
    "links_sent_since": ((SINCE,), {}),
    "active_chats": ((SINCE,), {}),
    "people_since": ((SINCE,), {}),
    "replies_since": ((SINCE,), {}),
    "recent_conversations": ((), {}),
    "sessions_to_close": ((), {}),
    "pending_users": ((), {}),
    "outreach_candidates": ((), {}),
    "unanswered_users": ((), {}),
    "add_message": ((42, "user", "ahoj"), {}),
    "recent_messages": ((42, 10), {}),
    "facts_for": ((42,), {}),
    "apply_facts": ((42, {"confirms": [11], "inserts": [{"key": "city", "value": "BA"}],
                          "supersedes": [12]}), {}),
    "add_episode": ((42, {"started_at": SINCE, "ended_at": SINCE, "title": "t"}), {}),
    "episodes_for": ((42,), {}),
    "open_loops": ((42,), {}),
    "add_loop": ((42, "dá vedieť ako dopadol pohovor"), {}),
    "close_loop": ((7,), {}),
    "search_archive": ((42, "pohovor"), {}),
    "self_claims": ((42,), {}),
    "add_self_claim": ((42, "som z Bratislavy"), {}),
    "log_judge": ((42, "draft", "fixed", "prečo"), {}),
    "tidy_facts": ((42,), {}),
    "photo_library": ((), {}),
    "photos_sent_to": ((42,), {}),
    "voice_library": ((), {}),
    "voices_sent_to": ((42,), {}),
    "record_voice_send": ((3, 42), {}),
    "record_photo_send": ((3, 42), {}),
    "_voice_count": ((3,), {}),
    "_photo_count": ((3,), {}),
    "upload_voice": (("model-A/x.ogg", b"zvuk"), {}),
    "add_voice_clip": (({"text": "ahoj", "url": "u"},), {}),
    "voice_clips": ((), {}),
    "pending_voice_job": ((), {}),
    "claim_voice_job": ((9,), {}),
    "finish_voice_job": ((9,), {}),
    "add_voice_job": (({"text": "ahoj"},), {}),
    "stats": ((), {}),
}

# Tenké delegáty na transport — samé o sebe žiadnu tabuľku neoslovujú.
DELEGATES = {"_get", "_patch", "_post"}


def _public_methods():
    return {
        name
        for name, fn in inspect.getmembers(TenantDb, inspect.iscoroutinefunction)
        if not name.startswith("__") and name not in DELEGATES
    }


def _assert_scoped(call, method_name):
    url, verb, body = call["url"], call["method"], call["body"]
    where = f"{method_name} -> {verb} {url} body={body}"

    if "/storage/" in url:
        # Cesty v úložisku sú už tenant-unikátne (volajúci ich stavia zo schémy
        # == model_id), model_id sa sem nepridáva.
        return

    if "/rpc/" in url:
        # RPC nemá URL filter — model_id musí byť v argumentoch. `pair_control_bot`
        # to má obzvlášť kriticky: bez `p_model` by párovací kód jednej modelky
        # prestavil majiteľa inej.
        assert any(fn in url for fn in ("search_messages", "pair_control_bot")), where
        assert body and body.get("p_model") == MODEL, where
        return

    if verb == "POST":
        # Insert/upsert: model_id musí byť v každom riadku tela.
        rows = body if isinstance(body, list) else [body]
        assert rows, where
        for row in rows:
            assert row.get("model_id") == MODEL, where
        return

    # Filtre (GET/PATCH/DELETE) musia byť v URL — telo pri PATCH nestačí.
    assert f"model_id=eq.{MODEL}" in url, where


def _stub_helper_modules(monkeypatch):
    """`tidy_facts` si ťahá `facts` a `similar` — tie prídu až v Task 9."""
    facts_mod = types.ModuleType("facts")
    facts_mod.is_transient = lambda key, value: False
    similar_mod = types.ModuleType("similar")
    similar_mod.same_idea = lambda a, b: False
    monkeypatch.setitem(sys.modules, "facts", facts_mod)
    monkeypatch.setitem(sys.modules, "similar", similar_mod)


def test_dispatch_table_covers_every_method():
    """Nová metóda bez záznamu v CALLS = diera v sieti. Radšej nech spadne."""
    assert _public_methods() == set(CALLS), _public_methods() ^ set(CALLS)


@pytest.mark.parametrize("name", sorted(CALLS))
async def test_all_table_methods_scoped(name, monkeypatch):
    _stub_helper_modules(monkeypatch)
    args, kwargs = CALLS[name]
    seen = []
    db = TenantDb(_capture(seen), MODEL)

    await getattr(db, name)(*args, **kwargs)

    assert seen, f"{name} neposlala žiadny dotaz — test by nič neoveril"
    for call in seen:
        _assert_scoped(call, name)


async def test_post_upsert_bodies_carry_model_id():
    """Upserty do *_sends idú na zloženom PK (model_id, *_id, tg_id)."""
    seen = []
    db = TenantDb(_capture(seen), MODEL)
    await db.record_photo_send(5, 42)
    await db.record_voice_send(6, 42)
    posts = [c for c in seen if c["method"] == "POST"]
    assert len(posts) == 2
    for call in posts:
        assert call["body"]["model_id"] == MODEL, call
        assert call["body"]["tg_id"] == 42, call


async def test_search_archive_passes_p_model():
    seen = []
    db = TenantDb(_capture(seen), MODEL)
    await db.search_archive(42, "pohovor")
    call = seen[-1]
    assert "/rpc/search_messages" in call["url"]
    assert call["body"] == {"p_model": MODEL, "p_tg_id": 42, "p_query": "pohovor", "p_limit": 5}


async def test_search_archive_skips_empty_query():
    seen = []
    db = TenantDb(_capture(seen), MODEL)
    assert await db.search_archive(42, "   ") == []
    assert seen == []


async def test_wipe_conversation_deletes_only_own_tenant():
    seen = []
    db = TenantDb(_capture(seen), MODEL)
    await db.wipe_conversation(42)
    deletes = [c for c in seen if c["method"] == "DELETE"]
    assert len(deletes) == 7
    for call in deletes:
        assert f"model_id=eq.{MODEL}" in call["url"] and "tg_id=eq.42" in call["url"]


async def test_singleton_tables_keyed_by_model_id_not_id():
    """persona/behavior/settings už nemajú stĺpec `id` — filter je model_id."""
    seen = []
    db = TenantDb(_capture(seen), MODEL)
    await db.set_persona_field("name", "Eva")
    await db.set_behavior_field("heat", "hot")
    await db.set_paused(True)
    await db.is_paused()
    for call in seen:
        assert "id=eq.1" not in call["url"], call["url"]
        assert f"model_id=eq.{MODEL}" in call["url"]


# ---------------------------------------------------------------------------
# ElevenLabs seam (migrácia 014)
#
# `behavior.eleven_key_enc` je šifrovaný AES-256-GCM; portované moduly
# (userbot/speech/voices/fvvoice) čítajú `behavior["eleven_key"]` ako čistý
# text a nesmú o šifrovaní vedieť. Rozhranie medzi tými dvoma svetmi je
# `get_behavior()` — a presne to sa tu overuje.
# ---------------------------------------------------------------------------

from crypto import encrypt  # noqa: E402  (patrí k sekcii nižšie)

KEY = "3q2+796tvu/erb7v3q2+796tvu/erb7v3q2+796tvu8="  # 32 B base64, len pre testy
PLAIN_KEY = "sk_eleven_tajny_kluc"

# Riadok `behavior`, ako ho vráti PostgREST. Okrem kľúča sú tu bežné polia —
# test nižšie stráži, že sa seam nedotkne ničoho iného.
BEHAVIOR_ROW = {
    "model_id": MODEL,
    "mode": "ai",
    "heat": "medium",
    "voices_enabled": True,
    "eleven_voice_id": "voice-123",
    "voice_ambience": "bedroom",
    "voice_tempo": 1.05,
    "eleven_key": "",
    "eleven_key_enc": "",
}


def _behavior_transport(row):
    """Transport, ktorý na `/behavior` vráti presne zadaný riadok."""
    def handler(req):
        if "/behavior" in str(req.url):
            return httpx.Response(200, json=[row])
        return httpx.Response(200, json=[])
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")
    return t


async def test_behavior_decrypts_eleven_key():
    """Šifrovaný kľúč príde von ako čistý text pod menom `eleven_key`."""
    row = {**BEHAVIOR_ROW, "eleven_key_enc": encrypt(PLAIN_KEY, KEY)}
    db = TenantDb(_behavior_transport(row), MODEL, KEY)

    out = await db.get_behavior()

    assert out["eleven_key"] == PLAIN_KEY


async def test_behavior_never_leaks_ciphertext():
    """`eleven_key_enc` sa do výsledku nedostane — ani keď sa dešifrovať dá."""
    sealed = encrypt(PLAIN_KEY, KEY)
    row = {**BEHAVIOR_ROW, "eleven_key_enc": sealed}
    db = TenantDb(_behavior_transport(row), MODEL, KEY)

    out = await db.get_behavior()

    assert "eleven_key_enc" not in out
    assert sealed not in out.values()


async def test_behavior_keeps_every_other_field_untouched():
    """Seam mení výhradne dvojicu eleven_key/_enc, zvyšok riadku je nedotknutý."""
    row = {**BEHAVIOR_ROW, "eleven_key_enc": encrypt(PLAIN_KEY, KEY)}
    db = TenantDb(_behavior_transport(row), MODEL, KEY)

    out = await db.get_behavior()

    assert {k: v for k, v in out.items() if k != "eleven_key"} == {
        k: v for k, v in BEHAVIOR_ROW.items() if k not in ("eleven_key", "eleven_key_enc")
    }


async def test_behavior_falls_back_to_legacy_plaintext():
    """Prázdny `_enc` = stará cesta (Simona pred backfillom) a musí fungovať."""
    row = {**BEHAVIOR_ROW, "eleven_key": PLAIN_KEY, "eleven_key_enc": ""}
    db = TenantDb(_behavior_transport(row), MODEL, KEY)

    out = await db.get_behavior()

    assert out["eleven_key"] == PLAIN_KEY
    assert "eleven_key_enc" not in out


async def test_behavior_legacy_works_without_encryption_key():
    """Bez ENCRYPTION_KEY (staré volania, testy) sa nič nedešifruje a nepadá."""
    row = {**BEHAVIOR_ROW, "eleven_key": PLAIN_KEY}
    db = TenantDb(_behavior_transport(row), MODEL)

    assert (await db.get_behavior())["eleven_key"] == PLAIN_KEY


async def test_behavior_bad_ciphertext_fails_open(caplog):
    """Poškodená šifra = žiadne hlasovky, ale tenant beží ďalej."""
    row = {**BEHAVIOR_ROW, "eleven_key_enc": "toto:nie:je-sifra"}
    db = TenantDb(_behavior_transport(row), MODEL, KEY)

    out = await db.get_behavior()

    assert out["eleven_key"] == ""
    assert out["eleven_voice_id"] == "voice-123"  # zvyšok chovania platí ďalej
    assert any("nedá dešifrovať" in r.getMessage() for r in caplog.records)


async def test_behavior_wrong_key_does_not_fall_back_to_legacy():
    """Keď má modelka `_enc`, starý čistý text sa už nepoužije.

    Inak by sa zlým kľúčom dal ticho oživiť kľúč, ktorý klient v dashboarde
    práve prepísal — a účtovalo by sa cudziemu účtu.
    """
    other = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    row = {
        **BEHAVIOR_ROW,
        "eleven_key": "sk_stary_kluc",
        "eleven_key_enc": encrypt(PLAIN_KEY, other),
    }
    db = TenantDb(_behavior_transport(row), MODEL, KEY)

    assert (await db.get_behavior())["eleven_key"] == ""


async def test_behavior_missing_row_stays_empty_dict():
    """Modelka bez riadku `behavior` — seam nesmie vyrobiť poloprázdny dict."""
    def handler(req):
        return httpx.Response(200, json=[])
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")

    assert await TenantDb(t, MODEL, KEY).get_behavior() == {}


async def test_fanvue_behavior_shares_the_same_seam():
    """`fvvoice.make()` číta ten istý `eleven_key` — cez TenantFanvueDb."""
    from fanvue_tenant import TenantFanvueDb

    row = {**BEHAVIOR_ROW, "eleven_key_enc": encrypt(PLAIN_KEY, KEY)}
    db = TenantFanvueDb(_behavior_transport(row), MODEL, KEY)

    out = await db.behavior()

    assert out["eleven_key"] == PLAIN_KEY
    assert "eleven_key_enc" not in out


# ---------------------------------------------------------------------------
# ElevenLabs kľúč na ÚČTE (migrácia 017)
#
# Kľúč sa presunul z modelky na účet: jeden účet ElevenLabs, jedna faktúra,
# jedno miesto, kde sa pripája. Per-model stĺpce ostali ako fallback, aby
# nasadenie prežilo databázu, v ktorej presun ešte nebežal.
# ---------------------------------------------------------------------------

ACCOUNT = "acc-0001"
ACCOUNT_KEY = "sk_eleven_kluc_uctu"


def _account_transport(row, account_sealed, hits=None, fail_accounts=False):
    """Transport, ktorý obslúži `/behavior` aj `/accounts`.

    `hits` (list) zbiera cesty — testy cache podľa neho počítajú dotazy.
    """
    def handler(req):
        path = str(req.url)
        if hits is not None:
            hits.append("accounts" if "/accounts" in path else "behavior")
        if "/accounts" in path:
            if fail_accounts:
                return httpx.Response(500, json={"message": "nope"})
            return httpx.Response(200, json=[{"eleven_key_enc": account_sealed}])
        if "/behavior" in path:
            return httpx.Response(200, json=[row])
        return httpx.Response(200, json=[])

    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")
    return t


async def test_account_key_wins_over_model_key():
    """Kľúč účtu prebíja per-model hodnotu z 014.

    Naopak by to znamenalo, že prepojenie v dashboarde u Simony a Mio nespraví
    nič — obe majú starú per-model hodnotu — a nikto by nevedel prečo.
    """
    row = {**BEHAVIOR_ROW, "eleven_key_enc": encrypt(PLAIN_KEY, KEY)}
    db = TenantDb(_account_transport(row, encrypt(ACCOUNT_KEY, KEY)), MODEL, KEY, ACCOUNT)

    out = await db.get_behavior()

    assert out["eleven_key"] == ACCOUNT_KEY
    assert "eleven_key_enc" not in out


async def test_model_key_still_works_without_account_key():
    """Účet bez kľúča (presun ešte nebežal) — platí per-model hodnota."""
    row = {**BEHAVIOR_ROW, "eleven_key_enc": encrypt(PLAIN_KEY, KEY)}
    db = TenantDb(_account_transport(row, ""), MODEL, KEY, ACCOUNT)

    assert (await db.get_behavior())["eleven_key"] == PLAIN_KEY


async def test_account_key_falls_through_to_legacy_plaintext():
    """Ani účet, ani `_enc` — zastaraný čistý text je stále platná cesta."""
    row = {**BEHAVIOR_ROW, "eleven_key": PLAIN_KEY, "eleven_key_enc": ""}
    db = TenantDb(_account_transport(row, ""), MODEL, KEY, ACCOUNT)

    assert (await db.get_behavior())["eleven_key"] == PLAIN_KEY


async def test_no_key_anywhere_is_silence_not_a_crash():
    """Nikde žiadny kľúč = hlasovky ticho nie sú. Zvyšok chovania platí."""
    db = TenantDb(_account_transport(dict(BEHAVIOR_ROW), ""), MODEL, KEY, ACCOUNT)

    out = await db.get_behavior()

    assert out["eleven_key"] == ""
    assert out["eleven_voice_id"] == "voice-123"


async def test_bad_account_ciphertext_fails_open(caplog):
    """Poškodená šifra účtu = žiadne hlasovky, žiadny pád — a NEPADÁ na modelku.

    Tichý downgrade na starší kľúč by znamenal účtovanie cudziemu účtu ElevenLabs
    presne vtedy, keď si majiteľ myslí, že prekľúčoval.
    """
    row = {**BEHAVIOR_ROW, "eleven_key_enc": encrypt(PLAIN_KEY, KEY)}
    db = TenantDb(_account_transport(row, "toto:nie:je-sifra"), MODEL, KEY, ACCOUNT)

    out = await db.get_behavior()

    assert out["eleven_key"] == ""
    assert any("nedá dešifrovať" in r.getMessage() for r in caplog.records)


async def test_account_key_is_read_once_not_per_reply():
    """Kľúč účtu sa nesmie ťahať pri každej odpovedi — na to je cache."""
    hits: list = []
    row = dict(BEHAVIOR_ROW)
    db = TenantDb(
        _account_transport(row, encrypt(ACCOUNT_KEY, KEY), hits), MODEL, KEY, ACCOUNT
    )

    for _ in range(5):
        assert (await db.get_behavior())["eleven_key"] == ACCOUNT_KEY

    assert hits.count("behavior") == 5
    assert hits.count("accounts") == 1


async def test_account_key_refreshes_after_ttl():
    """Prekľúčovanie v dashboarde sa prejaví bez reštartu tenanta."""
    from db import AccountKeyCache

    hits: list = []
    row = dict(BEHAVIOR_ROW)
    db = TenantDb(
        _account_transport(row, encrypt(ACCOUNT_KEY, KEY), hits), MODEL, KEY, ACCOUNT
    )
    db._account_key = AccountKeyCache(db._t, ACCOUNT, ttl_s=0.0)

    await db.get_behavior()
    await db.get_behavior()

    assert hits.count("accounts") == 2


async def test_account_key_survives_a_database_blip(caplog):
    """Výpadok pri čítaní účtu neznamená „kľúč zmizol"."""
    from db import AccountKeyCache

    cache = AccountKeyCache(
        _account_transport(dict(BEHAVIOR_ROW), "", fail_accounts=True), ACCOUNT
    )
    cache._sealed = "posledny:znamy:kluc="
    cache._at = 0.0  # TTL vypršané, takže sa naozaj skúsi načítať

    assert await cache.sealed() == "posledny:znamy:kluc="
    assert cache._at == 0.0  # čas sa neposunul → ďalšie volanie to skúsi znova
    assert any("posledný známy" in r.getMessage() for r in caplog.records)


async def test_account_without_id_never_touches_the_database():
    """Bez `account_id` (staré volania, testy) sa `/accounts` vôbec nečíta."""
    hits: list = []
    db = TenantDb(_account_transport(dict(BEHAVIOR_ROW), "x", hits), MODEL, KEY)

    await db.get_behavior()

    assert hits == ["behavior"]


async def test_fanvue_behavior_uses_the_account_key_too():
    """Hlasovky na Fanvue nemajú dôvod fungovať inak než na Telegrame."""
    from fanvue_tenant import TenantFanvueDb

    row = {**BEHAVIOR_ROW, "eleven_key_enc": encrypt(PLAIN_KEY, KEY)}
    db = TenantFanvueDb(
        _account_transport(row, encrypt(ACCOUNT_KEY, KEY)), MODEL, KEY, ACCOUNT
    )

    out = await db.behavior()

    assert out["eleven_key"] == ACCOUNT_KEY
    assert "eleven_key_enc" not in out


async def test_upload_voice_path_has_no_model_prefix():
    """Cestu stavia volajúci (schema == model_id), db.py ju nesmie prepisovať."""
    seen = []
    db = TenantDb(_capture(seen), MODEL)
    url = await db.upload_voice("abc/x.ogg", b"zvuk")
    assert seen[-1]["url"].endswith("/storage/v1/object/voices/abc/x.ogg")
    assert url == "https://x.supabase.co/storage/v1/object/public/voices/abc/x.ogg"


# ---------------------------------------------------------------------------
# Rozvrh dňa (migrácia 022)
#
# Číta sa pri KAŽDEJ odpovedi, ale mení sa vtedy, keď si klient otvorí kartu.
# Preto cache — a preto sa výpadok siete nesmie tváriť ako „modelka rozvrh
# nemá": to by ju uprostred dňa presunulo späť na napísanú šablónu.
# ---------------------------------------------------------------------------

SCHEDULE_ROW = {
    "model_id": MODEL,
    "wake_weekday_start_min": 600,
    "wake_weekday_end_min": 660,
    "wake_weekend_start_min": 700,
    "wake_weekend_end_min": 760,
    "night_place": "bedroom",
    "night_what": "leží v posteli",
    "night_pace": "0.60",
    "night_arrival": "práve si ľahla",
    "activities": [
        {"place": "cafe", "what": "sedí v kaviarni", "pace": 1.1,
         "min_minutes": 40, "max_minutes": 70, "arrival": "", "days": [0, 1, 2, 3, 4, 5, 6]}
    ],
}


def _schedule_transport(rows, hits, fail_after=None):
    """Transport, ktorý na `/model_schedule` vráti `rows` a počíta dotazy."""
    def handler(req):
        if "/model_schedule" in str(req.url):
            hits.append(str(req.url))
            if fail_after is not None and len(hits) > fail_after:
                return httpx.Response(500, json={"message": "mimo prevádzky"})
            return httpx.Response(200, json=rows)
        return httpx.Response(200, json=[])
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")
    return t


async def test_schedule_is_read_once_per_ttl():
    hits: list = []
    db = TenantDb(_schedule_transport([SCHEDULE_ROW], hits), MODEL)

    first = await db.get_schedule()
    second = await db.get_schedule()

    assert first == second == SCHEDULE_ROW
    assert len(hits) == 1, "rozvrh sa nemá ťahať pri každej správe"
    assert f"model_id=eq.{MODEL}" in hits[0]


async def test_schedule_missing_row_means_template():
    hits: list = []
    db = TenantDb(_schedule_transport([], hits), MODEL)
    assert await db.get_schedule() == {}


async def test_schedule_network_failure_keeps_last_known():
    """Výpadok DB nesmie modelku uprostred dňa presunúť inam."""
    from db import ScheduleCache

    hits: list = []
    cache = ScheduleCache(
        _schedule_transport([SCHEDULE_ROW], hits, fail_after=1), MODEL, ttl_s=0.0
    )

    assert await cache.row() == SCHEDULE_ROW
    assert await cache.row() == SCHEDULE_ROW, "po chybe platí posledný známy rozvrh"
    assert len(hits) == 2


async def test_schedule_row_becomes_a_usable_day():
    """Riadok z DB musí prejsť cez `den.Rozvrh` až po hotový deň."""
    import den
    from datetime import date

    hits: list = []
    db = TenantDb(_schedule_transport([SCHEDULE_ROW], hits), MODEL)

    rozvrh = den.Rozvrh.from_row(await db.get_schedule())

    bloky = den.plan(date(2026, 8, 17), MODEL, rozvrh)
    assert bloky[0].kde == "cafe"
    assert 600 <= bloky[0].od <= 660
    assert bloky[-1].do == den.KONIEC_DNA
