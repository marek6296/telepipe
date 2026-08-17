"""Skutočné počasie tam, kde modelka býva.

Keď sa jej niekto spýta, aké je u nej počasie, musí odpovedať pravdu — inak
povie „krásne slnečno" v čase, keď tam leje, a stačí jedna taká odpoveď, aby to
prestalo sedieť. Berie sa z Open-Meteo, ktoré nepotrebuje kľúč ani účet.

Mesto z persony sa najprv preloží na súradnice (geokódovanie) a to sa už
nemení, takže sa pamätá natrvalo. Počasie sa ťahá raz za 30 minút na modelku.

Všetko je fail-open: keď služba nefunguje, sekcia o počasí sa do promptu
jednoducho nedostane a modelka o počasí nezačne sama. Nikdy to nesmie zdržať
ani zhodiť odpoveď.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import httpx

log = logging.getLogger(__name__)

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Ako dlho platí jedno stiahnutie. Počasie sa za pol hodiny nezmení natoľko,
# aby to v chate niekto rozoznal, a ušetrí to volania.
CACHE_MINUTES = 30
TIMEOUT_S = 8.0

# WMO kódy → ako by to opísal človek, nie meteorológ.
_CODES = {
    0: "clear sky",
    1: "mostly clear", 2: "partly cloudy", 3: "cloudy",
    45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "raining", 65: "pouring rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snowing", 75: "heavy snow", 77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}

_coords: Dict[str, Optional[Tuple[float, float]]] = {}
_cache: Dict[str, Tuple[datetime, str]] = {}
_lock = asyncio.Lock()


def describe_code(code: int) -> str:
    return _CODES.get(int(code), "")


async def _geocode(client: httpx.AsyncClient, city: str) -> Optional[Tuple[float, float]]:
    """Mesto z persony na súradnice. „New York City, USA" → prvá časť stačí."""
    if city in _coords:
        return _coords[city]
    name = city.split(",")[0].strip()
    try:
        r = await client.get(GEO_URL, params={"name": name, "count": 1, "language": "en"})
        r.raise_for_status()
        hits = r.json().get("results") or []
        found = (float(hits[0]["latitude"]), float(hits[0]["longitude"])) if hits else None
    except Exception as exc:  # noqa: BLE001 - bez počasia sa dá odpisovať
        log.warning("Mesto %r sa nepodarilo nájsť: %s", city, exc)
        return None
    if found is None:
        log.warning("Mesto %r geokódovanie nenašlo", city)
    _coords[city] = found
    return found


async def current(city: str, now: Optional[datetime] = None) -> str:
    """Krátky opis počasia, napr. „61F, raining". Prázdny reťazec = nevieme.

    Teplota je vo Fahrenheitoch — modelky žijú v USA a nikto tam nehovorí
    o stupňoch Celzia.
    """
    city = (city or "").strip()
    if not city:
        return ""

    reference = now or datetime.now(timezone.utc)
    cached = _cache.get(city)
    if cached and reference - cached[0] < timedelta(minutes=CACHE_MINUTES):
        return cached[1]

    async with _lock:
        # Kým sme čakali na zámok, mohol to stiahnuť niekto iný.
        cached = _cache.get(city)
        if cached and reference - cached[0] < timedelta(minutes=CACHE_MINUTES):
            return cached[1]
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                point = await _geocode(client, city)
                if point is None:
                    return ""
                r = await client.get(
                    FORECAST_URL,
                    params={
                        "latitude": point[0],
                        "longitude": point[1],
                        "current": "temperature_2m,weather_code",
                        "temperature_unit": "fahrenheit",
                    },
                )
                r.raise_for_status()
                block = r.json().get("current") or {}
        except Exception as exc:  # noqa: BLE001 - počasie nesmie zdržať odpoveď
            log.warning("Počasie pre %r sa nepodarilo zistiť: %s", city, exc)
            return ""

        temperature = block.get("temperature_2m")
        text = describe_code(block.get("weather_code", -1))
        if temperature is None and not text:
            return ""
        parts = []
        if temperature is not None:
            parts.append(f"{round(float(temperature))}F")
        if text:
            parts.append(text)
        result = ", ".join(parts)
        _cache[city] = (reference, result)
        log.info("Počasie %s: %s", city, result)
        return result


def forget() -> None:
    """Vyprázdni pamäť — používajú testy."""
    _coords.clear()
    _cache.clear()
