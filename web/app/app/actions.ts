"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { requireUser } from "@/lib/models";

export type ActionResult = { error?: string; ok?: boolean };

/**
 * Nová modelka. Klient smie zapísať len `account_id` a `name` (column grant
 * v migrácii 007) — status ostáva na DB defaulte `draft`, singleton riadky
 * (persona/behavior/settings) doplní trigger `models_provision_rows`.
 */
export async function createModelAction(
  _prev: ActionResult | undefined,
  formData: FormData,
): Promise<ActionResult> {
  const user = await requireUser();
  const name = String(formData.get("name") ?? "").trim();

  if (name.length < 2) {
    return { error: "Give her a name with at least 2 characters." };
  }
  if (name.length > 60) {
    return { error: "That name is too long — keep it under 60 characters." };
  }

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("models")
    .insert({ account_id: user.id, name })
    .select("id")
    .single();

  if (error || !data) {
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

/** Zmazanie modelky — kaskáda v DB zmaže personu, chaty aj históriu. */
export async function deleteModelAction(modelId: string): Promise<ActionResult> {
  const supabase = await createClient();
  const { error } = await supabase.from("models").delete().eq("id", modelId);

  if (error) return { error: error.message };

  revalidatePath("/app", "layout");
  redirect("/app/models");
}
