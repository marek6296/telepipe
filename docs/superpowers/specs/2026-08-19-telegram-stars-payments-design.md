# Platba cez Telegram Stars — druhá cesta k Pipe Coinom

**Dátum:** 2026-08-19
**Stav:** návrh
**Krypto ostáva hlavná cesta.** Stars sú alternatíva pre toho, kto krypto nechce.

## Ekonomika (overené v oficiálnej tabuľke Telegramu)

Vývojár dostane **vždy $0,013 za Star**, nezávisle od veľkosti balíka.
Používateľ v App Store / Play zaplatí ~$0,02 za Star (30 % si berie Apple/Google,
~5 % Telegram). Pomer je teda **1,538×**.

| Používateľ zaplatí | Stars | Nám ostane |
|---|---|---|
| $4,99 | 250 | $3,25 |
| $9,99 | 500 | $6,50 |
| $14,99 | 750 | $9,75 |
| $19,99 | 1000 | $13,00 |
| $49,99 | 2500 | $32,50 |

**Pravidlo cenníka:** aby nám z balíka ostalo `X` dolárov, faktúra musí znieť na
`ceil(X / 0,013)` Stars. Používateľa to vyjde zhruba na `X × 1,54`.

Pre existujúce balíky:

| Balík | Cena v krypte | Stars | Používateľ zaplatí ~ | Nám ostane ~ |
|---|---|---|---|---|
| Starter | $50 | 3 850 | $77 | $50,05 |
| Creator | $100 | 7 700 | $154 | $100,10 |
| Agency | $250 | 19 250 | $385 | $250,25 |

**Bonusy za objem (+10 %, +20 %) pri Stars NEPLATIA.** Sú to peniaze navyše,
ktoré si môžeme dovoliť pri 1 % poplatku, nie pri 35 %. Klient dostane presne
`priceUsd × 1000` coinov. Krypto tak ostáva zjavne výhodnejšie, čo je zámer.

**Strop na jednu faktúru nie je dokumentovaný.** Preto je počet Stars na balík
**konfigurovateľný v DB**, nie v kóde — pri teste sa overí, či Telegram
19 250 Stars vôbec pustí, a ak nie, veľké balíky sa cez Stars jednoducho
neponúknu.

## Ako to funguje

Digitálny tovar sa v Telegrame smie predávať **výhradne v Stars** (`currency:
"XTR"`), `provider_token` sa nechá prázdny — **žiadna platobná brána netreba.**

```
web /app/billing  →  „Pay with Telegram"  →  t.me/<shopbot>?start=<token>
      ↓
bot: /start <token>  →  overí token, pozná account_id  →  sendInvoice(XTR)
      ↓
pre_checkout_query   →  answerPreCheckoutQuery(ok)
      ↓
successful_payment   →  settle_star_payment()  →  coiny na účte
```

**Naviazanie na účet** rieši jednorazový token z webu (`star_link_tokens`,
platnosť 30 min). Faktúra si potom v poli `payload` (1–128 B, používateľ ho
nevidí) nesie `account_id` + `pack_id`. Token sa spotrebuje pri vytvorení
faktúry, nie pri platbe — aby jeden token nevyrobil desať faktúr.

**Idempotencia:** `telegram_payment_charge_id` je unikátny kľúč v ledgeri,
presne ako `crypto_deposit_events`. Dvojité doručenie updatu coiny nepripíše
dvakrát.

## Kde to žije

**V webe, nie vo workeri** — rovnako ako [[TelePipe Admin Bot]]. Je to bezstavový
webhook, worker s tým nemá nič spoločné a nemá dôvod sa kvôli platbám deployovať.

Nový **verejný** bot (napr. `@TelePipeShopBot`). ZÁMERNE nie `@TelePipe_help_bot`:
ten je Marekov súkromný admin kanál, ktorý prijíma príkazy len z jeho chatu.
Zmiešať s ním verejného bota, ktorému môže napísať ktokoľvek, by tú kontrolu
zrušilo.

## Dátový model

```
accounts.telegram_user_id  bigint     -- kto platil (nepovinné, pre podporu)
star_link_tokens           token, account_id, pack_id, custom_usd, expires_at, used_at
star_payments              charge_id (unique), account_id, telegram_user_id,
                           stars, coins, credited_usd, refunded_at, created_at
```

RPC `settle_star_payment(charge_id, account_id, stars, coins, usd)` — security
definer, service-only, idempotentná cez unique index na `charge_id`.

## Refundy

Telegram má `refundStarPayment` a používateľ si o vrátenie môže požiadať sám.
Musíme vedieť coiny odobrať:

- príde `refunded_payment` update → `refund_star_payment(charge_id)`
- coiny sa odpočítajú; **zostatok smie ísť do mínusu**, inak by stačilo minúť
  ich pred žiadosťou o refund a služba by bola zadarmo
- záporný zostatok = účet neodpisuje (existujúca kontrola kreditu to už rieši)
- Marek dostane notifikáciu do admin bota

## Čo tento návrh ZÁMERNE nerobí

- **Nepredáva obsah fanúšikom.** Toto je predaj kreditu na AI službu klientom.
  Fanúšik platiaci modelke za obsah cez Stars je iný produkt a iné pravidlá —
  overiť zvlášť.
- **Žiadne predplatné cez Stars** (Telegram to vie, ale náš model je kredit).
- **Žiadne bonusy za objem** — viď vyššie.

## Overenie

- migrácia so sondou (idempotencia, RLS, klient si coiny nepripíše)
- `npm run typecheck`, `lint`, `build`
- test v **Telegram test environment** (Stars sa tam dajú testovať zadarmo)
- jedna reálna platba najmenšieho balíka → overiť `getStarTransactions`
  a skutočný net oproti tabuľke
