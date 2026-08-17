"use server";

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
  "language",
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
