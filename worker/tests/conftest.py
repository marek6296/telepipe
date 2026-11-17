"""Spoločné fixtures.

`fast` vypína reálne čakanie. NIE je autouse — inak by prepísala aj funkcie,
ktoré samotné unit testy overujú (test_behavior, test_humanize). Moduly, ktoré
prechádzajú celým tokom odpovede, si ju vyžiadajú cez pytestmark.

Oproti šablóne pribudli `transport`/`db` — v Telepipe si spojenie nedrží `Db`,
ale `SupabaseTransport`, ktorý sa zdieľa medzi modelkami. Testy preto dostanú
transport s podvrhnutým klientom a `TenantDb` pripnutú na `TEST_MODEL_ID`.
"""
import json

import httpx
import pytest
from db import TenantDb
from transport import SupabaseTransport

TEST_MODEL_ID = "test-model"


@pytest.fixture
def fast(monkeypatch):
    # Importy sú vnútri: tieto moduly sa portujú až v Task 9 a chýbajúci modul
    # by inak zhodil zber celej sady, nielen testy, ktoré fixture pýtajú.
    import behavior as bhv
    import humanize
    import judge
    import voices

    monkeypatch.setattr(humanize, "typing_delay", lambda *a, **k: 0)
    # Indikátor „nahráva hlasovku" trvá podľa dĺžky nahrávky — v testoch nie.
    monkeypatch.setattr(voices, "record_seconds", lambda *a, **k: 0)
    monkeypatch.setattr(bhv, "read_delay", lambda *a, **k: 0)
    monkeypatch.setattr(bhv, "reply_delay", lambda *a, **k: 0)
    monkeypatch.setattr(bhv, "debounce_delay", lambda *a, **k: 0)
    monkeypatch.setattr(bhv, "seen_only_delay", lambda *a, **k: 0)
    monkeypatch.setattr(bhv, "long_pause_delay", lambda *a, **k: 0)
    monkeypatch.setattr(bhv, "should_defer_reply", lambda *a, **k: 0)

    # Sudca má vlastné testy; inde nech len prepustí návrh.
    async def _pass(_llm, draft, *a, **k):
        return {"text": draft, "changed": False, "why": ""}

    monkeypatch.setattr(judge, "review", _pass)
    monkeypatch.setattr(bhv, "quick_reply", lambda *a, **k: None)


@pytest.fixture
def http_calls():
    """Zoznam, do ktorého padá každý HTTP dotaz — {method, url, body}."""
    return []


@pytest.fixture
def transport(http_calls):
    """SupabaseTransport s podvrhnutým klientom; nič nejde von."""
    def handler(req):
        try:
            body = json.loads(req.content) if req.content else None
        except ValueError:
            body = None  # binárny obsah — upload do úložiska
        http_calls.append({"method": req.method, "url": str(req.url), "body": body})
        return httpx.Response(200, json=[])

    t = SupabaseTransport("https://test.supabase.co", "test-key")
    t._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://test.supabase.co/rest/v1",
    )
    return t


@pytest.fixture
def db(transport):
    return TenantDb(transport, TEST_MODEL_ID)


@pytest.fixture(autouse=True)
def no_live_instagram_http(request, monkeypatch):
    if request.node.fspath.basename.startswith('test_instagram'):
        import instagram_api
        def blocked(*args, **kwargs):
            raise AssertionError('Instagram test attempted live HTTP; mock the provider boundary')
        monkeypatch.setattr(instagram_api, '_volaj', blocked)


@pytest.fixture(autouse=True)
def no_operator_wait(monkeypatch):
    # Provider send tests must not wait for real typing; dedicated delay tests
    # retain the original function reference to exercise its timing contract.
    from unittest.mock import AsyncMock
    import operator_delivery
    monkeypatch.setattr(operator_delivery, "composition_pause", AsyncMock())
