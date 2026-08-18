/**
 * Pipe Coins — jednotka, v ktorej klient vidí svoj zostatok a spotrebu.
 *
 * PREČO JE TO IBA PREZENTÁCIA A NIE NOVÝ TYP V DATABÁZE
 * ----------------------------------------------------
 * Účtovanie beží naostro: `accounts.credit_balance_usd` je živý zostatok,
 * `usage_events.charged_usd` / `atlas_cost_usd` je ledger, ktorý sa dopĺňa
 * dvoma nezávislými cestami (`worker/src/credits.py` a `web/lib/credits.ts`)
 * a odpočet robí `record_usage` v databáze. Zmena internej jednotky by musela
 * naraz prepísať každý existujúci riadok ledgeru, obe účtovacie cesty aj
 * kreditovú bránu vo workerovi — a to všetko za nulový produktový prínos,
 * lebo klientovi stačí, keď mu to isté číslo ukážeme inak.
 *
 * Preto: **v DB ostávajú doláre, coiny sú výhradne zobrazovacia vrstva.**
 * Prepočet žije TU a nikde inde — kto potrebuje coiny, importuje si ich odtiaľto.
 *
 *     coins = round(usd × COINS_PER_USD)
 *
 * ČO OSTÁVA V DOLÁROCH (zámerne)
 * ------------------------------
 * • `worker/src/credits.py` — kreditová brána (`balance <= 0`) aj celé
 *   účtovanie. Coiny sú kladný násobok dolára, takže znamienko sa nemení
 *   a brána nemá dôvod o coinoch vedieť.
 * • Admin pohľad na peniaze (`Atlas cost`, `Margin`) — to je naša nákupka
 *   a naša marža v reálnych dolároch, nie klientská mena.
 * • `admin_add_credit` a `credit_adjustments` — ledger úprav je v USD.
 */

// Relatívne cesty s príponou zámerne: `scripts/coins-test.mts` tento modul
// spúšťa priamo cez Node (type stripping), a ten alias `@/` nepozná.
import { toNumber } from "./format.ts";
import { DEFAULT_MULTIPLIER } from "./pricing.ts";

/** 1 Pipe Coin = $0.001 zostatku. 1 000 coinov = $1. */
export const COINS_PER_USD = 1000;

export const COIN_NAME = "Pipe Coin";
export const COIN_NAME_PLURAL = "Pipe Coins";

/* -------------------------------------------------------------------------- */
/*  Prepočet a formátovanie                                                    */
/* -------------------------------------------------------------------------- */

const GROUPED = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const GROUPED_1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** USD (Supabase vracia numeric ako string) → coiny, nezaokrúhlené. */
export function toCoins(value: number | string | null | undefined): number {
  return toNumber(value) * COINS_PER_USD;
}

/** Coiny → USD. Opačný smer potrebuje len cenník balíkov. */
export function coinsToUsd(coinCount: number): number {
  return coinCount / COINS_PER_USD;
}

/**
 * `$9.96` → `9,960`. Pre zostatky a súčty — celé coiny s oddeľovačom tisícov.
 */
export function coins(value: number | string | null | undefined): string {
  return GROUPED.format(Math.round(toCoins(value)));
}

/**
 * Ako `coins`, ale drobné sumy nezahodí na nulu: jedna odpoveď stojí jednotky
 * coinov, takže pod 100 ukazujeme jedno desatinné miesto (`5.5`).
 */
export function coinsPrecise(value: number | string | null | undefined): string {
  const n = toCoins(value);
  return Math.abs(n) < 100 && !Number.isInteger(n) ? GROUPED_1.format(n) : GROUPED.format(Math.round(n));
}

/** `9,960 Pipe Coins` — tam, kde jednotka nie je zrejmá z okolia. */
export function coinsLabel(value: number | string | null | undefined): string {
  const n = Math.round(toCoins(value));
  return `${GROUPED.format(n)} ${n === 1 ? COIN_NAME : COIN_NAME_PLURAL}`;
}

/** Coiny (už ako počet, nie USD) s oddeľovačom tisícov — pre cenník balíkov. */
export function formatCoins(coinCount: number): string {
  return GROUPED.format(Math.round(coinCount));
}

/* -------------------------------------------------------------------------- */
/*  Koľko stojí jedna odpoveď                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Odmeraná cena jednej ODOSLANEJ odpovede — all-in, zaokrúhlená nahor.
 *
 * POZOR NA `kind='chat'` — NIE JE TO „jedna odpoveď"
 * -------------------------------------------------
 * Do `chat` padá aj každé `structured` volanie workera (sudca, pamäťové
 * tvrdenia, fakty, recall) a aj beh AI wizardu v appke (persona builder,
 * schedule builder). Na Simone to bolo 363 riadkov `chat` proti 258 naozaj
 * odoslaným odpovediam — 1.41 riadku na odpoveď. Kto delí nákladom na riadok
 * `chat`, dostane číslo takmer trikrát nižšie, než klient reálne minie.
 *
 * Správny základ je preto CELÝ náklad delený počtom skutočne odoslaných
 * odpovedí (`dm_messages.role='assistant'`).
 *
 * Zdroj (2026-08-18, Simona, posledných 7 dní živej prevádzky):
 *
 *     258 odpovedí, atlas spolu $1.9983  →  $0.00775 na odpoveď
 *     (all-in: chat + summary + audio, teda aj pamäť a prepis hlasoviek)
 *     × multiplier 2.0  =  $0.0155  =  15.5 coinov
 *
 * Inzerujeme 16 — zaokrúhlené NAHOR, nech odhad počtu odpovedí radšej
 * podstrelíme než nafúkneme. Pri $50 = 50 000 coinov to je ~3 100 odpovedí.
 * Keď sa cenník modelov pohne, prepočítaj znova a uprav toto číslo aj
 * komentár; marketing sa drží jeho, nie naopak.
 */
export const COINS_PER_REPLY = 16;

/** Koľko odpovedí sa dá za daný počet coinov očakávať (zaokrúhlené nadol). */
export function estimatedReplies(coinCount: number): number {
  return Math.floor(coinCount / COINS_PER_REPLY);
}

/* -------------------------------------------------------------------------- */
/*  Balíky coinov                                                              */
/* -------------------------------------------------------------------------- */

/**
 * Násobok, ktorým sa klientovi účtuje nákupka Atlasu (`pricing.multiplier`).
 * Pri 2.0 ide polovica každého minutého dolára Atlasu — a presne o to sa
 * opiera invariant ziskovosti nižšie.
 */
export const BILLING_MULTIPLIER = DEFAULT_MULTIPLIER;

export type CoinPack = {
  id: string;
  name: string;
  /** Čo klient zaplatí, v USD. */
  priceUsd: number;
  /** Koľko Pipe Coinov dostane. */
  coins: number;
  /** Bonus oproti základnému kurzu 1 000 coinov / $. */
  bonusPct: number;
  tagline: string;
  featured?: boolean;
};

/**
 * Rebrík je zámerne rastúci: väčší balík = viac coinov za dolár. Opačné
 * poradie (drahší balík s horším kurzom) je produktová chyba, nie cenotvorba —
 * nikto by ho nekúpil.
 */
export const COIN_PACKS: CoinPack[] = [
  {
    id: "coins-50",
    name: "Starter",
    priceUsd: 50,
    coins: 50_000,
    bonusPct: 0,
    tagline: "Enough to see what she does with a full inbox.",
  },
  {
    id: "coins-100",
    name: "Creator",
    priceUsd: 100,
    coins: 110_000,
    bonusPct: 10,
    tagline: "One model, working every day, for weeks.",
    featured: true,
  },
  {
    id: "coins-250",
    name: "Agency",
    priceUsd: 250,
    coins: 300_000,
    bonusPct: 20,
    tagline: "A whole roster replying without you watching the balance.",
  },
];

/** Kurz balíka — koľko coinov klient dostane za dolár. */
export function coinsPerDollar(pack: CoinPack): number {
  return pack.coins / pack.priceUsd;
}

/* -------------------------------------------------------------------------- */
/*  Vlastná suma (custom top-up)                                               */
/* -------------------------------------------------------------------------- */

/**
 * Klient si môže dobiť ľubovoľnú sumu, nielen balík. Bonusové prahy sú TIE
 * ISTÉ ako pri balíkoch ($100 → +10 %, $250 → +20 %), takže custom $100 dá
 * presne toľko, čo balík Creator — cenník nemá dve pravdy.
 *
 * Invariant ziskovosti platí rovnako: pri multiplieri 2 je strop 2 000
 * coinov/$, najštedrejší custom kurz je 1 200 coinov/$ — bezpečne pod ním.
 * Stráži to `npm run test:coins`.
 */
export const CUSTOM_MIN_USD = 5;
export const CUSTOM_MAX_USD = 5000;

/** Zoradené zostupne — prvý prah, ktorý suma dosiahne, vyhráva. */
const CUSTOM_BONUS_TIERS: { minUsd: number; bonusPct: number }[] = [
  { minUsd: 250, bonusPct: 20 },
  { minUsd: 100, bonusPct: 10 },
];

export function customBonusPct(usd: number): number {
  for (const tier of CUSTOM_BONUS_TIERS) {
    if (usd >= tier.minUsd) return tier.bonusPct;
  }
  return 0;
}

/** Koľko coinov dostane klient za vlastnú sumu (vrátane bonusu, celé coiny). */
export function customCoinsForUsd(usd: number): number {
  return Math.round(usd * COINS_PER_USD * (1 + customBonusPct(usd) / 100));
}

/**
 * Čo nás balík bude stáť, keď klient minie VŠETKY coiny.
 *
 * Coiny sú zostatok, ktorý sa míňa účtovanou cenou = nákupka × multiplier.
 * Takže z `C` coinov (= `C/1000` dolárov zostatku) ide Atlasu `C/1000/mult`.
 */
export function packAtlasCostUsd(
  pack: CoinPack,
  multiplier: number = BILLING_MULTIPLIER,
): number {
  return coinsToUsd(pack.coins) / multiplier;
}

/** Zisk z balíka v najhoršom prípade (klient minie všetko do posledného coinu). */
export function packMarginUsd(
  pack: CoinPack,
  multiplier: number = BILLING_MULTIPLIER,
): number {
  return pack.priceUsd - packAtlasCostUsd(pack, multiplier);
}

/** Strop coinov, pri ktorom je balík ešte na nule. Nad ním sa prerába. */
export function maxProfitableCoins(
  priceUsd: number,
  multiplier: number = BILLING_MULTIPLIER,
): number {
  return priceUsd * COINS_PER_USD * multiplier;
}

/**
 * TVRDÝ INVARIANT — nikdy sa nesmie stať, že klient zaplatí veľa a my na tom
 * prerobíme.
 *
 *     zisk = cena − (coiny / 1000) / multiplier
 *
 * Pri multiplieri 2.0 to znamená, že bonus musí ostať pod 100 %. Kontrolu volá
 * `npm run test:coins` (`scripts/coins-test.mts`), takže balík, ktorý by prešiel
 * cez strop, zhodí test a nie účtovníctvo.
 *
 * Hádže pri prvom nevyhovujúcom balíku — nemá zmysel pokračovať a nemá zmysel
 * to len zalogovať.
 */
export function assertPacksProfitable(
  packs: CoinPack[] = COIN_PACKS,
  multiplier: number = BILLING_MULTIPLIER,
): void {
  if (!(multiplier > 0)) {
    throw new Error(`Pipe Coin packs: multiplier must be positive, got ${multiplier}`);
  }

  for (const pack of packs) {
    const ceiling = maxProfitableCoins(pack.priceUsd, multiplier);
    const margin = packMarginUsd(pack, multiplier);

    // Rovnosť = nula na balíku. Ani to nie je „v pluse", takže padá tiež.
    if (margin <= 0) {
      throw new Error(
        `Pipe Coin pack "${pack.id}" loses money: $${pack.priceUsd} buys ` +
          `${formatCoins(pack.coins)} coins, which costs us ` +
          `$${packAtlasCostUsd(pack, multiplier).toFixed(2)} at multiplier ${multiplier} ` +
          `(margin $${margin.toFixed(2)}). The ceiling for $${pack.priceUsd} is ` +
          `${formatCoins(ceiling)} coins — stay strictly under it.`,
      );
    }
  }

  // Väčší balík so slabším kurzom nikto nekúpi — to je taká istá chyba
  // v cenníku ako stratový balík, len sa prejaví na tržbe a nie na marži.
  const sorted = [...packs].sort((a, b) => a.priceUsd - b.priceUsd);
  for (let i = 1; i < sorted.length; i += 1) {
    if (coinsPerDollar(sorted[i]) < coinsPerDollar(sorted[i - 1])) {
      throw new Error(
        `Pipe Coin pack "${sorted[i].id}" ($${sorted[i].priceUsd}) gives ` +
          `${coinsPerDollar(sorted[i])} coins/$ — worse than the smaller ` +
          `"${sorted[i - 1].id}" at ${coinsPerDollar(sorted[i - 1])} coins/$.`,
      );
    }
  }
}
