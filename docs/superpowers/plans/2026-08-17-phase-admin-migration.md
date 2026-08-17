# Telepipe — admin panel + migrácia Simona/Mio: plán

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox tracking.

**Goal:** (A) Admin rozhranie — roly (user/admin/superadmin), Marek = superadmin, správa používateľov (rola, balík, kredit), monitoring botov (live stav z heartbeatov). (B) Idempotentný migračný skript starých modeliek (tgai/tgmio zo starého Supabase „ai news") do telepipe pod Marekov účet — v stave `paused`, s cutover postupom.

**Bezpečnosť:** Starý Supabase (dmxosdgvmzvkeivknczv) a starý Railway projekt sú READ-ONLY. Modelky sa v telepipe NIKDY neaktivujú, kým beží stará služba (dvojitá TG session = ban riziko). `/Users/marek/telegram` READ-ONLY.

---

### Task A1: Migrácia 009 — roly, balíky, admin RPC, worker_replicas

**Files:** `supabase/migrations/009_admin.sql`, worker: `main.py` (replica heartbeat), `registry.py`

- accounts: `role text not null default 'user' check in ('user','admin','superadmin')`, `plan text not null default 'free'`.
- UPDATE accounts set role='superadmin' where email='cmelo.marek@gmail.com'.
- `is_admin()` / `is_superadmin()` helper fns (security definer, číta accounts.role cez auth.uid()).
- Admin RPCs (security definer, pinned search_path, revoke public/anon; grant authenticated — vnútri kontrola is_admin/is_superadmin):
  - `admin_list_accounts()` → email, role, plan, credit_balance_usd, created_at, models_count, spend_30d (admin)
  - `admin_list_models()` → id, account_email, name, status, status_reason, claimed_by, heartbeat_at, msgs_today, spend_today (admin)
  - `admin_set_role(p_account uuid, p_role text)` — LEN superadmin; nikto nesmie meniť rolu superadmina okrem superadmina; nemôže degradovať sám seba ak je posledný superadmin
  - `admin_set_plan(p_account uuid, p_plan text)` — admin
  - `admin_add_credit(p_account uuid, p_amount numeric, p_note text)` — admin; zapíše aj do `credit_adjustments` audit tabuľky (id, account_id, admin_id, amount, note, created_at)
  - `admin_usage_summary(p_days int)` — denné súčty charged/atlas naprieč všetkými (admin; TU admin vidí aj atlas_cost = marža je pre admina OK)
- `worker_replicas` tabuľka: replica_name pk, last_seen, tenant_count, started_at. Worker main loop tick: upsert svojej repliky. RLS: len admin RPC `admin_list_replicas()` (service definer), inak service_role only. Stale = last_seen > 2 min.
- RLS policajt: bežné klientske policies sa NEROZŠIRUJÚ (admin ide výhradne cez RPC — žiadne „admin vidí všetko" table policies, menší povrch).
- Worker: v `Pool.tick()` po heartbeate upsert do worker_replicas (transport POST upsert). Test. Redeploy workera na Railway (`cd worker && railway up`).

### Task A2: Web — admin sekcia

**Files:** `web/app/app/admin/**`, sidebar update

- Sidebar: položka **Admin** (Shield ikona) viditeľná len ak `accounts.role in ('admin','superadmin')` (server-side check v layoute; client nikdy nerozhoduje).
- `/app/admin` — dashboard: karty (Users, Active models, Live bots = repliky+claimnuté modely s čerstvým heartbeatom, Credits balance sum, Spend today/30d, Atlas cost 30d + marža), tabuľka replík (name, tenants, last_seen, stale badge).
- `/app/admin/users` — tabuľka z admin_list_accounts, search; akcie: zmena plánu (select: free/starter/pro/custom), pridanie kreditu (dialóg suma+poznámka), zmena roly (LEN pre superadmina viditeľné). Všetko cez RPC, optimistic UI + toast.
- `/app/admin/models` — všetky modelky: status/claimed_by/heartbeat (live/stale/dead badge), account email, dnešná spotreba; link do detailu klienta modelky nie (privacy) — len metadáta.
- `/app/admin/usage` — graf admin_usage_summary (charged vs atlas = marža vizuálne), 30 dní.
- Guard: každá admin server action aj page znovu overí rolu server-side. Build + testy manuálne cez dočasného admin test usera NIE — použiť Marekov účet len read; testovať RPC cez service simuláciu v SQL.

### Task B1: Migračný skript Simona/Mio

**Files:** `scripts/migrate_model.py` (root repa; číta worker/src moduly cez sys.path)

- Vstup: `python scripts/migrate_model.py --source-schema tgai --name Simona [--fresh|--delta]`
- Zdroj: starý Supabase URL+service key z `/Users/marek/telegram/.env` (READ ONLY — žiadne write na starý projekt!). Cieľ: telepipe DB (root .env).
- Kroky:
  1. Nájde Marekov account (email cmelo.marek@gmail.com) v telepipe.
  2. Vytvorí/nájde models riadok (podľa `migration_source` stĺpca — pridaj v 009: `models.migration_source text default ''` unique kde nie prázdne, napr. 'tgai') — idempotencia. Status VŽDY 'paused', status_reason 'migration_standby'.
  3. TG creds: TG_API_ID/HASH/SESSION + CONTROL_BOT_TOKEN + OWNER_CHAT_ID zo starého `.env`/`.env.mio` → encrypt (worker crypto + telepipe ENCRYPTION_KEY) → models riadok.
  4. Tabuľky v poradí FK: persona, behavior (VRÁTANE eleven_key ak je), settings, dm_users, dm_messages, facts, photos, photo_sends, voices, voice_sends, episodes, open_loops, self_claims, judge_log, voice_clips, voice_jobs. Všetko s model_id. Upsert po dávkach 500 (on_conflict podľa PK; dm_messages/facts/episodes… majú identity id v cieli → idempotencia cez natural key: (model_id, tg_id, created_at, content hash) — pridaj pomocný unique index alebo delta-logiku „insert len novšie ako max(created_at) v cieli per tg_id" pre append-only tabuľky; pre mutable (dm_users, persona…) upsert celý riadok).
  5. Storage: voice_clips.url a photos.url — ak mieria na starý projekt storage, stiahni a nahraj do telepipe bucketov (`voices`/`photos`, prefix model_id), prepíš URL; ak externé URL, nechaj.
  6. Verifikačný report: per tabuľka count zdroj vs cieľ (delta run: nové riadky). Kontrolné vzorky: posledná správa najaktívnejšieho usera, počet photo_sends per fotka.
- `--delta`: znovu spustiteľné tesne pred cutoverom.
- DRY-RUN mód default (vypíše čo by robil), `--execute` reálne zapíše.
- Po skripte: spustiť pre tgai (Simona) aj tgmio (Mio) s --execute. Ayko NIE (Marek spomenul len Simonu a Mio).

### Cutover runbook (do README + report Marekovi — NEVYKONÁVA SA TERAZ)

1. Marek povie „prepíname Simonu".
2. `python scripts/migrate_model.py --source-schema tgai --delta --execute` (dotiahne rozdiel).
3. Marek (alebo my s jeho súhlasom) zastaví starú Railway službu `worker` v projekte telegram-ai-simona.
4. Počkať 2 min (session sa uvoľní), aktivovať model v telepipe (web Activate / RPC).
5. Sledovať logy telepipe workera; rollback = pauza v telepipe + reštart starej služby.
