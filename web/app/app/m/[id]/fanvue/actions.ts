"use server";

import { revalidatePath } from "next/cache";

import { getModel, requireUser } from "@/lib/models";
import { createServiceClient } from "@/lib/supabase/server";

/**
 * Odpojenie Fanvue účtu.
 *
 * Klient na `fanvue` nemá žiadny zápisový grant (migrácia 011), takže sa píše
 * service kľúčom — a ten obchádza RLS. Preto sa vlastníctvo overuje najprv
 * user-scoped `getModel` a filter `model_id` je aj v samotnom update.
 *
 * Tokeny sa prepisujú na prázdny reťazec, nie mažú s riadkom: riadok je
 * singleton modelky (zakladá ho trigger) a jeho zmiznutie by len rozbilo UI.
 * Odvolať prístup treba aj na strane Fanvue — my zahodíme len to, čo držíme.
 */
export async function disconnectFanvueAction(
  modelId: string,
): Promise<{ ok?: boolean; error?: string }> {
  await requireUser();
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  const admin = createServiceClient();
  const { error } = await admin
    .from("fanvue")
    .update({
      connected: false,
      enabled: false,
      access_token_enc: "",
      refresh_token_enc: "",
      expires_at: null,
      scope: "",
      creator_uuid: "",
      handle: "",
      display_name: "",
      last_error: "",
      updated_at: new Date().toISOString(),
    })
    .eq("model_id", model.id);

  if (error) return { error: error.message };

  revalidatePath(`/app/m/${model.id}/fanvue`);
  return { ok: true };
}

/**
 * Zapnutie/vypnutie odpisovania na Fanvue (`fanvue.enabled`).
 *
 * `enabled` je vypínač AGENTA, nie pripojenia — účet môže byť pripojený a
 * ticho. Default je false a ostáva ním aj po pripojení: rozbehnúť odpisovanie
 * je vedomé rozhodnutie, nie vedľajší účinok OAuth redirectu.
 *
 * Klient na tento stĺpec nemá zápisový grant (migrácia 011), takže sa píše
 * service kľúčom — a ten obchádza RLS. Vlastníctvo preto overuje user-scoped
 * `getModel` a `model_id` je aj vo filtri samotného update.
 *
 * Zapnúť sa dá len pripojený účet: bez tokenov by agent aj tak hneď spadol na
 * refresh, a `connected` vo filtri je lacnejšie než to zistiť až vo workeri.
 */
export async function setFanvueEnabledAction(
  modelId: string,
  enabled: boolean,
): Promise<{ ok?: boolean; error?: string }> {
  await requireUser();
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  const admin = createServiceClient();
  const { data, error } = await admin
    .from("fanvue")
    .update({ enabled, updated_at: new Date().toISOString() })
    .eq("model_id", model.id)
    .eq("connected", true)
    .select("model_id");

  if (error) return { error: error.message };
  if (!data?.length) return { error: "Connect the Fanvue account first." };

  revalidatePath(`/app/m/${model.id}/fanvue`);
  return { ok: true };
}
