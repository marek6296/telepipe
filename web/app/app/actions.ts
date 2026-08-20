"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { requireUnlocked, requireUser } from "@/lib/models";
import {
  DEFAULT_MODEL_TYPE,
  isModelTypeEnabled,
  modelTypeHasTab,
} from "@/lib/model-types";

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
  // RLS to zastaví tak či tak (`models_owner_insert` → `account_unlocked`), ale
  // zamknutý človek sa sem cez UI nemá ako dostať — a keby áno, nech dostane
  // redirect na `/locked`, nie hlášku z databázy.
  await requireUnlocked();
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
    // Strop slotov stráži trigger `models_slot_limit` v databáze, nie táto
    // akcia — modelka sa dá založiť viacerými cestami a dva súbežné requesty
    // pri jednom voľnom slote by kontrolu tu oba prešli. Sem už príde len
    // strojová hláška, ktorú treba preložiť do ľudskej.
    if (error?.message.includes("no free model slot")) {
      return {
        error:
          "All your model slots are in use. Delete a model to free one up, or add a slot on the Models page.",
      };
    }
    return { error: error?.message ?? "Could not create the model. Please try again." };
  }

  revalidatePath("/app", "layout");

  // Prvá otázka po založení je „chceš pomoc s personou?", nie „vlož api_id".
  // Kto pomoc nechce, klikne na tej istej obrazovke „set her up manually" a
  // pokračuje na Telegram — poradie sa mu nevnucuje, len ponúka.
  //
  // Typ, ktorý kartu Persona nemá, ide rovno na Telegram. Test je na mape
  // typov, nie na `=== "persona"`: nový typ tak nepotrebuje zásah tu.
  if (modelTypeHasTab(modelType, "persona")) {
    redirect(`/app/m/${data.id}/persona/build`);
  }
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
  // `paused_until` sa nuluje spolu s tým — je to tretia cesta k tomu istému
  // tichu (uspatie z control bota) a „Resume replies", ktoré ju nechá bežať,
  // by tlačidlo spravilo klamlivým: klient klikne a modelka mlčí ďalej.
  const { error } = await supabase
    .from("settings")
    .update({ ai_paused: paused, ...(paused ? {} : { paused_until: null }) })
    .eq("model_id", modelId);

  if (error) return { error: error.message };

  revalidatePath("/app", "layout");
  return { ok: true };
}

/**
 * „Reset stats" na dashboarde — čistý štart bez mazania účtovníctva.
 *
 * ČO ROBÍ: posunie `accounts.stats_since` na teraz (migrácia 027). Klientove
 * vlastné prehľady od tej chvíle počítajú od nuly.
 *
 * ČO NEROBÍ: nemaže `usage_events`. Tá tabuľka je účtovný ledger — je z nej
 * marža, zostatok aj dôkaz, za čo klient zaplatil. Keby ju vedelo vymazať
 * tlačidlo v prehliadači, história peňazí by bola prepisovateľná. Preto UI
 * hovorí rovno, že sa nič nemaže: čísla sa len začínajú počítať odznova a
 * stránka Usage ostáva úplným výpisom.
 *
 * Vlastníctvo rieši RPC: `reset_my_stats()` nemá parameter účtu a mení riadok
 * podľa `auth.uid()`, takže na cudzí účet sa cez ňu nedá siahnuť.
 */
export async function resetStatsAction(): Promise<ActionResult> {
  const supabase = await createClient();
  const { error } = await supabase.rpc("reset_my_stats");

  if (error) {
    return {
      error: error.message.includes("account not found")
        ? "We could not find your account. Sign in again."
        : "Could not reset your stats. Try again.",
    };
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

/* -------------------------------------------------------------------------- */
/*  Sloty na modelky                                                           */
/* -------------------------------------------------------------------------- */

/**
 * Kúpa ďalšieho slotu. Celá logika (kontrola zostatku, strop 8, odpočet,
 * zápis do `model_slot_purchases`) je v RPC `buy_model_slot` — jedna
 * transakcia, takže dva súbežné kliky nemôžu strhnúť dvakrát a pripísať raz.
 *
 * Tu prekladáme len strojové hlášky do ľudských; sumu ani strop tu NEDRŽÍME,
 * aby cena nemala dve pravdy (druhá by časom začala klamať).
 */
export async function buyModelSlotAction(): Promise<ActionResult> {
  await requireUser();
  await requireUnlocked();

  const supabase = await createClient();
  const { error } = await supabase.rpc("buy_model_slot");

  if (error) {
    const message = error.message ?? "";
    if (message.includes("insufficient credits")) {
      return { error: "Not enough Pipe Coins for another slot. Top up and try again." };
    }
    if (message.includes("slot limit reached")) {
      return { error: "You already have the maximum number of model slots." };
    }
    if (message.includes("does not need slots")) {
      return { error: "Your account already has unlimited models." };
    }
    return { error: "Could not add the slot. Please try again." };
  }

  revalidatePath("/app", "layout");
  return { ok: true };
}
