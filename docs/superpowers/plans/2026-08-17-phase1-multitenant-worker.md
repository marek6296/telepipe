# Telepipe fáza 1 — multi-tenant worker + databáza: implementačný plán

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-tenant Python worker (N Telethon userbotov v jednom procese, lease cez DB, kreditový ledger) nad novou Supabase DB `telepipe`, so správaním okopírovaným 1:1 z predlohy `/Users/marek/telegram`.

**Architecture:** Pool worker replík; každá si claimuje tenantov z tabuľky `models` (RPC `claim_models`, SKIP LOCKED, heartbeat 30 s, expirácia 90 s). Za tenanta beží `TenantRunner` (Telethon userbot + control bot + reconciler ako v predlohe). Dáta: jedna schéma `public`, všetky tabuľky s `model_id`. Kredity: check pred LLM volaním, po ňom RPC `record_usage` (2× Atlas cena).

**Tech Stack:** Python 3.11 · Telethon · httpx · Supabase (REST + RPC) · cryptography (AES-GCM) · pytest + pytest-asyncio · Railway (nixpacks, ffmpeg)

**KRITICKÉ PRAVIDLO:** Predloha `/Users/marek/telegram` je READ-ONLY. Nikdy do nej nezapisuj, nič tam nespúšťaj. Kopíruje sa z nej `cp`-čkom do `/Users/marek/telepipe/worker/`.

**Supabase:** projekt `telepipe`, ref `cggsyshfdjycfqrhtjld`. Migrácie aplikuj cez Supabase MCP `apply_migration` (project_id `cggsyshfdjycfqrhtjld`) a zároveň ulož SQL do `supabase/migrations/`. Kľúče sú v `/Users/marek/telepipe/.env` (gitignored).

---

## Prehľad súborov

```
worker/
├── requirements.txt          # T1
├── pytest.ini                # T1
├── nixpacks.toml             # T1 (ffmpeg — hlasovky)
├── railway.json              # T1
├── src/
│   ├── config.py             # T5 — globálny Config + TenantConfig
│   ├── crypto.py             # T4 — AES-GCM encrypt/decrypt
│   ├── transport.py          # T6 — SupabaseTransport (_get/_patch/_post/_rpc)
│   ├── registry.py           # T6 — claim/heartbeat/release/usage/pricing/models
│   ├── credits.py            # T8 — MeteredLlm wrapper
│   ├── db.py                 # T7 — TenantDb (port z predlohy, model_id všade)
│   ├── llm.py                # T8 — port (nemení sa logika, vracia usage)
│   ├── runner.py             # T10 — TenantRunner + backoff
│   ├── main.py               # T11 — claim slučka, heartbeat, SIGTERM
│   └── <28 modulov>          # T9 — kopírované 1:1 (persona.py, memory.py, …)
└── tests/                    # zrkadlí predlohu + nové testy
supabase/migrations/
├── 001_core.sql              # T2 — accounts, models, usage_events, pricing, RPC
└── 002_tenant_tables.sql     # T3 — 16 tabuliek z tgai s model_id
```

Moduly kopírované 1:1 v T9 (menia len import `db`→typ `TenantDb`, inak nič):
`persona.py memory.py humanize.py funnel.py judge.py den.py facts.py topics.py
recall.py similar.py taper.py gags.py weather.py speech.py livevoice.py eleven.py
voices.py photos.py limity.py outreach.py fanmatch.py checkout.py behavior.py
fvflow.py fvmedia.py fvvoice.py fanvue_api.py fanvue_agent.py` (fanvue_* sa
prenesú, aktivujú sa až vo fáze 3 — main ich nespúšťa).
`userbot.py control_bot.py` sa portujú v T12 (viac zásahov — cfg/notify wiring).

---

### Task 1: Scaffold worker projektu

**Files:**
- Create: `worker/requirements.txt`, `worker/pytest.ini`, `worker/nixpacks.toml`, `worker/railway.json`, `worker/src/__init__.py`, `worker/tests/__init__.py`, `worker/tests/conftest.py`

- [ ] **Step 1: Vytvor súbory**

`worker/requirements.txt` — obsah predlohy (`cat /Users/marek/telegram/requirements.txt`) + `cryptography>=42`:
```
telethon~=1.36
httpx~=0.27
python-dotenv~=1.0
cryptography>=42
```
(Over skutočný obsah predlohy a zachovaj jej verzie; `cryptography` pridaj.)

`worker/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```
(Skopíruj z predlohy `pytest.ini` a uprav `testpaths` ak treba; pridaj `pytest`, `pytest-asyncio` do requirements ak ich predloha inštalovala globálne.)

`worker/nixpacks.toml` — skopíruj `/Users/marek/telegram/nixpacks.toml` (ffmpeg).

`worker/railway.json` — ako predloha, startCommand `python src/main.py`.

`worker/tests/conftest.py` — zatiaľ prázdny (naplní T7).

- [ ] **Step 2: Vytvor venv a over pytest**

```bash
cd /Users/marek/telepipe/worker && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest pytest-asyncio
.venv/bin/pytest --collect-only
```
Expected: „no tests ran" (0 errors).

- [ ] **Step 3: Commit**
```bash
git add worker && git commit -m "feat: worker scaffold"
```

---

### Task 2: Migrácia 001 — core tabuľky + RPC

**Files:**
- Create: `supabase/migrations/001_core.sql`

- [ ] **Step 1: Napíš SQL**

```sql
-- Telepipe core: účty, modely (tenanti), ledger, cenník, lease RPC.
create extension if not exists pgcrypto;

create table accounts (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  credit_balance_usd numeric not null default 0,
  created_at timestamptz not null default now()
);

create table models (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  name text not null default '',
  status text not null default 'draft'
    check (status in ('draft','active','paused','error','disabled')),
  status_reason text not null default '',
  claimed_by text,
  heartbeat_at timestamptz,
  tg_api_id int,
  tg_api_hash text not null default '',
  tg_session_enc text not null default '',
  control_bot_token_enc text not null default '',
  owner_chat_id bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index models_claim_idx on models (status, claimed_by, heartbeat_at);

create table usage_events (
  id bigint generated always as identity primary key,
  model_id uuid not null references models(id) on delete cascade,
  account_id uuid not null references accounts(id) on delete cascade,
  kind text not null check (kind in ('chat','summary','vision','audio','voice')),
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  unit_count int not null default 0,
  atlas_cost_usd numeric not null,
  charged_usd numeric not null,
  created_at timestamptz not null default now()
);
create index usage_events_model_time_idx on usage_events (model_id, created_at desc);
create index usage_events_account_time_idx on usage_events (account_id, created_at desc);

create table pricing (
  model_slug text primary key,
  input_usd_per_mtok numeric not null default 0,
  output_usd_per_mtok numeric not null default 0,
  multiplier numeric not null default 2.0
);
insert into pricing (model_slug, input_usd_per_mtok, output_usd_per_mtok) values ('_default', 0, 0);

-- Lease: atomicky si replika zoberie voľných/opustených tenantov.
create or replace function claim_models(p_replica text, p_capacity int)
returns setof models language sql security definer as $$
  update models m set claimed_by = p_replica, heartbeat_at = now()
  where m.id in (
    select id from models
    where status = 'active'
      and (claimed_by is null or heartbeat_at < now() - interval '90 seconds')
      and (claimed_by is distinct from p_replica)
    order by created_at
    for update skip locked
    limit p_capacity
  )
  returning m.*;
$$;

create or replace function heartbeat_models(p_replica text)
returns void language sql security definer as $$
  update models set heartbeat_at = now() where claimed_by = p_replica;
$$;

create or replace function release_models(p_replica text)
returns void language sql security definer as $$
  update models set claimed_by = null where claimed_by = p_replica;
$$;

create or replace function release_model(p_model uuid)
returns void language sql security definer as $$
  update models set claimed_by = null where id = p_model;
$$;

-- Ledger + odpočet kreditu v jednej transakcii.
create or replace function record_usage(
  p_model uuid, p_kind text,
  p_input_tokens int, p_output_tokens int, p_unit_count int,
  p_atlas_cost_usd numeric, p_charged_usd numeric
) returns numeric language plpgsql security definer as $$
declare v_account uuid; v_balance numeric;
begin
  select account_id into v_account from models where id = p_model;
  insert into usage_events (model_id, account_id, kind, input_tokens,
    output_tokens, unit_count, atlas_cost_usd, charged_usd)
  values (p_model, v_account, p_kind, p_input_tokens, p_output_tokens,
    p_unit_count, p_atlas_cost_usd, p_charged_usd);
  update accounts set credit_balance_usd = credit_balance_usd - p_charged_usd
  where id = v_account
  returning credit_balance_usd into v_balance;
  return v_balance;
end;
$$;

create or replace function credit_balance(p_model uuid)
returns numeric language sql security definer as $$
  select a.credit_balance_usd from accounts a
  join models m on m.account_id = a.id where m.id = p_model;
$$;

alter table accounts enable row level security;
alter table models enable row level security;
alter table usage_events enable row level security;
alter table pricing enable row level security;
```

- [ ] **Step 2: Aplikuj cez Supabase MCP**

`apply_migration(project_id="cggsyshfdjycfqrhtjld", name="001_core", query=<SQL>)`.
Over: `list_tables(schemas=["public"])` → accounts, models, usage_events, pricing.

- [ ] **Step 3: Smoke test RPC v SQL editore (execute_sql)**

```sql
insert into accounts (email, credit_balance_usd) values ('test@test.dev', 10) returning id;
-- s vráteným id:
insert into models (account_id, status) values ('<id>', 'active') returning id;
select claim_models('replika-a', 25);          -- vráti 1 riadok
select claim_models('replika-b', 25);          -- vráti 0 riadkov (claimnuté, heartbeat čerstvý)
select record_usage('<model_id>', 'chat', 100, 50, 0, 0.01, 0.02);  -- vráti 9.98
delete from accounts where email = 'test@test.dev';
```

- [ ] **Step 4: Commit** — `git add supabase && git commit -m "feat: core schema + lease/usage RPC"`

---

### Task 3: Migrácia 002 — 16 tenant tabuliek z predlohy

**Files:**
- Create: `supabase/migrations/002_tenant_tables.sql`

- [ ] **Step 1: Vygeneruj SQL z predlohy**

Zdroj: `/Users/marek/telegram/supabase/schema.sql`. Pre KAŽDÚ zo 16 tabuliek
(persona, behavior, settings, dm_users, dm_messages, facts, photos, photo_sends,
voices, voice_sends, episodes, open_loops, self_claims, judge_log, voice_clips,
voice_jobs) platí mechanická transformácia:

1. `tgai.` → `public.` (t. j. bez prefixu)
2. Pridaj PRVÝ stĺpec `model_id uuid not null references models(id) on delete cascade`
3. PK transformácie:
   - `persona`, `behavior`, `settings`: zruš `id int primary key default 1`,
     PK je `model_id`
   - `dm_users`: PK `(model_id, tg_id)`
   - `dm_messages`, `facts`, `episodes`, `open_loops`, `self_claims`, `judge_log`,
     `voice_clips`, `voice_jobs`, `photos`, `voices`: nechaj `id bigint identity` PK,
     ale FK na `dm_users` zmeň z `references tgai.dm_users(tg_id)` na
     `foreign key (model_id, tg_id) references dm_users(model_id, tg_id) on delete cascade`
   - `photo_sends`: PK `(model_id, photo_id, tg_id)`; `voice_sends`: PK `(model_id, voice_id, tg_id)`
4. Každý index z predlohy: pridaj `model_id` ako prvý stĺpec, prefixuj názov nezmenený
5. VŠETKY defaulty hodnôt zachovaj identické (voice_chance 0.18, voice_tempo 1.12, …)
6. `alter table <t> enable row level security;` pre všetky
7. Partial indexy (napr. `voice_jobs_pending_idx … where status='pending'`) zachovaj, pridaj model_id

Postupuj tabuľku po tabuľke proti zdrojovému súboru — neskracuj, nevynechávaj stĺpce.

- [ ] **Step 2: Aplikuj cez MCP + over**

`apply_migration(... name="002_tenant_tables")`. Over `list_tables` → 20 tabuliek spolu.
Porovnaj počet stĺpcov každej tabuľky proti predlohe (`grep -c` v schema.sql vs
`list_tables verbose`) — musí sedieť +1 (model_id), pri persona/behavior/settings ±0 (id von, model_id dnu).

- [ ] **Step 3: Storage buckets**

Cez `execute_sql`: `insert into storage.buckets (id, name, public) values ('voices','voices',true), ('photos','photos',true) on conflict do nothing;`

- [ ] **Step 4: Commit** — `git commit -m "feat: tenant tables ported from template schema"`

---

### Task 4: crypto.py — AES-GCM

**Files:**
- Create: `worker/src/crypto.py`, `worker/tests/test_crypto.py`

- [ ] **Step 1: Failing test**

```python
"""Šifrovanie session stringov — roundtrip, zlý kľúč, formát."""
import pytest
from crypto import encrypt, decrypt, CryptoError

KEY = "u" * 43 + "="  # 32 bajtov base64 — testovací

def test_roundtrip():
    token = encrypt("1BVtsOH4Bu...session", KEY)
    assert decrypt(token, KEY) == "1BVtsOH4Bu...session"

def test_token_format_three_parts():
    assert encrypt("x", KEY).count(":") == 2

def test_wrong_key_fails_cleanly():
    token = encrypt("secret", KEY)
    with pytest.raises(CryptoError):
        decrypt(token, "v" * 43 + "=")

def test_tampered_ciphertext_fails():
    token = encrypt("secret", KEY)
    parts = token.split(":")
    parts[1] = parts[1][:-4] + "AAAA"
    with pytest.raises(CryptoError):
        decrypt(":".join(parts), KEY)

def test_empty_plaintext_roundtrip():
    assert decrypt(encrypt("", KEY), KEY) == ""
```

- [ ] **Step 2: Run** — `.venv/bin/pytest tests/test_crypto.py -v` → FAIL (no module crypto)

- [ ] **Step 3: Implementácia**

```python
"""AES-256-GCM pre TG session a bot tokeny.

Kľúč žije len v env (ENCRYPTION_KEY, base64 32 bajtov) — únik databázy sám
o sebe session nevydá. Formát tokenu: base64(nonce):base64(ciphertext):base64(tag).
"""
from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(RuntimeError):
    pass


def _key_bytes(key_b64: str) -> bytes:
    try:
        raw = base64.b64decode(key_b64, validate=True)
    except Exception as exc:
        raise CryptoError("ENCRYPTION_KEY nie je platný base64") from exc
    if len(raw) != 32:
        raise CryptoError("ENCRYPTION_KEY musí byť 32 bajtov (AES-256)")
    return raw


def encrypt(plaintext: str, key_b64: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key_bytes(key_b64)).encrypt(nonce, plaintext.encode(), None)
    ct, tag = sealed[:-16], sealed[-16:]
    b64 = lambda b: base64.b64encode(b).decode()
    return f"{b64(nonce)}:{b64(ct)}:{b64(tag)}"


def decrypt(token: str, key_b64: str) -> str:
    try:
        n_b64, ct_b64, tag_b64 = token.split(":")
        nonce, ct, tag = (base64.b64decode(x) for x in (n_b64, ct_b64, tag_b64))
    except Exception as exc:
        raise CryptoError("Poškodený šifrovaný token") from exc
    try:
        return AESGCM(_key_bytes(key_b64)).decrypt(nonce, ct + tag, None).decode()
    except InvalidTag as exc:
        raise CryptoError("Dešifrovanie zlyhalo — zlý kľúč alebo poškodené dáta") from exc
```

- [ ] **Step 4: Run** — všetkých 5 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: AES-GCM crypto for session storage"`

---

### Task 5: config.py — globálny Config + TenantConfig

**Files:**
- Create: `worker/src/config.py`, `worker/tests/test_config.py`
- Referencia: `/Users/marek/telegram/src/config.py` (prečítaj celý)

- [ ] **Step 1: Failing testy**

```python
"""Global config z env; TenantConfig z riadku models + dešifrovanie."""
import pytest
from config import Config, TenantConfig
from crypto import encrypt

KEY = "u" * 43 + "="

ENV = {
    "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "sk",
    "LLM_API_KEY": "ak", "ENCRYPTION_KEY": KEY,
}

def test_config_from_env(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    assert cfg.supabase_url == "https://x.supabase.co"
    assert cfg.max_tenants == 25          # default
    assert cfg.replica_name              # nikdy prázdne

def test_config_missing_required(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        Config.from_env()

def test_tenant_config_decrypts_session(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    cfg = Config.from_env()
    row = {
        "id": "m-1", "account_id": "a-1", "name": "Lola",
        "tg_api_id": 12345, "tg_api_hash": "hash",
        "tg_session_enc": encrypt("SESSION", KEY),
        "control_bot_token_enc": encrypt("BOT:token", KEY),
        "owner_chat_id": 777,
    }
    t = TenantConfig.from_row(row, cfg)
    assert t.tg_session == "SESSION"
    assert t.control_bot_token == "BOT:token"
    assert t.model_id == "m-1"
    assert t.link_min_messages == 6       # zdedené globálne defaulty predlohy
```

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implementácia**

Vzor je `Config.from_env()` predlohy — zachovaj z nej VŠETKY LLM/voice/správanie
polia a defaulty (llm_base_url, model, summary_model, reasoning_effort,
vision_model, audio_model, voice_api_*, context_messages=12, summary_every=15,
skip_contacts, link_min_messages=6, link_cooldown_hours=48, link_max_pushes=3).
Odstráň per-modelkové: TG_API_ID/HASH/SESSION, CONTROL_BOT_TOKEN, OWNER_CHAT_ID,
SUPABASE_SCHEMA. Pridaj:

```python
    encryption_key: str          # _req("ENCRYPTION_KEY")
    max_tenants: int             # _int("MAX_TENANTS", 25)
    replica_name: str            # os.getenv("RAILWAY_REPLICA_ID") or f"{socket.gethostname()}-{os.getpid()}"
    claim_interval_s: int        # _int("CLAIM_INTERVAL_S", 30)
    fallback_price_per_mtok: float  # float(os.getenv("FALLBACK_PRICE_PER_MTOK", "5.0"))
```

`TenantConfig` je dataclass s per-tenant poľami (model_id, account_id, name,
tg_api_id, tg_api_hash, tg_session, control_bot_token, owner_chat_id,
owner_as_client=False) + skopírované behaviorálne defaulty z globálneho Config
(context_messages, summary_every, link_*, skip_contacts, contact_exceptions,
voice_only_ids=(), …), aby moduly predlohy, ktoré čítajú `cfg.link_min_messages`
a pod., dostali JEDEN objekt s rovnakými atribútmi ako doteraz. Konštruktor:

```python
    @classmethod
    def from_row(cls, row: dict, g: "Config") -> "TenantConfig":
        return cls(
            model_id=row["id"], account_id=row["account_id"], name=row.get("name", ""),
            tg_api_id=int(row["tg_api_id"]), tg_api_hash=row["tg_api_hash"],
            tg_session=decrypt(row["tg_session_enc"], g.encryption_key),
            control_bot_token=decrypt(row["control_bot_token_enc"], g.encryption_key),
            owner_chat_id=int(row["owner_chat_id"] or 0),
            # …behaviorálne polia = getattr(g, pole)
        )
```

DÔLEŽITÉ: prejdi `grep -o 'cfg\.[a-z_]*' /Users/marek/telegram/src/*.py | sort -u`
a zabezpeč, že KAŽDÝ atribút, ktorý moduly predlohy čítajú, existuje na
TenantConfig (hoci len ako zdedený globálny default). Inak port v T9/T12 padne
na AttributeError.

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: global + tenant config"`

---

### Task 6: transport.py + registry.py

**Files:**
- Create: `worker/src/transport.py`, `worker/src/registry.py`, `worker/tests/test_registry.py`
- Referencia: `/Users/marek/telegram/src/db.py:50-86` (konštruktor a _get/_patch/_post)

- [ ] **Step 1: Failing testy** (httpx MockTransport)

```python
"""Registry — claim/heartbeat/release/usage cez Supabase RPC."""
import httpx, json, pytest
from transport import SupabaseTransport
from registry import Registry

def _mock(handler):
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")
    return t

async def test_claim_calls_rpc():
    seen = {}
    def handler(req):
        seen["url"] = str(req.url); seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=[{"id": "m-1", "account_id": "a-1"}])
    reg = Registry(_mock(handler))
    rows = await reg.claim("replika-a", 25)
    assert "/rpc/claim_models" in seen["url"]
    assert seen["body"] == {"p_replica": "replika-a", "p_capacity": 25}
    assert rows[0]["id"] == "m-1"

async def test_record_usage_returns_balance():
    def handler(req):
        return httpx.Response(200, json=9.98)
    reg = Registry(_mock(handler))
    balance = await reg.record_usage("m-1", "chat", 100, 50, 0, 0.01, 0.02)
    assert balance == 9.98

async def test_pricing_cached():
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=[
            {"model_slug": "_default", "input_usd_per_mtok": 0, "output_usd_per_mtok": 0, "multiplier": 2.0},
            {"model_slug": "x-ai/grok-4.5", "input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0, "multiplier": 2.0},
        ])
    reg = Registry(_mock(handler))
    p1 = await reg.pricing("x-ai/grok-4.5")
    p2 = await reg.pricing("x-ai/grok-4.5")
    assert p1["input_usd_per_mtok"] == 3.0 and calls["n"] == 1  # cache 5 min

async def test_set_model_status():
    seen = {}
    def handler(req):
        seen["method"] = req.method; seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(204)
    reg = Registry(_mock(handler))
    await reg.set_status("m-1", "paused", "out_of_credits")
    assert seen["method"] == "PATCH" and "models" in seen["url"]
    assert seen["body"] == {"status": "paused", "status_reason": "out_of_credits"}
```

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implementácia**

`transport.py` — vytiahni z predlohy db.py konštruktor + `_get/_patch/_post`
(zachovaj retry logiku a hlavičky, schema headers vyhoď — všetko je public)
a pridaj `_rpc`:

```python
class SupabaseTransport:
    def __init__(self, url: str, service_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{url}/rest/v1",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    # _get, _patch, _post: prenes z predlohy vrátane error handlingu
    async def _rpc(self, fn: str, args: dict) -> Any:
        r = await self._client.post(f"/rpc/{fn}", json=args)
        r.raise_for_status()
        return r.json() if r.content else None
```

`registry.py`:

```python
class Registry:
    """Globálne operácie — lease, ledger, cenník, stav modelov."""
    def __init__(self, transport: SupabaseTransport) -> None:
        self._t = transport
        self._pricing_cache: dict | None = None
        self._pricing_at = 0.0

    async def claim(self, replica: str, capacity: int) -> list[dict]:
        return await self._t._rpc("claim_models", {"p_replica": replica, "p_capacity": capacity}) or []

    async def heartbeat(self, replica: str) -> None:
        await self._t._rpc("heartbeat_models", {"p_replica": replica})

    async def release_all(self, replica: str) -> None:
        await self._t._rpc("release_models", {"p_replica": replica})

    async def release(self, model_id: str) -> None:
        await self._t._rpc("release_model", {"p_model": model_id})

    async def model_row(self, model_id: str) -> dict | None:
        rows = await self._t._get("models", {"id": f"eq.{model_id}", "limit": "1"})
        return rows[0] if rows else None

    async def set_status(self, model_id: str, status: str, reason: str = "") -> None:
        await self._t._patch("models", {"id": f"eq.{model_id}"},
                             {"status": status, "status_reason": reason})

    async def credit_balance(self, model_id: str) -> float:
        return float(await self._t._rpc("credit_balance", {"p_model": model_id}) or 0)

    async def record_usage(self, model_id, kind, in_tok, out_tok, units,
                           atlas_cost, charged) -> float:
        return float(await self._t._rpc("record_usage", {
            "p_model": model_id, "p_kind": kind,
            "p_input_tokens": in_tok, "p_output_tokens": out_tok,
            "p_unit_count": units, "p_atlas_cost_usd": atlas_cost,
            "p_charged_usd": charged}))

    async def pricing(self, slug: str) -> dict:
        import time
        if self._pricing_cache is None or time.monotonic() - self._pricing_at > 300:
            rows = await self._t._get("pricing", {})
            self._pricing_cache = {r["model_slug"]: r for r in rows}
            self._pricing_at = time.monotonic()
        return self._pricing_cache.get(slug) or self._pricing_cache.get("_default") or {}
```

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: supabase transport + registry (lease, ledger)"`

---

### Task 7: db.py — port na TenantDb

**Files:**
- Create: `worker/src/db.py`, `worker/tests/test_tenant_db.py`
- Modify: `worker/tests/conftest.py`
- Referencia: `/Users/marek/telegram/src/db.py` (celý — 656 riadkov, ~60 metód)

- [ ] **Step 1: Napíš izolačné testy**

```python
"""TenantDb — každý dotaz nesie model_id; izolácia tenantov."""
import httpx, json
from transport import SupabaseTransport
from db import TenantDb

def _capture(store):
    def handler(req):
        store.append({"method": req.method, "url": str(req.url),
                      "body": json.loads(req.content) if req.content else None})
        return httpx.Response(200, json=[])
    t = SupabaseTransport("https://x.supabase.co", "sk")
    t._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  base_url="https://x.supabase.co/rest/v1")
    return t

async def test_every_get_filters_by_model_id():
    seen = []
    db = TenantDb(_capture(seen), "model-A")
    await db.get_persona()
    await db.recent_messages(42, limit=10)
    await db.photo_library()
    for call in seen:
        assert "model_id=eq.model-A" in call["url"], call["url"]

async def test_writes_carry_model_id():
    seen = []
    db = TenantDb(_capture(seen), "model-A")
    await db.add_message(42, "user", "ahoj")
    body = seen[-1]["body"]
    assert body["model_id"] == "model-A" and body["tg_id"] == 42

async def test_two_tenants_never_share_transport_state():
    seen = []
    t = _capture(seen)
    a, b = TenantDb(t, "model-A"), TenantDb(t, "model-B")
    await a.get_behavior(); await b.get_behavior()
    assert "model_id=eq.model-A" in seen[0]["url"]
    assert "model_id=eq.model-B" in seen[1]["url"]
```

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Port**

Skopíruj `/Users/marek/telegram/src/db.py` do `worker/src/db.py` a aplikuj:

1. `class Db:` → `class TenantDb:`; konštruktor
   `def __init__(self, transport: SupabaseTransport, model_id: str)` —
   `self._t = transport; self.model_id = model_id`. `_get/_patch/_post` deleguj
   na transport. `close()` odstráň (transport vlastní main).
2. KAŽDÉ čítanie tabuľky: pridaj do params `"model_id": f"eq.{self.model_id}"`.
3. KAŽDÝ insert/upsert: pridaj do body `"model_id": self.model_id`.
   Pri upsertoch over `on_conflict` — `persona/behavior/settings` majú teraz
   conflict target `model_id`; `dm_users` `model_id,tg_id`; `photo_sends`
   `model_id,photo_id,tg_id`; `voice_sends` `model_id,voice_id,tg_id`.
4. KAŽDÝ update/delete s `tg_id=eq.` filtrom: pridaj aj model_id filter.
5. Voice storage cesty (`db.py:569,577` v predlohe): do path v buckete vlož
   prefix `{self.model_id}/` aby sa súbory tenantov neprepisovali.
6. Zachovaj názvy metód, signatúry, návratové typy a KOMENTÁRE — moduly
   z T9 ich volajú bez zmeny.

Kontrola úplnosti (spusti a prejdi ručne):
```bash
grep -n '_get\|_patch\|_post' worker/src/db.py | grep -v 'model_id' 
```
Expected: 0 riadkov s tabuľkovým dotazom bez model_id (výnimka: žiadna).

- [ ] **Step 4: conftest.py** — port fixtures z predlohy `tests/conftest.py`;
  fixture `db` vracia `TenantDb(mock_transport, "test-model")`.

- [ ] **Step 5: Run** → PASS
- [ ] **Step 6: Commit** — `git commit -m "feat: TenantDb — model_id everywhere"`

---

### Task 8: llm.py port + credits.py (MeteredLlm)

**Files:**
- Create: `worker/src/llm.py` (port), `worker/src/credits.py`, `worker/tests/test_credits.py`
- Referencia: `/Users/marek/telegram/src/llm.py` (celý)

- [ ] **Step 1: Port llm.py**

Skopíruj 1:1. JEDINÁ zmena: `_chat()` nech okrem textu vráti aj usage —
zmeň návrat na `(text, usage_dict)` kde `usage_dict = {"input": resp["usage"]["prompt_tokens"], "output": resp["usage"]["completion_tokens"]}`
(over presné kľúče v predlohe — Atlas je OpenAI-kompatibilný). Verejné metódy
(`reply`, `structured`, `summarize`, `transcribe_voice`, `describe_image`)
nech vracajú to čo doteraz A usage si Llm odloží do `self.last_usage`
(prepíše sa každým volaním). Tak sa nemení signatúra pre volajúce moduly.

- [ ] **Step 2: Failing testy pre MeteredLlm**

```python
"""Kreditový wrapper — check pred volaním, zápis po ňom, pauza pri nule."""
import pytest
from credits import MeteredLlm, OutOfCredits

class FakeLlm:
    def __init__(self):
        self.last_usage = {"input": 1000, "output": 500}
        self.calls = 0
    async def reply(self, *a, **kw):
        self.calls += 1
        return "ahoj"

class FakeRegistry:
    def __init__(self, balance=10.0):
        self._balance = balance
        self.usage_rows = []
        self.status_calls = []
    async def credit_balance(self, model_id): return self._balance
    async def pricing(self, slug):
        return {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0, "multiplier": 2.0}
    async def record_usage(self, model_id, kind, i, o, u, atlas, charged):
        self.usage_rows.append((kind, i, o, atlas, charged))
        self._balance -= charged
        return self._balance
    async def set_status(self, model_id, status, reason=""):
        self.status_calls.append((status, reason))

async def test_charges_double_atlas_cost():
    reg = FakeRegistry(); llm = FakeLlm()
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="x-ai/grok-4.5")
    await m.reply("sys", [])
    kind, i, o, atlas, charged = reg.usage_rows[0]
    # 1000/1e6*3.0 + 500/1e6*15.0 = 0.003 + 0.0075 = 0.0105
    assert atlas == pytest.approx(0.0105)
    assert charged == pytest.approx(0.021)     # ×2
    assert kind == "chat" and i == 1000 and o == 500

async def test_zero_balance_blocks_and_pauses():
    reg = FakeRegistry(balance=0.0); llm = FakeLlm()
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s")
    with pytest.raises(OutOfCredits):
        await m.reply("sys", [])
    assert llm.calls == 0                       # LLM sa vôbec nezavolalo
    assert reg.status_calls == [("paused", "out_of_credits")]

async def test_summarize_uses_summary_kind():
    reg = FakeRegistry(); llm = FakeLlm()
    llm.summarize = llm.reply
    m = MeteredLlm(llm, reg, model_id="m-1", model_slug="s")
    await m.summarize("facts", "transcript")
    assert reg.usage_rows[0][0] == "summary"

async def test_missing_pricing_uses_fallback():
    reg = FakeRegistry()
    async def no_price(slug): return {}
    reg.pricing = no_price
    m = MeteredLlm(FakeLlm(), reg, model_id="m-1", model_slug="s",
                   fallback_per_mtok=5.0)
    await m.reply("sys", [])
    _, _, _, atlas, charged = reg.usage_rows[0]
    assert atlas == pytest.approx(1500 / 1e6 * 5.0)
    assert charged == pytest.approx(2 * atlas)  # multiplier default 2 pri fallbacku
```

- [ ] **Step 3: Run** → FAIL

- [ ] **Step 4: Implementácia credits.py**

```python
"""Meranie a účtovanie LLM volaní.

MeteredLlm má rovnaké verejné metódy ako Llm — moduly predlohy nič nepoznajú.
Pred volaním kontrola zostatku (≤0 → OutOfCredits + pauza modelu), po volaní
zápis do ledgeru: atlas cena z cenníka, klientovi × multiplier.
"""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)

KIND_BY_METHOD = {"reply": "chat", "structured": "chat", "summarize": "summary",
                  "describe_image": "vision", "transcribe_voice": "audio"}


class OutOfCredits(RuntimeError):
    pass


class MeteredLlm:
    def __init__(self, llm, registry, model_id: str, model_slug: str,
                 fallback_per_mtok: float = 5.0) -> None:
        self._llm = llm
        self._reg = registry
        self._model_id = model_id
        self._slug = model_slug
        self._fallback = fallback_per_mtok
        self.last_usage = {}

    def __getattr__(self, name):          # metódy Llm, ktoré nemeriame (close…)
        return getattr(self._llm, name)

    async def _metered(self, method: str, *args, **kwargs):
        if await self._reg.credit_balance(self._model_id) <= 0:
            await self._reg.set_status(self._model_id, "paused", "out_of_credits")
            raise OutOfCredits(self._model_id)
        result = await getattr(self._llm, method)(*args, **kwargs)
        usage = getattr(self._llm, "last_usage", None) or {}
        i, o = int(usage.get("input", 0)), int(usage.get("output", 0))
        price = await self._reg.pricing(self._slug)
        if price.get("input_usd_per_mtok") or price.get("output_usd_per_mtok"):
            atlas = i / 1e6 * float(price["input_usd_per_mtok"]) \
                  + o / 1e6 * float(price["output_usd_per_mtok"])
        else:
            log.warning("Chýba cenník pre %s — fallback %.2f/Mtok", self._slug, self._fallback)
            atlas = (i + o) / 1e6 * self._fallback
        charged = atlas * float(price.get("multiplier", 2.0))
        try:
            await self._reg.record_usage(self._model_id, KIND_BY_METHOD[method],
                                         i, o, 0, round(atlas, 6), round(charged, 6))
        except Exception:
            log.exception("Zápis usage zlyhal — odpoveď ide ďalej, dorovná sa ďalším volaním")
        return result

    async def reply(self, *a, **kw): return await self._metered("reply", *a, **kw)
    async def structured(self, *a, **kw): return await self._metered("structured", *a, **kw)
    async def summarize(self, *a, **kw): return await self._metered("summarize", *a, **kw)
    async def describe_image(self, *a, **kw): return await self._metered("describe_image", *a, **kw)
    async def transcribe_voice(self, *a, **kw): return await self._metered("transcribe_voice", *a, **kw)
```

- [ ] **Step 5: Run** → PASS
- [ ] **Step 6: Commit** — `git commit -m "feat: llm port + credit metering"`

---

### Task 9: Kopírovanie 28 nezmenených modulov + ich testov

**Files:**
- Create: `worker/src/{persona,memory,humanize,funnel,judge,den,facts,topics,recall,similar,taper,gags,weather,speech,livevoice,eleven,voices,photos,limity,outreach,fanmatch,checkout,behavior,fvflow,fvmedia,fvvoice,fanvue_api,fanvue_agent}.py`
- Create: zodpovedajúce `worker/tests/test_*.py` z predlohy

- [ ] **Step 1: Skopíruj moduly**

```bash
cd /Users/marek/telepipe/worker/src
for f in persona memory humanize funnel judge den facts topics recall similar \
         taper gags weather speech livevoice eleven voices photos limity \
         outreach fanmatch checkout behavior fvflow fvmedia fvvoice \
         fanvue_api fanvue_agent; do
  cp "/Users/marek/telegram/src/$f.py" .
done
```
ŽIADNE úpravy obsahu — typy `Db` v anotáciách sú len anotácie; moduly dostanú
TenantDb, ktorý má identické metódy. Ak niektorý modul robí `from db import Db`,
zmeň na `from db import TenantDb as Db` (jediná povolená úprava — over grepom
`grep -l 'from db import' *.py`).

- [ ] **Step 2: Skopíruj testy predlohy**

```bash
cd /Users/marek/telepipe/worker/tests
for t in $(ls /Users/marek/telegram/tests/test_*.py); do cp "$t" .; done
```
Vynechaj (portujú sa neskôr / netýkajú sa): `test_session.py` (viaže sa na
predlohovú Config), inak ber všetko.

- [ ] **Step 3: Sprav testy zelené**

`.venv/bin/pytest -x -q`. Očakávané zlyhania a fixy (LEN v testoch/conftest,
nie v moduloch):
- fixtures vyrábajúce `Db(...)` → `TenantDb(transport, "test-model")`
- fixtures s `Config(...)` → `TenantConfig(...)` s rovnakými hodnotami
- monkeypatche na `db.<metóda>` fungujú bez zmeny (mená metód sa nemenili)
Ak test odhalí skutočný rozdiel v správaní modulu → STOP, nahlás; správanie
sa meniť NESMIE.

- [ ] **Step 4: Run všetko** — `.venv/bin/pytest -q` → PASS (rádovo 600+ testov)
- [ ] **Step 5: Commit** — `git commit -m "feat: port behaviour modules 1:1 from template"`

---

### Task 10: runner.py — TenantRunner

**Files:**
- Create: `worker/src/runner.py`, `worker/tests/test_runner.py`
- Referencia: `/Users/marek/telegram/src/main.py:40-139` (run() — wiring userbot/control/reconciler/sweeper)

- [ ] **Step 1: Failing testy**

```python
"""TenantRunner — životný cyklus, backoff, čistý stop."""
import asyncio, pytest
from runner import TenantRunner, BACKOFF_S

class FakeDeps:  # klienti/boti sa nahradia — testuje sa orchestrácia
    pass

async def test_backoff_progression():
    assert BACKOFF_S == [30, 60, 300, 900]

async def test_five_failures_sets_error(monkeypatch):
    calls = {"n": 0}; statuses = []
    class Reg:
        async def set_status(self, mid, s, r=""): statuses.append((s, r))
        async def release(self, mid): pass
    async def boom(self): calls["n"] += 1; raise RuntimeError("pád")
    monkeypatch.setattr(TenantRunner, "_run_once", boom)
    monkeypatch.setattr(TenantRunner, "_sleep", staticmethod(lambda s: asyncio.sleep(0)))
    r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=Reg(), transport=None)
    await r.run()
    assert calls["n"] == 5
    assert statuses[-1] == ("error", "crashed_repeatedly")

async def test_stop_cancels_cleanly(monkeypatch):
    started = asyncio.Event()
    async def forever(self): started.set(); await asyncio.sleep(3600)
    monkeypatch.setattr(TenantRunner, "_run_once", forever)
    class Reg:
        async def set_status(self, *a, **kw): pass
        async def release(self, mid): pass
    r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=Reg(), transport=None)
    task = asyncio.create_task(r.run())
    await started.wait()
    await r.stop()
    await asyncio.wait_for(task, 2)      # skončí bez výnimky

async def test_auth_revoked_no_retry(monkeypatch):
    from telethon.errors import AuthKeyUnregisteredError
    statuses = []
    class Reg:
        async def set_status(self, mid, s, r=""): statuses.append((s, r))
        async def release(self, mid): pass
    calls = {"n": 0}
    async def revoked(self):
        calls["n"] += 1
        raise AuthKeyUnregisteredError(request=None)
    monkeypatch.setattr(TenantRunner, "_run_once", revoked)
    r = TenantRunner(tenant_cfg=None, global_cfg=None, registry=Reg(), transport=None)
    await r.run()
    assert calls["n"] == 1               # žiadny retry
    assert statuses[-1] == ("error", "session_revoked")
```

Pozn.: `TenantRunner.__init__` musí zniesť None hodnoty (deps sa vyrábajú lenivo
v `_run_once`, nie v konštruktore) — presne kvôli testovateľnosti.

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implementácia**

```python
"""Jeden tenant = jeden runner. Pád jedného nezhodí ostatných.

_run_once obsahuje presne to, čo run() v predlohe main.py robí pre jednu
modelku: Telethon klient zo session, control bot (best effort — FloodWait
bota nesmie zhodiť userbota), reconciler, sweeper, voice_jobs.
"""
from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient
from telethon.errors import AuthKeyUnregisteredError
from telethon.sessions import StringSession

from credits import MeteredLlm, OutOfCredits

log = logging.getLogger(__name__)

BACKOFF_S = [30, 60, 300, 900]   # 5. pokus už nie je — status error
MAX_TRIES = 5


class TenantRunner:
    def __init__(self, tenant_cfg, global_cfg, registry, transport) -> None:
        self._cfg = tenant_cfg
        self._g = global_cfg
        self._reg = registry
        self._t = transport
        self._stopping = asyncio.Event()
        self._cleanup = []          # klienti/tasky na zatvorenie pri stope

    @staticmethod
    async def _sleep(seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def run(self) -> None:
        model_id = getattr(self._cfg, "model_id", "?")
        for attempt in range(MAX_TRIES):
            if self._stopping.is_set():
                break
            try:
                await self._run_once()
                break                                  # čistý koniec (stop)
            except asyncio.CancelledError:
                raise
            except AuthKeyUnregisteredError:
                log.warning("[%s] session odvolaná — bez retry", model_id)
                await self._reg.set_status(model_id, "error", "session_revoked")
                await self._reg.release(model_id)
                return
            except OutOfCredits:
                # MeteredLlm už model pauzol; runner len skončí.
                await self._reg.release(model_id)
                return
            except Exception:
                log.exception("[%s] runner spadol (pokus %d/%d)", model_id, attempt + 1, MAX_TRIES)
                if attempt + 1 < MAX_TRIES:
                    await self._sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
        else:
            await self._reg.set_status(model_id, "error", "crashed_repeatedly")
            await self._reg.release(model_id)

    async def stop(self) -> None:
        self._stopping.set()
        for item in self._cleanup:
            try:
                if isinstance(item, asyncio.Task):
                    item.cancel()
                else:
                    await item.disconnect()
            except Exception:       # noqa: BLE001 — stop musí prejsť vždy
                pass
        self._cleanup.clear()

    async def _run_once(self) -> None:
        # Wiring podľa predlohy main.py::run(), s TenantDb + MeteredLlm.
        from db import TenantDb
        from llm import Llm
        from control_bot import ControlBot
        from userbot import Reconciler, UserBot

        cfg = self._cfg
        db = TenantDb(self._t, cfg.model_id)
        raw_llm = Llm(self._g.llm_key, self._g.model, self._g.summary_model,
                      self._g.llm_base_url, self._g.reasoning_effort,
                      self._g.vision_model, self._g.audio_model)
        llm = MeteredLlm(raw_llm, self._reg, cfg.model_id, self._g.model,
                         self._g.fallback_price_per_mtok)

        user_client = TelegramClient(StringSession(cfg.tg_session),
                                     cfg.tg_api_id, cfg.tg_api_hash)
        bot_client = TelegramClient(StringSession(), cfg.tg_api_id, cfg.tg_api_hash)
        self._cleanup += [user_client, bot_client]

        # Ďalej zrkadli predlohu: connect, is_user_authorized check,
        # ControlBot best-effort start, UserBot.register, start_sweeper,
        # start_voice_jobs, Reconciler.run, run_until_disconnected.
        # (Kód prenes z /Users/marek/telegram/src/main.py:40-139 — vrátane
        # komentárov o FloodWaite kontrolného bota.)
        ...
```

Časť `_run_once` označená `...` sa prenáša z predlohy main.py — je to existujúci,
odladený kód; prenes ho celý vrátane try/finally upratovania (sweeper.cancel,
llm.close — POZOR: `db.close()` už neexistuje, transport vlastní main; a namiesto
`asyncio.gather(...)` na konci pridaj wait aj na `self._stopping.wait()`, nech
`stop()` vie runner ukončiť).

- [ ] **Step 4: Run** — testy z Step 1 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: TenantRunner with backoff + clean stop"`

---

### Task 11: main.py — claim slučka

**Files:**
- Create: `worker/src/main.py`, `worker/tests/test_main_loop.py`

- [ ] **Step 1: Failing testy**

```python
"""Claim slučka — spúšťanie/zastavovanie runnerov podľa lease."""
import asyncio
from main import Pool

class FakeReg:
    def __init__(self):
        self.claims = []; self.released = []; self.hb = 0
        self.next_rows = []
        self.rows_by_id = {}
    async def claim(self, replica, capacity):
        self.claims.append(capacity); return self.next_rows
    async def heartbeat(self, replica): self.hb += 1
    async def release_all(self, replica): self.released.append("ALL")
    async def model_row(self, mid): return self.rows_by_id.get(mid)
    async def release(self, mid): self.released.append(mid)

class FakeRunner:
    instances = []
    def __init__(self, *a, **kw):
        FakeRunner.instances.append(self); self.stopped = False
    async def run(self): await asyncio.sleep(3600)
    async def stop(self): self.stopped = True

ROW = {"id": "m-1", "account_id": "a-1", "name": "", "tg_api_id": 1,
       "tg_api_hash": "h", "tg_session_enc": "", "control_bot_token_enc": "",
       "owner_chat_id": 1, "status": "active"}

def make_pool(reg):
    return Pool(registry=reg, transport=None, global_cfg=_cfg(),
                runner_factory=FakeRunner, tenant_factory=lambda row, g: row)

def _cfg():
    class C: max_tenants = 2; replica_name = "r-1"; claim_interval_s = 0
    return C()

async def test_claims_up_to_capacity_and_starts_runner():
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    assert reg.claims == [2]                     # capacity - 0 bežiacich
    assert len(FakeRunner.instances) == 1

async def test_second_tick_claims_remaining_capacity():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    reg.next_rows = []
    await pool.tick()
    assert reg.claims == [2, 1]

async def test_paused_model_gets_stopped():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    reg.next_rows = []
    reg.rows_by_id["m-1"] = {**ROW, "status": "paused"}
    await pool.tick()
    assert FakeRunner.instances[0].stopped
    assert "m-1" in reg.released

async def test_shutdown_releases_all():
    FakeRunner.instances.clear()
    reg = FakeReg(); reg.next_rows = [ROW]
    pool = make_pool(reg)
    await pool.tick()
    await pool.shutdown()
    assert FakeRunner.instances[0].stopped
    assert "ALL" in reg.released
```

- [ ] **Step 2: Run** → FAIL

- [ ] **Step 3: Implementácia**

```python
"""Entrypoint — pool: claim → runneri → heartbeat → graceful shutdown."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

log = logging.getLogger("main")


class Pool:
    def __init__(self, registry, transport, global_cfg,
                 runner_factory=None, tenant_factory=None) -> None:
        from runner import TenantRunner
        from config import TenantConfig
        self._reg = registry
        self._t = transport
        self._g = global_cfg
        self._runner_factory = runner_factory or TenantRunner
        self._tenant_factory = tenant_factory or TenantConfig.from_row
        self._running: dict[str, tuple] = {}      # model_id → (runner, task)

    async def tick(self) -> None:
        # 1) dozretí na stop: status už nie je active → stop + release
        for mid in list(self._running):
            row = await self._reg.model_row(mid)
            if not row or row.get("status") != "active":
                runner, task = self._running.pop(mid)
                await runner.stop(); task.cancel()
                await self._reg.release(mid)
                log.info("Tenant %s zastavený (status=%s)", mid, row and row.get("status"))
        # 2) mŕtve tasky (runner skončil sám — error/out_of_credits) von z evidencie
        for mid in list(self._running):
            _, task = self._running[mid]
            if task.done():
                self._running.pop(mid)
        # 3) doclaimuj do kapacity
        free = self._g.max_tenants - len(self._running)
        if free > 0:
            for row in await self._reg.claim(self._g.replica_name, free):
                try:
                    cfg = self._tenant_factory(row, self._g)
                except Exception:
                    log.exception("Tenant %s má pokazený config — error", row.get("id"))
                    await self._reg.set_status(row["id"], "error", "bad_config")
                    await self._reg.release(row["id"])
                    continue
                runner = self._runner_factory(cfg, self._g, self._reg, self._t)
                task = asyncio.create_task(runner.run())
                self._running[row["id"]] = (runner, task)
                log.info("Tenant %s spustený", row["id"])
        await self._reg.heartbeat(self._g.replica_name)

    async def shutdown(self) -> None:
        for mid, (runner, task) in list(self._running.items()):
            await runner.stop(); task.cancel()
        self._running.clear()
        await self._reg.release_all(self._g.replica_name)


async def run() -> None:
    from config import Config
    from registry import Registry
    from transport import SupabaseTransport

    g = Config.from_env()
    transport = SupabaseTransport(g.supabase_url, g.supabase_key)
    pool = Pool(Registry(transport), transport, g)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    log.info("Replika %s, kapacita %d", g.replica_name, g.max_tenants)
    try:
        while not stop.is_set():
            try:
                await pool.tick()
            except Exception:
                log.exception("Tick zlyhal — pokračujem")   # Supabase výpadok nesmie zabiť proces
            try:
                await asyncio.wait_for(stop.wait(), timeout=g.claim_interval_s or 30)
            except asyncio.TimeoutError:
                pass
    finally:
        await pool.shutdown()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
                        stream=sys.stdout)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Ukončené používateľom")


if __name__ == "__main__":
    main()
```

Pozn.: `tick()` musí mať aj vetvu `set_status` v registry Fake — doplň do FakeReg
`async def set_status(self, *a, **kw): pass` ak testy padnú na AttributeError.

- [ ] **Step 4: Run** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: pool main loop (claim/heartbeat/shutdown)"`

---

### Task 12: Port userbot.py + control_bot.py

**Files:**
- Create: `worker/src/userbot.py`, `worker/src/control_bot.py`
- Create: `worker/tests/` — príslušné testy predlohy (test_reply_flow.py už je z T9)
- Referencia: `/Users/marek/telegram/src/userbot.py` (2101 r.), `control_bot.py` (735 r.)

- [ ] **Step 1: Skopíruj oba súbory 1:1**

```bash
cp /Users/marek/telegram/src/userbot.py /Users/marek/telegram/src/control_bot.py \
   /Users/marek/telepipe/worker/src/
```

- [ ] **Step 2: Minimálne úpravy**

Oba súbory berú `(cfg, db, …)` — dostanú `TenantConfig` a `TenantDb`, ktoré majú
rovnaké atribúty/metódy. Povolené úpravy:
1. importy typu `from config import Config` → `from config import TenantConfig as Config`
   a `from db import Db` → `from db import TenantDb as Db` (alias — telá funkcií nezmenené)
2. Ak niektorý kód číta `cfg.<atribút>`, ktorý TenantConfig nemá → doplň atribút
   do TenantConfig (T5 grep to mal odhaliť; tu je druhá poistka), NIE úpravu userbota.
3. NIČ iné. Prompty, handlery, menu, sweeper, reconciler — bajt po bajte predloha.

- [ ] **Step 3: Testy**

Testy pre userbot/control_bot z predlohy už ležia v tests/ (T9). Spusti celú sadu:
`.venv/bin/pytest -q` → všetko PASS. Zlyhania rieš v conftest/fixtures, nie v moduloch.

- [ ] **Step 4: Commit** — `git commit -m "feat: port userbot + control bot"`

---

### Task 13: Integračný smoke test proti reálnej DB

**Files:**
- Create: `worker/tests/test_integration_db.py` (marker `integration`, default skip)

- [ ] **Step 1: Test**

```python
"""Proti reálnej telepipe DB (kľúče z ../.env). Spúšťa sa ručne:
   .venv/bin/pytest -m integration
"""
import os, uuid, pytest, asyncio

pytestmark = pytest.mark.integration

@pytest.fixture
async def real():
    from dotenv import load_dotenv
    load_dotenv("/Users/marek/telepipe/.env")
    from transport import SupabaseTransport
    from registry import Registry
    t = SupabaseTransport(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    yield Registry(t), t

async def test_lease_lifecycle(real):
    reg, t = real
    acc = (await t._post("accounts", {"email": f"it-{uuid.uuid4()}@test.dev",
                                      "credit_balance_usd": 5}))[0]
    row = (await t._post("models", {"account_id": acc["id"], "status": "active",
                                    "tg_api_id": 1, "owner_chat_id": 1}))[0]
    try:
        claimed = await reg.claim("it-replika", 5)
        assert any(r["id"] == row["id"] for r in claimed)
        again = await reg.claim("it-replika-2", 5)
        assert not any(r["id"] == row["id"] for r in again)   # SKIP LOCKED drží
        balance = await reg.record_usage(row["id"], "chat", 10, 5, 0, 0.001, 0.002)
        assert balance == pytest.approx(4.998)
        await reg.release_all("it-replika")
    finally:
        await t._client.delete(f"/accounts?id=eq.{acc['id']}")   # cascade zmaže model aj usage
```

`pytest.ini` doplň: `markers = integration: proti reálnej DB` a
`addopts = -m "not integration"`.

- [ ] **Step 2: Spusti ručne** — `.venv/bin/pytest -m integration -v` → PASS
- [ ] **Step 3: Commit** — `git commit -m "test: integration smoke against telepipe DB"`

---

### Task 14: README + finálna kontrola

**Files:**
- Create: `README.md` (root), `worker/.env.example`

- [ ] **Step 1: README** — stručne: čo je Telepipe, ako spustiť worker lokálne,
  ako pridať tenanta SQL-om (insert accounts + models so zašifrovanou session —
  ukáž príkaz `python -c "from crypto import encrypt; ..."`), fázy 2–4 TODO.
- [ ] **Step 2: worker/.env.example** — všetky env z Config.from_env s komentármi
  (SUPABASE_URL, SUPABASE_SERVICE_KEY, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
  ENCRYPTION_KEY — vygeneruj `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`,
  MAX_TENANTS, CLAIM_INTERVAL_S, FALLBACK_PRICE_PER_MTOK, LOG_LEVEL, voice premenné).
- [ ] **Step 3: Celá sada** — `.venv/bin/pytest -q` PASS; `git status` čistý okrem .env.
- [ ] **Step 4: Commit** — `git commit -m "docs: README + env example"`

---

## Poradie a závislosti

T1 → T2 → T3 (DB hotová) → T4, T5, T6 (nezávislé po T1) → T7 (po T6) →
T8 (po T6) → T9 (po T5, T7) → T10 (po T8, T9) → T11 (po T10) → T12 (po T9) →
T13 (po T11) → T14.
