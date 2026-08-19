"use server";

import { normalizeExtra, normalizePrimary } from "@/lib/languages";
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
