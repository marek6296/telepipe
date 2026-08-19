"use server";

import { revalidatePath } from "next/cache";

import { requireSuperadmin } from "@/lib/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Ceny a marže. Autorizácia je dvakrát: raz tu (`requireSuperadmin`, aby sa
 * bežný admin nedostal ani k chybovej hláške) a raz v RPC `admin_set_config`
 * (`is_superadmin()` v DB) — tá je jediná skutočná obrana.
 *
 * Prečo superadmin a nie admin: toto sú peniaze celej platformy, nie jedného
 * účtu. Zmena `margin_free_plus` prepíše maržu všetkým klientom naraz.
 */

export type ConfigResult = { error?: string; ok?: boolean; value?: number };

/** Rozumné medze — poistka proti preklepu, nie cenová politika. */
const LIMITS: Record<string, { min: number; max: number }> = {
  margin_free: { min: 1, max: 10 },
  margin_free_plus: { min: 1, max: 10 },
  margin_vip_lite: { min: 1, max: 10 },
  margin_vip: { min: 1, max: 10 },
  voice_managed_usd: { min: 0, max: 10 },
  voice_own_usd: { min: 0, max: 10 },
  photo_usd: { min: 0, max: 10 },
  model_slot_usd: { min: 0, max: 500 },
  max_model_slots: { min: 1, max: 100 },
};

export async function setConfigAction(key: string, value: number): Promise<ConfigResult> {
  await requireSuperadmin();

  const limit = LIMITS[key];
  if (!limit) return { error: "Unknown setting." };
  if (!Number.isFinite(value)) return { error: "That is not a number." };
  if (value < limit.min || value > limit.max) {
    return { error: `Value must be between ${limit.min} and ${limit.max}.` };
  }

  // Marža pod 1.0 by znamenala, že klientovi účtujeme MENEJ, než nás stojí
  // Atlas — každá jeho správa by nás stála peniaze. Nechať to na preklep
  // v prehliadači je príliš drahá chyba.
  if (key.startsWith("margin_") && value < 1) {
    return { error: "A margin below 1.0 would bill less than the tokens cost us." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_set_config", {
    p_key: key,
    p_value: value,
  });

  if (error) {
    if (error.message.includes("forbidden")) {
      return { error: "Only a superadmin can change pricing." };
    }
    if (error.message.includes("unknown config key")) {
      return { error: "Unknown setting." };
    }
    return { error: "Could not save. Try again." };
  }

  revalidatePath("/app/admin/pricing");
  revalidatePath("/app", "layout");
  return { ok: true, value: Number(data) };
}
