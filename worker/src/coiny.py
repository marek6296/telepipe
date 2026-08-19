"""Dobitie Pipe Coinov z control bota modelky.

PREČO SA FAKTÚRA NEVYSTAVUJE TU
-------------------------------
Control bot je KLIENTOV bot — jeho token, jeho účet. Telegram Stars vždy
pristanú na tom botovi, ktorý faktúru vystavil. Keby si ju teda vystavil control
bot, hviezdy by skončili u klienta a my by sme mu za ne pripísali coiny zadarmo,
pri každom jednom dobití.

Faktúru preto razí VÝHRADNE náš shop bot cez `/api/internal/stars-invoice` a
control bot z nej dostane len odkaz, ktorý sa dá otvoriť tlačidlom. Klient tak
platí nášmu botovi, hoci klikol v tom svojom.

CENNÍK TU NIE JE A NEBUDE
-------------------------
Ceny aj tvar payloadu žijú vo `web/lib/stars.ts`. Ponuka nižšie je len zoznam
veľkostí balíkov na vykreslenie tlačidiel — koľko coinov za ne bude, rozhoduje
web pri vystavení faktúry a vracia to v odpovedi. Keby sa ceny počítali aj tu,
sú to dve pravdy a raz sa ticho rozídu.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Veľkosti, ktoré predáva Telegram. Musia sedieť so `STAR_PACKS` na webe — keby
# tu bola veľkosť, ktorú web nepozná, klient klikne a nedostane nič.
BALIKY: Tuple[int, ...] = (500, 1000, 2500, 5000)

_TIMEOUT_S = 12


async def faktura(cfg, stars: int) -> Optional[Dict[str, Any]]:
    """Vypýta si od webu platobný odkaz. `None` = nedá sa, tlačidlo sa neukáže.

    NIKDY nehádže. Control bot je jediná cesta, ako klient modelku ovláda —
    výpadok dobíjania mu nesmie zhodiť menu.
    """
    base = (getattr(cfg, "web_api_url", "") or "").rstrip("/")
    secret = getattr(cfg, "internal_api_secret", "") or ""
    account = getattr(cfg, "account_id", "") or ""
    if not base or not secret or not account:
        log.warning("dobitie: chýba web_api_url, tajomstvo alebo account_id")
        return None
    if stars not in BALIKY:
        return None

    payload = json.dumps({"accountId": account, "stars": stars}).encode()
    request = urllib.request.Request(
        f"{base}/api/internal/stars-invoice",
        data=payload,
        headers={"Content-Type": "application/json", "x-internal-secret": secret},
        method="POST",
    )
    try:
        import asyncio

        def _call() -> Dict[str, Any]:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                return json.loads(response.read().decode() or "{}")

        # `urllib` je blokujúce; do eventloopu ho pustiť nesmieme, inak by sa
        # počas výpadku webu zastavilo odpovedanie VŠETKÝCH modeliek na replike.
        data = await asyncio.to_thread(_call)
    except urllib.error.HTTPError as exc:
        log.warning("dobitie: web odmietol faktúru (%s)", exc.code)
        return None
    except Exception:  # noqa: BLE001
        log.exception("dobitie: faktúra sa nepodarila")
        return None

    url = str(data.get("url") or "")
    if not url.startswith("https://t.me/"):
        log.warning("dobitie: web vrátil nepoužiteľný odkaz")
        return None
    return {"url": url, "stars": int(data.get("stars") or stars), "coins": int(data.get("coins") or 0)}


def popis(coins_balance: float) -> str:
    """Hlavička obrazovky dobitia — koľko má a zhruba na koľko odpovedí to je."""
    coins = int(round(coins_balance))
    # 60 coinov na odpoveď je to isté číslo ako `COINS_PER_REPLY` na webe.
    # Je to ODHAD pre klienta, nie účtovanie, takže konštanta tu neškodí.
    odpovede = coins // 60
    return f"Balance: *{coins:,}* coins (~{odpovede:,} replies)".replace(",", " ")


def tlacidla_balikov() -> List[int]:
    return list(BALIKY)
