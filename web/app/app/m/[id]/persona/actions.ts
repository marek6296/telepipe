"use server";

import { revalidatePath } from "next/cache";

import { normalizeExtra, normalizePrimary } from "@/lib/languages";
import { PRESET_FIELDS, buildPreset } from "@/lib/persona-preset";
import { createClient } from "@/lib/supabase/server";

/**
 * Uloženie persony. Worker ju číta pri každej odpovedi, takže zmena platí od
 * najbližšej správy — žiadny reštart, žiadne „Save" tlačidlo.
 *
 * Whitelist stĺpcov je tu preto, aby sa cez patch nedalo poslať čokoľvek —
 * RLS síce chráni cudzie riadky, ale nie tvar dát.
 */

const TEXT_COLUMNS = [
  "name",
  "city",
  // `language` (voľný text) sa už do promptu nedáva — jazyk určuje
  // `lang_primary`. Ostáva v databáze kvôli starým riadkom, ale zapisovať sa
  // nedá: dve pravdy o jazyku by si v prompte odporovali.
  "languages",
  "backstory",
  "tone",
  "msg_style",
  "boundaries",
  "funnel_rules",
  "cta_link",
  // Zamknutá fotka — druhá cesta k peniazom popri odkaze na platformu.
  // Vypnutá je zámerne: väčšina klientov chce len svoj funnel.
  "unlock_link",
  "unlock_enabled",
  "extra_rules",
  "examples",
] as const;

export type SaveResult = { error?: string };

export async function savePersonaAction(
  modelId: string,
  patch: Record<string, unknown>,
): Promise<SaveResult> {
  const update: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(patch)) {
    if ((TEXT_COLUMNS as readonly string[]).includes(key)) {
      update[key] = typeof value === "string" ? value.slice(0, 8000) : "";
      continue;
    }
    // Jazyky sa neukladajú naslepo — do databázy smie ísť len to, čo appka
    // pozná. CHECK v DB stráži tvar, toto stráži katalóg: kód mimo zoznamu by
    // prešiel constraintom, ale worker by ho v prompte nemal ako pomenovať.
    if (key === "lang_primary") {
      update.lang_primary = normalizePrimary(value);
      continue;
    }
    if (key === "lang_extra") {
      // Primárny musí byť známy UŽ TERAZ, inak by `normalizeExtra` nevedela,
      // ktorý kód z poľa vyhodiť ako duplicitu hlavného jazyka.
      const primary =
        typeof patch.lang_primary === "string"
          ? normalizePrimary(patch.lang_primary)
          : normalizePrimary(await currentPrimary(modelId));
      update.lang_extra = normalizeExtra(value, primary);
      continue;
    }
    // Platforma mení LEN to, ako stránku pomenuje. Whitelist je tu preto, aby
    // sa do stĺpca nedostala hodnota, ktorú prompt nevie preložiť na názov —
    // vtedy by o stránke mlčala, hoci klient si myslí, že ju menuje.
    if (key === "platform") {
      const platform = String(value);
      if (!["fanvue", "onlyfans", "other"].includes(platform)) {
        return { error: "Unknown platform." };
      }
      update.platform = platform;
      continue;
    }
    if (key === "age") {
      if (value === null || value === "") {
        update.age = null;
        continue;
      }
      const age = Number(value);
      if (!Number.isFinite(age) || age < 18 || age > 99) {
        return { error: "Age must be between 18 and 99." };
      }
      update.age = Math.round(age);
      continue;
    }
    return { error: `Unknown field: ${key}` };
  }

  if (Object.keys(update).length === 0) return {};

  if (typeof update.cta_link === "string" && update.cta_link.trim()) {
    const link = update.cta_link.trim();
    if (!/^https?:\/\/\S+\.\S+/.test(link)) {
      return { error: "The link must start with https:// and look like a real URL." };
    }
    update.cta_link = link;
  }

  // Ten istý tvar ako `cta_link` — zlý odkaz by modelka poslala tak, ako je,
  // a fanúšik by skončil na chybovej stránke.
  if (typeof update.unlock_link === "string" && update.unlock_link.trim()) {
    const link = update.unlock_link.trim();
    if (!/^https?:\/\/\S+\.\S+/.test(link)) {
      return { error: "The locked-photo link must start with https:// and look like a real URL." };
    }
    update.unlock_link = link;
  }

  if (typeof update.name === "string" && !update.name.trim()) {
    return { error: "She needs a name — it is the one thing every message leans on." };
  }

  update.updated_at = new Date().toISOString();

  const supabase = await createClient();
  const { error } = await supabase.from("persona").update(update).eq("model_id", modelId);

  if (error) return { error: error.message };
  return {};
}

/**
 * Aktuálny hlavný jazyk modelky.
 *
 * Potrebné vtedy, keď patch nesie len `lang_extra` (klient pridal jazyk, ale
 * hlavný nemenil). Bez neho by sa nedalo rozhodnúť, či niektorý z vedľajších
 * nie je zhodou okolností ten hlavný — a CHECK v databáze by patch odmietol
 * chybou, ktorej by klient nerozumel.
 */
async function currentPrimary(modelId: string): Promise<string> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("persona")
    .select("lang_primary")
    .eq("model_id", modelId)
    .maybeSingle();
  return (data as { lang_primary?: string } | null)?.lang_primary ?? "";
}

/* -------------------------------------------------------------------------- */
/*  Easy agent — prepínač módu                                                 */
/* -------------------------------------------------------------------------- */

/**
 * Prepnutie medzi Personal a Easy.
 *
 * PRI ZAPNUTÍ EASY sa preset zapíše LEN DO PRÁZDNYCH polí. Čo si klient napísal
 * sám, ostáva — prepínač nie je „zahoď moju prácu". Práve preto sa dá zapnúť aj
 * na rozrobenej modelke a doplní len to, čo chýba.
 *
 * PRI VYPNUTÍ sa NEMAŽE nič. Klient dostane plný formulár aj s tým, čo mu
 * preset naplnil, a môže to prepísať. Mazať by znamenalo, že prepnutie tam a
 * späť zmaže rozpísanú personu.
 *
 * Worker o `setup_mode` NEVIE a vedieť nemá: preset skončí v tabuľke `persona`
 * a číta sa odtiaľ presne ako čokoľvek ručne napísané. Vďaka tomu nemôže tento
 * prepínač rozbiť bežiacu modelku — mení dáta, nie správanie.
 */
export async function setSetupModeAction(
  modelId: string,
  mode: "personal" | "easy",
): Promise<SaveResult> {
  if (mode !== "personal" && mode !== "easy") {
    return { error: "Unknown mode." };
  }

  const supabase = await createClient();

  if (mode === "easy") {
    // Meno, vek a mesto musia byť známe UŽ TERAZ — backstory sa o ne opiera.
    // Bez nich by vznikla šablóna, v ktorej si modelka vek aj bydlisko vymyslí
    // pri každej odpovedi inak.
    const { data, error } = await supabase
      .from("persona")
      .select(
        "name, age, city, backstory, tone, msg_style, boundaries, funnel_rules, examples",
      )
      .eq("model_id", modelId)
      .maybeSingle();

    if (error) return { error: error.message };
    if (!data) return { error: "Her persona row is missing. Reload the page." };

    const row = data as Record<string, unknown>;
    if (!String(row.name ?? "").trim()) {
      return { error: "Give her a name first — the preset is written around it." };
    }

    const preset = buildPreset({
      name: String(row.name ?? ""),
      age: typeof row.age === "number" ? row.age : null,
      city: String(row.city ?? ""),
    });

    const update: Record<string, string> = {};
    for (const field of PRESET_FIELDS) {
      if (!String(row[field] ?? "").trim()) update[field] = preset[field];
    }

    if (Object.keys(update).length > 0) {
      const { error: writeError } = await supabase
        .from("persona")
        .update({ ...update, updated_at: new Date().toISOString() })
        .eq("model_id", modelId);
      if (writeError) return { error: writeError.message };
    }
  }

  const { error } = await supabase
    .from("models")
    .update({ setup_mode: mode })
    .eq("id", modelId);

  if (error) return { error: error.message };

  revalidatePath("/app", "layout");
  return {};
}
