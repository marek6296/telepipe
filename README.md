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
- **Worker:** `cd worker && railway up` (project `telepipe`, service `worker`).

See `worker/README.md` and `web/.env.example` for environment variables. Before the first
real tenant, seed the `pricing` table (or let the daily Atlas sync populate it).
