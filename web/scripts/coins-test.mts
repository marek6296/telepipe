/**
 * Pipe Coins — prepočet, formátovanie a hlavne INVARIANT ZISKOVOSTI balíkov.
 *
 * Testuje sa to, čo nás môže stáť peniaze: aby sa do cenníka nedal pridať
 * balík, kde klient zaplatí veľa a my na ňom prerobíme. Rovnica je jedna
 * jediná a musí sedieť na tú, ktorou sa coiny naozaj míňajú:
 *
 *     zisk = cena − (coiny / 1000) / multiplier
 *
 * (Zostatok sa odpočítava účtovanou cenou = nákupka Atlasu × multiplier,
 * viď `record_usage` v migrácii 021 a `MeteredLlm._bill_inner` vo workeri.)
 *
 * Spustenie:  npm run test:coins
 * (Node 26 vie .ts spustiť priamo cez type stripping, netreba build krok.)
 */
import {
  BILLING_MULTIPLIER,
  COINS_PER_REPLY,
  COINS_PER_USD,
  COIN_PACKS,
  CUSTOM_MAX_USD,
  CUSTOM_MIN_USD,
  assertPacksProfitable,
  customBonusPct,
  customCoinsForUsd,
  coins,
  coinsLabel,
  coinsPerDollar,
  coinsPrecise,
  coinsToUsd,
  estimatedReplies,
  formatCoins,
  maxProfitableCoins,
  packAtlasCostUsd,
  packMarginUsd,
  toCoins,
  type CoinPack,
} from "../lib/coins.ts";

let failed = 0;
let passed = 0;

function check(condition: boolean, message: string): void {
  if (condition) {
    passed++;
    return;
  }
  failed++;
  console.error(`✗ ${message}`);
}

function eq(actual: unknown, expected: unknown, message: string): void {
  check(
    actual === expected,
    `${message} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );
}

function throws(fn: () => void, message: string): void {
  try {
    fn();
  } catch {
    passed++;
    return;
  }
  failed++;
  console.error(`✗ ${message} — it did not throw`);
}

/* ------------------------------------------------------------- prepočet USD ↔ coiny */
{
  eq(COINS_PER_USD, 1000, "1 000 Pipe Coins is one dollar of spendable balance");
  eq(toCoins(1), 1000, "$1 is 1 000 coins");
  eq(toCoins("9.96"), 9960, "numeric-as-string from Supabase converts too");
  eq(coinsToUsd(50_000), 50, "50 000 coins is $50 of balance");
  eq(coinsToUsd(toCoins(3.25)), 3.25, "the conversion round-trips");
  eq(toCoins(null), 0, "a missing balance is zero coins, not NaN");
  eq(toCoins(undefined), 0, "an undefined balance is zero coins");
}

/* ------------------------------------------------------------------ formátovanie */
{
  eq(coins(9.96), "9,960", "balances get a thousands separator");
  eq(coins(0), "0", "an empty balance shows as 0");
  eq(coins(0.0055), "6", "coins() rounds to whole coins");
  eq(coinsPrecise(0.005487), "5.5", "a single reply keeps one decimal instead of rounding to 5");
  eq(coinsPrecise(0.00137), "1.4", "the cheapest measured reply is still visible");
  eq(coinsPrecise(2.5), "2,500", "above 100 coins we drop the decimal and group");
  eq(coinsPrecise(0), "0", "zero stays zero, not 0.0");
  eq(coinsLabel(9.96), "9,960 Pipe Coins", "the unit is spelled out where context needs it");
  eq(coinsLabel(0.001), "1 Pipe Coin", "one coin is singular");
  eq(formatCoins(110_000), "110,000", "pack sizes are grouped");
}

/* ---------------------------------------------------------- odhad počtu odpovedí */
{
  // COINS_PER_REPLY je all-in náklad na SKUTOČNE odoslanú odpoveď, zaokrúhlený
  // nahor — nie medián riadku `kind='chat'` (do toho padá aj `structured` a
  // wizard, viď komentár v coins.ts). Podstreliť ho znamená sľubovať klientovi
  // viac odpovedí, než za svoje coiny dostane.
  // Hranica je 17: nameraných 15.5 pri okne 12 správ + odhad +10–15 % za
  // dvojnásobné kontextové okno (CONTEXT_MESSAGES 24, worker config.py).
  // Keď sa okno alebo cenník modelov pohne, prepočítaj v coins.ts a uprav
  // aj túto hranicu.
  check(
    COINS_PER_REPLY >= 17,
    "the advertised per-reply cost is not below the measured all-in cost per sent reply",
  );
  // Konkrétne počty sa odvodzujú z konštanty — test stráži, že sa marketing
  // (stránka /pricing číta to isté číslo) nerozíde s prepočtom, nie konkrétnu
  // hodnotu konštanty samotnú. Tú stráži hranica vyššie.
  eq(estimatedReplies(50_000), Math.floor(50_000 / COINS_PER_REPLY), "$50 reply estimate derives from the constant");
  eq(estimatedReplies(110_000), Math.floor(110_000 / COINS_PER_REPLY), "$100 reply estimate derives from the constant");
  eq(estimatedReplies(300_000), Math.floor(300_000 / COINS_PER_REPLY), "$250 reply estimate derives from the constant");
}

/* ------------------------------------------------- INVARIANT: balík nesmie prerobiť */
{
  eq(BILLING_MULTIPLIER, 2, "the shipped multiplier is 2× — half of every dollar goes to Atlas");
  eq(maxProfitableCoins(50), 100_000, "$50 breaks even at 100 000 coins");
  eq(maxProfitableCoins(100), 200_000, "$100 breaks even at 200 000 coins");
  eq(maxProfitableCoins(250), 500_000, "$250 breaks even at 500 000 coins");

  // Cenník, ktorý naozaj shipujeme.
  assertPacksProfitable();
  passed++;

  const expected = [
    { id: "coins-50", price: 50, coins: 50_000, perDollar: 1000, atlas: 25, margin: 25 },
    { id: "coins-100", price: 100, coins: 110_000, perDollar: 1100, atlas: 55, margin: 45 },
    { id: "coins-250", price: 250, coins: 300_000, perDollar: 1200, atlas: 150, margin: 100 },
  ];
  eq(COIN_PACKS.length, expected.length, "three packs ship");
  for (const want of expected) {
    const pack = COIN_PACKS.find((p) => p.id === want.id);
    check(Boolean(pack), `pack ${want.id} exists`);
    if (!pack) continue;
    eq(pack.priceUsd, want.price, `${want.id} costs $${want.price}`);
    eq(pack.coins, want.coins, `${want.id} gives ${want.coins} coins`);
    eq(coinsPerDollar(pack), want.perDollar, `${want.id} is ${want.perDollar} coins per dollar`);
    eq(packAtlasCostUsd(pack), want.atlas, `${want.id} costs us $${want.atlas} at Atlas if fully spent`);
    eq(packMarginUsd(pack), want.margin, `${want.id} keeps $${want.margin} margin`);
  }

  // Marekov pôvodný príklad ($100 → 70 000) je ziskový, ale kurzovo horší než
  // $50 → 50 000. Nesmie prejsť — inak by sme shipli balík, ktorý nikto nekúpi.
  const marekOriginal: CoinPack[] = [
    { ...COIN_PACKS[0] },
    { ...COIN_PACKS[1], coins: 70_000 },
  ];
  throws(
    () => assertPacksProfitable(marekOriginal),
    "a bigger pack with a worse rate is rejected",
  );

  // A toto je ten prípad, kvôli ktorému invariant existuje: bonus ≥ 100 %.
  const tooGenerous: CoinPack[] = [{ ...COIN_PACKS[0], id: "coins-boom", coins: 100_001 }];
  throws(
    () => assertPacksProfitable(tooGenerous),
    "a pack above the break-even ceiling is rejected loudly",
  );
  const exactlyBreakEven: CoinPack[] = [{ ...COIN_PACKS[0], id: "coins-zero", coins: 100_000 }];
  throws(
    () => assertPacksProfitable(exactlyBreakEven),
    "break-even is not 'in the plus' either — it is rejected",
  );

  // Ziskovosť visí na multiplieri. Keby ho niekto v `pricing` stiahol na 1×,
  // dnešný cenník okamžite prerába — a musí to prasknúť, nie prejsť.
  throws(
    () => assertPacksProfitable(COIN_PACKS, 1),
    "at multiplier 1× today's ladder loses money and the guard says so",
  );
  throws(() => assertPacksProfitable(COIN_PACKS, 0), "a zero multiplier is rejected");

  // Nad 2× je priestor väčší — sanity check, že to nie je natvrdo napísané.
  assertPacksProfitable(COIN_PACKS, 3);
  passed++;
}

/* ------------------------------------------------- custom top-up (vlastná suma) */
{
  eq(CUSTOM_MIN_USD, 5, "custom top-up starts at $5");
  eq(CUSTOM_MAX_USD, 5000, "custom top-up is capped at $5 000");

  // Bonusové prahy = tie isté ako balíky, aby cenník nemal dve pravdy.
  eq(customBonusPct(5), 0, "no bonus below $100");
  eq(customBonusPct(99.99), 0, "still no bonus at $99.99");
  eq(customBonusPct(100), 10, "+10% from $100");
  eq(customBonusPct(249.99), 10, "+10% below $250");
  eq(customBonusPct(250), 20, "+20% from $250");

  eq(customCoinsForUsd(5), 5_000, "$5 buys 5 000 coins");
  eq(customCoinsForUsd(8), 8_000, "$8 buys 8 000 coins");
  eq(customCoinsForUsd(8.5), 8_500, "cents are honoured");
  eq(customCoinsForUsd(100), 110_000, "custom $100 equals the Creator pack");
  eq(customCoinsForUsd(250), 300_000, "custom $250 equals the Agency pack");

  // INVARIANT: žiadna custom suma nesmie prerobiť — kurz musí ostať ostro
  // pod break-even stropom (multiplier × 1000 coinov/$).
  for (const usd of [CUSTOM_MIN_USD, 50, 99.99, 100, 249.99, 250, 1000, CUSTOM_MAX_USD]) {
    const coinsBought = customCoinsForUsd(usd);
    check(
      coinsBought < maxProfitableCoins(usd),
      `custom $${usd} stays profitable (${coinsBought} coins < ceiling ${maxProfitableCoins(usd)})`,
    );
  }
}

console.log(`${passed} passed, ${failed} failed`);
if (failed > 0) process.exitCode = 1;
