"""Denný auto-sync cien z Atlas Cloud Billing API + stráženie zostatku.

Atlas chat odpovede nesú len počty tokenov, nie USD (`credits.py` cenu
dopočítava z tabuľky `pricing`). Tá sa doteraz musela manuálne udržiavať —
tento modul ju raz za `pricing_sync_hours` (main.py) automaticky dorovná
podľa skutočne fakturovaných cien z Atlas Billing Public API.

Schéma /model-usage a /model-costs bola overená empiricky (throwaway probe
proti reálnemu účtu, nie z dokumentácie — tá presné názvy polí nešpecifikuje):

  GET /balance
    {"available": {"value": "123.45", "currency": "usd"}, ...}
    (aj cash/bonus/frozen/credit_grant — pre alert nás zaujíma len available)

  GET /model-usage?start_date=&end_date=&scope=account&group_by[]=model
    {"data": [{"date": "2026-08-14", "results": [
        {"model_type": "text", "model": {"name": "xai/grok-4.5", ...},
         "usage": {"tokens": {"input": 275088, "output": 3500, ...}}},
        {"model_type": "image", ...},   # ignorujeme — cenník je len text/token
    ]}]}

  GET /model-costs (rovnaké parametre a tvar bucketov)
    {"data": [{"date": "2026-08-14", "results": [
        {"model_type": "text", "model": {"name": "xai/grok-4.5", ...},
         "amount": {"value": "0.627688", "currency": "usd"}},
    ]}]}

Dôležité: /model-costs vracia JEDNU blendovanú sumu za deň/model (input aj
output dokopy) — Atlas cenu na vstup/výstup nerozdeľuje, hoci tokeny áno.
Presné rozdelenie preto nie je možné odvodiť len z Atlas dát — `compute_prices`
ho aproximuje pomerom cien z nášho vlastného ledgeru (`usage_events`), a keď
pre model ešte žiadny nemáme, použije rovnakú (blendovanú) cenu pre obe strany
— konzervatívne, samoopravné (ďalší sync použije už presnejší pomer).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

_BASE_URL = "https://api.atlascloud.ai/public/v1"
_TIMEOUT = 20.0


def _client() -> httpx.AsyncClient:
    """Samostatný klient na Atlas Billing API — mimo SupabaseTransport (iný host)."""
    return httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT)


def _num(value: Any, default: float = 0.0) -> float:
    """Tolerantný parser čísiel z Atlas JSON (ceny/tokeny chodia ako string aj number)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def fetch_atlas_daily(api_key: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Stiahne a zlúči /model-usage + /model-costs za dané obdobie.

    Vracia riadky {model_slug, date, input_tokens, output_tokens, cost_usd} —
    po jednom za (deň, model). Berie len `model_type == "text"` (chat/vision/
    audio modely účtované cez tokeny) — image/video majú inú tarifikáciu a
    `pricing` tabuľka ich nerieši. Chýbajúci cost bucket pre model → cost_usd=0
    (nespadne, len ho sync_pricing pri delení nulou preskočí/ignoruje).
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"start_date": start_date, "end_date": end_date, "scope": "account",
              "group_by[]": "model"}

    async with _client() as client:
        usage_r = await client.get("/model-usage", params=params, headers=headers)
        usage_r.raise_for_status()
        costs_r = await client.get("/model-costs", params=params, headers=headers)
        costs_r.raise_for_status()

    usage_json = usage_r.json()
    costs_json = costs_r.json()

    # (date, slug) -> cost_usd, z /model-costs bucketov
    cost_by_key: Dict[tuple, float] = {}
    for bucket in costs_json.get("data") or []:
        date_ = bucket.get("date", "")
        for res in bucket.get("results") or []:
            if res.get("model_type") != "text":
                continue
            slug = (res.get("model") or {}).get("name")
            if not slug:
                continue
            amount = (res.get("amount") or {}).get("value")
            cost_by_key[(date_, slug)] = _num(amount)

    rows: List[Dict[str, Any]] = []
    for bucket in usage_json.get("data") or []:
        date_ = bucket.get("date", "")
        for res in bucket.get("results") or []:
            if res.get("model_type") != "text":
                continue
            slug = (res.get("model") or {}).get("name")
            if not slug:
                continue
            tokens = (res.get("usage") or {}).get("tokens") or {}
            in_tok = int(_num(tokens.get("input")))
            out_tok = int(_num(tokens.get("output")))
            rows.append({
                "model_slug": slug,
                "date": date_,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": cost_by_key.get((date_, slug), 0.0),
            })
    return rows


async def compute_prices(
    rows: List[Dict[str, Any]],
    ledger_ratios: Optional[Dict[str, float]] = None,
) -> Dict[str, Dict[str, float]]:
    """Spočíta efektívnu cenu za Mtok z (agregovaných) Atlas riadkov.

    `ledger_ratios[slug]` = pomer output/input ceny odvodený z nášho vlastného
    ledgeru (usage_events) — použije sa na rozdelenie blendovanej Atlas ceny
    tak, aby spätne sedela na celkovú sumu:

        cost = in_tok/1e6 * P_in + out_tok/1e6 * (r * P_in)
        =>  P_in  = cost * 1e6 / (in_tok + r * out_tok)
            P_out = r * P_in

    Bez pomeru (model v ledgeri ešte nemá dáta) sa použije jednotná blendovaná
    cena pre obe strany — konzervatívne, samoopravné ďalším behom.
    """
    ledger_ratios = ledger_ratios or {}

    agg: Dict[str, Dict[str, float]] = {}
    for row in rows:
        slug = row["model_slug"]
        a = agg.setdefault(slug, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        a["input_tokens"] += row.get("input_tokens", 0)
        a["output_tokens"] += row.get("output_tokens", 0)
        a["cost_usd"] += row.get("cost_usd", 0.0)

    out: Dict[str, Dict[str, float]] = {}
    for slug, a in agg.items():
        in_tok, out_tok, cost = a["input_tokens"], a["output_tokens"], a["cost_usd"]
        total_tok = in_tok + out_tok
        if total_tok <= 0:
            continue  # žiadne dáta za obdobie — nemáme z čoho počítať, preskoč
        blended = cost / (total_tok / 1e6)

        ratio = ledger_ratios.get(slug)
        if not ratio or ratio <= 0:
            p_in = p_out = blended
        else:
            denom = in_tok + ratio * out_tok
            if denom <= 0:
                p_in = p_out = blended
            else:
                p_in = cost * 1e6 / denom
                p_out = ratio * p_in

        out[slug] = {"input_usd_per_mtok": p_in, "output_usd_per_mtok": p_out}
    return out


async def sync_pricing(transport, registry, api_key: str, notify=None) -> None:
    """Stiahne posledné 3 celé dni Atlas billing dát a dorovná `pricing` tabuľku.

    Fail-open — akákoľvek výnimka (výpadok Atlas API, Supabase, zlá schéma…)
    sa len zaloguje (`log.warning`), nikdy nesmie zhodiť pool v main.py.

    Upsert cez POST .../pricing s Prefer: resolution=merge-duplicates a telom
    bez `multiplier` — PostgREST pri konflikte updatuje LEN stĺpce, ktoré sú
    v tele requestu, takže multiplikátor (klientská prirážka) ostáva
    nedotknutý. `_default` riadok (fallback cena) sa nikdy neupravuje.
    """
    try:
        import datetime

        end = datetime.date.today() - datetime.timedelta(days=1)      # včera = posledný celý deň
        start = end - datetime.timedelta(days=2)                       # 3 celé dni dokopy
        start_s, end_s = start.isoformat(), end.isoformat()

        rows = await fetch_atlas_daily(api_key, start_s, end_s)
        if not rows:
            log.info("pricing sync: Atlas nevrátil žiadne usage dáta za %s..%s", start_s, end_s)
            return

        ledger_ratios: Dict[str, float] = {}
        try:
            ledger_ratios = await _ledger_ratios(transport)
        except Exception:  # noqa: BLE001 — chýbajúci pomer len zhorší presnosť, nie pád
            log.debug("pricing sync: pomer z ledgeru sa nepodarilo zistiť, blendovaná cena", exc_info=True)

        prices = await compute_prices(rows, ledger_ratios)
        body = [
            {"model_slug": slug, "input_usd_per_mtok": round(p["input_usd_per_mtok"], 6),
             "output_usd_per_mtok": round(p["output_usd_per_mtok"], 6)}
            for slug, p in prices.items()
            if slug != "_default"
        ]
        if not body:
            log.info("pricing sync: nič na upsert (len _default alebo prázdne dáta)")
            return

        await transport._post("/pricing", body, upsert=True)
        log.info("pricing sync: aktualizovaných %d modelov (%s)", len(body),
                  ", ".join(r["model_slug"] for r in body))
    except Exception:  # noqa: BLE001 — sync nesmie zhodiť worker pool
        log.warning("pricing sync zlyhal — cenník ostáva na predošlých hodnotách", exc_info=True)


async def _ledger_ratios(transport) -> Dict[str, float]:
    """Pomer output/input tokenov z nášho ledgeru (usage_events), per model slug.

    `usage_events` neukladá model_slug priamo — len `kind` (chat/summary/
    vision/audio/voice), lebo LLM model je v tomto procese spoločný pre
    všetkých tenantov (globálny `Config`). Mapujeme kind -> slug cez aktuálny
    Config a použijeme len ako ORIENTAČNÝ pomer pri rozdeľovaní blendovanej
    Atlas ceny (viď `compute_prices`) — nie ako presnú hodnotu.
    """
    from config import Config

    cfg = Config.from_env()
    kind_slug = {
        "chat": cfg.model,
        "summary": cfg.summary_model,
        "vision": cfg.vision_model,
        "audio": cfg.audio_model,
    }

    rows = await transport._get(
        "/usage_events",
        {"select": "kind,input_tokens,output_tokens", "order": "created_at.desc", "limit": "5000"},
    )

    agg: Dict[str, List[int]] = {}
    for row in rows:
        slug = kind_slug.get(row.get("kind"))
        if not slug:
            continue
        a = agg.setdefault(slug, [0, 0])
        a[0] += int(row.get("input_tokens") or 0)
        a[1] += int(row.get("output_tokens") or 0)

    ratios: Dict[str, float] = {}
    for slug, (in_tok, out_tok) in agg.items():
        if in_tok > 0 and out_tok > 0:
            ratios[slug] = out_tok / in_tok
    return ratios


async def check_atlas_balance(api_key: str, threshold_usd: float) -> Optional[float]:
    """GET /balance, vráti dostupný zostatok (USD). Pod hranicou zaloguje log.error.

    Fail-open — výpadok Atlas API vráti None (main.py loop to preskočí ďalším behom).
    """
    try:
        async with _client() as client:
            r = await client.get("/balance", headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            data = r.json()
        balance = _num((data.get("available") or {}).get("value"))
        if balance < threshold_usd:
            log.error("Atlas zostatok nízky: $%.2f (hranica $%.2f) — treba dobiť", balance, threshold_usd)
        return balance
    except Exception:  # noqa: BLE001 — stráženie zostatku nesmie zhodiť worker
        log.warning("check_atlas_balance zlyhal", exc_info=True)
        return None
