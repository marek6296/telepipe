#!/usr/bin/env python3
"""Doplní `behavior.eleven_key_enc` k existujúcim čistotextovým kľúčom (014).

    worker/.venv/bin/python scripts/backfill_eleven_key.py
    worker/.venv/bin/python scripts/backfill_eleven_key.py --execute

Bez `--execute` beží DRY-RUN: nič nezapíše, len vypíše čo by spravil.

PREČO PYTHON A NIE SQL
----------------------
Šifruje sa AES-256-GCM kľúčom z env (`ENCRYPTION_KEY`), ktorý v databáze nie je
a byť nemá — migrácia 014 preto stĺpec len založí a naplniť ho vie iba niečo,
čo ten kľúč drží. Rovnaká krypto funkcia ako všade inde: `worker/src/crypto.py`
(a `web/lib/crypto.ts` na druhej strane).

ČO SA NEDEJE
------------
Starý stĺpec `eleven_key` sa NEVYNULUJE. Kým nie je vonku UI a nasadený worker,
ktorý číta `_enc`, je čistý text jediná fungujúca cesta k Simoniným hlasovkám —
vymazať ho tu by znamenalo rozbiť produkciu kvôli upratovaniu. Vynulovanie je
samostatný krok neskôr (a `set_eleven_key()` ho pri prvom zápise z dashboardu
spraví sama).

BEZPEČNOSŤ VÝPISU
-----------------
Kľúč sa nikdy nevypíše ani nezaloguje — porovnáva sa dĺžka a sha256 prefix.
Skript je idempotentný: riadok, ktorý už má `_enc` dešifrovateľný na tú istú
hodnotu, sa preskočí; riadok, kde sa `_enc` a čistý text NEZHODUJÚ, sa hlučne
ohlási a nechá tak (prepísať by znamenalo zahodiť novší kľúč z dashboardu).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker" / "src"))

from crypto import decrypt, encrypt  # noqa: E402  (worker/src na sys.path vyššie)

ENV_FILE = ROOT / ".env"
TIMEOUT_S = 60


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def fingerprint(value: str) -> str:
    """Odtlačok kľúča do výpisu — dĺžka + prvých 12 znakov sha256.

    Dosť na to, aby sa dve hodnoty dali porovnať očami aj naprieč behmi;
    málo na to, aby sa z toho dal kľúč získať.
    """
    if not value:
        return "prázdne"
    return f"len={len(value)} sha256={hashlib.sha256(value.encode()).hexdigest()[:12]}"


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


def rows_with_key(base: str, key: str) -> list[dict[str, Any]]:
    """Riadky `behavior`, ktoré vôbec nejaký ElevenLabs kľúč majú.

    Filtruje sa až v Pythone: `eleven_key` aj `eleven_key_enc` sú `not null
    default ''`, takže „prázdne" je prázdny reťazec a ten sa v PostgREST URL
    píše otravne. Riadkov je toľko, koľko modeliek — na filtrovanie v DB tu nie
    je dôvod.
    """
    url = (
        f"{base}/rest/v1/behavior?"
        + urllib.parse.urlencode(
            {"select": "model_id,eleven_key,eleven_key_enc", "order": "model_id.asc"}
        )
    )
    rows = _call("GET", url, key) or []
    return [
        r
        for r in rows
        if str(r.get("eleven_key") or "") or str(r.get("eleven_key_enc") or "")
    ]


def write_enc(base: str, key: str, model_id: str, sealed: str) -> None:
    url = f"{base}/rest/v1/behavior?" + urllib.parse.urlencode(
        {"model_id": f"eq.{model_id}"}
    )
    _call("PATCH", url, key, {"eleven_key_enc": sealed})


def read_enc(base: str, key: str, model_id: str) -> str:
    url = f"{base}/rest/v1/behavior?" + urllib.parse.urlencode(
        {"model_id": f"eq.{model_id}", "select": "eleven_key_enc"}
    )
    rows = _call("GET", url, key) or []
    return str(rows[0].get("eleven_key_enc") or "") if rows else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="naozaj zapíš (inak dry-run)")
    ap.add_argument("--env", default=str(ENV_FILE), help="odkiaľ vziať kľúče")
    args = ap.parse_args()

    env = load_env(Path(args.env))
    base = env.get("SUPABASE_URL", "").rstrip("/")
    service = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SECRET_KEY") or ""
    enc_key = env.get("ENCRYPTION_KEY", "")
    missing = [
        name
        for name, val in (
            ("SUPABASE_URL", base),
            ("SUPABASE_SERVICE_KEY", service),
            ("ENCRYPTION_KEY", enc_key),
        )
        if not val
    ]
    if missing:
        print(f"CHYBA: v {args.env} chýba {', '.join(missing)}")
        return 2

    mode = "ZÁPIS" if args.execute else "DRY-RUN"
    print(f"== backfill eleven_key_enc ({mode}) ==")
    print(f"   projekt: {base}")

    rows = rows_with_key(base, service)
    if not rows:
        print("   žiadna modelka nemá ElevenLabs kľúč — nie je čo robiť")
        return 0

    done = skipped = written = problems = 0
    for row in rows:
        model_id = str(row["model_id"])
        legacy = str(row.get("eleven_key") or "")
        sealed = str(row.get("eleven_key_enc") or "")
        head = f"   model {model_id}"

        if sealed:
            # Už zašifrované — overiť, či to sedí, a ísť ďalej. Toto je celá
            # idempotencia skriptu.
            try:
                plain = decrypt(sealed, enc_key)
            except Exception as exc:  # noqa: BLE001
                print(f"{head}: _enc sa NEDÁ dešifrovať ({exc}) — nechávam tak")
                problems += 1
                continue
            if not legacy:
                print(f"{head}: hotové (len _enc, {fingerprint(plain)})")
                done += 1
            elif plain == legacy:
                print(f"{head}: hotové (_enc == eleven_key, {fingerprint(plain)})")
                done += 1
            else:
                print(
                    f"{head}: POZOR — _enc ({fingerprint(plain)}) sa nezhoduje "
                    f"s eleven_key ({fingerprint(legacy)}); neprepisujem"
                )
                problems += 1
            continue

        if not legacy:
            skipped += 1
            continue

        print(f"{head}: čistý text bez _enc ({fingerprint(legacy)})")
        if not args.execute:
            print(f"{head}: [dry-run] zašifroval by som a zapísal eleven_key_enc")
            skipped += 1
            continue

        new_sealed = encrypt(legacy, enc_key)
        write_enc(base, service, model_id, new_sealed)

        # Overenie sa robí z DATABÁZY, nie z premennej: zaujíma nás, či sa dá
        # späť prečítať to, čo tam naozaj doletelo.
        back = read_enc(base, service, model_id)
        if not back:
            print(f"{head}: CHYBA — po zápise je _enc prázdny")
            problems += 1
            continue
        try:
            plain = decrypt(back, enc_key)
        except Exception as exc:  # noqa: BLE001
            print(f"{head}: CHYBA — zápis sa nedá dešifrovať ({exc})")
            problems += 1
            continue
        if plain != legacy:
            print(f"{head}: CHYBA — round-trip nesedí ({fingerprint(plain)})")
            problems += 1
            continue
        print(f"{head}: zapísané a overené, round-trip OK ({fingerprint(plain)})")
        written += 1

    print(
        f"== hotovo: {written} zapísaných, {done} už hotových, "
        f"{skipped} preskočených, {problems} problémov =="
    )
    print("   `eleven_key` (čistý text) zostáva — maže sa až po nasadení UI")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
