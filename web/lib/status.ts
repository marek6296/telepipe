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

/**
 * Triedy badge-u pre každý stav — monochróm, farba len ako tlmený signál.
 * (App-only mapa; landing/auth ju nepoužívajú.)
 */
export const STATUS_STYLE: Record<ModelStatus, string> = {
  draft: "border-[#262626] text-[#a1a1aa]",
  active: "border-[rgba(74,222,128,0.28)] text-[#86efac]",
  paused: "border-[rgba(250,204,21,0.26)] text-[#fde047]",
  error: "border-[rgba(248,113,113,0.3)] text-[#fca5a5]",
  disabled: "border-[#1f1f1f] text-[#52525b]",
};

/** Farba bodky v zozname / na karte — jediné farebné miesto pri stave. */
export const STATUS_DOT: Record<ModelStatus, string> = {
  draft: "bg-[#52525b]",
  active: "bg-[#4ade80]",
  paused: "bg-[#facc15]",
  error: "bg-[#f87171]",
  disabled: "bg-[#3f3f46]",
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

/**
 * Konkrétne chýbajúce políčko — worker ho odteraz posiela ako
 * `bad_config:<stĺpec>` (viď `config.BadModelRow`). Bez tohto by z toho
 * `prettifyCode` spravil „Bad config:tg api id", čo klientovi nepovie nič
 * o tom, čo má urobiť.
 */
const BAD_CONFIG_FIELD: Record<string, string> = {
  tg_api_id:
    "Her api_id is missing, so she cannot sign in to Telegram. Fill it in on the Connection tab and reconnect.",
  tg_api_hash:
    "Her api_hash is missing, so she cannot sign in to Telegram. Fill it in on the Connection tab and reconnect.",
};

/** Strojový dôvod → veta pre klienta. Neznámy kód aspoň zľudštíme. */
export function statusReasonText(reason: string | null | undefined): string | null {
  const key = (reason ?? "").trim();
  if (!key) return null;
  if (key.startsWith("bad_config:")) {
    const field = key.slice("bad_config:".length);
    return BAD_CONFIG_FIELD[field] ?? REASON_TEXT.bad_config;
  }
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
