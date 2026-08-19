/**
 * Telegram Stars — druhá cesta k Pipe Coinom. Krypto ostáva hlavná.
 *
 * Relatívne cesty s príponou zámerne: modul spúšťa `scripts/stars-test.mts`
 * priamo cez Node, a ten alias `@/` nepozná (rovnako ako `coins.ts`).
 */
import { COINS_PER_USD } from "./coins.ts";

/**
 * Koľko nám z jedného Staru naozaj ostane.
 *
 * Číslo je z oficiálnej tabuľky Telegramu a je pre všetky balíky rovnaké:
 * používateľ v App Store / Play zaplatí ~$0,02 za Star, Apple/Google si vezme
 * 30 %, Telegram ~5 %, a nám ostane presne $0,013. Overené na piatich riadkoch
 * tabuľky (50 ⭐ → $0,65 · 500 ⭐ → $6,50 · 2500 ⭐ → $32,50).
 *
 * Keby to Telegram raz zmenil, mení sa TENTO riadok a nič iné.
 */
export const USD_PER_STAR = 0.013;

/**
 * Koľko používateľa stojí jeden Star v obchode. Slúži LEN na to, aby sme mu
 * vedeli ukázať približnú cenu v dolároch — účtuje Telegram, nie my, a
 * skutočná suma sa líši podľa DPH a krajiny.
 */
export const APPROX_USD_PER_STAR_FOR_USER = 0.02;

/** Najmenší a najväčší nákup cez Stars. */
export const STARS_MIN_USD = 5;
export const STARS_MAX_USD = 500;

/**
 * Koľko Stars musí faktúra pýtať, aby nám ostalo `usd`.
 *
 * Zaokrúhľuje sa NAHOR na desiatku — nadol by znamenalo predávať pod cenu, a
 * pri stovkách nákupov je to reálna strata. Desiatka je kvôli tomu, aby
 * v Telegrame nesvietili čísla ako „771 ⭐".
 */
export function starsForUsd(usd: number): number {
  const raw = usd / USD_PER_STAR;
  return Math.ceil(raw / 10) * 10;
}

/** Koľko coinov klient dostane. Bonusy za objem pri Stars ZÁMERNE neplatia —
 *  sú to peniaze navyše, ktoré si vieme dovoliť pri 1 % poplatku, nie pri 35 %.
 *  Krypto tak ostáva zjavne výhodnejšie, čo je zámer. */
export function starsCoinsForUsd(usd: number): number {
  return Math.round(usd * COINS_PER_USD);
}

/** Približná cena pre používateľa — na zobrazenie „≈ $15", nič viac. */
export function approxUserCostUsd(stars: number): number {
  return stars * APPROX_USD_PER_STAR_FOR_USER;
}

/* -------------------------------------------------------------------------- */
/*  Payload faktúry — na ňom stojí celé priradenie platby k účtu               */
/* -------------------------------------------------------------------------- */

/**
 * `payload` má 1–128 bajtov a používateľ ho nikdy nevidí. Nesie si, komu sa má
 * platba pripísať — vďaka tomu netreba žiadne párovanie Telegram účtu s webom.
 *
 * Verzia na začiatku je tam schválne: keby sa tvar raz zmenil, faktúry
 * vystavené pred zmenou musia ostať zaplatiteľné.
 *
 * Žije tu, a nie v `telegram-shop.ts`, aby sa to dalo otestovať bez servera —
 * je to jediné miesto, kde sa rozhoduje, na čí účet pôjdu peniaze.
 */
export function buildPayload(accountId: string, usd: number): string {
  return `v1:${accountId}:${usd}`;
}

export type ParsedPayload = { accountId: string; usd: number } | null;

export function parsePayload(payload: string): ParsedPayload {
  const m = /^v1:([0-9a-f-]{36}):(\d+(?:\.\d+)?)$/.exec(payload ?? "");
  if (!m) return null;
  const usd = Number(m[2]);
  if (!Number.isFinite(usd) || usd <= 0) return null;
  if (usd > STARS_MAX_USD) return null;
  return { accountId: m[1], usd };
}

export type StarOption = {
  usd: number;
  stars: number;
  coins: number;
  featured?: boolean;
};

/**
 * Ponuka pre Stars. ZÁMERNE začína na $5 a ťažisko je na $10–20: cez Telegram
 * ľudia kupujú malé sumy, nie balíky za $250. Kto chce veľa, má krypto, kde
 * dostane aj bonus.
 */
export const STAR_OPTIONS: StarOption[] = [5, 10, 20, 50].map((usd) => ({
  usd,
  stars: starsForUsd(usd),
  coins: starsCoinsForUsd(usd),
  featured: usd === 10,
}));

/**
 * Kontrola, že cez Stars nikdy nepredávame pod cenu.
 *
 * Volá ju `npm run test:stars`. Bez nej by stačilo raz zle zaokrúhliť a každý
 * nákup by nás stál peniaze — potichu a pri každom klientovi.
 */
export function assertStarsProfitable(options: StarOption[] = STAR_OPTIONS): void {
  for (const option of options) {
    const net = option.stars * USD_PER_STAR;
    if (net < option.usd) {
      throw new Error(
        `Stars: ${option.stars} ⭐ vynesie $${net.toFixed(2)}, ale pripisujeme ` +
          `$${option.usd.toFixed(2)} — predávame pod cenu`,
      );
    }
    if (option.coins !== Math.round(option.usd * COINS_PER_USD)) {
      throw new Error(`Stars: ${option.usd} USD → nesedí počet coinov`);
    }
  }
}
