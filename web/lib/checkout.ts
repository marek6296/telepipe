/**
 * Odkaz na Fanvue, ktorý si so sebou nesie, komu bol poslaný.
 *
 * DRUHÁ KÓPIA, A JE TO ZÁMER. Originál je `worker/src/checkout.py` — tam sa
 * odkaz skladá pri odpisovaní. Tu sa skladá pri kliknutí na krátky odkaz
 * (`app/r/[token]/route.ts`), teda v inom procese a v inom jazyku. Musia
 * dávať rovnaký výsledok, preto to stráži `npm run test:checkout`.
 *
 * Fanvue vracia `client_reference_id` v každej udalosti o platbe, takže vieme
 * spojiť fanúšika na Fanvue s človekom, s ktorým si modelka písala na Telegrame.
 */

/** Predpona, podľa ktorej sa pozná, že v hodnote je Telegram id. */
export const PREFIX = "tg-";

export function reference(tgId: number): string {
  return Number.isFinite(tgId) ? `${PREFIX}${Math.trunc(tgId)}` : "";
}

/**
 * Odkaz doplnený o to, komu ide.
 *
 * Cudzie odkazy ani odkazy bez id nechá tak — radšej nech ide von presne to, čo
 * si klient nastavil, než aby sa doň prilepilo niečo naslepo.
 */
export function attributedLink(link: string, tgId: number): string {
  const clean = (link ?? "").trim();
  if (!clean || !clean.toLowerCase().includes("fanvue.com")) return clean;

  const ref = reference(tgId);
  if (!ref) return clean;
  if (clean.includes("client_reference_id=")) return clean;

  // Kotva musí ostať na konci, inak by sa parameter stal jej súčasťou.
  const hashAt = clean.indexOf("#");
  const base = hashAt === -1 ? clean : clean.slice(0, hashAt);
  const fragment = hashAt === -1 ? "" : clean.slice(hashAt);
  const separator = base.includes("?") ? "&" : "?";
  return `${base}${separator}client_reference_id=${encodeURIComponent(ref)}${fragment}`;
}
