/**
 * Stav OTP providera → náš stav.
 *
 * PREČO SAMOSTATNÝ MODUL: dá sa otestovať holým Node (`npm run test:otp-status`)
 * bez servera a bez Supabase. Kým to žilo vo `vrnum.ts`, testovať sa to nedalo —
 * a presne tam sa schovala chyba popísaná nižšie.
 *
 * SLOVO „received" ZNAMENÁ U KAŽDÉHO PROVIDERA NIEČO INÉ
 * -----------------------------------------------------
 * U VRNUM „received" = dorazil KÓD.
 * U 5simu `RECEIVED`  = dorazilo ČÍSLO a čaká sa na SMS — presný opak.
 *
 * Kým sa na to slovo mapovalo bez ohľadu na providera, appka pri 5sime hlásila
 * „Code received" a pole s kódom ostalo prázdne. Klient čakal na niečo, čo
 * nikdy neprišlo, a číslo mu medzitým vypršalo.
 *
 * Bezpečný výklad je PREDVOLENÝ. Dnes ide všetko cez 5sim a cez VRNUM neprešla
 * ani jedna objednávka, takže VRNUM je výnimka — a neznámy provider padne do
 * bezpečnej vetvy. Sľúbiť kód, ktorý nikde nie je, je horšie než nechať klienta
 * chvíľu čakať.
 */

export type TelegramOtpStatus =
  /** Coiny sú rezervované, u providera sme ešte nič nekúpili. */
  | "reserved"
  | "provisioning"
  | "waiting"
  | "code_received"
  | "completed"
  | "cancelled"
  | "expired"
  | "failed";

export function mapProviderStatus(
  status: string,
  hasCode: boolean,
  provider: string,
): TelegramOtpStatus {
  // Kód je kód. Keď ho máme, na názvosloví providera nezáleží.
  if (hasCode) return "code_received";

  const value = (status || "").trim().toLowerCase().replaceAll("-", "_");

  if (value.includes("cancel")) return "cancelled";
  if (value.includes("expire") || value === "timeout") return "expired";
  if (
    value.includes("fail") ||
    value.includes("error") ||
    value.includes("reject") ||
    value === "banned"
  ) {
    return "failed";
  }
  if (value.includes("complete") || value.includes("success") || value === "finished") {
    return "completed";
  }
  if (value.includes("provision") || value.includes("pending")) return "provisioning";

  // Jediný provider, u ktorého „received" znamená kód. Legacy.
  if (provider === "vrnum" && value.includes("received")) return "code_received";

  return "waiting";
}
