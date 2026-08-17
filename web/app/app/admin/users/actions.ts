"use server";

import { revalidatePath } from "next/cache";

import { requireAdmin, requireSuperadmin } from "@/lib/admin";
import { PLANS, ROLES, adminErrorText, type Plan, type AccountRole } from "@/lib/admin-ui";
import { createClient } from "@/lib/supabase/server";
import { toNumber } from "@/lib/format";

/**
 * Admin akcie. Autorizácia je dvakrát: raz tu (`requireAdmin` / `requireSuperadmin`,
 * aby neadmin nedostal ani chybovú hlášku) a raz v RPC (`is_admin()` v DB, ktorá
 * je jediná skutočná obrana). Volá sa user-scoped klientom.
 */

export type AdminActionResult = { error?: string; ok?: boolean };
export type CreditResult = AdminActionResult & { balance?: number };
export type PlanResult = AdminActionResult & { plan?: Plan };
export type RoleResult = AdminActionResult & { role?: AccountRole };

const MAX_CREDIT = 100_000;

/** Zmena balíka — RPC drží whitelist free/starter/pro/custom. */
export async function setPlanAction(accountId: string, plan: string): Promise<PlanResult> {
  await requireAdmin();

  if (!PLANS.includes(plan as Plan)) {
    return { error: "Unknown plan." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_set_plan", {
    p_account: accountId,
    p_plan: plan,
  });

  if (error) return { error: adminErrorText(error.message) };

  revalidatePath("/app/admin/users");
  return { ok: true, plan: (data as Plan) ?? (plan as Plan) };
}

/**
 * Pridanie/odobranie kreditu. RPC zapíše riadok do `credit_adjustments` (audit,
 * kto komu koľko) a vráti nový zostatok.
 */
export async function addCreditAction(
  accountId: string,
  amount: number,
  note: string,
): Promise<CreditResult> {
  await requireAdmin();

  if (!Number.isFinite(amount) || amount === 0) {
    return { error: "Enter an amount other than zero." };
  }
  if (Math.abs(amount) > MAX_CREDIT) {
    return { error: `Keep the adjustment under $${MAX_CREDIT.toLocaleString("en-US")}.` };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_add_credit", {
    p_account: accountId,
    p_amount: Number(amount.toFixed(4)),
    p_note: note.slice(0, 500),
  });

  if (error) return { error: adminErrorText(error.message) };

  revalidatePath("/app/admin/users");
  revalidatePath("/app/admin");
  return { ok: true, balance: toNumber(data as string | number) };
}

/**
 * Zmena roly — LEN superadmin. Posledného superadmina DB degradovať nedovolí
 * (`cannot demote the last superadmin`), inak by sa admin sekcia uzamkla navždy.
 */
export async function setRoleAction(accountId: string, role: string): Promise<RoleResult> {
  await requireSuperadmin();

  if (!ROLES.includes(role as AccountRole)) {
    return { error: "Unknown role." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_set_role", {
    p_account: accountId,
    p_role: role,
  });

  if (error) return { error: adminErrorText(error.message) };

  revalidatePath("/app", "layout");
  return { ok: true, role: (data as AccountRole) ?? (role as AccountRole) };
}
