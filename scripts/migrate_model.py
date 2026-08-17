#!/usr/bin/env python3
"""Migrácia starej jednomodelkovej inštalácie (schéma tgai/tgmio v projekte
„ai news") do telepipe — idempotentne, do stavu `paused`.

    worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona
    worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona --execute
    worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona --delta --execute
    worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona --only-fanvue --execute

Bez `--execute` beží DRY-RUN: nič nezapíše, len vypíše čo by spravil.

BEZPEČNOSŤ
----------
* Starý projekt je READ-ONLY. `Supa(read_only=True)` vyhodí výnimku pri
  akejkoľvek metóde inej než GET ešte pred otvorením socketu — zapísať doň
  sa cez tento skript nedá ani omylom.
* Modelka v telepipe vzniká VŽDY so `status='paused'` a
  `status_reason='migration_standby'`. Stará služba stále beží a druhá
  Telegram session nad tým istým účtom = ban. Ak už riadok existuje a nie je
  `paused`, skript sa hlučne ukončí a nič nezapíše.
* Idempotencia: modelka sa hľadá podľa `models.migration_source`
  ('tgai' / 'tgmio', partial unique index). Mutable tabuľky sa upsertujú,
  append-only tabuľky sa deduplikujú podľa prirodzeného kľúča — opakovaný beh
  teda nič nezduplikuje.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker" / "src"))

from crypto import encrypt  # noqa: E402  (worker/src na sys.path vyššie)

OLD_ENV_FILES = {
    "tgai": Path("/Users/marek/telegram/.env"),
    "tgmio": Path("/Users/marek/telegram/.env.mio"),
}
OWNER_EMAIL = "cmelo.marek@gmail.com"
BATCH = 500
# Prekryv pri --delta: radšej pár riadkov navyše (dedup ich zahodí) než diera.
DELTA_OVERLAP = timedelta(minutes=10)
# Staré buckety → telepipe buckety.
BUCKET_MAP = {"model-photos": "photos", "model-voices": "voices"}
# `id` je v cieli iný (bigserial naprieč všetkými modelkami), `fts` je generated.
DROP_COLS = {"id", "fts"}


# ---------------------------------------------------------------------------
# env + HTTP
# ---------------------------------------------------------------------------

def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


class HttpError(RuntimeError):
    pass


class ReadOnlyViolation(RuntimeError):
    """Pokus o zápis do read-only projektu. Nikdy by nemal nastať."""


def _raw(method: str, url: str, headers: dict[str, str], body: bytes | None,
         timeout: int = 180) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, method=method, data=body)
    for key, val in headers.items():
        req.add_header(key, val)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:600].decode("utf-8", "replace")
        raise HttpError(f"{method} {url} → HTTP {exc.code}: {detail}") from None


class Supa:
    """Tenký PostgREST/Storage klient. `read_only=True` = tvrdá poistka."""

    def __init__(self, base: str, key: str, *, schema: str | None = None,
                 read_only: bool = False, label: str = "") -> None:
        self.base = base.rstrip("/")
        self.key = key
        self.schema = schema
        self.read_only = read_only
        self.label = label or self.base
        self.gets = 0
        self.writes = 0

    # -- poistka -------------------------------------------------------------
    def _guard(self, method: str, url: str) -> None:
        if not url.startswith(self.base):
            raise ReadOnlyViolation(f"{self.label}: URL mimo base ({url})")
        if self.read_only and method.upper() not in ("GET", "HEAD"):
            raise ReadOnlyViolation(
                f"{self.label} je READ-ONLY — pokus o {method.upper()} na {url}")
        if method.upper() in ("GET", "HEAD"):
            self.gets += 1
        else:
            self.writes += 1

    def _headers(self, extra: dict[str, str] | None = None, *, write: bool = False) -> dict[str, str]:
        head = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        if self.schema:
            head["Accept-Profile"] = self.schema
            if write:
                head["Content-Profile"] = self.schema
        head.update(extra or {})
        return head

    # -- REST ----------------------------------------------------------------
    def rest(self, method: str, table: str, *, params: dict[str, Any] | None = None,
             rows: Any = None, headers: dict[str, str] | None = None) -> tuple[dict[str, str], Any]:
        url = f"{self.base}/rest/v1/{table}"
        if params:
            url += "?" + urllib.parse.urlencode(params, safe="().,*:-")
        self._guard(method, url)
        body = None
        extra = dict(headers or {})
        if rows is not None:
            body = json.dumps(rows).encode()
            extra["Content-Type"] = "application/json"
        _, head, raw = _raw(method, url, self._headers(extra, write=rows is not None), body)
        payload = json.loads(raw) if raw.strip() else None
        return head, payload

    def count(self, table: str, params: dict[str, Any] | None = None) -> int:
        head, _ = self.rest("GET", table, params={**(params or {}), "select": "count"},
                            headers={"Prefer": "count=exact", "Range": "0-0"})
        rng = head.get("Content-Range", "*/0")
        return int(rng.split("/")[-1])

    def fetch_all(self, table: str, *, select: str = "*", order: str | None = None,
                  params: dict[str, Any] | None = None) -> list[dict]:
        out: list[dict] = []
        page, offset = 1000, 0
        while True:
            query = {**(params or {}), "select": select, "limit": page, "offset": offset}
            if order:
                query["order"] = order
            _, rows = self.rest("GET", table, params=query)
            rows = rows or []
            out.extend(rows)
            if len(rows) < page:
                return out
            offset += page

    def openapi_columns(self) -> dict[str, set[str]]:
        url = f"{self.base}/rest/v1/"
        self._guard("GET", url)
        _, _, raw = _raw("GET", url, self._headers({"Accept": "application/openapi+json"}), None)
        spec = json.loads(raw)
        defs = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
        return {name: set(body.get("properties", {})) for name, body in defs.items()}

    # -- Storage -------------------------------------------------------------
    def download(self, url: str) -> bytes:
        self._guard("GET", url)
        _, _, raw = _raw("GET", url, self._headers(), None)
        return raw

    def object_exists(self, bucket: str, path: str) -> bool:
        url = f"{self.base}/storage/v1/object/public/{bucket}/{urllib.parse.quote(path)}"
        self._guard("HEAD", url)
        try:
            _raw("HEAD", url, self._headers(), None, timeout=60)
            return True
        except HttpError:
            return False

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> str:
        url = f"{self.base}/storage/v1/object/{bucket}/{urllib.parse.quote(path)}"
        self._guard("POST", url)
        _raw("POST", url, self._headers({"Content-Type": content_type, "x-upsert": "true"}), data)
        return f"{self.base}/storage/v1/object/public/{bucket}/{urllib.parse.quote(path)}"


# ---------------------------------------------------------------------------
# tabuľky
# ---------------------------------------------------------------------------
# kind:
#   singleton … presne 1 riadok, PK = model_id (upsert)
#   upsert    … mutable riadky s prirodzeným PK (dm_users)
#   mapped    … mutable, ale cieľové `id` je iné → drží sa mapa staré→nové id
#   sends     … kompozitný PK obsahujúci remapované id (photo_sends/voice_sends)
#   facts     … append-only + self-reference `superseded_by` (remap)
#   append    … append-only, dedup podľa prirodzeného kľúča
TABLES: list[dict[str, Any]] = [
    {"name": "persona", "kind": "singleton"},
    {"name": "behavior", "kind": "singleton"},
    {"name": "settings", "kind": "singleton"},
    {"name": "dm_users", "kind": "upsert", "conflict": "model_id,tg_id", "order": "tg_id"},
    {"name": "dm_messages", "kind": "append", "order": "id", "ts": "created_at",
     "nat": ("tg_id", "role", "content", "created_at")},
    {"name": "facts", "kind": "facts", "order": "id", "ts": "first_seen",
     "nat": ("tg_id", "key", "value", "first_seen")},
    {"name": "photos", "kind": "mapped", "order": "id", "storage": "photos",
     "nat": ("url", "caption", "created_at")},
    {"name": "photo_sends", "kind": "sends", "order": "sent_at", "ref": "photo_id",
     "ref_table": "photos", "conflict": "model_id,photo_id,tg_id",
     "nat": ("photo_id", "tg_id")},
    {"name": "voices", "kind": "mapped", "order": "id", "storage": "voices",
     "nat": ("transcript", "slot", "url", "created_at")},
    {"name": "voice_sends", "kind": "sends", "order": "sent_at", "ref": "voice_id",
     "ref_table": "voices", "conflict": "model_id,voice_id,tg_id",
     "nat": ("voice_id", "tg_id")},
    {"name": "episodes", "kind": "append", "order": "id", "ts": "created_at",
     "nat": ("tg_id", "started_at", "ended_at", "title")},
    {"name": "open_loops", "kind": "append", "order": "id", "ts": "created_at",
     "nat": ("tg_id", "what", "created_at")},
    {"name": "self_claims", "kind": "append", "order": "id", "ts": "said_at",
     "nat": ("tg_id", "claim", "said_at")},
    {"name": "judge_log", "kind": "append", "order": "id", "ts": "created_at",
     "nat": ("tg_id", "draft", "created_at")},
    {"name": "voice_clips", "kind": "append", "order": "id", "ts": "created_at",
     "storage": "voices", "nat": ("tg_id", "text", "created_at")},
    {"name": "voice_jobs", "kind": "append", "order": "id", "ts": "created_at",
     "nat": ("text", "created_at")},
    # --- Fanvue (migrácia 012) --------------------------------------------
    # Poradie je dané cudzími kľúčmi: fanúšik a médium musia existovať skôr,
    # než sa naň odvolá správa alebo záznam o poslaní.
    #
    # Samotný riadok `fanvue` (OAuth tokeny) sa NEmigruje zámerne: v starej DB
    # je v čistom texte, tu je šifrovaný naším kľúčom a vydaný pre inú appku.
    # Účet sa v telepipe pripája nanovo cez OAuth v dashboarde.
    {"name": "fv_users", "kind": "upsert", "conflict": "model_id,fan_uuid",
     "order": "fan_uuid"},
    {"name": "fv_messages", "kind": "append", "order": "id", "ts": "created_at",
     "nat": ("fan_uuid", "role", "content", "created_at")},
    {"name": "fv_folders", "kind": "upsert", "conflict": "model_id,name", "order": "name"},
    {"name": "fv_media", "kind": "upsert", "conflict": "model_id,media_uuid",
     "order": "media_uuid"},
    # V starej schéme mala táto tabuľka `id bigserial` a mohla obsahovať tú istú
    # dvojicu viackrát; v 012 je PK prirodzený, takže upsert prípadné duplicity
    # zlúči do jedného riadku (číta sa z nej len množina `media_uuid`).
    {"name": "fv_media_sends", "kind": "upsert", "conflict": "model_id,media_uuid,fan_uuid",
     "order": "id"},
]


# Časové stĺpce normalizujeme na UTC ISO — dva PostgRESTy môžu ten istý
# okamih vypísať odlišne a prirodzený kľúč by potom zbytočne nesedel.
TS_COLS = {"created_at", "updated_at", "first_seen", "last_confirmed", "said_at",
           "sent_at", "started_at", "ended_at", "done_at", "closed_at"}


def natural_key(row: dict, cols: Iterable[str]) -> tuple:
    out = []
    for col in cols:
        val = row.get(col)
        if col in TS_COLS and isinstance(val, str):
            try:
                val = (datetime.fromisoformat(val.replace("Z", "+00:00"))
                       .astimezone(timezone.utc).isoformat())
            except ValueError:
                pass
        out.append(json.dumps(val, sort_keys=True, default=str))
    return tuple(out)


def strip_cols(row: dict, allowed: set[str]) -> dict:
    return {k: v for k, v in row.items() if k not in DROP_COLS and k in allowed}


def zip_new_ids(table: str, to_insert: list[tuple[int, dict]], created: list[dict],
                nat: Iterable[str], execute: bool) -> dict[int, Any]:
    """Staré id → nové id pre práve vložené riadky.

    PostgREST vracia `return=representation` v poradí vkladania; poradie ešte
    krížovo overíme prirodzeným kľúčom, aby sa remap `superseded_by` /
    `photo_id` nemohol potichu rozísť. V DRY-RUN sa mapujú zástupné hodnoty,
    nech aj naprázdno vyjdú počty závislých tabuliek.
    """
    if not execute:
        return {old_id: f"dry-{old_id}" for old_id, _ in to_insert}
    if len(created) != len(to_insert):
        raise SystemExit(f"STOP: {table} — vložených {len(created)} z {len(to_insert)} "
                         f"riadkov, mapa id by bola nespoľahlivá.")
    out: dict[int, Any] = {}
    for (old_id, body), made in zip(to_insert, created):
        if natural_key(body, nat) != natural_key(made, nat):
            raise SystemExit(f"STOP: {table} — návratové poradie riadkov nesedí "
                             f"(staré id {old_id}), remap id prerušený.")
        out[old_id] = made["id"]
    return out


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

class Storage:
    """Prenos objektov zo starého public bucketu do telepipe bucketu."""

    def __init__(self, old: Supa, new: Supa, model_id: str | None, execute: bool) -> None:
        self.old, self.new = old, new
        self.model_id = model_id
        self.execute = execute
        self.prefix = f"{old.base}/storage/v1/object/public/"
        self.copied = 0
        self.reused = 0
        self.planned = 0
        self.external = 0
        self._done: dict[str, str] = {}

    def rewrite(self, url: str) -> str:
        """Vráti novú URL (a prípadne objekt prekopíruje). Externé nechá tak."""
        if not url:
            return url
        if not url.startswith(self.prefix):
            if url.startswith(self.new.base):
                return url  # už premigrované
            self.external += 1
            return url
        rest = url[len(self.prefix):]
        bucket_old, _, obj_path = rest.partition("/")
        bucket = BUCKET_MAP.get(bucket_old)
        if not bucket:
            self.external += 1
            return url
        obj_path = urllib.parse.unquote(obj_path.split("?")[0])
        if url in self._done:
            return self._done[url]
        model = self.model_id or "<new-model-id>"
        dest = f"{model}/{obj_path}"
        new_url = (f"{self.new.base}/storage/v1/object/public/{bucket}/"
                   f"{urllib.parse.quote(dest)}")
        if not self.execute:
            self.planned += 1
            self._done[url] = new_url
            return new_url
        if self.new.object_exists(bucket, dest):
            self.reused += 1
        else:
            data = self.old.download(url)
            ctype = ("image/jpeg" if obj_path.lower().endswith((".jpg", ".jpeg"))
                     else "image/png" if obj_path.lower().endswith(".png")
                     else "audio/ogg" if obj_path.lower().endswith((".ogg", ".oga"))
                     else "audio/mpeg" if obj_path.lower().endswith(".mp3")
                     else "application/octet-stream")
            new_url = self.new.upload(bucket, dest, data, ctype)
            self.copied += 1
        self._done[url] = new_url
        return new_url


# ---------------------------------------------------------------------------
# model riadok
# ---------------------------------------------------------------------------

def find_or_create_model(new: Supa, schema: str, name: str, old_env: dict[str, str],
                         enc_key: str, account_id: str, execute: bool,
                         touch_model: bool = True) -> tuple[str | None, dict]:
    _, rows = new.rest("GET", "models", params={
        "select": "*", "migration_source": f"eq.{schema}"})
    existing = (rows or [None])[0]

    # `--only-fanvue` dobehá fv_* tabuľky k modelke, ktorá už môže byť ostrá.
    # Nesiaha na riadok `models` ani na Telegram creds, takže dôvod pre kontrolu
    # `paused` (dve sessions nad jedným účtom) tu neplatí — a bez zápisu do
    # `models` ho ani nemá ako porušiť.
    if not touch_model:
        if not existing:
            raise SystemExit(f"STOP: modelka pre migration_source={schema!r} v telepipe "
                             f"neexistuje. Najprv bežná migrácia, potom --only-fanvue.")
        print(f"  models: {existing['id']} (status={existing['status']}) — nedotknuté "
              f"(--only-fanvue)")
        return existing["id"], {}

    if existing and existing["status"] != "paused":
        raise SystemExit(
            f"\nSTOP: modelka '{existing['name']}' ({existing['id']}) má status "
            f"'{existing['status']}' — nie 'paused'.\nMigrácia sa nespustí: bežiaci "
            f"telepipe worker + stará Railway služba = dve Telegram sessions nad "
            f"jedným účtom.\nNajprv modelku pauzni, potom skript spusti znova.")

    creds = {
        "tg_api_id": int(old_env["TG_API_ID"]),
        "tg_api_hash": old_env["TG_API_HASH"],
        "tg_session_enc": encrypt(old_env["TG_SESSION"], enc_key),
        "control_bot_token_enc": encrypt(old_env["CONTROL_BOT_TOKEN"], enc_key),
        "owner_chat_id": int(old_env["OWNER_CHAT_ID"]),
        "owner_as_client": old_env.get("OWNER_AS_CLIENT", "false").lower() == "true",
        "voice_only_ids": [int(x) for x in old_env.get("VOICE_ONLY_IDS", "").split(",") if x.strip()],
    }

    if existing:
        print(f"  models: existujúci riadok {existing['id']} (status={existing['status']}) "
              f"→ obnovím meno + TG creds")
        if execute:
            new.rest("PATCH", "models", params={"id": f"eq.{existing['id']}"},
                     rows={**creds, "name": name}, headers={"Prefer": "return=minimal"})
        return existing["id"], creds

    print(f"  models: riadok neexistuje → vytvorím ('{name}', status=paused, "
          f"status_reason=migration_standby, migration_source={schema})")
    if not execute:
        return None, creds
    _, created = new.rest("POST", "models", rows={
        "account_id": account_id, "name": name, "status": "paused",
        "status_reason": "migration_standby", "migration_source": schema, **creds},
        headers={"Prefer": "return=representation"})
    return created[0]["id"], creds


# ---------------------------------------------------------------------------
# migrácia jednej tabuľky
# ---------------------------------------------------------------------------

def migrate_table(spec: dict, old: Supa, new: Supa, model_id: str | None,
                  target_cols: dict[str, set[str]], storage: Storage,
                  id_maps: dict[str, dict[int, int]], execute: bool,
                  delta: bool) -> dict[str, Any]:
    table = spec["name"]
    kind = spec["kind"]
    allowed = target_cols.get(table, set())
    scope = {"model_id": f"eq.{model_id}"} if model_id else None

    src_count = old.count(table)
    tgt_before = new.count(table, scope) if model_id else 0

    src_rows = old.fetch_all(table, order=spec.get("order"))

    # --delta: pri append-only tabuľkách si berieme len to, čo je novšie než
    # najnovší riadok v cieli (s prekryvom; duplicity zahodí dedup nižšie).
    delta_from: str | None = None
    if delta and model_id and kind == "append" and spec.get("ts"):
        _, newest = new.rest("GET", table, params={
            "select": spec["ts"], "model_id": f"eq.{model_id}",
            "order": f"{spec['ts']}.desc", "limit": 1})
        if newest:
            cut = datetime.fromisoformat(newest[0][spec["ts"]].replace("Z", "+00:00"))
            cut -= DELTA_OVERLAP
            delta_from = cut.astimezone(timezone.utc).isoformat()
            src_rows = [r for r in src_rows
                        if r.get(spec["ts"]) and
                        datetime.fromisoformat(r[spec["ts"]].replace("Z", "+00:00")) >= cut]

    # URL prepis (storage) ešte pred tvorbou prirodzených kľúčov.
    if spec.get("storage"):
        for row in src_rows:
            if row.get("url"):
                row["url"] = storage.rewrite(row["url"])

    dropped = sorted({k for r in src_rows[:1] for k in r if k not in DROP_COLS and k not in allowed})
    stat = {"table": table, "source": src_count, "target_before": tgt_before,
            "inserted": 0, "updated": 0, "skipped": 0, "dropped_cols": dropped,
            "delta_from": delta_from}

    def post(rows: list[dict], *, conflict: str | None = None,
             representation: bool = False) -> list[dict]:
        if not rows or not execute:
            return []
        out: list[dict] = []
        prefer = "return=representation" if representation else "return=minimal"
        if conflict:
            prefer += ",resolution=merge-duplicates"
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            params = {"on_conflict": conflict} if conflict else None
            _, payload = new.rest("POST", table, params=params, rows=chunk,
                                  headers={"Prefer": prefer})
            out.extend(payload or [])
        return out

    # ---- singleton / dm_users: plný upsert ---------------------------------
    if kind in ("singleton", "upsert"):
        conflict = "model_id" if kind == "singleton" else spec["conflict"]
        payload = [{**strip_cols(r, allowed), "model_id": model_id} for r in src_rows]
        post(payload, conflict=conflict)
        stat["updated" if tgt_before else "inserted"] = len(payload)
        if not execute:
            stat["inserted"] = len(payload)
        stat["target_after"] = new.count(table, scope) if (model_id and execute) else tgt_before
        return stat

    # ---- photos / voices: mutable + mapa starých id ------------------------
    if kind == "mapped":
        existing = new.fetch_all(table, params={"model_id": f"eq.{model_id}"}) if model_id else []
        by_key = {natural_key(r, spec["nat"]): r for r in existing}
        id_map: dict[int, int] = {}
        to_insert: list[tuple[int, dict]] = []
        for row in src_rows:
            key = natural_key(row, spec["nat"])
            body = {**strip_cols(row, allowed), "model_id": model_id}
            if key in by_key:
                target = by_key[key]
                id_map[row["id"]] = target["id"]
                stat["updated"] += 1
                if execute:
                    new.rest("PATCH", table, params={"id": f"eq.{target['id']}"},
                             rows=body, headers={"Prefer": "return=minimal"})
            else:
                to_insert.append((row["id"], body))
        created = post([b for _, b in to_insert], representation=True)
        id_map.update(zip_new_ids(table, to_insert, created, spec["nat"], execute))
        stat["inserted"] = len(to_insert)
        id_maps[table] = id_map
        stat["target_after"] = new.count(table, scope) if (model_id and execute) else tgt_before
        return stat

    # ---- photo_sends / voice_sends: remap id + upsert na kompozitný PK -----
    if kind == "sends":
        id_map = id_maps.get(spec["ref_table"], {})
        payload, orphan = [], 0
        for row in src_rows:
            new_ref = id_map.get(row[spec["ref"]])
            if new_ref is None:
                orphan += 1
                continue
            body = {**strip_cols(row, allowed), "model_id": model_id, spec["ref"]: new_ref}
            payload.append(body)
        post(payload, conflict=spec["conflict"])
        stat["inserted"] = len(payload)
        stat["skipped"] = orphan
        stat["target_after"] = new.count(table, scope) if (model_id and execute) else tgt_before
        return stat

    # ---- facts: append + remap self-reference ------------------------------
    if kind == "facts":
        all_src = old.fetch_all(table, order=spec.get("order"))  # kvôli mape vždy všetko
        existing = new.fetch_all(table, params={"model_id": f"eq.{model_id}"}) if model_id else []
        by_key = {natural_key(r, spec["nat"]): r["id"] for r in existing}
        id_map: dict[int, int] = {}
        to_insert: list[tuple[int, dict]] = []
        for row in all_src:
            key = natural_key(row, spec["nat"])
            if key in by_key:
                id_map[row["id"]] = by_key[key]
                stat["skipped"] += 1
                continue
            body = {**strip_cols(row, allowed), "model_id": model_id}
            body["superseded_by"] = None  # doplní sa až po remape
            to_insert.append((row["id"], body))
        created = post([b for _, b in to_insert], representation=True)
        id_map.update(zip_new_ids(table, to_insert, created, spec["nat"], execute))
        stat["inserted"] = len(to_insert)

        remapped = 0
        for row in all_src:
            old_ref = row.get("superseded_by")
            if not old_ref:
                continue
            new_id, new_ref = id_map.get(row["id"]), id_map.get(old_ref)
            if new_id is None or new_ref is None:
                continue
            remapped += 1
            if execute:
                new.rest("PATCH", table, params={"id": f"eq.{new_id}"},
                         rows={"superseded_by": new_ref},
                         headers={"Prefer": "return=minimal"})
        stat["remapped_refs"] = remapped
        id_maps[table] = id_map
        stat["target_after"] = new.count(table, scope) if (model_id and execute) else tgt_before
        return stat

    # ---- append-only: dedup podľa prirodzeného kľúča -----------------------
    existing_params = {"model_id": f"eq.{model_id}"} if model_id else None
    if existing_params and delta_from:
        existing_params[spec["ts"]] = f"gte.{delta_from}"
    existing = new.fetch_all(table, params=existing_params) if model_id else []
    seen = {natural_key(r, spec["nat"]) for r in existing}
    payload = []
    for row in src_rows:
        key = natural_key(row, spec["nat"])
        if key in seen:
            stat["skipped"] += 1
            continue
        seen.add(key)
        payload.append({**strip_cols(row, allowed), "model_id": model_id})
    post(payload)
    stat["inserted"] = len(payload)
    stat["target_after"] = new.count(table, scope) if (model_id and execute) else tgt_before
    return stat


# ---------------------------------------------------------------------------
# kontrolné vzorky
# ---------------------------------------------------------------------------

def sample_checks(old: Supa, new: Supa, model_id: str) -> list[str]:
    out: list[str] = []
    users = old.fetch_all("dm_users", select="tg_id,msg_count", order="msg_count.desc")
    if users:
        tg_id = users[0]["tg_id"]
        def last(client: Supa, params: dict) -> dict | None:
            _, rows = client.rest("GET", "dm_messages", params={
                "select": "role,content,created_at", "order": "created_at.desc,id.desc",
                "limit": 1, **params})
            return (rows or [None])[0]
        src = last(old, {"tg_id": f"eq.{tg_id}"})
        tgt = last(new, {"tg_id": f"eq.{tg_id}", "model_id": f"eq.{model_id}"})
        same = bool(src and tgt and src["content"] == tgt["content"]
                    and src["created_at"] == tgt["created_at"] and src["role"] == tgt["role"])
        out.append(f"posledná správa najaktívnejšieho usera ({tg_id}): "
                   f"{'ZHODA' if same else 'NEZHODA'} — {(src or {}).get('created_at')} "
                   f"„{((src or {}).get('content') or '')[:60]}“")
    else:
        out.append("dm_users prázdne — vzorka správy preskočená")

    sends = old.fetch_all("photo_sends", order="sent_at.desc")
    if sends:
        photo_id = sends[0]["photo_id"]
        src_n = sum(1 for s in sends if s["photo_id"] == photo_id)
        src_photo = old.fetch_all("photos", params={"id": f"eq.{photo_id}"})
        url_tail = src_photo[0]["url"].rsplit("/", 1)[-1] if src_photo else ""
        tgt_photos = new.fetch_all("photos", select="id,url",
                                   params={"model_id": f"eq.{model_id}"})
        match = [p for p in tgt_photos if p["url"].rsplit("/", 1)[-1] == url_tail]
        tgt_n = (new.count("photo_sends", {"model_id": f"eq.{model_id}",
                                           "photo_id": f"eq.{match[0]['id']}"}) if match else -1)
        out.append(f"photo_sends pre fotku …/{url_tail[:32]}: zdroj {src_n} / cieľ {tgt_n} "
                   f"— {'ZHODA' if src_n == tgt_n else 'NEZHODA'}")
    else:
        out.append("photo_sends prázdne — vzorka preskočená")
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Migrácia starej modelky do telepipe (paused).")
    ap.add_argument("--source-schema", required=True, choices=sorted(OLD_ENV_FILES))
    ap.add_argument("--name", required=True, help="Meno modelky v telepipe (Simona / Mio)")
    ap.add_argument("--execute", action="store_true", help="Reálne zapíše (inak DRY-RUN)")
    ap.add_argument("--delta", action="store_true",
                    help="Doťahuje len novšie riadky append-only tabuliek (cutover)")
    ap.add_argument("--only-fanvue", action="store_true",
                    help="Len fv_* tabuľky; riadok models a Telegram creds nechá tak "
                         "(preto nevyžaduje status=paused)")
    args = ap.parse_args()

    schema = args.source_schema
    old_env = load_env(OLD_ENV_FILES[schema])
    new_env = load_env(ROOT / ".env")
    if old_env["SUPABASE_URL"].rstrip("/") == new_env["SUPABASE_URL"].rstrip("/"):
        raise SystemExit("STOP: zdroj a cieľ sú ten istý projekt.")
    if old_env.get("SUPABASE_SCHEMA") != schema:
        raise SystemExit(f"STOP: {OLD_ENV_FILES[schema]} má SUPABASE_SCHEMA="
                         f"{old_env.get('SUPABASE_SCHEMA')!r}, čakal som {schema!r}.")

    old = Supa(old_env["SUPABASE_URL"], old_env["SUPABASE_SERVICE_KEY"],
               schema=schema, read_only=True, label=f"OLD/{schema}")
    new = Supa(new_env["SUPABASE_URL"], new_env["SUPABASE_SERVICE_KEY"], label="TELEPIPE")

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"\n=== migrate_model {schema} → '{args.name}' [{mode}"
          f"{', DELTA' if args.delta else ''}] ===")
    print(f"  zdroj (read-only): {old.base}  schéma {schema}")
    print(f"  cieľ:              {new.base}")

    _, accounts = new.rest("GET", "accounts", params={
        "select": "id,email", "email": f"eq.{OWNER_EMAIL}"})
    if not accounts:
        raise SystemExit(f"STOP: účet {OWNER_EMAIL} v telepipe neexistuje.")
    account_id = accounts[0]["id"]
    print(f"  účet:              {account_id} ({OWNER_EMAIL})")

    target_cols = new.openapi_columns()
    model_id, _ = find_or_create_model(new, schema, args.name, old_env,
                                       new_env["ENCRYPTION_KEY"], account_id, args.execute,
                                       touch_model=not args.only_fanvue)
    storage = Storage(old, new, model_id, args.execute)
    id_maps: dict[str, dict[int, int]] = {}

    tables = [t for t in TABLES if t["name"].startswith("fv_")] if args.only_fanvue else TABLES
    stats = []
    for spec in tables:
        stat = migrate_table(spec, old, new, model_id, target_cols, storage,
                             id_maps, args.execute, args.delta)
        stats.append(stat)
        print(f"  {stat['table']:<13} zdroj {stat['source']:>5} | cieľ pred "
              f"{stat['target_before']:>5} → po {stat.get('target_after', '?'):>5} | "
              f"ins {stat['inserted']:>4} upd {stat['updated']:>4} skip {stat['skipped']:>4}"
              + (f" | remap {stat['remapped_refs']}" if stat.get("remapped_refs") else "")
              + (f" | DROPPED {stat['dropped_cols']}" if stat["dropped_cols"] else ""))

    print(f"\n  storage: skopírované {storage.copied}, už existujúce {storage.reused}, "
          f"externé (nechané) {storage.external}"
          + (f", na skopírovanie {storage.planned}" if not args.execute else ""))

    if args.execute and model_id and args.only_fanvue:
        for spec in tables:
            src = old.count(spec["name"])
            tgt = new.count(spec["name"], {"model_id": f"eq.{model_id}"})
            print(f"  vzorka: {spec['name']:<15} zdroj {src} / cieľ {tgt} — "
                  f"{'ZHODA' if tgt >= src else 'NEZHODA'}")
    elif args.execute and model_id:
        _, rows = new.rest("GET", "models", params={
            "select": "id,name,status,status_reason,migration_source",
            "id": f"eq.{model_id}"})
        row = rows[0]
        print(f"\n  model: {row['id']}  '{row['name']}'  status={row['status']} "
              f"({row['status_reason']})  source={row['migration_source']}")
        if row["status"] != "paused":
            raise SystemExit("STOP: model po importe NIE JE paused! Okamžite pauzni.")
        print("  ✓ status po importe overený: paused")
        for line in sample_checks(old, new, model_id):
            print(f"  vzorka: {line}")

    mismatched = [s for s in stats
                  if args.execute and s.get("target_after", 0) < s["source"]
                  and s["table"] not in ("photo_sends", "voice_sends")]
    if mismatched:
        print("\n  POZOR — cieľ má menej riadkov než zdroj: "
              + ", ".join(f"{s['table']} ({s.get('target_after')}<{s['source']})" for s in mismatched))

    print(f"\n  HTTP: OLD gets={old.gets} writes={old.writes} (read-only guard aktívny), "
          f"NEW gets={new.gets} writes={new.writes}")
    if old.writes:
        raise SystemExit("STOP: na starý projekt sa poslal zápis — to nemá nastať.")
    if not args.execute:
        print("\n  DRY-RUN — nič sa nezapísalo. Spusti znova s --execute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
