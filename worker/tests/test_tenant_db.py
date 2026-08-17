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
        assert "search_messages" in url, where
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


async def test_upload_voice_path_has_no_model_prefix():
    """Cestu stavia volajúci (schema == model_id), db.py ju nesmie prepisovať."""
    seen = []
    db = TenantDb(_capture(seen), MODEL)
    url = await db.upload_voice("abc/x.ogg", b"zvuk")
    assert seen[-1]["url"].endswith("/storage/v1/object/voices/abc/x.ogg")
    assert url == "https://x.supabase.co/storage/v1/object/public/voices/abc/x.ogg"
