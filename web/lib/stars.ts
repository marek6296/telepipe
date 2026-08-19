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
 * Bezpečnostná rezerva pri prepočte na Stars.
 *
 * PREČO: Telegram vo vlastnej tabuľke píše, že sumy sa môžu líšiť „kvôli DPH
 * a ďalším poplatkom mimo kontroly Telegramu". Bez rezervy vychádzalo 770 ⭐
 * na $10,01 oproti pripísaným $10,00 — rezerva jednej desatiny percenta.
 * Stačilo by, aby nám z niektorej krajiny prišlo o percento menej, a pri
 * KAŽDOM nákupe by sme pripisovali viac, než sme dostali.
 *
 * Päť percent je kompromis: klienta to za $10 coinov vyjde o ~80 centov
 * drahšie, čo pri metóde, ktorá je aj tak drahšia, nikoho neprekvapí — a nás
 * to drží nad vodou aj keď sa kurz mierne pohne.
 *
 * Až budeme mať skutočné čísla z `getStarTransactions`, dá sa to dotiahnuť.
 */
export const SAFETY_MARGIN = 0.05;

/** Kurz, s ktorým naozaj počítame — kurz Telegramu znížený o rezervu. */
export const USD_PER_STAR_SAFE = USD_PER_STAR * (1 - SAFETY_MARGIN);

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
  const raw = usd / USD_PER_STAR_SAFE;
  return Math.ceil(raw / 10) * 10;
}

/** Koľko coinov klient dostane. Bonusy za objem pri Stars ZÁMERNE neplatia —
 *  sú to peniaze navyše, ktoré si vieme dovoliť pri 1 % poplatku, nie pri 35 %.
 *  Krypto tak ostáva zjavne výhodnejšie, čo je zámer.
 *
 *  POZOR pri budúcich úpravách: sem NEPRIDÁVAJ odhad počtu správ („≈166
 *  replies"). Verejné tvrdenia typu „koľko správ za $10" stoja na KRYPTO cene,
 *  kde $1 = 1 000 coinov. Cez Stars je dolár slabší (Apple a Telegram si berú
 *  svoje), takže rovnaké číslo by pri tejto metóde klamalo. Prepočet
 *  coiny → správy je spoločný a ten pokojne ukazuj — mení sa len doláre → coiny. */
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
    // Nestačí „aspoň na svoje". Musí ostať aj rezerva — inak by pohyb kurzu
    // o percento robil z každého nákupu stratu.
    const potrebne = option.usd / (1 - SAFETY_MARGIN);
    if (net < potrebne) {
      throw new Error(
        `Stars: ${option.stars} ⭐ vynesie $${net.toFixed(2)}, ale pri pripísaných ` +
          `$${option.usd.toFixed(2)} potrebujeme aspoň $${potrebne.toFixed(2)} ` +
          `(rezerva ${SAFETY_MARGIN * 100} %)`,
      );
    }
    if (option.coins !== Math.round(option.usd * COINS_PER_USD)) {
      throw new Error(`Stars: ${option.usd} USD → nesedí počet coinov`);
    }
  }
}
