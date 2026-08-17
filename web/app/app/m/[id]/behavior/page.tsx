import type { Metadata } from "next";

import { BehaviorForm, type BehaviorRow } from "@/components/app/behavior-form";
import { Callout } from "@/components/app/ui";
import { requireModel } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Behavior",
};

/**
 * `eleven_key` v zozname chýba zámerne — `select('*')` by na tejto tabuľke
 * skončil chybou „permission denied", klient má len column grant (migrácia 007).
 */
const BEHAVIOR_COLUMNS =
  "model_id, mode, heat, slang, no_diacritics, activity_waves, active_tz, " +
  "active_start_min, active_end_min, debounce_min_s, debounce_max_s, " +
  "read_delay_min_s, read_delay_max_s, reply_delay_min_s, reply_delay_max_s, " +
  "quick_reply_chance, quick_read_max_s, quick_reply_min_s, quick_reply_max_s, " +
  "seen_only_chance, seen_only_min_s, seen_only_max_s, long_pause_chance, " +
  "long_pause_min_s, long_pause_max_s, defer_reply_chance, defer_min_s, defer_max_s, " +
  "question_chance, gag_chance, greeting_gap_hours, summary_every, " +
  "max_replies_per_hour, max_links_per_hour, photo_cooldown_min, voices_enabled, " +
  "morning_enabled, morning_max_per_day, eleven_voice_id, voice_ambience, " +
  "voice_strength, voice_chance, voice_tempo, voice_ambience_level";

export default async function BehaviorPage({ params }: PageProps<"/app/m/[id]/behavior">) {
  const { id } = await params;
  const model = await requireModel(id);

  const supabase = await createClient();
  const { data } = await supabase
    .from("behavior")
    .select(BEHAVIOR_COLUMNS)
    .eq("model_id", model.id)
    .maybeSingle();

  if (!data) {
    return (
      <Callout tone="danger">
        Her behaviour row is missing. Reload the page, and contact us if it stays empty.
      </Callout>
    );
  }

  return <BehaviorForm behavior={data as unknown as BehaviorRow} />;
}
