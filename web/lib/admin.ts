import { redirect } from "next/navigation";

import { adminErrorText, asPlan, asRole, type AccountRole, type AdminRole, type Plan } from "@/lib/admin-ui";
import { toNumber } from "@/lib/format";
import { requireUser } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

/**
 * Serverová admin vrstva. Všetko ide cez RPC z migrácie 009 volané USER-scoped
 * klientom — service key sa v aplikácii neobjaví nikdy. Autorizáciu stráži
 * `is_admin()` / `is_superadmin()` vnútri každej funkcie (chyba `forbidden`,
 * errcode 42501); my ju overujeme ešte raz, aby sa stránka ani nevykreslila.
 */

/* --------------------------------------------------------------------------
   Guardy
-------------------------------------------------------------------------- */

/** Vlastný riadok z `accounts` — rola je jediné, čo o prístupe rozhoduje. */
export async function getViewerRole(): Promise<AccountRole> {
  const user = await requireUser();
  const supabase = await createClient();
  const { data } = await supabase
    .from("accounts")
    .select("id, role, plan")
    .eq("id", user.id)
    .maybeSingle();

  return asRole(data?.role as string | undefined);
}

/**
 * Guard pre KAŽDÚ admin stránku aj server action. Neadmin nedostane 403, ale
 * ticho redirect do svojej appky — admin sekcia sa tak ani neprezradí.
 */
export async function requireAdmin(): Promise<AdminRole> {
  const role = await getViewerRole();
  if (role !== "admin" && role !== "superadmin") redirect("/app");
  return role;
}

/** Ako `requireAdmin`, ale pre veci, ktoré RPC pustí len superadminovi. */
export async function requireSuperadmin(): Promise<"superadmin"> {
  const role = await getViewerRole();
  if (role !== "superadmin") redirect("/app");
  return role;
}

/* --------------------------------------------------------------------------
   Čítanie — tvary vracia migrácia 009 (overené na živej DB).
-------------------------------------------------------------------------- */

export type AdminAccount = {
  id: string;
  email: string;
  role: AccountRole;
  plan: Plan;
  creditBalance: number;
  createdAt: string;
  modelsCount: number;
  spend30d: number;
};

export type AdminModel = {
  id: string;
  accountId: string;
  accountEmail: string;
  name: string;
  /** Typ agenta (migrácia 018) — štítok v tabuľke, nie filter. */
  modelType: string;
  status: string;
  statusReason: string;
  claimedBy: string | null;
  heartbeatAt: string | null;
  msgsToday: number;
  spendToday: number;
};

export type AdminReplica = {
  name: string;
  tenantCount: number;
  lastSeen: string | null;
  startedAt: string | null;
  stale: boolean;
};

export type AdminUsageDay = {
  day: string;
  charged: number;
  atlasCost: number;
  margin: number;
  events: number;
};

async function rpc<T>(name: string, args?: Record<string, unknown>): Promise<T[]> {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc(name, args ?? {});
  if (error) throw new Error(adminErrorText(error.message));
  return (data ?? []) as T[];
}

type AccountRowRaw = {
  id: string;
  email: string | null;
  role: string;
  plan: string;
  credit_balance_usd: string | number;
  created_at: string;
  models_count: string | number;
  spend_30d: string | number;
};

export async function listAdminAccounts(): Promise<AdminAccount[]> {
  const rows = await rpc<AccountRowRaw>("admin_list_accounts");
  return rows.map((row) => ({
    id: row.id,
    email: row.email ?? "",
    role: asRole(row.role),
    plan: asPlan(row.plan),
    creditBalance: toNumber(row.credit_balance_usd),
    createdAt: row.created_at,
    modelsCount: toNumber(row.models_count),
    spend30d: toNumber(row.spend_30d),
  }));
}

type ModelRowRaw = {
  id: string;
  account_id: string;
  account_email: string | null;
  name: string | null;
  model_type: string | null;
  status: string;
  status_reason: string | null;
  claimed_by: string | null;
  heartbeat_at: string | null;
  msgs_today: string | number;
  spend_today: string | number;
};

export async function listAdminModels(): Promise<AdminModel[]> {
  const rows = await rpc<ModelRowRaw>("admin_list_models");
  return rows.map((row) => ({
    id: row.id,
    accountId: row.account_id,
    accountEmail: row.account_email ?? "",
    name: row.name ?? "",
    modelType: row.model_type ?? "persona",
    status: row.status,
    statusReason: row.status_reason ?? "",
    claimedBy: row.claimed_by,
    heartbeatAt: row.heartbeat_at,
    msgsToday: toNumber(row.msgs_today),
    spendToday: toNumber(row.spend_today),
  }));
}

type ReplicaRowRaw = {
  replica_name: string;
  tenant_count: string | number;
  last_seen: string | null;
  started_at: string | null;
  stale: boolean;
};

export async function listAdminReplicas(): Promise<AdminReplica[]> {
  const rows = await rpc<ReplicaRowRaw>("admin_list_replicas");
  return rows.map((row) => ({
    name: row.replica_name,
    tenantCount: toNumber(row.tenant_count),
    lastSeen: row.last_seen,
    startedAt: row.started_at,
    stale: Boolean(row.stale),
  }));
}

type UsageRowRaw = {
  day: string;
  charged_usd: string | number;
  atlas_cost_usd: string | number;
  margin_usd: string | number;
  events: string | number;
};

/**
 * RPC vracia LEN dni, v ktorých niečo bolo (group by). Graf potrebuje súvislú
 * os, tak prázdne dni doplníme na nuly.
 */
export async function adminUsageSummary(days: number): Promise<AdminUsageDay[]> {
  const rows = await rpc<UsageRowRaw>("admin_usage_summary", { p_days: days });

  const byDay = new Map<string, AdminUsageDay>();
  for (const row of rows) {
    const key = String(row.day).slice(0, 10);
    byDay.set(key, {
      day: key,
      charged: toNumber(row.charged_usd),
      atlasCost: toNumber(row.atlas_cost_usd),
      margin: toNumber(row.margin_usd),
      events: toNumber(row.events),
    });
  }

  const now = new Date();
  const start = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate() - (days - 1),
  );

  const filled: AdminUsageDay[] = [];
  for (let index = 0; index < days; index += 1) {
    const key = new Date(start + index * 86_400_000).toISOString().slice(0, 10);
    filled.push(
      byDay.get(key) ?? { day: key, charged: 0, atlasCost: 0, margin: 0, events: 0 },
    );
  }
  return filled;
}
