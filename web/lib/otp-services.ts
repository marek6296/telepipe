/**
 * Čo ponúkame na overenie číslom — kurátorovaný zoznam, nie všetko z 5simu.
 *
 * 5sim má tisíce služieb a 140+ krajín, ale drvivá väčšina je pre našich
 * klientov bezcenná: čínske burzy, indické doručovacie appky, čísla z krajín,
 * ktoré nikto nechce. Široká ponuka by rozhodovanie len sťažila.
 *
 * Držíme preto päť platforiem a dvanásť známych krajín. Čísla v komentároch sú
 * namerané 2026-08-19 z verejného cenníka 5simu.
 *
 * Klientsky bezpečné — používa to aj UI, žiadny import zo servera.
 */

export type OtpService = {
  /** Identifikátor, ktorý pozná 5sim. Ide do URL, takže sa nesmie meniť. */
  id: string;
  name: string;
  hint: string;
};

export const OTP_SERVICES: OtpService[] = [
  { id: "telegram", name: "Telegram", hint: "New account or a second number" },
  { id: "whatsapp", name: "WhatsApp", hint: "Business or personal account" },
  { id: "instagram", name: "Instagram", hint: "Account verification" },
  { id: "tiktok", name: "TikTok", hint: "Account verification" },
  { id: "google", name: "Google", hint: "Gmail and Google services" },
];

export type OtpCountry = {
  /** Kód podľa 5simu — `england`, nie `uk`. Ide do URL. */
  id: string;
  name: string;
  flag: string;
};

/**
 * Zámerne len veľké a známe krajiny.
 *
 * Nigéria či Kamerun majú milióny čísel za pár centov, ale číslo z takej krajiny
 * si nikto neobjedná — a v zozname by len prekážalo. Kto potrebuje lacno,
 * vyberie si Česko alebo Kanadu.
 */
export const OTP_COUNTRIES: OtpCountry[] = [
  { id: "usa", name: "United States", flag: "🇺🇸" },
  { id: "england", name: "United Kingdom", flag: "🇬🇧" },
  { id: "canada", name: "Canada", flag: "🇨🇦" },
  { id: "germany", name: "Germany", flag: "🇩🇪" },
  { id: "france", name: "France", flag: "🇫🇷" },
  { id: "spain", name: "Spain", flag: "🇪🇸" },
  { id: "italy", name: "Italy", flag: "🇮🇹" },
  { id: "netherlands", name: "Netherlands", flag: "🇳🇱" },
  { id: "austria", name: "Austria", flag: "🇦🇹" },
  { id: "sweden", name: "Sweden", flag: "🇸🇪" },
  { id: "poland", name: "Poland", flag: "🇵🇱" },
  { id: "czech", name: "Czechia", flag: "🇨🇿" },
];

export const DEFAULT_OTP_SERVICE = "telegram";
export const DEFAULT_OTP_COUNTRY = "usa";

export function otpService(id: string): OtpService | null {
  return OTP_SERVICES.find((s) => s.id === id) ?? null;
}

export function otpCountry(id: string): OtpCountry | null {
  return OTP_COUNTRIES.find((c) => c.id === id) ?? null;
}

/** Whitelist — do URL na providera nesmie ísť nič, čo sme neschválili. */
export function isKnownOtpService(id: string): boolean {
  return OTP_SERVICES.some((s) => s.id === id);
}

export function isKnownOtpCountry(id: string): boolean {
  return OTP_COUNTRIES.some((c) => c.id === id);
}
