"use server";

import { loadVoiceCatalog, type VoiceCatalog } from "@/lib/eleven";
import { getAccount, requireUser } from "@/lib/models";

/**
 * Znovunačítanie zoznamu hlasov.
 *
 * Stránka si zoznam ťahá pri renderi, takže toto je len tlačidlo „skús znova" —
 * po prekľúčovaní v nastaveniach účtu alebo keď ElevenLabs práve nešlo.
 *
 * `accountId` sa berie z prihlásenia (`getAccount()`), nikdy z parametra: kľúč
 * sa číta service kľúčom, ktorý obchádza RLS, a jediné, čo tam potom drží
 * cudzie účty od seba, je práve toto.
 */
export async function reloadVoicesAction(): Promise<VoiceCatalog> {
  await requireUser();
  const account = await getAccount();
  if (!account) {
    return { connected: false, voices: [], error: "Your session expired. Sign in again." };
  }
  return loadVoiceCatalog(account.id);
}
