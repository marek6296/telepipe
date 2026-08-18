# Telepipe

Multi-tenant SaaS for AI chat agents that reply from creators' Telegram (and, coming
soon, Fanvue) accounts — with tuned persona, memory, human-like rhythm, voice messages
and a conversion funnel. Clients sign up, connect their own accounts, configure their
model, and pay per usage in credits.

**Live:** [telepipe.me](https://telepipe.me)

## Repo layout

| Path | What |
|---|---|
| `web/` | Next.js app (landing, auth, client dashboard) — deployed to Vercel |
| `worker/` | Python multi-tenant worker (Telethon userbots pool + credits + login jobs) — deployed to Railway |
| `supabase/migrations/` | Postgres schema, RLS, RPCs |
| `scripts/` | One-off operational scripts (see *Migrating a legacy model* below) |
| `docs/superpowers/` | Specs & implementation plans |

## Architecture

- **One tenant = one row** (`models` table). A worker replica pool leases tenants via
  `claim_models` (heartbeat 30 s / reclaim 90 s) and runs one agent per model.
- **Credits:** every AI call is metered and charged at 2× the Atlas Cloud cost; prices
  auto-sync daily from the Atlas billing API.
- **Telegram connect:** the browser can't speak MTProto, so login runs as a DB job queue
  (`tg_login_jobs`) that the worker processes with Telethon; sessions are AES-256-GCM
  encrypted with a key shared byte-for-byte between web (Vercel) and worker (Railway).
- **Isolation:** Postgres RLS scopes every client to their own account; the worker uses
  the service key.

## Deploy

- **Web:** push to `main` → Vercel builds `web/` and deploys to telepipe.me.
- **Worker:** `worker/deploy.sh` (project `telepipe`, service `worker`, env `production`).
  Nasadzuj **len** cez tento skript, nikdy nie holým `cd worker && railway up`: `railway up`
  nahráva živý pracovný adresár vrátane necommitnutých súborov, čím raz do produkcie odišiel
  polorozpísaný modul a zhodil worker. Skript nahráva `git archive HEAD worker` a odmietne
  bežať, ak má `worker/` rozrobené zmeny.

See `worker/README.md` and `web/.env.example` for environment variables. Before the first
real tenant, seed the `pricing` table (or let the daily Atlas sync populate it).

## Migrating a legacy model (`scripts/migrate_model.py`)

Marek's two original bots (Simona, Mio) live in the old single-tenant Supabase project
"ai news" — one schema per model (`tgai`, `tgmio`) — and still run on the old Railway
project `telegram-ai-simona`. `scripts/migrate_model.py` copies one of those schemas into
telepipe as a normal tenant row.

```bash
worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona            # dry run
worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona --execute
worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona --delta --execute
```

- **The old project is read-only.** The source client refuses any method other than
  GET/HEAD before a socket is opened, and the run aborts if a single write is counted.
- **Idempotent.** The tenant row is keyed by `models.migration_source` (`'tgai'` /
  `'tgmio'`, partial unique index). Mutable tables are upserted; append-only tables are
  de-duplicated on a natural key, so re-running never doubles anything. `--delta` only
  looks at rows newer than the target's latest (10 min overlap) — that's the cheap
  cut-over pass.
- **Never active.** The row is created with `status='paused'`,
  `status_reason='migration_standby'`, and the script refuses to run at all if it finds
  the row in any other status. Two Telethon sessions on one Telegram account = ban.
- Identity PKs differ between the projects, so `facts.superseded_by`, `photo_sends.photo_id`
  and `voice_sends.voice_id` are remapped to the new ids. Storage objects on the old
  project are copied into the `photos` / `voices` buckets under `{model_id}/` and the URLs
  are rewritten; external URLs are left alone.

### Cut-over runbook

1. Marek says "switching Simona over".
2. `worker/.venv/bin/python scripts/migrate_model.py --source-schema tgai --name Simona --delta --execute`
   — pulls in everything the old bot has written since the last run.
3. Stop the `worker` service in the **old** Railway project `telegram-ai-simona`.
4. Wait ~2 min for Telegram to release the session, then activate the model in telepipe
   (dashboard *Activate*, or `set_model_status`).
5. Watch the telepipe worker logs. Rollback = pause the model in telepipe and restart the
   old Railway service.
