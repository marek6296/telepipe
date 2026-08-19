# Prístup na pozvanie — Standard+ a schvaľovanie žiadostí

**Dátum:** 2026-08-19
**Vrstva:** 1 z 3 (gating → notifikácie → chat)
**Stav:** návrh schválený, čaká na plán

## Problém

Registrácia je otvorená a kto sa zaregistruje, dostane hneď plnú aplikáciu.
Marek to takto nechce: na začiatku nesmie prísť veľa ľudí naraz, lebo každý
používateľ znamená bežiaceho workera, Telegram účet a spotrebu Atlasu. Potrebuje
ventil — **registrovať sa smie ktokoľvek, pracovať až po jeho schválení.**

Dnes v systéme žiadne gating podľa plánu neexistuje. `accounts.plan` (`free` /
`vip`) riadi jedinú vec: cenu. Funkčné brány sú tri a ani jedna sa na plán
nepozerá — kredit (`lib/credits.ts`), rola (`requireAdmin`) a typ modelky
(`lib/model-types.ts`). Zámok teda staviame od nuly.

## Čo staviame

Tretí balík **Standard+** (`free_plus`). Účet je odomknutý, keď platí aspoň
jedno:

- `plan in ('free_plus', 'vip')`
- `role in ('admin', 'superadmin')`

Zamknutý účet nevidí z `/app` nič okrem jednej obrazovky: stav žiadosti,
tlačidlo *Request access* a (od vrstvy 3) chat. Keď Marek žiadosť schváli, účet
prejde na `free_plus` a otvorí sa mu presne to, čo má dnes `free`.

### Prečo tretia hodnota v `plan`, a nie nový stĺpec

Zvažovali sme samostatný `accounts.access_status`. Bolo by to ortogonálnejšie
(plán = peniaze, prístup = povolenie), ale Marek chce prístup spravovať **ako
balík v tom istom dropdowne v admin paneli**, kde dnes vidí Standard/VIP. Dva
nezávislé prepínače pre jednu myšlienku by boli len zdroj nesúladu.

Rozšírenie je bezpečné, lebo jediné miesto, kde plán ovplyvňuje peniaze, je
`case when v_plan = 'vip'` v `record_usage` (021). `free_plus` padne do vetvy
`else` a účtuje sa **presne ako `free` dnes** — marža `pricing.multiplier`.
Fakturáciu sa nedotýkame ani riadkom.

### Existujúce účty

V databáze sú dva: Marek (`superadmin`) a kamarát (`vip`). Oboch odomyká
pravidlo, nie migrácia — **žiadny dátový presun netreba.** Zámok tak platí len
na účty, ktoré vzniknú odteraz.

## Kde je skutočný zámok

Nie v UI a nie v server action. Zámok je v **RLS na `models` INSERT**.

Toto je celý trik: každá tenant tabuľka (persona, behavior, settings, dm_users,
dm_messages, photos, voices, fanvue…) visí cez `model_id` na vlastníctve
modelky. Kto si nevie založiť modelku, nemá sa čoho chytiť — ani ručne
napísanou URL, ani priamym volaním PostgREST. Jedna brána namiesto dvadsiatich.

Druhá brána je nákup Pipe Coinov: **pred schválením od nikoho neberieme peniaze.**
Tá musí byť v route handleri `/api/payments/topup`, nie v RLS — depozitnú adresu
zakladá service klient, ktorého sa RLS netýka. Rola `authenticated` má na
platobných tabuľkách jediný grant, `select (invoice_url)`, takže iná cesta
k platbe neexistuje; ak by niekto grant pridal, treba doplniť aj RLS policy.

Zvyšok je pohodlie, nie bezpečnosť:

| Vrstva | Kde | Čo robí |
|---|---|---|
| RLS `models` INSERT | migrácia | **skutočná hranica** — zamknutý si nezaloží modelku |
| `isUnlocked()` v topup route | `/api/payments/topup` | **skutočná hranica** — zamknutý si nekúpi coiny |
| `requireUnlocked()` | `web/lib/models.ts` | server-side redirect na `/locked` |
| `/app` layout | `web/app/app/layout.tsx` | zamknutý nevidí workspace nav |

## Dátový model

### `accounts_plan_check`

```
check (plan in ('free', 'free_plus', 'vip'))
```

Constraint sa nahrádza pod rovnakým menom (rovnaká konvencia ako 024, aby sa
v `pg_constraint` nehromadili historické verzie).

### `access_requests`

| Stĺpec | Typ | Poznámka |
|---|---|---|
| `id` | uuid pk | |
| `account_id` | uuid → accounts | |
| `status` | text | `pending` / `approved` / `rejected` |
| `message` | text | čo o sebe napísal žiadateľ, max 1000 znakov |
| `created_at` | timestamptz | |
| `decided_at` | timestamptz | |
| `decided_by` | uuid → accounts | ktorý admin rozhodol |
| `decided_note` | text | dôvod zamietnutia, vidí ho žiadateľ |

Partial unique index na `(account_id) where status = 'pending'` — jeden účet má
naraz najviac jednu otvorenú žiadosť. Žiadateľ vidí RLS-om len svoje riadky
a nesmie si prepísať `status`; zapisuje výhradne RPC.

### Funkcie

- `account_unlocked(uuid) → boolean` — security definer, **jediný zdroj pravdy**.
  Používa ju RLS aj appka, aby sa pravidlo nedalo rozísť na dvoch miestach.
- `request_access(p_message text) → uuid` — žiadateľ o seba. Idempotentné: ak už
  má otvorenú žiadosť, vráti jej id namiesto vytvorenia druhej. Odmietne účet,
  ktorý je už odomknutý.
- `admin_list_access_requests() → setof …` — pre admin panel, ako ostatné
  `admin_list_*` (security definer + `is_admin()`).
- `admin_decide_access_request(p_id uuid, p_approve boolean, p_note text) → text`
  — pri `true` nastaví `plan = 'free_plus'`, zapíše audit do
  `credit_adjustments` (amount 0, rovnako ako `admin_set_plan`) a označí žiadosť.

### `admin_set_plan`

Prepis: zoznam `('free', 'free_plus', 'vip')`. Obyčajný admin smie prepínať
`free ↔ free_plus`, VIP ostáva superadmin-only v oboch smeroch — pravidlo z 024
sa nemení, len sa mu rozšíri zoznam bežných balíkov.

### Sonda v migrácii

Rovnaký postup ako 021/024 — `do $$` blok, ktorý na existujúcom nesuperadmin
účte skúsi zakázané ťahy a na konci sa odroluje sentinel výnimkou. Musí overiť:

1. `accounts_plan_check` prijme `free_plus` a odmietne neznámy balík
2. `admin_set_plan` pustí `free_plus` obyčajnému adminovi
3. VIP guard z 024 ďalej drží (oboma smermi)
4. `account_unlocked()` vráti `false` pre `free`, `true` pre `free_plus`, `vip`,
   `admin`, `superadmin`
5. zamknutý účet **neprejde** cez RLS INSERT do `models`
6. odomknutý účet cez ten istý INSERT **prejde**
7. `record_usage` účtuje `free_plus` s maržou, nie za nákupku
8. sonda po sebe nenechá zmenený riadok ani audit záznam

Bod 5 a 7 sú tu podstatné — bez nich by migrácia mohla prejsť aj s dierou.

## Web

**Nové**

- `web/lib/access.ts` — `isUnlocked(account)`, `PLAN_LOCKED`. Klientsky bezpečné
  (žiadny `next/headers`), aby sa dalo importovať aj do komponentu.
- `requireUnlocked()` ide do `web/lib/models.ts` k `requireUser()`/`getAccount()`,
  lebo robí redirect a číta session — rovnaké rozdelenie ako
  `admin-ui.ts` (browser) vs `admin.ts` (server).
- `web/app/locked/page.tsx` — jediná obrazovka zamknutého účtu. Stav
  (`Čaká na schválenie` / `Zamietnuté` + dôvod / `Ešte si nepožiadal`), formulár
  s krátkou správou, tlačidlo *Request access*.
- `web/app/locked/actions.ts` — `requestAccessAction`, volá `request_access`
  a odošle Telegram ping.
- `web/app/app/admin/requests/page.tsx` + tabuľka — nová záložka v admin paneli
  vedľa Users / Models / Usage. Approve / Reject na riadok.
- `web/lib/telegram-admin.ts` — odoslanie správy na Bot API.
- `web/app/api/telegram/admin/route.ts` — webhook pre tlačidlá v Telegrame.

**Zmeny**

- `web/lib/admin-ui.ts` — `PLANS`, `PLAN_LABEL` (`free_plus → "Standard+"`),
  `PLAN_HINT`, `ADMIN_ASSIGNABLE_PLANS`. Dropdown v `users-table.tsx` sa
  prekreslí sám, nemení sa.
- `web/app/app/layout.tsx` — zamknutý účet dostane redirect na `/locked`
  a shell mu nevykreslí workspace nav.
- Server actions, ktoré zakladajú modelku a kupujú coiny, dostanú
  `requireUnlocked()`.

Poradie balíkov v `PLANS` je `free, free_plus, vip` — `vip` ostáva posledný,
lebo `ADMIN_ASSIGNABLE_PLANS` ho odfiltrúva a nikde sa neinzeruje.

## Telegram ping Marekovi

**Samostatný súkromný bot, ktorý si Marek vyrobí cez @BotFather.** Nemá nič
spoločné s control botmi modeliek — worker sa nedotýkame vôbec. Správu posiela
priamo web cez Bot API.

```
ENV: TELEGRAM_ADMIN_BOT_TOKEN
     TELEGRAM_ADMIN_CHAT_ID        (Marekov súkromný chat)
     TELEGRAM_ADMIN_WEBHOOK_SECRET (generujeme my)
```

Príde: *„Nová žiadosť o prístup — email · správa"* + inline tlačidlá
**Approve / Reject**. Tlačidlo trafí `/api/telegram/admin`, ktorý zavolá tú istú
RPC ako web.

**Bezpečnosť webhooku — tri nezávislé kontroly:**

1. hlavička `X-Telegram-Bot-Api-Secret-Token` sedí s `TELEGRAM_ADMIN_WEBHOOK_SECRET`
2. `callback_query.message.chat.id` sedí s `TELEGRAM_ADMIN_CHAT_ID`
3. RPC sa volá pod Marekovým účtom cez service client a `is_admin()` platí ďalej

Aj keby niekto bota našiel a napísal mu, neschváli nič.

Odoslanie pingu **nesmie zhodiť žiadosť**: keď Telegram nedostupný alebo ENV
chýba, žiadosť sa aj tak uloží a v admin paneli je vidieť. Ping je doručovacia
cesta, nie stav.

## Rozhodnutia, ktoré si vieme neskôr rozmyslieť

- **Odobratie Standard+** zamkne web, ale **modelky sa nezmažú ani nezastavia** —
  worker beží cez `service_role`, RLS sa ho netýka. Nič sa nestratí. Automatické
  pauzovanie replík pri odobratí vieme dorobiť, ak to bude treba.
- **Zamietnutá žiadosť** sa dá podať znova (partial unique index platí len na
  `pending`). Žiadny cooldown zatiaľ nerobíme — pri desiatkach používateľov je
  to problém, ktorý neexistuje.

## Návrh na ďalšie vrstvy

Vrstvy 2 a 3 dostanú vlastný spec. Tu len to, čo nesmieme teraz zabetónovať:

- **Vrstva 2 — notifikácie.** Tabuľka `notifications` per účet, Supabase
  Realtime, zvonček v shelli. Schválenie žiadosti bude jej prvý producent, preto
  `admin_decide_access_request` musí ostať jediným miestom, kde sa schvaľuje —
  notifikáciu doňho neskôr len dopíšeme.
- **Vrstva 3 — chat.** Dva verejné kanály: **Community** pre všetkých vrátane
  zamknutých a **Community+** len pre odomknutých, plus DM na Mareka. Preto
  `/locked` **nesmie** byť slepá ulica — chat sa naň musí dať pripojiť, a
  `account_unlocked()` bude rozhodovať aj o prístupe do Community+.

## Overenie

- `npm run build` + typecheck vo `web/`
- migrácia prejde vlastnou sondou (8 bodov vyššie)
- ručne: nová registrácia → `/locked` → request → ping do Telegramu →
  approve → workspace sa otvorí, Marekov a kamarátov účet sa nezmenia
