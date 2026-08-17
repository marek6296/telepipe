"use server";

import { revalidatePath } from "next/cache";

import { getModel, requireUser } from "@/lib/models";
import { createClient, createServiceClient } from "@/lib/supabase/server";

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

/* -------------------------------------------------------------------------- */
/*  Nastavenia Fanvue agenta                                                   */
/* -------------------------------------------------------------------------- */

export type SaveResult = { error?: string };

const ENUMS: Record<string, readonly string[]> = {
  heat: ["mild", "medium", "hot"],
  post_audience: ["subscribers", "followers-and-subscribers"],
};

const BOOLEANS = [
  "greet_new",
  "sell_content",
  "send_photos",
  "thank_purchases",
  "voices_enabled",
  "posting_enabled",
] as const;

/**
 * stĺpec → [min, max]. Rozsahy sedia na `check` constrainty v migrácii 015 —
 * DB je posledná poistka, ale chybu z nej by používateľ videl ako
 * „violates check constraint", a to nie je hláška pre človeka.
 */
const INTEGERS: Record<string, [number, number]> = {
  discovery_msgs: [0, 20],
  summary_every: [1, 200],
  reply_min_s: [0, 3600],
  reply_max_s: [0, 3600],
  active_start_min: [0, 1439],
  active_end_min: [0, 1439],
  offer_after_msgs: [0, 200],
  offer_cooldown_h: [0, 720],
  nudge_after_msgs: [0, 500],
  voice_price_cents: [0, 100_000],
  free_photo_max: [0, 50],
  post_every_h: [0, 720],
};

/**
 * Uloženie nastavení Fanvue agenta.
 *
 * Ide USER-SCOPED klientom, nie service kľúčom: migrácia 015 dala klientovi
 * column-scoped `update` a policy `fanvue_owner_update`, takže o vlastníctve
 * rozhoduje RLS a nie náš `if`. Stĺpce, ktoré tu chýbajú (`enabled`,
 * `connected`, tokeny, `last_post_at`, `media_synced_at`), by aj tak skončili
 * chybou „permission denied" — to je zámer, nie nedopatrenie.
 */
export async function saveFanvueSettingsAction(
  modelId: string,
  patch: Record<string, unknown>,
): Promise<SaveResult> {
  const update: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(patch)) {
    if (key in ENUMS) {
      if (typeof value !== "string" || !ENUMS[key].includes(value)) {
        return { error: `Unexpected value for ${key}.` };
      }
      update[key] = value;
      continue;
    }
    if ((BOOLEANS as readonly string[]).includes(key)) {
      update[key] = Boolean(value);
      continue;
    }
    if (key in INTEGERS) {
      const number = Number(value);
      if (!Number.isFinite(number)) return { error: `${key} must be a number.` };
      const [min, max] = INTEGERS[key];
      update[key] = clamp(Math.round(number), min, max);
      continue;
    }
    if (key === "extra_rules") {
      update.extra_rules = String(value ?? "").slice(0, 4000);
      continue;
    }
    return { error: `Unknown field: ${key}` };
  }

  if (Object.keys(update).length === 0) return {};
  update.updated_at = new Date().toISOString();

  const supabase = await createClient();
  const { error } = await supabase.from("fanvue").update(update).eq("model_id", modelId);
  if (error) return { error: error.message };
  return {};
}

/* -------------------------------------------------------------------------- */
/*  Vault                                                                      */
/* -------------------------------------------------------------------------- */

const FOLDER_ROLES = ["ignore", "sfw", "nsfw", "post"];

/**
 * Rola priečinka a jeho východisková cena.
 *
 * Priečinky nevytvára klient — vznikajú synchronizáciou z vaultu. Preto je to
 * `update`, nie `upsert`: riadok pre priečinok, ktorý na Fanvue neexistuje, by
 * len ticho nikdy nič neposlal.
 */
export async function saveFolderAction(
  modelId: string,
  name: string,
  patch: { role?: string; price_cents?: number },
): Promise<SaveResult> {
  const update: Record<string, unknown> = {};

  if (patch.role !== undefined) {
    if (!FOLDER_ROLES.includes(patch.role)) return { error: "Unknown folder role." };
    update.role = patch.role;
  }
  if (patch.price_cents !== undefined) {
    const number = Number(patch.price_cents);
    if (!Number.isFinite(number)) return { error: "Price must be a number." };
    update.price_cents = clamp(Math.round(number), 0, 100_000);
  }
  if (Object.keys(update).length === 0) return {};
  update.updated_at = new Date().toISOString();

  const supabase = await createClient();
  const { error } = await supabase
    .from("fv_folders")
    .update(update)
    .eq("model_id", modelId)
    .eq("name", name);
  if (error) return { error: error.message };

  revalidatePath(`/app/m/${modelId}/fanvue`);
  return {};
}

/** Popis, cena, ostrosť a vypínač jednej fotky. Zvyšok riadku je záznam
 *  synchronizácie a klient naň grant nemá (migrácia 015). */
export async function saveMediaAction(
  modelId: string,
  mediaUuid: string,
  patch: { caption?: string; price_cents?: number; active?: boolean; spicy?: boolean },
): Promise<SaveResult> {
  const update: Record<string, unknown> = {};

  if (patch.caption !== undefined) update.caption = String(patch.caption).slice(0, 400);
  if (patch.active !== undefined) update.active = Boolean(patch.active);
  if (patch.spicy !== undefined) update.spicy = Boolean(patch.spicy);
  if (patch.price_cents !== undefined) {
    const number = Number(patch.price_cents);
    if (!Number.isFinite(number)) return { error: "Price must be a number." };
    update.price_cents = clamp(Math.round(number), 0, 100_000);
  }
  if (Object.keys(update).length === 0) return {};

  const supabase = await createClient();
  const { error } = await supabase
    .from("fv_media")
    .update(update)
    .eq("model_id", modelId)
    .eq("media_uuid", mediaUuid);
  if (error) return { error: error.message };
  return {};
}

/* -------------------------------------------------------------------------- */
/*  Fronta „načítaj vault"                                                     */
/* -------------------------------------------------------------------------- */

/** Po tomto čase sa čakajúca požiadavka považuje za stratenú. Worker si ju
 *  berie do štyroch sekúnd; pätnásť minút znamená, že nebeží vôbec. */
const SYNC_STALE_MS = 15 * 60 * 1000;

/**
 * Požiadavka o načítanie vaultu.
 *
 * Web ho načítať nevie a nemá: prístupový token je šifrovaný a dešifruje ho
 * jediné miesto — `worker/src/fanvue_tenant.py`. Sem teda ide len riadok do
 * fronty, ktorý si vezme `fvvault.VaultSync`.
 *
 * Vloženie ide user-scoped klientom (policy `fanvue_sync_owner_insert`), ale
 * vypršanie zaseknutej požiadavky service kľúčom: `finished_at` je stĺpec
 * workera a klient naň grant nemá — ani na svoj vlastný riadok.
 */
export async function requestVaultSyncAction(
  modelId: string,
): Promise<{ ok?: boolean; error?: string }> {
  await requireUser();
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  const admin = createServiceClient();
  const { data: connection } = await admin
    .from("fanvue")
    .select("connected, creator_uuid")
    .eq("model_id", model.id)
    .maybeSingle();

  if (!connection?.connected || !connection.creator_uuid) {
    return { error: "Connect the Fanvue account first." };
  }

  // Zaseknutá požiadavka je zámok (partial unique index z 015) — vypnutý worker
  // nesmie zablokovať tlačidlo navždy.
  await admin
    .from("fanvue_sync_requests")
    .update({
      finished_at: new Date().toISOString(),
      ok: false,
      error: "The worker did not pick this up in time.",
    })
    .eq("model_id", model.id)
    .is("finished_at", null)
    .lt("requested_at", new Date(Date.now() - SYNC_STALE_MS).toISOString());

  const supabase = await createClient();
  const { error } = await supabase.from("fanvue_sync_requests").insert({ model_id: model.id });

  if (error) {
    // 23505 = partial unique index, teda „jedna už čaká". To nie je chyba,
    // to je presne to, čo tlačidlo malo dosiahnuť.
    if (error.code === "23505") {
      revalidatePath(`/app/m/${model.id}/fanvue`);
      return { ok: true };
    }
    return { error: error.message };
  }

  revalidatePath(`/app/m/${model.id}/fanvue`);
  return { ok: true };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
