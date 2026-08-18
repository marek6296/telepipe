#!/usr/bin/env python3
"""Vypíše napísaný deň zo `den.py` do `model_schedule` (migrácia 022).

    worker/.venv/bin/python scripts/seed_schedule.py --check
    worker/.venv/bin/python scripts/seed_schedule.py --model Simona --execute
    worker/.venv/bin/python scripts/seed_schedule.py --all --execute

Bez `--execute` je to DRY-RUN: nič nezapíše, len povie, čo by spravil.
`--check` nezapisuje vôbec — porovná deň, ktorý vyjde z DB, s dňom, ktorý
vyjde zo šablóny, blok po bloku na 14 dní dopredu.

PREČO TO NIE JE LEN SQL
-----------------------
Migrácia 022 má šablónu ako DEFAULT stĺpca, takže riadok stačí založiť. Lenže
tá šablóna je v SQL prepísaná ručne a jediný pravdivý zdroj je Python
(`den.SABLONA`). Tento skript materializuje priamo z neho a `--check` overí, že
sa tie dva zoznamy nerozišli — a hlavne to, na čom naozaj záleží: že modelke
s riadkom v DB vyjde presne ten istý deň ako modelke bez neho.

ČO SA STANE, KEĎ SI KLIENT DEŇ UŽ UPRAVIL
-----------------------------------------
Nič. `--execute` prepíše riadok len s `--force`; inak existujúci rozvrh
nechá tak a povie to. Prepísať niekomu nastavený deň šablónou je presne ten
druh „upratovania", po ktorom sa modelka zrazu správa inak, než klient čaká.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker" / "src"))

import den as D  # noqa: E402  (worker/src na sys.path vyššie)

ENV_FILE = ROOT / ".env"
TIMEOUT_S = 60
# Koľko dní dopredu sa porovnáva. Týždeň by nechytil rozdiel, ktorý sa deje raz
# za dva týždne; štrnásť dní prejde každý deň v týždni dvakrát.
DNI_KONTROLY = 14


def load_env(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _call(method: str, url: str, key: str, body: Any = None) -> Any:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal"
    req = urllib.request.Request(url, method=method, data=data)
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:600].decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} → HTTP {exc.code}: {detail}") from None
    return json.loads(raw) if raw.strip() else None


def models(base: str, key: str, meno: str = "") -> List[Dict[str, Any]]:
    params = {"select": "id,name,status", "order": "created_at.asc"}
    if meno:
        params["name"] = f"eq.{meno}"
    url = f"{base}/rest/v1/models?" + urllib.parse.urlencode(params)
    return _call("GET", url, key) or []


def schedule_row(base: str, key: str, model_id: str) -> Optional[Dict[str, Any]]:
    url = f"{base}/rest/v1/model_schedule?" + urllib.parse.urlencode(
        {"model_id": f"eq.{model_id}", "select": "*"}
    )
    rows = _call("GET", url, key) or []
    return rows[0] if rows else None


def write_row(base: str, key: str, model_id: str, telo: Dict[str, Any]) -> None:
    """Zápis cez upsert — jedno volanie pre nový aj existujúci riadok."""
    url = f"{base}/rest/v1/model_schedule"
    headers_body = dict(telo)
    headers_body["model_id"] = model_id
    req = urllib.request.Request(url, method="POST", data=json.dumps(headers_body).encode())
    for name, value in (
        ("apikey", key),
        ("Authorization", f"Bearer {key}"),
        ("Content-Type", "application/json"),
        ("Prefer", "resolution=merge-duplicates,return=minimal"),
    ):
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:600].decode("utf-8", "replace")
        raise RuntimeError(f"POST {url} → HTTP {exc.code}: {detail}") from None


def rozdiely(seed: str, rozvrh: Optional[D.Rozvrh], odkedy: date) -> List[str]:
    """Dni, v ktorých sa rozvrh z DB líši od napísanej šablóny."""
    out: List[str] = []
    for offset in range(DNI_KONTROLY):
        d = odkedy + timedelta(days=offset)
        if D.plan(d, seed) != D.plan(d, seed, rozvrh):
            out.append(d.isoformat())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="", help="meno modelky (inak všetky)")
    ap.add_argument("--all", action="store_true", help="všetky modelky")
    ap.add_argument("--execute", action="store_true", help="naozaj zapíš (inak dry-run)")
    ap.add_argument("--force", action="store_true", help="prepíš aj existujúci rozvrh")
    ap.add_argument("--check", action="store_true", help="len porovnaj, nezapisuj")
    ap.add_argument("--env", default=str(ENV_FILE))
    args = ap.parse_args()

    if not args.model and not args.all and not args.check:
        print("CHYBA: povedz --model <meno> alebo --all (alebo --check)")
        return 2

    env = load_env(Path(args.env))
    base = env.get("SUPABASE_URL", "").rstrip("/")
    service = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SECRET_KEY") or ""
    if not base or not service:
        print(f"CHYBA: v {args.env} chýba SUPABASE_URL alebo SUPABASE_SERVICE_KEY")
        return 2

    mode = "KONTROLA" if args.check else ("ZÁPIS" if args.execute else "DRY-RUN")
    print(f"== rozvrh dňa zo šablóny ({mode}) ==")
    print(f"   projekt: {base}")
    print(f"   šablóna: {len(D.SABLONA.cinnosti)} činností, "
          f"vstávanie {D.SABLONA.vstavanie_tyzden} / {D.SABLONA.vstavanie_vikend}")

    telo = D.SABLONA.to_row()
    dnes = date.today()
    problems = written = 0

    for model in models(base, service, args.model):
        model_id = str(model["id"])
        head = f"   {model.get('name') or '(bez mena)'} [{model_id[:8]}]"
        existing = schedule_row(base, service, model_id)

        if not args.check:
            if existing and not args.force:
                print(f"{head}: rozvrh už má — nechávam tak (--force ho prepíše)")
            elif not args.execute:
                print(f"{head}: [dry-run] zapísal by som {len(telo['activities'])} činností")
            else:
                write_row(base, service, model_id, telo)
                written += 1
                existing = schedule_row(base, service, model_id)
                print(f"{head}: zapísané")

        # Overuje sa VŽDY a z databázy — zaujíma nás deň, ktorý vyjde z toho,
        # čo tam naozaj doletelo, nie z toho, čo sme poslali.
        rozvrh = D.Rozvrh.from_row(existing)
        if rozvrh is None:
            print(f"{head}: rozvrh v DB nie je → beží šablóna (deň sa nemení)")
            continue
        zle = rozdiely(model_id, rozvrh, dnes)
        if zle:
            problems += 1
            print(f"{head}: POZOR — deň z DB sa líši od šablóny v {len(zle)} dňoch: "
                  f"{', '.join(zle[:5])}")
        else:
            print(f"{head}: OK — {DNI_KONTROLY} dní blok po bloku zhodných so šablónou")

    print(f"== hotovo: {written} zapísaných, {problems} problémov ==")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
