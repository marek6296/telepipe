#!/usr/bin/env python3
"""Presunie ElevenLabs kľúč z modeliek na účet (`accounts.eleven_key_enc`, 017).

    worker/.venv/bin/python scripts/move_eleven_key_to_account.py
    worker/.venv/bin/python scripts/move_eleven_key_to_account.py --execute

Bez `--execute` beží DRY-RUN: nič nezapíše, len vypíše čo by spravil.

PREČO PYTHON A NIE SQL
----------------------
Rovnaký dôvod ako pri `backfill_eleven_key.py`: kľúč je zašifrovaný AES-256-GCM
kľúčom z env (`ENCRYPTION_KEY`), ktorý v databáze nie je a byť nemá. SQL by
vedelo hodnotu iba prehodiť medzi stĺpcami naslepo — my ju chceme rozšifrovať,
overiť a zašifrovať nanovo, aby sa nedalo presunúť niečo, čo sa už dnes nedá
prečítať. Rovnaká krypto funkcia ako všade inde: `worker/src/crypto.py`
(a `web/lib/crypto.ts` na druhej strane).

AKO SA ROZHODUJE
----------------
Pre každú modelku sa zistí jej EFEKTÍVNY kľúč rovnako, ako ho číta worker:
`eleven_key_enc` (dešifrovaný), inak zastaraný čistý text `eleven_key`. Potom sa
kľúče modeliek jedného účtu porovnajú:

  * žiadny kľúč           → účet sa preskočí, nie je čo presúvať;
  * všetky rovnaké        → presunie sa;
  * ROZDIELNE             → hlučne sa ohlási a účet sa PRESKOČÍ.

Tá posledná vetva je celý dôvod, prečo je toto skript a nie jeden UPDATE.
Uhádnuť, ktorý z dvoch rôznych kľúčov je „ten správny", sa nedá — a zlá voľba
znamená, že jednej modelke prestanú chodiť hlasovky a nikto nebude vedieť prečo.
Nech to radšej rozhodne človek.

ČO SA NEDEJE
------------
`behavior.eleven_key_enc` ani `behavior.eleven_key` sa NEVYNULUJÚ. Kým nie je
nasadený worker, ktorý číta účet, sú per-model hodnoty jediná fungujúca cesta
k Simoniným hlasovkám — vymazať ich tu by znamenalo rozbiť produkciu kvôli
upratovaniu. A aj po nasadení ostávajú ako rollback: worker na ne padá, keď účet
kľúč nemá.

BEZPEČNOSŤ VÝPISU
-----------------
Kľúč sa nikdy nevypíše ani nezaloguje — porovnáva sa dĺžka a sha256 prefix.
Skript je idempotentný: účet, ktorý už má `eleven_key_enc` dešifrovateľný na tú
istú hodnotu, sa preskočí; účet, kde sa nezhoduje, sa ohlási a nechá tak
(prepísať by znamenalo zahodiť novší kľúč z dashboardu).
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


def _get(base: str, key: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    url = f"{base}/rest/v1/{table}?" + urllib.parse.urlencode(params)
    return _call("GET", url, key) or []


def write_account_enc(base: str, key: str, account_id: str, sealed: str) -> None:
    url = f"{base}/rest/v1/accounts?" + urllib.parse.urlencode({"id": f"eq.{account_id}"})
    _call("PATCH", url, key, {"eleven_key_enc": sealed})


def read_account_enc(base: str, key: str, account_id: str) -> str:
    rows = _get(
        base, key, "accounts", {"id": f"eq.{account_id}", "select": "eleven_key_enc"}
    )
    return str(rows[0].get("eleven_key_enc") or "") if rows else ""


def effective_key(row: dict[str, Any], enc_key: str) -> tuple[str, str]:
    """Kľúč modelky tak, ako ho dnes číta worker. Vracia (kľúč, odkiaľ).

    Poradie je zhodné s `unseal_eleven_key()` PRED touto zmenou: `_enc`
    prednostne, čistý text ako fallback. Nedešifrovateľné `_enc` je chyba, nie
    dôvod tíško siahnuť po starom čistom texte — presne ako vo workeri.
    """
    sealed = str(row.get("eleven_key_enc") or "")
    legacy = str(row.get("eleven_key") or "")
    if sealed:
        try:
            return decrypt(sealed, enc_key), "eleven_key_enc"
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"eleven_key_enc sa nedá dešifrovať ({exc})") from None
    if legacy:
        return legacy, "eleven_key (čistý text)"
    return "", ""


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
    print(f"== presun eleven_key na účet ({mode}) ==")
    print(f"   projekt: {base}")

    models = _get(base, service, "models", {"select": "id,account_id,name", "order": "name.asc"})
    behaviors = {
        str(r["model_id"]): r
        for r in _get(
            base, service, "behavior", {"select": "model_id,eleven_key,eleven_key_enc"}
        )
    }
    accounts = {
        str(r["id"]): r
        for r in _get(base, service, "accounts", {"select": "id,email,eleven_key_enc"})
    }

    # account_id → [(meno modelky, kľúč, odkiaľ)]
    per_account: dict[str, list[tuple[str, str, str]]] = {}
    problems = 0
    for model in models:
        account_id = str(model["account_id"])
        name = str(model.get("name") or model["id"])
        row = behaviors.get(str(model["id"]))
        if not row:
            continue
        try:
            plain, source = effective_key(row, enc_key)
        except RuntimeError as exc:
            print(f"   modelka {name}: {exc} — účet {account_id} preskakujem")
            per_account.setdefault(account_id, []).append((name, "", "CHYBA"))
            problems += 1
            continue
        if plain:
            per_account.setdefault(account_id, []).append((name, plain, source))

    if not per_account:
        print("   žiadna modelka nemá ElevenLabs kľúč — nie je čo presúvať")
        return 0

    moved = done = skipped = 0
    for account_id, entries in sorted(per_account.items()):
        email = str(accounts.get(account_id, {}).get("email") or "?")
        head = f"   účet {account_id} ({email})"

        if any(source == "CHYBA" for _, _, source in entries):
            print(f"{head}: niektorá modelka má nečitateľný kľúč — preskakujem")
            skipped += 1
            continue

        distinct = {plain for _, plain, _ in entries}
        for name, plain, source in entries:
            print(f"{head}: modelka {name} → {fingerprint(plain)} (z {source})")

        if len(distinct) > 1:
            print(
                f"{head}: POZOR — modelky majú RÔZNE kľúče "
                f"({', '.join(sorted(fingerprint(p) for p in distinct))}); "
                "neviem ktorý je ten správny, preskakujem"
            )
            problems += 1
            skipped += 1
            continue

        plain = next(iter(distinct))
        current = str(accounts.get(account_id, {}).get("eleven_key_enc") or "")
        if current:
            try:
                already = decrypt(current, enc_key)
            except Exception as exc:  # noqa: BLE001
                print(f"{head}: účet už má _enc, ale NEDÁ sa dešifrovať ({exc}) — nechávam")
                problems += 1
                continue
            if already == plain:
                print(f"{head}: hotové (účet už má ten istý kľúč, {fingerprint(already)})")
                done += 1
            else:
                print(
                    f"{head}: POZOR — účet má INÝ kľúč ({fingerprint(already)}) "
                    f"než modelky ({fingerprint(plain)}); neprepisujem"
                )
                problems += 1
            continue

        if not args.execute:
            print(f"{head}: [dry-run] zašifroval by som a zapísal accounts.eleven_key_enc")
            skipped += 1
            continue

        write_account_enc(base, service, account_id, encrypt(plain, enc_key))

        # Overenie sa robí z DATABÁZY, nie z premennej: zaujíma nás, či sa dá
        # späť prečítať to, čo tam naozaj doletelo.
        back = read_account_enc(base, service, account_id)
        if not back:
            print(f"{head}: CHYBA — po zápise je eleven_key_enc prázdny")
            problems += 1
            continue
        try:
            check = decrypt(back, enc_key)
        except Exception as exc:  # noqa: BLE001
            print(f"{head}: CHYBA — zápis sa nedá dešifrovať ({exc})")
            problems += 1
            continue
        if check != plain:
            print(f"{head}: CHYBA — round-trip nesedí ({fingerprint(check)})")
            problems += 1
            continue
        print(f"{head}: zapísané a overené, round-trip OK ({fingerprint(check)})")
        moved += 1

    print(
        f"== hotovo: {moved} presunutých, {done} už hotových, "
        f"{skipped} preskočených, {problems} problémov =="
    )
    print("   per-model `eleven_key*` zostávajú — worker ich používa ako fallback")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
