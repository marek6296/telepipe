/**
 * Stavy modelky — labely a vysvetlenia pre UI (client-safe, žiadny server import).
 *
 * `status_reason` plní worker (`runner.py`, `credits.py`) strojovými kódmi;
 * klientovi ich prekladáme do vety, ktorá mu povie čo s tým.
 */

export type ModelStatus = "draft" | "active" | "paused" | "error" | "disabled";

export const STATUS_LABEL: Record<ModelStatus, string> = {
  draft: "Draft",
  active: "Active",
  paused: "Paused",
  error: "Error",
  disabled: "Disabled",
};

/** Tailwind triedy badge-u pre každý stav. */
export const STATUS_STYLE: Record<ModelStatus, string> = {
  draft: "border-white/12 bg-white/[0.05] text-white/55",
  active: "border-[#2e7d52]/45 bg-[#0f2a1d] text-[#6ee7a8]",
  paused: "border-[#8a6d1f]/50 bg-[#2a2210] text-[#f2cd6b]",
  error: "border-[#7a2b23]/70 bg-[#2a100d] text-[#ffb3a7]",
  disabled: "border-white/10 bg-white/[0.03] text-white/35",
};

/** Farba bodky v zozname / na karte. */
export const STATUS_DOT: Record<ModelStatus, string> = {
  draft: "bg-white/35",
  active: "bg-[#4ade80]",
  paused: "bg-[#f2cd6b]",
  error: "bg-[#ff7a6a]",
  disabled: "bg-white/20",
};

const REASON_TEXT: Record<string, string> = {
  session_revoked:
    "The Telegram session was revoked. Reconnect the account to bring her back online.",
  crashed_repeatedly:
    "She kept crashing and was parked automatically. Try activating again — if it repeats, contact us.",
  bad_config:
    "Her configuration is incomplete. Finish the Telegram setup and try again.",
  out_of_credits:
    "You ran out of credits, so she was paused. Top up and switch her back on.",
};

/** Strojový dôvod → veta pre klienta. Neznámy kód aspoň zľudštíme. */
export function statusReasonText(reason: string | null | undefined): string | null {
  const key = (reason ?? "").trim();
  if (!key) return null;
  return REASON_TEXT[key] ?? prettifyCode(key);
}

/** `phone_code_expired` → „Phone code expired". */
export function prettifyCode(code: string): string {
  const words = code.replace(/[_-]+/g, " ").trim();
  if (!words) return "";
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Krátke vysvetlenie stavu pod nadpisom karty. */
export function statusHint(status: ModelStatus): string {
  switch (status) {
    case "draft":
      return "Not connected yet — finish the setup to bring her online.";
    case "active":
      return "Online and replying to fans.";
    case "paused":
      return "Sleeping. Switch her back on whenever you want.";
    case "error":
      return "Something stopped her.";
    case "disabled":
      return "Switched off by Telepipe. Contact us if you need her back.";
  }
}

/** Stav z DB je text — zúžime ho na známe hodnoty, nech TS nefňuká. */
export function asStatus(value: string | null | undefined): ModelStatus {
  const known: ModelStatus[] = ["draft", "active", "paused", "error", "disabled"];
  return known.includes(value as ModelStatus) ? (value as ModelStatus) : "draft";
}

/**
 * Smie klient prepnúť stav? Whitelist musí sedieť s RPC `set_model_status`
 * (migrácia 007) — inak by UI ponúkalo tlačidlo, ktoré DB odmietne.
 */
export function canActivate(status: ModelStatus, reason: string): boolean {
  if (status === "draft" || status === "paused") return true;
  if (status === "error") return reason !== "session_revoked";
  return false;
}

export function canPause(status: ModelStatus): boolean {
  return status === "active";
}
