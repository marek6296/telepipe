/**
 * Admin helpery, ktoré musia fungovať aj v prehliadači (badge-e, selecty).
 * Serverová časť (RPC volania, guardy) žije v `lib/admin.ts` — tá importuje
 * `next/headers`, takže do client komponentu sa dostať nesmie.
 */

export const ROLES = ["user", "admin", "superadmin"] as const;
export const PLANS = ["free", "starter", "pro", "custom"] as const;

export type AccountRole = (typeof ROLES)[number];
export type AdminRole = "admin" | "superadmin";
export type Plan = (typeof PLANS)[number];

export function asRole(value: string | null | undefined): AccountRole {
  return ROLES.includes(value as AccountRole) ? (value as AccountRole) : "user";
}

export function asPlan(value: string | null | undefined): Plan {
  return PLANS.includes(value as Plan) ? (value as Plan) : "free";
}

export function isAdminRole(role: string | null | undefined): boolean {
  const value = asRole(role);
  return value === "admin" || value === "superadmin";
}

export const ROLE_LABEL: Record<AccountRole, string> = {
  user: "User",
  admin: "Admin",
  superadmin: "Superadmin",
};

export const ROLE_STYLE: Record<AccountRole, string> = {
  user: "border-white/10 bg-white/[0.04] text-white/45",
  admin: "border-[rgba(212,175,55,0.35)] bg-[rgba(212,175,55,0.1)] text-[var(--gold-light)]",
  superadmin: "border-[rgba(212,175,55,0.6)] bg-[rgba(212,175,55,0.18)] text-[var(--gold-light)]",
};

export const PLAN_LABEL: Record<Plan, string> = {
  free: "Free",
  starter: "Starter",
  pro: "Pro",
  custom: "Custom",
};

/* --------------------------------------------------------------------------
   Čerstvosť heartbeatu — jediné, čo o bežiacom workerovi naozaj vieme.
   Worker píše heartbeat každých ~30 s, takže <90 s = živý.
-------------------------------------------------------------------------- */

export type Freshness = "live" | "stale" | "dead";

export const LIVE_MS = 90_000;
export const STALE_MS = 10 * 60_000;

export function freshness(iso: string | null | undefined): Freshness {
  if (!iso) return "dead";
  const ms = new Date(iso).getTime();
  if (!Number.isFinite(ms)) return "dead";
  const age = Date.now() - ms;
  if (age < LIVE_MS) return "live";
  if (age < STALE_MS) return "stale";
  return "dead";
}

export const FRESHNESS_LABEL: Record<Freshness, string> = {
  live: "Live",
  stale: "Stale",
  dead: "Dead",
};

export const FRESHNESS_STYLE: Record<Freshness, string> = {
  live: "border-[#2e7d52]/45 bg-[#0f2a1d] text-[#6ee7a8]",
  stale: "border-[#8a6d1f]/50 bg-[#2a2210] text-[#f2cd6b]",
  dead: "border-[#7a2b23]/70 bg-[#2a100d] text-[#ffb3a7]",
};

export const FRESHNESS_DOT: Record<Freshness, string> = {
  live: "bg-[#4ade80]",
  stale: "bg-[#f2cd6b]",
  dead: "bg-[#ff7a6a]",
};

/** `7f3a1c9e-93d6-…` → `7f3a1c9e` (celá hodnota ostáva v tooltipe). */
export function shortId(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  if (!text) return "—";
  return text.length <= 10 ? text : `${text.slice(0, 8)}…`;
}

/** RPC chyba → veta pre admina. `forbidden` = rola medzitým padla. */
export function adminErrorText(message: string): string {
  const text = (message ?? "").toLowerCase();
  if (text.includes("forbidden") || text.includes("permission denied")) {
    return "You no longer have permission for that action.";
  }
  if (text.includes("cannot demote the last superadmin")) {
    return "You cannot demote the last superadmin.";
  }
  if (text.includes("account not found")) return "That account no longer exists.";
  if (text.includes("invalid plan")) return "Unknown plan.";
  if (text.includes("invalid role")) return "Unknown role.";
  if (text.includes("amount must be non-zero")) return "Enter an amount other than zero.";
  return message || "Something went wrong. Try again.";
}
