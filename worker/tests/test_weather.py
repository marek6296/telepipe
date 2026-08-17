"""Počasie musí byť skutočné — a keď sa nedá zistiť, musí sa mlčky vzdať."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import weather


@pytest.fixture(autouse=True)
def cista_pamat():
    weather.forget()
    yield
    weather.forget()


def fake_transport(handler):
    """Podstrčí odpovede namiesto skutočného Open-Meteo."""
    original = httpx.AsyncClient

    class Client(original):
        def __init__(self, *a, **kw):
            super().__init__(*a, transport=httpx.MockTransport(handler), **kw)

    return Client


def odpovedaj(geo=None, forecast=None, geo_status=200, forecast_status=200):
    def handler(request):
        if "geocoding" in str(request.url):
            return httpx.Response(geo_status, json=geo if geo is not None else {})
        return httpx.Response(forecast_status, json=forecast if forecast is not None else {})
    return handler


GEO_NY = {"results": [{"latitude": 40.71, "longitude": -74.0, "name": "New York"}]}
POCASIE = {"current": {"temperature_2m": 61.4, "weather_code": 63}}


class TestPopisKodu:
    def test_zname_kody(self):
        assert weather.describe_code(0) == "clear sky"
        assert weather.describe_code(63) == "raining"
        assert weather.describe_code(95) == "thunderstorm"

    def test_neznamy_kod_nevymysla(self):
        assert weather.describe_code(1234) == ""


class TestSucasnePocasie:
    def test_vrati_teplotu_aj_popis(self, monkeypatch):
        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(odpovedaj(GEO_NY, POCASIE)))
        assert asyncio.run(weather.current("New York City, USA")) == "61F, raining"

    def test_teplota_je_vo_fahrenheitoch(self, monkeypatch):
        """Modelky žijú v USA — o stupňoch Celzia tam nikto nehovorí."""
        zachytene = {}

        def handler(request):
            if "geocoding" in str(request.url):
                return httpx.Response(200, json=GEO_NY)
            zachytene["jednotka"] = request.url.params.get("temperature_unit")
            return httpx.Response(200, json=POCASIE)

        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(handler))
        asyncio.run(weather.current("New York City, USA"))
        assert zachytene["jednotka"] == "fahrenheit"

    def test_prazdne_mesto_nic_netiahne(self):
        assert asyncio.run(weather.current("")) == ""

    def test_neznama_lokalita_vrati_prazdno(self, monkeypatch):
        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(odpovedaj({"results": []})))
        assert asyncio.run(weather.current("Vymyslene mesto")) == ""

    def test_vypadok_sluzby_nezhodi_odpoved(self, monkeypatch):
        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(odpovedaj(GEO_NY, forecast_status=503)))
        assert asyncio.run(weather.current("New York City, USA")) == ""

    def test_rozbita_odpoved_vrati_prazdno(self, monkeypatch):
        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(odpovedaj(GEO_NY, {"current": {}})))
        assert asyncio.run(weather.current("New York City, USA")) == ""


class TestPamat:
    def test_druhe_volanie_uz_netiahne(self, monkeypatch):
        volania = {"n": 0}

        def handler(request):
            if "geocoding" in str(request.url):
                return httpx.Response(200, json=GEO_NY)
            volania["n"] += 1
            return httpx.Response(200, json=POCASIE)

        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(handler))
        asyncio.run(weather.current("New York City, USA"))
        asyncio.run(weather.current("New York City, USA"))
        assert volania["n"] == 1, "počasie sa má ťahať raz za 30 minút"

    def test_po_polhodine_sa_obnovi(self, monkeypatch):
        volania = {"n": 0}

        def handler(request):
            if "geocoding" in str(request.url):
                return httpx.Response(200, json=GEO_NY)
            volania["n"] += 1
            return httpx.Response(200, json=POCASIE)

        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(handler))
        teraz = datetime.now(timezone.utc)
        asyncio.run(weather.current("New York City, USA", now=teraz))
        asyncio.run(weather.current("New York City, USA", now=teraz + timedelta(minutes=31)))
        assert volania["n"] == 2

    def test_kazde_mesto_zvlast(self, monkeypatch):
        monkeypatch.setattr(httpx, "AsyncClient", fake_transport(odpovedaj(GEO_NY, POCASIE)))
        asyncio.run(weather.current("New York City, USA"))
        assert "California, USA" not in weather._cache
