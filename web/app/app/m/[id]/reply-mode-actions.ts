"use server";

import { createClient } from "@/lib/supabase/server";

/**
 * Uloženie režimu odpovedania (Off / Auto / Semi) + času do auto-odoslania.
 * Per kanál a nezávisle: Telegram žije na `settings` (tg_reply_mode,
 * tg_fallback_minutes), Fanvue na `fanvue` (reply_mode, fallback_minutes).
 * Ide cez RLS klienta (owner policy), nie service kľúčom — je to obyčajný
 * formulár. Worker číta tie isté stĺpce (spec §8).
 */

const MODES = ["off", "auto", "semi"] as const;
export type ReplyMode = (typeof MODES)[number];
export type SaveResult = { error?: string };

export async function saveReplyModeAction(
  modelId: string,
  channel: "telegram" | "fanvue",
  patch: { mode?: string; fallback_minutes?: number | null | string },
): Promise<SaveResult> {
  const supabase = await createClient();
  const body: Record<string, unknown> = {};

  if (patch.mode !== undefined) {
    if (!MODES.includes(patch.mode as ReplyMode)) return { error: "Invalid mode." };
    body[channel === "telegram" ? "tg_reply_mode" : "reply_mode"] = patch.mode;
  }

  if (patch.fallback_minutes !== undefined) {
    // 0 / prázdne / neplatné = „čakaj navždy" (NULL). Inak 1–1440 min.
    let minutes: number | null = Number(patch.fallback_minutes);
    if (!Number.isFinite(minutes) || minutes < 1) minutes = null;
    else minutes = Math.min(1440, Math.round(minutes));
    body[channel === "telegram" ? "tg_fallback_minutes" : "fallback_minutes"] = minutes;
  }

  if (Object.keys(body).length === 0) return {};

  const table = channel === "telegram" ? "settings" : "fanvue";
  const { error } = await supabase.from(table).update(body).eq("model_id", modelId);
  if (error) return { error: error.message };
  return {};
}
