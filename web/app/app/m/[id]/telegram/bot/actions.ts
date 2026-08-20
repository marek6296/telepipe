"use server";

import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

/**
 * Prepínače notifikácií control bota.
 *
 * Whitelist stĺpcov je tu preto, aby sa cez patch nedal poslať `daily_report_sent_at`
 * ani `credits_warned_at` — to sú poistky workera proti opakovaným správam a
 * klient si ich prepísaním vypne. RLS chráni cudzie riadky, nie tvar dát;
 * skutočnú hranicu drží stĺpcový grant v databáze, toto je prvá z dvoch.
 */
const PREPINACE = [
  "notify_fanvue_subscribe",
  "notify_fanvue_payment",
  "notify_fanvue_follow",
  "notify_fanvue_like",
  "notify_fanvue_comment",
  "notify_credits_low",
  "notify_startup",
  "notify_crash",
  "notify_hot_lead",
  "daily_report",
  "weekly_report",
] as const;

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
    update[key] = Boolean(value);
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
