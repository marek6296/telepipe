"use server";

import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

/**
 * Jediná aktívna notifikácia control bota: nová správa vyžadujúca pozornosť.
 *
 * Whitelist stĺpcov je tu preto, aby sa cez patch nedal poslať `daily_report_sent_at`
 * ani `credits_warned_at` — to sú poistky workera proti opakovaným správam a
 * klient si ich prepísaním vypne. RLS chráni cudzie riadky, nie tvar dát;
 * skutočnú hranicu drží stĺpcový grant v databáze, toto je prvá z dvoch.
 */
const PREPINACE = ["notify_social_inbound"] as const;

export type BotSettingsResult = { error?: string };

export async function saveBotSettingsAction(
  modelId: string,
  patch: Record<string, unknown>,
): Promise<BotSettingsResult> {
  // Kontrola vlastníctva aj toho, že modelka Telegram vôbec má.
  await requireModelSubTab(modelId, "telegram", "bot");

  const update: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(patch)) {
    if (!(PREPINACE as readonly string[]).includes(key)) {
      return { error: `Unknown setting: ${key}` };
    }
    if (typeof value !== "boolean") return { error: "Notification settings must be true or false." };
    update[key] = value;
  }
  if (Object.keys(update).length === 0) return {};
  update.updated_at = new Date().toISOString();

  const supabase = await createClient();
  // `upsert` a nie `update`: modelka založená pred migráciou riadok nemá a
  // prvé prepnutie by ticho neurobilo nič.
  const { error } = await supabase
    .from("control_bot_settings")
    .upsert({ model_id: modelId, ...update }, { onConflict: "model_id" });

  if (error) return { error: error.message };
  return {};
}
