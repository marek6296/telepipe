# Telepipe — fáza 2: web (landing + auth + klientská app)

**Dátum:** 2026-08-17 · **Stav:** dizajn schválený Marekom, spec na review
**Nadväzuje na:** fáza 1 (multi-tenant worker + DB, hotová — 1231 testov)

## Vizuálna identita

- **Čierne pozadie, zlaté akcenty, biele logo** (`telepipe logo white.png` v roote repa;
  čierne logo sa nepoužíva — web je tmavý).
- Písmo: Poppins. UI kompletne **po anglicky**.
- Štýl: „premium SaaS" — blur, gradienty, hlboké tiene, hmatateľné buttony
  (tactile: hover translateY(-3px), active stlačenie), film grain, grid pozadie.
- Referencie od Mareka (obe sa preberajú ako predloha, nie doslovný kód):
  1. **SaaS template** (Poppins, gradient text, blur nav) — štýl navigácie a app UI
  2. **CinematicHero** (GSAP + ScrollTrigger) — celá landing page, viď nižšie

## Stack

- Next.js (App Router, TypeScript) v `web/`
- Tailwind CSS + shadcn štruktúra (`components/ui`)
- **GSAP + ScrollTrigger** — landing (pinned scroll scéna)
- **Framer Motion** — mikrointerakcie v appke (page transitions, karty, tlačidlá)
- Supabase Auth (`@supabase/ssr`): **email+heslo aj Google OAuth**
- Deploy: Vercel

## Landing page (`/`)

Adaptácia CinematicHero template na Telepipe — rovnaká mechanika, naše farby/obsah:

- **Farebná adaptácia:** deep-blue kartu (#162C6D→#0A101D) nahradí čierno-zlatá
  (grafit #111→#000 s jemným zlatým nádychom; progress ring a akcenty zlaté
  namiesto modrej #3B82F6; floating badge ikony zlaté odtiene).
- **Scéna 1 (intro):** tagline gradient text — napr. „Your models never sleep." /
  „AI that turns chats into subscribers." (finálne texty pri implementácii,
  angličtina, predajný tón).
- **Scéna 2 (scroll):** naletí karta s **TELEPIPE** brand textom + iPhone mockup.
  **Obsah telefónu = reklamný príbeh:** Telegram konverzácia (AI odpovedá fanúšikovi),
  progress ring s countrom **„Fans converted"** (namiesto Days Sober), widgety:
  „New Fanvue subscriber 💰", „AI replied · voice message 🎙️". Floating badges:
  „24/7 auto-replies" a „+38 subscribers this week" (ilustračné čísla).
- **Scéna 3 (CTA):** namiesto App Store/Google Play buttonov dva tactile buttony:
  **Get Started** (svetlý, primárny → /register) a **Sign In** (tmavý → /login).
- Fixná blur navigácia (zo SaaS templatu): biele logo + Login / Get Started buttony.
- Pod hero scénou klasické sekcie: features (3–4 karty), how it works (3 kroky:
  Connect Telegram → Set up your model → Watch credits convert), pricing teaser
  (fáza 4), footer.
- GSAP scéna sa na mobile zjednodušuje presne ako v template (scale wrapper,
  responsive pullback) a rešpektuje `prefers-reduced-motion` (bez pinned scrollu,
  statické sekcie).

## Auth

- Supabase Auth: email+heslo (s email confirm) + Google OAuth.
- **Google zatiaľ NEfunkčný zámerne** — button v UI je (disabled + „Available soon"
  tooltip), kód na Google flow pripravený, aktivuje sa na konci keď Marek nastaví
  Google provider v Supabase. Email+heslo funguje plne od začiatku.
- `/login`, `/register` — **SignInPage glass template** (Marekova referencia):
  dvojstĺpcový layout, glass inputy (blur, focus ring — vo fialovej v template →
  u nás ZLATÁ), show/hide heslo, testimonials karty na hero obrázku vpravo
  (u nás: screenshot/render appky alebo abstraktný čierno-zlatý vizuál),
  animate-element stagger animácie. Register = rovnaký štýl s confirm heslom.
- **Prepojenie na accounts:** migrácia 007 — `accounts.id` = `auth.users.id`
  (FK na auth.users, default gen_random_uuid preč) + DB trigger `on auth.users
  insert → insert into accounts (id, email)`. Google aj email flow tak automaticky
  založia účet s 0 kreditmi.
- Middleware chráni `/app/**`; session cez `@supabase/ssr` cookies.

## RLS — klientský prístup k dátam

Fáza 1 nechala tabuľky bez policies (worker ide service key). Fáza 2 pridáva
policies pre klientov (migrácia 007):

- `accounts`: select/update len vlastný riadok (`id = auth.uid()`); `credit_balance_usd`
  update klientom ZAKÁZANÝ (column-level: update len cez view/funkcie — jednoduchšie:
  klient smie update len `email`… v praxi: select only, zmeny robí server/worker).
- `models`: CRUD len kde `account_id = auth.uid()`; `claimed_by/heartbeat_at/status`
  menia len worker+server (klient mení `status` len draft↔active↔paused cez RPC
  `set_model_status` s whitelistom prechodov).
- Tenant tabuľky (persona, behavior, settings, photos, voices, dm_users, dm_messages,
  facts, episodes, …): select/update/insert/delete len kde
  `model_id in (select id from models where account_id = auth.uid())`;
  konverzačné tabuľky (dm_users, dm_messages, facts, episodes, open_loops,
  self_claims, judge_log) **read-only** pre klienta.
- `usage_events`: select len vlastné (`account_id = auth.uid()`), žiadny write.
- `pricing`: žiadny klientský prístup.
- Web používa **user-scoped klienta** (anon key + session) — RLS je jediná obrana,
  service key sa vo web app nepoužíva na klientské operácie (len v server actions,
  ktoré to vyžadujú, napr. login-job orchestrácia — vždy s vlastnou kontrolou
  vlastníctva ako v simona-dashboard `myModel` vzore).

## Telegram connect wizard (`/app/m/[id]/telegram`)

Next.js nevie MTProto → **DB fronta úloh**, spracúva ju worker (má Telethon):

Nová tabuľka `tg_login_jobs` (migrácia 007):
- `id`, `model_id`, `account_id`, `phase` (`send_code`/`code_sent`/`verify_code`/
  `need_password`/`verify_password`/`done`/`error`), `phone`, `code_enc`,
  `password_enc`, `phone_code_hash`, `tmp_session_enc` (medzistav Telethon klienta
  medzi krokmi), `error text`, `created_at`, `updated_at`, `expires_at` (10 min).
- RLS: klient smie insert (send_code s vlastným model_id) a select vlastných
  (bez `*_enc` stĺpcov — column privileges).
- Šifrovanie: **web server dostane ten istý `ENCRYPTION_KEY`** (Vercel env,
  server-only — nikdy v client bundle). Server action šifruje `code_enc`,
  `password_enc` aj `api_hash` pred zápisom (TS port AES-GCM v `web/lib/crypto.ts`,
  kompatibilný formát nonce:ct:tag s worker/src/crypto.py — roundtrip test
  Python↔TS). Worker po použití hodnoty maže + TTL cleanup 10 min. Výslednú
  session šifruje worker do `models.tg_session_enc`.
- Worker: `login_jobs.py` — poller v main loope (každé 2 s, len jobs vo fáze
  vyžadujúcej akciu), Telethon `send_code_request` → `sign_in(code)` →
  `sign_in(password=…)` pri 2FA; výsledná session → encrypt → `models.tg_session_enc`,
  job `done`, phase 1 mechanizmus modelku spustí keď klient klikne Activate.
- Wizard UI kroky: (1) návod my.telegram.org s screenshotmi textovo (api_id/api_hash
  polia), (2) telefón → Send code, (3) SMS kód (+ 2FA heslo ak treba), (4) BotFather
  návod → control bot token, owner chat id (návod s @userinfobot), (5) Activate.
  Polling stavu jobu každé 2 s. Chyby (zlý kód, flood wait) zobrazené z `error`.

## Klientská app (`/app`)

Layout: **AppShell v štýle „Efferd Dashboard"** (Marekova referencia) — bočný
sidebar s ikonkami (lucide-react), sekcie menu, biele logo hore, user menu dole;
obsah = karty na čiernom pozadí so zlatými akcentmi, Framer Motion transitions.
Rovnaké ikonky/menu vzory ako referencia, obsah navrhnutý pre náš biznis
(modelky, konverzácie, kredity). Všetko server components + server actions
(vzor simona-dashboard, ale multi-account).

- **`/app`** — zoznam modeliek (karty so statusom: draft/active/paused/error
  + status_reason), kredit zostatok veľký + „contact us to top up" (fáza 4 nahradí),
  Add model button.
- **`/app/m/[id]/telegram`** — wizard (vyššie) + stav pripojenia + Reconnect.
- **`/app/m/[id]/persona`** — všetky polia `persona` tabuľky (name, age, city,
  language(s), backstory, tone, msg_style, boundaries, funnel_rules, cta_link,
  extra_rules, examples) — formuláre s auto-save (worker ich číta pri každej
  odpovedi, žiadny reštart netreba).
- **`/app/m/[id]/behavior`** — všetky polia `behavior` (mode, heat, slang,
  no_diacritics, activity_waves, TZ, hlasové: voices_enabled, voice_chance,
  voice_tempo, ambience, strength… presne stĺpce z DB, skupinované ako
  v control bote). ElevenLabs kľúč + voice picker = fáza 3 (pole eleven_key
  sa zobrazí ako „coming soon").
- **`/app/m/[id]/photos`** — knižnica: upload do `photos` bucketu
  (cesta `{model_id}/…`), caption/situation/parts/spicy/active — ako dashboard.
- **`/app/m/[id]/chats`** — dm_users zoznam (read-only) + detail konverzácie
  (dm_messages), funnel stage badge.
- **`/app/m/[id]/usage`** — spotreba: graf po dňoch z `usage_events` (charged_usd),
  breakdown per kind, zostatok účtu.
- **`/app/account`** — email, heslo/Google, (fáza 4: billing).

## Mimo rozsahu fázy 2

- Fanvue OAuth + ElevenLabs connect (fáza 3 — karty existujú ako „coming soon")
- Platby/dobíjanie (fáza 4)
- Admin rozhranie pre Mareka (dobíjanie kreditov robí SQL-om / neskôr)

## Testovanie

- Migrácia 007: RLS testy — user A nevidí dáta usera B (SQL testy cez dva JWT).
- Worker login_jobs: unit testy poller stavového automatu (mock Telethon).
- Web: build + typecheck + lint; Playwright smoke (registrácia flow proti
  lokálnemu Supabase alebo mock) — rozsah určí plán.
- Vizuálne: lokálny dev server, kontrola GSAP scény (desktop + mobil viewport).
