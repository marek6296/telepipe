"""Dobitie Pipe Coinov z control bota.

Celý zmysel tohto modulu je jedna vec: faktúru NESMIE vystaviť klientov control
bot, lebo Telegram Stars pristanú tomu botovi, ktorý ju vystavil — a klient by
tak zaplatil sám sebe. Testy nižšie strážia, že sa o faktúru vždy pýtame webu
a že pri akomkoľvek probléme radšej nevrátime nič, než niečo pochybné.
"""
import asyncio
import json
import types

import coiny


class _Cfg:
    def __init__(self, **kw):
        self.web_api_url = kw.get("web_api_url", "https://telepipe.me")
        self.internal_api_secret = kw.get("internal_api_secret", "tajne")
        self.account_id = kw.get("account_id", "1e23e8bb-1aa7-451d-b5cd-f8c526653939")


def _spusti(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_urlopen(monkeypatch, payload, zaznam=None):
    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return json.dumps(payload).encode()

    def _open(request, timeout=None):
        if zaznam is not None:
            zaznam.append({
                "url": request.full_url,
                "secret": request.headers.get("X-internal-secret"),
                "body": json.loads(request.data.decode()),
            })
        return _Resp()

    monkeypatch.setattr(coiny.urllib.request, "urlopen", _open)


def test_faktura_pyta_web_s_uctom_a_tajomstvom(monkeypatch):
    """Bez account_id a tajomstva by web nevedel, komu coiny pripísať."""
    zaznam = []
    _fake_urlopen(monkeypatch, {"url": "https://t.me/$abc", "stars": 500, "coins": 6000}, zaznam)

    out = _spusti(coiny.faktura(_Cfg(), 500))

    assert out == {"url": "https://t.me/$abc", "stars": 500, "coins": 6000}
    assert zaznam[0]["url"].endswith("/api/internal/stars-invoice")
    assert zaznam[0]["secret"] == "tajne"
    assert zaznam[0]["body"]["accountId"] == "1e23e8bb-1aa7-451d-b5cd-f8c526653939"
    assert zaznam[0]["body"]["stars"] == 500


def test_neznamy_balik_sa_nepyta(monkeypatch):
    """Veľkosť mimo ponuky by web aj tak odmietol — nemá zmysel ho obťažovať."""
    zaznam = []
    _fake_urlopen(monkeypatch, {"url": "https://t.me/$abc"}, zaznam)
    assert _spusti(coiny.faktura(_Cfg(), 123)) is None
    assert zaznam == []


def test_chybajuce_tajomstvo_nevystavi_nic(monkeypatch):
    zaznam = []
    _fake_urlopen(monkeypatch, {"url": "https://t.me/$abc"}, zaznam)
    assert _spusti(coiny.faktura(_Cfg(internal_api_secret=""), 500)) is None
    assert zaznam == []


def test_chybajuci_ucet_nevystavi_nic(monkeypatch):
    """Bez účtu by faktúra viedla na prázdny payload a platba by sa stratila."""
    zaznam = []
    _fake_urlopen(monkeypatch, {"url": "https://t.me/$abc"}, zaznam)
    assert _spusti(coiny.faktura(_Cfg(account_id=""), 500)) is None
    assert zaznam == []


def test_podvrhnuty_odkaz_sa_odmietne(monkeypatch):
    """Odkaz musí viesť na Telegram. Čokoľvek iné by bolo tlačidlo do neznáma."""
    _fake_urlopen(monkeypatch, {"url": "https://zly-web.example/pay", "stars": 500, "coins": 6000})
    assert _spusti(coiny.faktura(_Cfg(), 500)) is None


def test_vypadok_webu_nezhodi_bota(monkeypatch):
    def _boom(request, timeout=None):
        raise OSError("sieť spadla")
    monkeypatch.setattr(coiny.urllib.request, "urlopen", _boom)
    assert _spusti(coiny.faktura(_Cfg(), 500)) is None


def test_baliky_su_velkosti_ktore_telegram_predava():
    """Veľkosť, ktorú Telegram nepredáva, by nechala klientovi zvyšné hviezdy."""
    assert coiny.BALIKY == (500, 1000, 2500, 5000)
