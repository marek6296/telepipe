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

/**
 * Koľko používateľa stojí jeden Star v obchode. Slúži LEN na to, aby sme mu
 * vedeli ukázať približnú cenu v dolároch — účtuje Telegram, nie my, a
 * skutočná suma sa líši podľa DPH a krajiny.
 */
export const APPROX_USD_PER_STAR_FOR_USER = 0.02;

/** Horná zábrana pre payload. Najväčší balík je hlboko pod ňou. */
export const STARS_MAX_USD = 500;

/**
 * Koľko Pipe Coinov dostane klient za jednu hviezdu.
 *
 * Z jednej ⭐ nám príde $0,013, čiže 13 coinov. Pripisujeme 12. Tá jedna coina
 * je rezerva na to, čo Telegram sám priznáva: sumy sa vraj môžu líšiť „kvôli
 * DPH a ďalším poplatkom mimo kontroly Telegramu". Bez rezervy by stačil
 * percentuálny výkyv a pri KAŽDOM nákupe by sme pripisovali viac, než sme
 * dostali.
 *
 * Kurz je LINEÁRNY — 500 ⭐ aj 5 000 ⭐ dávajú rovnako coinov na hviezdu.
 * Objemové bonusy pri Stars zámerne neplatia: sú to peniaze navyše, ktoré si
 * vieme dovoliť pri ~1 % poplatku (krypto), nie pri 35 %. Krypto tak ostáva
 * zjavne výhodnejšie, čo je zámer.
 *
 * POZOR pri budúcich úpravách: sem NEPRIDÁVAJ odhad počtu správ („≈166
 * replies"). Verejné tvrdenia typu „koľko správ za $10" stoja na KRYPTO cene,
 * kde $1 = 1 000 coinov. Cez Stars je dolár slabší (Apple a Telegram si berú
 * svoje), takže rovnaké číslo by pri tejto metóde klamalo. Prepočet
 * coiny → správy je spoločný a ten pokojne ukazuj — mení sa len doláre → coiny.
 */
export const COINS_PER_STAR = 12;

/** Suma zostatku → coiny. Používa to webhook pri pripísaní platby. */
export function coinsForUsd(usd: number): number {
  return Math.round(usd * COINS_PER_USD);
}

/** Približná cena pre používateľa — na zobrazenie „≈ $20", nič viac. */
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

export type StarPack = {
  /** Koľko hviezd pýta faktúra. Musí to byť veľkosť, akú Telegram naozaj
   *  predáva — inak klientovi ostanú nevyužité hviezdy. */
  stars: number;
  coins: number;
  /** O koľko sa zdvihne zostatok. Ide do payloadu aj do `star_payments`. */
  usd: number;
  /** Čo za balík zaplatí v Telegrame, bez DPH jeho krajiny. */
  approxUsd: number;
  featured?: boolean;
};

/**
 * Ponuka pre Stars — PEVNÉ BALÍKY, žiadna vlastná suma.
 *
 * Veľkosti sú zhodné s balíkmi, ktoré predáva sám Telegram. To je celý dôvod,
 * prečo tu nie je voľné pole na sumu: hviezdy sa nedajú kúpiť po kuse, takže
 * faktúra na 410 ⭐ znamená, že klient kúpi balík za 500 a 90 ⭐ mu ostane
 * visieť na účte. Pri zhodných veľkostiach kúpi presne toľko, koľko minie.
 *
 * Keby Telegram veľkosti balíkov zmenil, mení sa TENTO riadok.
 */
const PACK_STARS = [500, 1000, 2500, 5000] as const;

export const STAR_PACKS: StarPack[] = PACK_STARS.map((stars) => ({
  stars,
  coins: stars * COINS_PER_STAR,
  usd: (stars * COINS_PER_STAR) / COINS_PER_USD,
  approxUsd: approxUserCostUsd(stars),
  featured: stars === 1000,
}));

/**
 * Whitelist balíkov.
 *
 * Počet hviezd chodí z prehliadača, takže sa NIKDY nesmie použiť priamo — bez
 * tejto kontroly by si klient vypýtal faktúru na 1 ⭐ a dostal coiny za balík.
 */
export function starPack(stars: number): StarPack | null {
  return STAR_PACKS.find((p) => p.stars === stars) ?? null;
}

/**
 * Koľko z klientovej platby zhltnú Apple/Google a Telegram, v percentách.
 *
 * Klient zaplatí ~$0,02 za hviezdu a na zostatku sa mu z nej objaví $0,012 —
 * čiže 40 %. Pri kryptu je poplatok nula a $1 je vždy 1 000 coinov.
 *
 * Toto číslo sa klientovi UKAZUJE. Nie je to naša marža: leví podiel berie
 * obchod s aplikáciami, nie my.
 */
export const PLATFORM_FEE_PCT = Math.round(
  (1 - COINS_PER_STAR / COINS_PER_USD / APPROX_USD_PER_STAR_FOR_USER) * 100,
);

/**
 * Kontrola, že cez Stars nikdy nepredávame pod cenu.
 *
 * Volá ju `npm run test:stars`. Bez nej by stačilo raz zle zaokrúhliť a každý
 * nákup by nás stál peniaze — potichu a pri každom klientovi.
 */
export function assertStarsProfitable(packs: StarPack[] = STAR_PACKS): void {
  for (const pack of packs) {
    const net = pack.stars * USD_PER_STAR;
    // Nestačí „aspoň na svoje". Musí ostať aj rezerva — inak by pohyb kurzu
    // o percento robil z každého nákupu stratu.
    const potrebne = pack.usd / (1 - SAFETY_MARGIN);
    if (net < potrebne) {
      throw new Error(
        `Stars: ${pack.stars} ⭐ vynesie $${net.toFixed(2)}, ale pri pripísaných ` +
          `$${pack.usd.toFixed(2)} potrebujeme aspoň $${potrebne.toFixed(2)} ` +
          `(rezerva ${SAFETY_MARGIN * 100} %)`,
      );
    }
    if (pack.coins !== coinsForUsd(pack.usd)) {
      throw new Error(`Stars: ${pack.stars} ⭐ → coiny a suma si neodpovedajú`);
    }
  }

  // Kurz musí byť rovnaký pri každom balíku. Keby väčší balík dával menej
  // coinov na hviezdu, je to chyba v cenníku — a keby dával viac, prestal by
  // platiť výpočet ziskovosti vyššie pre malé balíky.
  const kurzy = new Set(packs.map((p) => p.coins / p.stars));
  if (kurzy.size > 1) {
    throw new Error(`Stars: balíky nemajú rovnaký kurz (${[...kurzy].join(", ")} coinov/⭐)`);
  }
}
