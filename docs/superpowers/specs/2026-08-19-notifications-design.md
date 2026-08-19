# Notifikácie — zvonček v appke

**Dátum:** 2026-08-19
**Vrstva:** 2 z 3 (gating ✅ → **notifikácie** → chat)
**Stav:** návrh, čaká na plán

## Problém

Veci sa dejú mimo obrazovky a klient sa o nich dozvie neskoro alebo nikdy:

- Marek schváli prístup — človek sedí na `/locked` a nevie o tom.
- Worker zhodí modelku do `error`, alebo si po Telegram flood warningu sám
  nastaví `settings.ai_paused` — klient pozerá na dashboard a diví sa, prečo
  nikto neodpisuje.
- Dôjdu Pipe Coiny a modelka zmĺkne uprostred konverzácie.

Dnes v aplikácii **žiadne notifikácie neexistujú**. Jediná spätná väzba je
toast v admin sekcii (`components/app/admin/toast.tsx`) a inline `role="alert"`
hlášky z formulárov. Nič, čo prežije reload.

## Čo staviame

Tabuľka `notifications` (jedna na účet), **červený bod na zvončeku** v hlavičke
appky a rozbaľovací zoznam. Žiadne toasty, žiadny zvuk — bod drží, kým si to
človek neprečíta.

Plus jedna vec navyše: **`/locked` sa po schválení prepne sám**, bez refreshu.
To je zároveň prvé nasadenie Supabase Realtime v tomto projekte — a schválne,
lebo vrstva 3 (chat) na ňom celá stojí. Radšej ho vyskúšame na jednej udalosti
než rovnou na chate.

### Čo notifikáciu vyrobí

| Druh (`kind`) | Kedy | Kto to spustí |
|---|---|---|
| `access_approved` | Marek schváli žiadosť | `decide_access_request()` — jediné jadro z vrstvy 1 |
| `access_rejected` | Marek zamietne | to isté jadro |
| `model_error` | `models.status` prejde na `error` | trigger na `models` |
| `model_muted` | `settings.ai_paused` naskočí na `true` | trigger na `settings` |
| `credits_low` | zostatok klesne pod prah | trigger na `accounts` |

**Worker sa nedotýkame ani riadkom.** Všetky tri „prevádzkové" notifikácie
vznikajú z triggerov nad zmenami, ktoré worker do databázy zapisuje aj dnes.
To je celý dôvod, prečo je to takto: keby notifikácie posielal worker, museli by
sme ho meniť pri každom novom druhu — a hlavne by ich nevyrobil nikdy, keď zmenu
spraví web alebo Marek ručne v SQL.

**`paused` notifikáciu nerobí.** To je klientov vlastný power button; upozorňovať
ho na to, čo práve klikol, je otravné.

### Prah pre `credits_low`

$5 zostatku (≈ 5000 Pipe Coinov). Účty s `unlimited` sa preskakujú — tým
nikdy nič nedochádza.

## Dátový model

### `notifications`

| Stĺpec | Typ | Poznámka |
|---|---|---|
| `id` | uuid pk | |
| `account_id` | uuid → accounts | on delete cascade |
| `kind` | text | whitelist v `check` |
| `title` | text | jeden riadok |
| `body` | text | voliteľný detail |
| `href` | text | kam klik vedie (`/app/m/<id>/telegram`, `/app/billing`) |
| `read_at` | timestamptz | null = neprečítané |
| `created_at` | timestamptz | |

Index `(account_id, created_at desc)` a partial `(account_id) where read_at is null`
— zvonček sa pýta „mám niečo neprečítané?" pri každom načítaní stránky.

### RLS

- SELECT: vlastné riadky
- UPDATE: vlastné riadky, **len stĺpec `read_at`** (column grant) — nikto si
  nemá prepísať text vlastnej notifikácie
- INSERT/DELETE: **žiadne** pre `authenticated`. Zapisujú výhradne triggery
  a security-definer funkcie.

### `notify_account()` — jediné miesto, kde notifikácia vzniká

```
notify_account(p_account uuid, p_kind text, p_title text,
               p_body text, p_href text, p_dedupe interval) → uuid
```

Security definer. **Dedupe je jej hlavná úloha, nie doplnok:** `credits_low` by
sa inak vyrobila pri každom jednom LLM volaní pod prahom a klient by mal do
minúty stovku notifikácií. Pravidlo: ak pre daný účet a `kind` existuje
notifikácia mladšia než `p_dedupe`, nová sa nevytvorí a vráti sa `null`.

### Realtime

`alter publication supabase_realtime add table notifications`. Realtime v Supabase
rešpektuje RLS, takže každý klient dostane iba svoje riadky. Počúvame **len
`INSERT`** — nič iné zvonček nepotrebuje.

## Web

**Nové**

- `web/lib/notifications.ts` — typy + serverové čítanie (posledných 20 + počet
  neprečítaných).
- `web/app/app/notifications-actions.ts` — `markReadAction`, `markAllReadAction`.
- `web/components/app/notification-bell.tsx` — zvonček, bod, rozbaľovací zoznam,
  realtime subscription.
- `web/components/app/live-unlock.tsx` — na `/locked`; keď príde
  `access_approved`, spraví `router.refresh()` a stránka sa sama prepne do appky.

**Zmeny**

- `web/components/app/app-shell.tsx` — zvonček do hlavičky.
- `web/app/app/layout.tsx` — dotiahne počet neprečítaných a pošle ho do shellu.
- `web/app/locked/page.tsx` — vloží `<LiveUnlock />`.

## Čo tento návrh ZÁMERNE nerieši

- **Mŕtvy worker (stale heartbeat).** Trigger ho nechytí — nikto nič nezapisuje,
  keď proces spadne. Chce to cron, ktorý skenuje `heartbeat_at`; pridáme ho
  k existujúcemu `/api/payments/reconcile` cronu, ak sa ukáže, že to treba.
- **Oznámenie od admina všetkým** — Marek ho v tejto vrstve nechcel.
- **E-mail a push.** Mailová služba v projekte nie je.
- **Notifikácie z chatu** — vrstva 3. `notify_account()` je preto napísaná
  všeobecne, aby jej stačilo pridať `kind`.

## Overenie

- migrácia so sondou (vzor 021/024): dedupe naozaj deduplikuje; cudzí človek
  nevidí cudzie notifikácie; `authenticated` si nevie vyrobiť ani zmazať
  notifikáciu; prepis `title` neprejde, prepis `read_at` áno; schválenie
  žiadosti vyrobí presne jednu notifikáciu
- `npm run typecheck`, `npm run lint`, `npm run build`
- ručne: schválenie → `/locked` sa prepne bez refreshu; bod na zvončeku zmizne
  po prečítaní a neobjaví sa po reloade
