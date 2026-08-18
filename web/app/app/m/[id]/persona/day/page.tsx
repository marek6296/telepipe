import type { Metadata } from "next";

import { ScheduleForm } from "@/components/app/schedule-form";
import { Callout, PageHeader } from "@/components/app/ui";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import { SCHEDULE_COLUMNS, normaliseActivities, type ScheduleRow } from "@/lib/schedule";

export const metadata: Metadata = {
  title: "Daily life",
};

/**
 * Denný život — kde je o ktorej. Persona hovorí, KTO je; Behavior, AKO sa
 * správa; toto, KDE je. Preto vlastná podkarta a nie ďalšia sekcia Identity:
 * je to zoznam, ktorý sa pridáva, maže a preusporadúva, a k tomu ukážka
 * vygenerovaného dňa — iný spôsob práce než formulár s textami.
 *
 * `select('*')` by tu skončil chybou „permission denied for column" ako pri
 * `behavior`: rola `authenticated` má column-scoped grant (migrácia 022).
 */
export default async function DayPage({ params }: PageProps<"/app/m/[id]/persona/day">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "persona", "day");

  const supabase = await createClient();
  const { data } = await supabase
    .from("model_schedule")
    .select(`${SCHEDULE_COLUMNS}, updated_at`)
    .eq("model_id", model.id)
    .maybeSingle();

  if (!data) {
    // Riadok zakladá trigger `models_provision_rows` (migrácia 022) a rovnaká
    // migrácia ho doplnila všetkým existujúcim modelkám — chýbať nemá ako.
    return (
      <Callout tone="danger">
        Her schedule row is missing. Reload the page, and contact us if it stays empty.
      </Callout>
    );
  }

  const row = data as unknown as ScheduleRow & { updated_at: string };
  const schedule: ScheduleRow = {
    ...row,
    night_pace: Number(row.night_pace),
    activities: normaliseActivities(row.activities),
  };

  return (
    <>
      <PageHeader
        eyebrow="Persona · Telegram agent"
        title="Daily life"
        description="Where she is at what time of day. It decides three things: what she tells fans she is doing, how fast she replies from there, and what her voice notes sound like behind her. The times are never exact — she wakes and moves a different minute every day, so nobody can spot a timetable."
      />
      {/* Kľúč z `updated_at`: po „Apply" vygenerovaného dňa sa editor musí
          postaviť nanovo z databázy, inak by klient upravoval starý stav. */}
      <ScheduleForm key={row.updated_at} modelId={model.id} schedule={schedule} />
    </>
  );
}
