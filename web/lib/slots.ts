import { cache } from "react";

import { createClient } from "@/lib/supabase/server";

/**
 * Sloty na modelky a ceny za kus.
 *
 * PRAVDA JE V DATABÁZE (`app_config`), nie tu.
 * Cena musí byť na dvoch miestach naraz: transakcia ju strháva, ale UI ju
 * musí napísať skôr, než klient klikne. Keby bola v kóde, sú to dve pravdy
 * a raz sa rozídu — tlačidlo sľúbi jedno a účet strhne druhé. Preto ju
 * čítame odtiaľ, kde ju číta aj RPC `buy_model_slot`.
 *
 * Čísla nižšie sú POISTKA pre prípad, že sa riadok nenačíta (výpadok, chýbajúci
 * grant) — nie cenník. Musia sedieť s hodnotami v migrácii 20260819160000.
 */
const FALLBACK = {
  model_slot_usd: 20,
  max_model_slots: 8,
  voice_managed_usd: 0.5,
  voice_own_usd: 0.3,
  photo_usd: 0.1,
} as const;

export type ConfigKey = keyof typeof FALLBACK;

/**
 * Celá konfigurácia naraz. `cache` drží hodnotu v rámci jedného renderu, takže
 * layout aj stránka platia jeden dotaz.
 */
export const getAppConfig = cache(async function getAppConfig(): Promise<
  Record<ConfigKey, number>
> {
  const supabase = await createClient();
  const { data, error } = await supabase.from("app_config").select("key, value");

  if (error || !data) return { ...FALLBACK };

  const config = { ...FALLBACK } as Record<ConfigKey, number>;
  for (const row of data as { key: string; value: number | string }[]) {
    if (row.key in config) {
      const parsed = Number(row.value);
      if (Number.isFinite(parsed)) config[row.key as ConfigKey] = parsed;
    }
  }
  return config;
});

/**
 * Kto strop nemá. Zrkadlí SQL funkciu `account_slot_exempt()` — admin a
 * superadmin rolou, kamarát plánom `vip`. `vip_lite` sloty MÁ: jeho zľava je
 * na spotrebe, nie na kapacite.
 */
export function isSlotExempt(account: { role: string; plan: string }): boolean {
  return (
    account.role === "admin" || account.role === "superadmin" || account.plan === "vip"
  );
}
