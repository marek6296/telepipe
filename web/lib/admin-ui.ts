/**
 * Admin helpery, ktoré musia fungovať aj v prehliadači (badge-e, selecty).
 * Serverová časť (RPC volania, guardy) žije v `lib/admin.ts` — tá importuje
 * `next/headers`, takže do client komponentu sa dostať nesmie.
 */

export const ROLES = ["user", "admin", "superadmin"] as const;

/** Dva balíky, nič viac (migrácia 024). Predplatné neexistuje — klient si kupuje
 *  Pipe Coiny a míňa ich, ako modelka pracuje. Plán už neriadi funkcie, riadi
 *  jedinú vec: cenu.
 *
 *  free      — bežný účet, účtovaný `pricing.multiplier` (2.0). Od migrácie
 *              20260819120000 je ZAMKNUTÝ: nesmie založiť modelku ani kúpiť
 *              coiny, kým ho Marek neschváli.
 *  free_plus — schválený účet („Standard+"). Účtuje sa PRESNE ako `free`;
 *              nesie povolenie pracovať, nie inú cenu.
 *  vip       — kamaráti, účtovaní nákupnou cenou Atlasu (1.0), nezarábame na nich
 *
 *  `vip` je zámerne posledný: nikde sa neinzeruje, prideliť ho smie iba
 *  superadmin a `record_usage` mu prepočíta sumu sám (021). Verejný cenník
 *  (`/pricing`) vymenúva balíky coinov natvrdo z `lib/coins.ts`, takže sa tam
 *  odtiaľto nemá ako dostať. */
export const PLANS = ["free", "free_plus", "vip"] as const;

/** Balíky, ktoré smie prideliť aj obyčajný admin. VIP chýba schválne —
 *  DB to strážila prvá (`admin_set_plan` → 42501), toto je len UI. */
export const ADMIN_ASSIGNABLE_PLANS = PLANS.filter((p) => p !== "vip");

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

/** Monochróm — rola je hierarchia, tú nesie jas textu, nie farba. */
export const ROLE_STYLE: Record<AccountRole, string> = {
  user: "border-[#1f1f1f] text-[#71717a]",
  admin: "border-[#3f3f46] text-[#d4d4d8]",
  superadmin: "border-[#52525b] bg-[#161616] text-[#fafafa]",
};

/** „Standard", nie „Free" — účet nie je zadarmo, len sa naň dokupujú coiny. */
export const PLAN_LABEL: Record<Plan, string> = {
  free: "Standard",
  free_plus: "Standard+",
  vip: "VIP",
};

/** Vysvetlenie pri balíkoch, ktoré niečo naozaj robia — aby bolo v admine hneď
 *  jasné, čo prepnutie spôsobí, a aby sa VIP neplietlo s `unlimited` (ten
 *  neodpočítava vôbec). */
export const PLAN_HINT: Partial<Record<Plan, string>> = {
  free: "Locked — cannot create models or buy coins until approved.",
  free_plus: "Approved — full access. Billed like Standard.",
  vip: "Billed at cost — no margin. Pipe Coins still run down.",
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
  live: "border-[rgba(74,222,128,0.28)] text-[#86efac]",
  stale: "border-[rgba(250,204,21,0.26)] text-[#fde047]",
  dead: "border-[rgba(248,113,113,0.3)] text-[#fca5a5]",
};

export const FRESHNESS_DOT: Record<Freshness, string> = {
  live: "bg-[#4ade80]",
  stale: "bg-[#facc15]",
  dead: "bg-[#f87171]",
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
