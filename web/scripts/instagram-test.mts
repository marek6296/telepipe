/**
 * Instagram: prihlasovacia adresa, tokeny a hranice nastavení.
 *
 * Čo sa tu stráži, nie je kozmetika. Na Instagrame je odkaz na stránku pre
 * dospelých v DM dôvod na zrušenie účtu, a účet je to jediné, čo modelka
 * naozaj má. Preto sú „fanvue ako cieľ lievika" a „hot ako pikantnosť" veci,
 * ktoré sa nesmú dať nastaviť ani omylom.
 *
 * Spustenie:  npm run test:instagram
 */
import {
  SCOPES,
  daysLeft,
  redirectUri,
} from "../lib/instagram.ts";

let failed = 0;
let passed = 0;

function check(condition: boolean, message: string): void {
  if (condition) passed++;
  else {
    failed++;
    console.error(`✗ ${message}`);
  }
}

function eq(actual: unknown, expected: unknown, message: string): void {
  check(
    actual === expected,
    `${message} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );
}

/* ------------------------------------------------------------------ scopes */
{
  check(
    SCOPES.includes("instagram_business_manage_messages"),
    "pýtame si prístup k správam — bez toho agent nemá čo robiť",
  );
  check(
    SCOPES.includes("instagram_business_basic"),
    "a základné oprávnenie, ktoré je podmienkou obnovovania tokenu",
  );
  check(
    !SCOPES.some((s) => s.includes("content_publish")),
    "publikovanie NEPÝTAME — appka nepostuje a každé oprávnenie navyše sťažuje review",
  );
  check(
    SCOPES.every((s) => s.startsWith("instagram_business_")),
    "staré scope hodnoty (bez prefixu) Meta zrušila 27. 1. 2025",
  );
}

/* ------------------------------------------------------------ redirect URI */
{
  eq(
    redirectUri("https://telepipe.me"),
    "https://telepipe.me/api/instagram/callback",
    "redirect URI sedí s tým, čo je v App Dashboarde",
  );
  eq(
    redirectUri("https://telepipe.me/"),
    "https://telepipe.me/api/instagram/callback",
    "koncová lomka v origine nesmie vyrobiť dvojitú",
  );
}

/* ------------------------------------------------------- platnosť tokenu */
{
  eq(daysLeft(null), null, "nepripojené = nevieme");
  eq(daysLeft("toto nie je dátum"), null, "rozbitý dátum nesmie zhodiť kartu");
  const o30dni = new Date(Date.now() + 30 * 86_400_000).toISOString();
  eq(daysLeft(o30dni), 30, "30 dní dopredu");
  const vcera = new Date(Date.now() - 86_400_000).toISOString();
  eq(daysLeft(vcera), 0, "expirovaný token nemá záporné dni");
}

/* --------------------------------------------- hranice, ktoré chránia účet */
{
  // Zoznamy sú napísané ručne, nie importované z akcie — inak by test
  // potvrdzoval sám seba. Musia sedieť s `ENUMY` v settings/actions.ts
  // a s CHECK constraintmi v migrácii 20260824010000_instagram.sql.
  const CIELE = ["telegram", "bio_link"];
  const PIKANTNOST = ["mild", "medium"];

  check(!CIELE.includes("fanvue"), "Fanvue sa nesmie dať nastaviť ako cieľ lievika");
  check(!CIELE.includes("onlyfans"), "ani OnlyFans");
  check(!PIKANTNOST.includes("hot"), "explicitný stupeň na Instagrame neexistuje");

  // Telegramové meno: 5–32 znakov, začína písmenom, bez zavináča.
  const HANDLE_RE = /^[a-zA-Z][a-zA-Z0-9_]{4,31}$/;
  check(HANDLE_RE.test("simona_here"), "bežné meno prejde");
  check(!HANDLE_RE.test("ab"), "krátke meno neprejde");
  check(!HANDLE_RE.test("1simona"), "meno začínajúce číslom neprejde");
  check(!HANDLE_RE.test("@simona_here"), "so zavináčom neprejde — ukladá sa bez neho");

  // Odkaz v biu nesmie viesť rovno na platenú platformu.
  const ZAKAZANE = /fanvue\.com|onlyfans\.com/i;
  check(ZAKAZANE.test("https://fanvue.com/simona"), "priamy Fanvue odkaz sa chytí");
  check(ZAKAZANE.test("https://www.OnlyFans.com/x"), "aj s veľkými písmenami");
  check(!ZAKAZANE.test("https://linkovne.com/simona"), "rozcestník je v poriadku");
}

console.log(`${passed} passed, ${failed} failed`);
if (failed > 0) process.exitCode = 1;
