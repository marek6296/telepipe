# Telepipe

Multi-tenant SaaS version of the "Telegram AI Modelka" project. A client
signs up, connects their own Telegram account (userbot), optionally Fanvue
and ElevenLabs, sets up a persona — and an AI agent replies from their
account the same way it already does for the original single-tenant project.

**Phase 1 (this repo, current state): multi-tenant worker + database.**
Accounts/models are inserted manually by an operator via SQL — there is no
web UI yet.

| Phase | Scope | Status |
|---|---|---|
| 1 | Multi-tenant worker + Supabase schema | done |
| 2 | Web: signup, login (Supabase Auth), Telegram connect wizard, settings | planned |
| 3 | Fanvue OAuth + ElevenLabs connect | planned |
| 4 | Credits: top-up, subscriptions, payment gateway | planned |

## Architecture

A pool of stateless worker replicas leases tenants ("models") out of a
shared Supabase database via an atomic RPC claim. Each replica runs up to
`MAX_TENANTS` tenants concurrently as independent `TenantRunner` tasks
inside one event loop.

```
Railway: worker replica 1..N          Supabase (telepipe)
┌─────────────────────────┐           ┌──────────────────────┐
│ claim loop (30s)        │──lease───▶│ models               │
│ ┌─────────────────────┐ │           │  claimed_by           │
│ │ TenantRunner (≤N)   │ │           │  heartbeat_at         │
│ │  Telethon userbot   │ │◀──config──│ persona/behavior/…    │
│ │  control bot        │ │──usage───▶│ usage_events          │
│ │  reconciler         │ │           │ accounts.credit_bal   │
│ └─────────────────────┘ │           └──────────────────────┘
└─────────────────────────┘
```

- **Lease:** `claim_models(replica, capacity)` is a Postgres RPC that
  atomically claims up to `capacity` tenants with status `active` whose
  lease is free or stale (`heartbeat_at` older than 90s), using
  `FOR UPDATE SKIP LOCKED` so two replicas never claim the same tenant.
  Each replica sends a heartbeat every `CLAIM_INTERVAL_S` and releases its
  leases on graceful shutdown (SIGTERM).
- **Credits:** every paid LLM call (chat/summary/vision/audio/voice) is
  checked against `accounts.credit_balance_usd` before it fires, and
  recorded afterwards via the `record_usage` RPC. Clients are charged
  **2× the underlying Atlas Cloud cost** (`pricing.multiplier`); an unknown
  model falls back to `FALLBACK_PRICE_PER_MTOK`.
- **Encrypted sessions:** the Telegram session string and control-bot token
  are stored AES-256-GCM encrypted (`tg_session_enc`, `control_bot_token_enc`)
  under a single `ENCRYPTION_KEY` that lives only in the worker's env. A
  database leak alone does not expose a usable session.

## Repo layout

```
telepipe/
├── worker/                # Python worker — the only running service in phase 1
│   ├── src/                # main.py (claim loop + Pool), config.py, db.py, crypto.py,
│   │                        # runner.py (TenantRunner), + ported behavior modules
│   ├── tests/               # unit + integration test suite
│   ├── requirements.txt
│   ├── nixpacks.toml        # ffmpeg (voice message conversion)
│   └── railway.json         # Railway service config (start command, restart policy)
├── supabase/migrations/    # SQL migrations, applied in order (001…)
├── web/                    # phase 2 — not started yet
└── docs/superpowers/        # specs and plans
```

## Local development

```bash
cd worker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env   # fill in real values, see below
```

Run the test suite:

```bash
cd worker
.venv/bin/pytest -q                 # default suite (mocks, no network) — 1212 passed
.venv/bin/pytest -q -m integration  # + integration tests against a real Supabase project
```

Run the worker itself (requires a populated `.env`, see `worker/.env.example`):

```bash
cd worker
.venv/bin/python src/main.py
```

## Adding a tenant manually (phase 1 has no UI)

Until the phase 2 web wizard exists, an operator provisions tenants with SQL
against the `telepipe` Supabase project. The Telegram session string itself
is obtained separately via a one-off Telethon login (`StringSession`); once
you have it, encrypt it with the worker's `crypto.py` before inserting it:

```bash
cd worker
.venv/bin/python -c "
import sys; sys.path.insert(0, 'src')
from crypto import encrypt
print(encrypt('SESSION_STRING', 'ENCRYPTION_KEY_B64'))
"
```

Do the same for the control bot's BotFather token. Then insert the account
and model:

```sql
insert into accounts (email, credit_balance_usd)
values ('client@example.com', 20.00)
returning id;
-- use the returned id as account_id below

insert into models (
  account_id, name, status,
  tg_api_id, tg_api_hash, tg_session_enc,
  control_bot_token_enc, owner_chat_id
) values (
  '<account_id>', 'client-model-1', 'active',
  123456, 'tg-api-hash-from-my.telegram.org',
  'nonce_b64:ciphertext_b64:tag_b64',   -- output of the encrypt call above
  'nonce_b64:ciphertext_b64:tag_b64',   -- control bot token, same encryption
  111222333                              -- owner's Telegram chat id
);
```

Inserting into `models` fires a trigger (`005_provision_trigger.sql`) that
auto-seeds the tenant's `persona`, `behavior`, and `settings` rows with
defaults — no need to insert those by hand. Set `status='active'` once
everything is filled in; a running worker replica will pick the tenant up
on its next claim cycle (≤ `CLAIM_INTERVAL_S`).

## Deploy

The worker deploys as a single Railway service built from `worker/`
(`worker/railway.json` — Nixpacks builder, `python src/main.py` start
command, restart-on-failure).

1. Create a Railway service pointing at `worker/` as the root/build directory.
2. Set the environment variables listed in `worker/.env.example` (Supabase
   URL + service key, LLM key, `ENCRYPTION_KEY`, etc.) in the Railway
   service's variables.
3. Scale horizontally by increasing `numReplicas` in `railway.json` (or the
   Railway dashboard) and/or raising `MAX_TENANTS` per replica — the lease
   protocol handles distribution automatically, no coordination needed.
4. Railway's replica identifier (`RAILWAY_REPLICA_ID`) is picked up
   automatically as the lease owner name; no extra config required.

### ⚠️ Before activating any tenant: seed the `pricing` table

Billing reads per-model token prices from `pricing`. The table ships with a
single `_default` row that carries the multiplier only (`2.0`) and **no real
prices**, so every call for a model that is not in the table is billed with
the conservative fallback `FALLBACK_PRICE_PER_MTOK × multiplier` (default
`5.00 USD/Mtok × 2`) — usually far more than the model actually costs. The
worker logs `Chýba cenník pre <slug>` once per model slug per process when
this happens.

Insert the real Atlas Cloud prices for every model slug in use (the slugs
from `LLM_MODEL`, `LLM_SUMMARY_MODEL`, `LLM_VISION_MODEL`, `LLM_AUDIO_MODEL`)
before flipping any tenant to `status='active'`:

```sql
-- Replace every <FILL_IN> with the current Atlas Cloud price in USD per
-- million tokens for that model. Do NOT guess — copy them from the provider.
insert into pricing (model_slug, input_usd_per_mtok, output_usd_per_mtok, multiplier)
values
  ('xai/grok-4.5',                        <FILL_IN>, <FILL_IN>, 2.0),
  ('qwen/qwen3-vl-235b-a22b-thinking',    <FILL_IN>, <FILL_IN>, 2.0),
  ('google/gemini-3.5-flash',             <FILL_IN>, <FILL_IN>, 2.0)
on conflict (model_slug) do update
  set input_usd_per_mtok  = excluded.input_usd_per_mtok,
      output_usd_per_mtok = excluded.output_usd_per_mtok,
      multiplier          = excluded.multiplier;
```

`multiplier` is the client-facing markup (billed = atlas cost × multiplier);
`_default` keeps `2.0` and is used for any slug not listed. Prices are cached
in the worker for 5 minutes, so updates take effect without a redeploy.

No real keys are committed anywhere in this repo — `.env` is gitignored,
only `worker/.env.example` (placeholders) is tracked.
