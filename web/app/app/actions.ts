"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/models";
import { DEFAULT_MODEL_TYPE, isModelTypeEnabled } from "@/lib/model-types";

export type ActionResult = { error?: string; ok?: boolean };

/**
 * Nová modelka. Klient smie zapísať `account_id`, `name` a `model_type`
 * (column granty z migrácií 007 a 018) — status ostáva na DB defaulte `draft`,
 * singleton riadky (persona/behavior/settings) doplní trigger
 * `models_provision_rows`.
 *
 * Typ sa validuje proti allowlistu ZAPNUTÝCH typov, nie proti zoznamu známych:
 * prepnúť si v dev tools `disabled` na karte „Coming soon" nesmie stačiť. A keby
 * niekto obišiel aj túto akciu, čaká ho trigger `models_type_guard` v DB — UI
 * nie je hranica bezpečnosti, len prvá z dvoch.
 *
 * Zakladanie je zámerne v JEDNEJ akcii, aby sa nad ňu dal neskôr nasadiť ďalší
 * krok dialógu (napr. asistovaná tvorba persony) bez toho, aby sa vytváranie
 * modelky rozsypalo do viacerých ciest.
 */
export async function createModelAction(
  _prev: ActionResult | undefined,
  formData: FormData,
): Promise<ActionResult> {
  const user = await requireUser();
  const name = String(formData.get("name") ?? "").trim();
  const modelType = String(formData.get("model_type") ?? DEFAULT_MODEL_TYPE);

  if (name.length < 2) {
    return { error: "Give it a name with at least 2 characters." };
  }
  if (name.length > 60) {
    return { error: "That name is too long — keep it under 60 characters." };
  }
  if (!isModelTypeEnabled(modelType)) {
    return { error: "That agent type is not available yet — pick AI Persona Agent." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("models")
    .insert({ account_id: user.id, name, model_type: modelType })
    .select("id")
    .single();

  if (error || !data) {
    // Hláška z `models_type_guard` je strojová — klientovi povieme to isté,
    // čo by mu povedala validácia vyššie.
    if (error?.message.includes("model type not available yet")) {
      return { error: "That agent type is not available yet — pick AI Persona Agent." };
    }
    return { error: error?.message ?? "Could not create the model. Please try again." };
  }

  revalidatePath("/app", "layout");
  // Rovno do wizardu — bez Telegram účtu nemá modelka čo robiť.
  redirect(`/app/m/${data.id}/telegram`);
}

/** Premenovanie. Jediný stĺpec, ktorý smie klient meniť voľne. */
export async function renameModelAction(
  modelId: string,
  name: string,
): Promise<ActionResult> {
  const trimmed = name.trim();
  if (trimmed.length < 2 || trimmed.length > 60) {
    return { error: "Name must be between 2 and 60 characters." };
  }

  const supabase = await createClient();
  const { error } = await supabase
    .from("models")
    .update({ name: trimmed, updated_at: new Date().toISOString() })
    .eq("id", modelId);

  if (error) return { error: error.message };

  revalidatePath("/app", "layout");
  return { ok: true };
}

/**
 * Zmena stavu ide výhradne cez RPC `set_model_status` — klient nemá grant na
 * stĺpec `status` a RPC stráži whitelist prechodov (draft→active, active→paused,
 * paused→active, error→active okrem odvolanej session).
 */
export async function setModelStatusAction(
  modelId: string,
  status: "active" | "paused",
): Promise<ActionResult> {
  const supabase = await createClient();
  const { error } = await supabase.rpc("set_model_status", {
    p_model: modelId,
    p_status: status,
  });

  if (error) {
    if (error.message.includes("not allowed")) {
      return {
        error:
          "That switch is not available right now — refresh the page to see her current state.",
      };
    }
    if (error.message.includes("model not found")) {
      return { error: "Model not found." };
    }
    return { error: error.message };
  }

  revalidatePath("/app", "layout");
  return { ok: true };
}

/**
 * Zrušenie globálnej pauzy odpovedania (`settings.ai_paused`).
 *
 * PREČO TO NIE JE POWER BUTTON: `models.status` hovorí, či agent beží;
 * `settings.ai_paused` hovorí, či beží a mlčí. Pauzu zapína worker sám po
 * `PeerFloodError` a control bot v Telegrame — dashboard ju doteraz nevedel ani
 * ukázať, nieto zrušiť. Zlúčiť tieto dve veci do jedného tlačidla by znamenalo,
 * že „chcem zase odpovedať" zhodí a nadvihne Telethon session; po flood
 * warningu je to presne ten pohyb, ktorý účet stojí život.
 *
 * Zapisuje user-scoped klient — `settings` má od 007 plný RLS-krytý grant, cudzí
 * riadok teda skončí ako 0 zmenených riadkov, nie ako chyba.
 */
export async function setAiPausedAction(
  modelId: string,
  paused: boolean,
): Promise<ActionResult> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("settings")
    .update({ ai_paused: paused })
    .eq("model_id", modelId);

  if (error) return { error: error.message };

  revalidatePath("/app", "layout");
  return { ok: true };
}

/** Zmazanie modelky — kaskáda v DB zmaže personu, chaty aj históriu. */
export async function deleteModelAction(modelId: string): Promise<ActionResult> {
  const supabase = await createClient();
  const { error } = await supabase.from("models").delete().eq("id", modelId);

  if (error) return { error: error.message };

  revalidatePath("/app", "layout");
  redirect("/app/models");
}
