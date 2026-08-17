# Telepipe — fáza 1: multi-tenant worker + databáza

**Dátum:** 2026-08-17 · **Stav:** schválené Marekom (dizajn), spec na review

## Čo je Telepipe

SaaS verzia projektu Telegram AI Modelka (`/Users/marek/telegram` — ďalej „predloha").
Klient sa zaregistruje, sám si pripojí Telegram účet (userbot), voliteľne Fanvue
a ElevenLabs, nastaví personu — a AI agent odpisuje z jeho účtu presne tak, ako
odpisujú Marekove modelky dnes. Predloha sa **nikde nemení ani nevypína** — jej kód
slúži len ako vzor; Marekove modelky (Simona/Mio/Ayko) bežia ďalej zo starého projektu.

### Rozhodnutia z brainstormingu

| Otázka | Rozhodnutie |
|---|---|
| Telegram napojenie | Userbot (Telethon/MTProto), SMS login priamo na stránke |
| Rozsah | 5–100 tenantov, škálovanie Railway replikami |
| AI náklady | Náš Atlas Cloud kľúč; klientove kredity sa míňajú v **2× hodnote** Atlas ceny |
| Fanvue | Jedna naša OAuth appka (klient len klikne Connect) — fáza 3 |
| Kód | Úplne nový projekt; z predlohy sa kopíruje správanie 1:1 |
| Databáza | Nový Supabase projekt `telepipe` (`cggsyshfdjycfqrhtjld`, eu-west-1) |
| Jazyk UI | Angličtina (kódové komentáre slovensky) |

### Fázy celého projektu (tento spec = fáza 1)

1. **Multi-tenant worker + databáza** ← tento dokument
2. Web: registrácia, login (Supabase Auth), Telegram connect wizard, nastavenia
3. Fanvue OAuth + ElevenLabs connect
4. Kredity: dobíjanie, predplatné, platobná brána

Po fáze 2 je služba ručne predateľná (kredity klientom nastaví Marek v DB).

## Architektúra

Zvolený prístup: **pool workerov s lease systémom** (namiesto jedného monolitu
alebo Railway služby per tenant). Dôvody: škáluje sa pridaním repliky, pád jednej
repliky vyradí len jej tenantov na ~1 min, deploy po replikách nikdy nezhodí
všetkých naraz. S jednou replikou sa správa ako obyčajný single proces.

```
Railway: worker replika 1..N          Supabase (telepipe)
┌─────────────────────────┐           ┌──────────────────────┐
│ claim slučka (30 s)     │──lease───▶│ models               │
│ ┌─────────────────────┐ │           │  claimed_by          │
│ │ TenantRunner (max25)│ │           │  heartbeat_at        │
│ │  Telethon userbot   │ │◀──config──│ persona/behavior/…   │
│ │  control bot        │ │──usage───▶│ usage_events         │
│ │  reconciler         │ │           │ accounts.credit_bal  │
│ └─────────────────────┘ │           └──────────────────────┘
└─────────────────────────┘
```

### Štruktúra repa

```
telepipe/
├── worker/
│   ├── src/          # prekopírované moduly z predlohy, prerobené na model_id
│   ├── tests/        # prenesená test sada + nové multi-tenant testy
│   ├── requirements.txt
│   ├── nixpacks.toml # ffmpeg kvôli hlasovkám (ako v predlohe)
│   └── railway.json  # startCommand: python src/main.py
├── web/              # Next.js — fáza 2, teraz len skeleton
├── supabase/migrations/
└── docs/superpowers/specs/
```

## Databáza — tenant = riadok

Všetko v schéme `public`. Žiadne per-tenant schémy (predloha má schému per modelka —
to sa pri 100 klientoch nedá spravovať, a exposed-schemas limit by to zabil).

### Nové tabuľky

**`accounts`** — klient služby
- `id uuid pk default gen_random_uuid()`
- `email text unique not null`
- `credit_balance_usd numeric not null default 0` — v USD; záporné nedovolíme
- `created_at timestamptz`
- Vo fáze 2 sa napojí na `auth.users` (id = auth uid); teraz vkladá riadky Marek ručne.

**`models`** — modelka klienta (nahrádza dnešný .env + Railway service)
- `id uuid pk`, `account_id uuid references accounts not null`
- `name text` (interné meno pre klienta), `status text check in ('draft','active','paused','error','disabled') default 'draft'`
- `status_reason text default ''` — prečo je paused/error („out_of_credits", „session_revoked", …)
- lease: `claimed_by text`, `heartbeat_at timestamptz`
- Telegram: `tg_api_id int`, `tg_api_hash text`, `tg_session_enc text`, `control_bot_token_enc text`, `owner_chat_id bigint`
- `created_at`, `updated_at`

**`usage_events`** — kreditový ledger (append-only)
- `id bigint identity pk`, `model_id uuid`, `account_id uuid`
- `kind text check in ('chat','summary','vision','audio','voice')`
- `input_tokens int`, `output_tokens int`, `unit_count int` (znaky pri voice)
- `atlas_cost_usd numeric not null`, `charged_usd numeric not null` (= atlas × multiplikátor)
- `created_at timestamptz`

**`pricing`** — ceny bez deployu
- `model_slug text pk` (napr. `x-ai/grok-4.5`), `input_usd_per_mtok numeric`, `output_usd_per_mtok numeric`
- `multiplier numeric not null default 2.0` — globálny riadok `_default` nesie multiplikátor

### Prenesené tabuľky z predlohy

Všetkých 16 tabuliek z `tgai` (persona, behavior, settings, dm_users, dm_messages,
facts, photos, photo_sends, voices, voice_sends, episodes, open_loops, self_claims,
judge_log, voice_clips, voice_jobs) sa prenáša so **zhodnými stĺpcami** + zmeny:

- každá dostane `model_id uuid not null references models on delete cascade`
- PK sa rozšíri: `persona/behavior/settings` z `id int default 1` na `model_id` pk;
  `dm_users` z `(tg_id)` na `(model_id, tg_id)`; FK v `dm_messages`, `facts`, … analogicky
- indexy z predlohy sa prenesú s `model_id` ako prvým stĺpcom
- defaulty hodnôt (voice_chance 0.18, voice_tempo 1.12, …) ostávajú **identické** —
  to je to vyladené správanie

RLS: zapnuté na všetkom, žiadne policies pre anon (worker aj web server idú cez
service key). Klientske policies pribudnú vo fáze 2.

Storage: bucket `voices` (public read ako v predlohe) + `photos`.

## Worker

### Prenos kódu z predlohy

Moduly sa kopírujú 1:1 vrátane promptov, konštánt a komentárov. Menia sa len:

1. **`db.py`** — najväčší zásah: každá metóda dostane `model_id` parameter a filter;
   schéma je vždy `public`. Roztriedime na `Db` (globálne: claim, pricing, usage)
   a `TenantDb` (viazaný na model_id — to dostanú všetky ostatné moduly, takže
   ich signatúry sa takmer nemenia).
2. **`config.py`** — globálny config (Supabase, Atlas kľúč, ENCRYPTION_KEY,
   REPLICA_NAME, MAX_TENANTS) z env; per-tenant config (tg_session, bot token,
   owner_chat_id, link limity…) z riadku `models` + `behavior`/`settings`.
3. **`main.py`** — nový: claim slučka + správa TenantRunnerov.
4. **`llm.py`** — obalí volania meraním: pred volaním credit check, po volaní
   zápis usage + odpočet kreditu.

Nemenia sa: persona.py, memory.py, humanize.py, funnel.py, judge.py, den.py,
facts.py, topics.py, recall.py, similar.py, taper.py, gags.py, weather.py,
speech.py, livevoice.py, eleven.py, voices.py, photos.py, limity.py, outreach.py,
fanmatch.py, checkout.py — dostanú `TenantDb` namiesto `Db` a idú ďalej.
(fanvue_* moduly sa prenesú tiež, aktivujú sa vo fáze 3.)

### Lease protokol

- Claim: Postgres **RPC funkcia** `claim_models(replica text, capacity int)` —
  jedno atomické `UPDATE … WHERE status='active' AND (claimed_by IS NULL OR
  heartbeat_at < now() - interval '90 seconds') … FOR UPDATE SKIP LOCKED
  LIMIT capacity RETURNING *`. REST filtre by mali race condition, preto RPC.
- Heartbeat: každých 30 s `UPDATE models SET heartbeat_at=now() WHERE claimed_by=$replica`.
- Release: pri SIGTERM graceful `claimed_by=NULL` + odpojenie Telethon klientov.
- Expirácia: replika umrie → za 90 s si tenantov claimne iná.
- Unclaim jedného tenanta: keď `status` prestane byť `active` (web/kredity ho
  prepli), runner sa pri najbližšom refreshi (≤60 s) zastaví a `claimed_by=NULL`.
- `REPLICA_NAME` = Railway `RAILWAY_REPLICA_ID` (fallback hostname+pid).

### TenantRunner

Zapuzdruje presne to, čo dnes robí `main.py` predlohy pre jednu modelku:
Telethon klient zo session stringu, control bot (klientov BotFather token,
menu 1:1 z predlohy), reconciler, sweeper. Beží ako `asyncio.Task` v spoločnom
event loope. Pád runnera nezhodí proces — reštart s exponenciálnym backoffom
(30 s → 1 m → 5 m → 15 m, max 5 pokusov, potom `status='error'` + status_reason).

## Kredity

- **Check** pred každým plateným volaním (chat/summary/vision/audio/voice):
  `credit_balance_usd > 0`. Nie → `status='paused'`, `status_reason='out_of_credits'`,
  control-bot správa majiteľovi, runner sa zastaví. (Jedno volanie smie zostatok
  podliezť pod nulu — strop je „nezačne sa nové volanie bez kreditu", nie
  centové účtovníctvo uprostred odpovede.)
- **Zápis** po volaní: Atlas vracia `usage` v response → `atlas_cost_usd` z tabuľky
  `pricing` → `charged_usd = atlas_cost_usd × multiplier` → RPC
  `record_usage(...)` vloží event a atomicky odpočíta z `accounts.credit_balance_usd`.
- Keď cena modelu v `pricing` chýba, volanie prejde, ale zaloguje sa warning
  a účtuje sa konzervatívny fallback (env `FALLBACK_PRICE_PER_MTOK`).

## Bezpečnosť

- `tg_session_enc`, `control_bot_token_enc`: **AES-256-GCM**, kľúč `ENCRYPTION_KEY`
  výhradne v Railway env. Formát `nonce:ciphertext:tag` base64. DB leak sám
  o sebe session nevydá.
- Service key len v server env (worker, neskôr web server actions). Anon key
  bez policies nič neprečíta.
- Supabase test kľúče v `.env` (gitignored) — Marek ich pred launchom rerollne.

## Error handling

| Situácia | Reakcia |
|---|---|
| Pád TenantRunnera | reštart s backoffom; po 5. zlyhaní `status='error'` + notifikácia |
| `AuthKeyUnregistered` / session revoked | okamžite `status='error'`, `status_reason='session_revoked'` — bez retry (spamovalo by Telegram) |
| FloodWait | ako v predlohe (rešpektovať čas), navyše log do `usage_events` nejde |
| Replika umrie | heartbeat vyprší za 90 s, tenantov preberú ostatné |
| Supabase nedostupný | runner beží ďalej z pamäti, retry s backoffom (ako predloha) |
| Došiel kredit | `paused` + dôvod; obnovenie kreditu vo fáze 4 model znova aktivuje |

## Testovanie

1. **Prenesená sada** — testy predlohy bežia ďalej (fixtures dostanú model_id).
   Logika správania sa nemení, testy to strážia.
2. **Nové testy:**
   - lease: dve „repliky" claimujú súčasne → žiadny tenant dvakrát (SKIP LOCKED)
   - heartbeat expirácia → prevzatie tenanta
   - credit check: nula → pause + žiadne LLM volanie; usage zápis = 2× atlas
   - izolácia: TenantDb modelu A nikdy nevráti riadky modelu B (test na každú tabuľku)
   - šifrovanie: roundtrip + zlý kľúč zlyhá čisto
3. Integračný smoke test proti reálnej telepipe DB (service key z .env).

## Mimo rozsahu fázy 1

- Web UI (fáza 2) — accounts/models vkladá zatiaľ Marek SQL-om
- Fanvue + ElevenLabs aktivácia (fáza 3; kód sa prenáša, ale neaktivuje)
- Platby a dobíjanie (fáza 4)
- Migrácia Marekových modeliek — **nikdy** (ostávajú v starom projekte)
