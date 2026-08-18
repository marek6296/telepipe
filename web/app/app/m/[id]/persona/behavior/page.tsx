import type { Metadata } from "next";

import { BehaviorForm, type BehaviorRow } from "@/components/app/behavior-form";
import { Callout, PageHeader } from "@/components/app/ui";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Behavior",
};

/**
 * `eleven_key` v zozname chýba zámerne — `select('*')` by na tejto tabuľke
 * skončil chybou „permission denied", klient má len column grant (migrácia 007).
 *
 * Hlasové stĺpce (`voices_enabled`, `voice_*`, `eleven_voice_id`) tu tiež nie
 * sú: presťahovali sa na kartu Voice. Rovnako tri anti-ban stropy
 * (`max_active_chats`, `chat_slot_min`, `max_outreach_per_hour`) — tie sedia
 * v Telegram → Settings, lebo strážia telegramový účet, nie jej povahu. Je to
 * tá istá tabuľka a to isté auto-save (`saveBehaviorAction`), len iná obrazovka.
 */
const BEHAVIOR_COLUMNS =
  "model_id, mode, heat, slang, no_diacritics, activity_waves, active_tz, " +
  "active_start_min, active_end_min, debounce_min_s, debounce_max_s, " +
  "read_delay_min_s, read_delay_max_s, reply_delay_min_s, reply_delay_max_s, " +
  "quick_reply_chance, quick_read_max_s, quick_reply_min_s, quick_reply_max_s, " +
  "seen_only_chance, seen_only_min_s, seen_only_max_s, long_pause_chance, " +
  "long_pause_min_s, long_pause_max_s, defer_reply_chance, defer_min_s, defer_max_s, " +
  "question_chance, gag_chance, greeting_gap_hours, summary_every, " +
  "max_replies_per_hour, max_links_per_hour, photo_cooldown_min, " +
  "morning_enabled, morning_max_per_day";

export default async function BehaviorPage({
  params,
}: PageProps<"/app/m/[id]/persona/behavior">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "persona", "behavior");

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

  return (
    <>
      {/* Persona hovorí, KTO je; toto, AKO sa správa — preto sedia pod jednou
          kartou. Zároveň platí len pre telegramového agenta: Fanvue má vlastné
          tempo, otvorenosť aj okno hodín na svojej karte. Zdieľa sa persona,
          pamäť a časová zóna — je to tá istá osoba. */}
      <PageHeader
        eyebrow="Persona · Telegram agent"
        title="Behavior"
        description="Who she is sits on Identity; this is how she acts — chat style, timing, randomness, limits. It applies to Telegram: voice notes have their own tab, her Fanvue agent has its own set on the Fanvue tab, and the caps that keep her account safe live in Telegram → Settings. Only the persona, the memory and the time zone below are shared."
      />
      <BehaviorForm behavior={data as unknown as BehaviorRow} />
    </>
  );
}
