"use client";

import { useMemo, useState } from "react";
import { Clock } from "lucide-react";

import { Card, CardHeader } from "@/components/app/ui";
import {
  PACE_OPTIONS,
  PLACE_LABEL,
  WEEKDAYS,
  clockLabel,
  durationLabel,
  nearestPace,
  previewDay,
  type Place,
  type ScheduleActivity,
} from "@/lib/schedule";
import { cn } from "@/lib/utils";

/**
 * Ukážka jedného dňa — jediná vec, ktorá z rozvrhu robí pochopiteľnú vec.
 *
 * Používa ju aj ručný editor, aj vygenerovaný návrh, a preto stojí samostatne:
 * klient musí vidieť to isté, nech deň vznikol akokoľvek.
 *
 * PREČO NIE SÚ ČASY TIE ISTÉ AKO U NEJ. Presné minúty losuje worker každý deň
 * nanovo (`den.plan()`), takže rovnaké čísla by boli sľub, ktorý sa nedá
 * dodržať. Ukážka ukazuje TVAR dňa — poradie, miesta, zhruba kedy a ako dlho —
 * a ten sedí presne. Hovorí to aj popis, aby to nikoho neprekvapilo.
 */

export type PreviewShape = {
  wake_weekday_start_min: number;
  wake_weekday_end_min: number;
  wake_weekend_start_min: number;
  wake_weekend_end_min: number;
  night_place: Place;
  night_what: string;
  night_pace: number;
  night_arrival: string;
  activities: ScheduleActivity[];
};

export function DayPreview({
  day,
  title = "A day like this",
  description = "An example of how the settings above play out. The exact minutes are drawn fresh every day, so no two look the same — the shape is what you are setting.",
  seed = "preview",
}: {
  day: PreviewShape;
  title?: string;
  description?: string;
  seed?: string;
}) {
  const [weekday, setWeekday] = useState(0);
  const blocks = useMemo(() => previewDay(day, weekday, seed), [day, weekday, seed]);

  return (
    <Card>
      <CardHeader
        title={title}
        icon={<Clock className="h-3.5 w-3.5" strokeWidth={1.75} />}
        description={description}
      />
      <div className="flex flex-wrap gap-1.5 border-b border-[var(--app-border)] px-5 py-3">
        {WEEKDAYS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={option.value === weekday}
            onClick={() => setWeekday(option.value)}
            className={cn(
              "app-tap rounded-md border px-2.5 py-1.5 text-[11.5px] transition-colors",
              option.value === weekday
                ? "border-[var(--app-text-3)] bg-[#161616] text-[var(--app-text)]"
                : "border-[var(--app-border)] text-[var(--app-text-4)] hover:text-[var(--app-text-2)]",
            )}
          >
            {option.short}
          </button>
        ))}
      </div>

      {blocks.length === 0 ? (
        <p className="px-5 py-8 text-center text-[12.5px] text-[var(--app-text-4)]">
          Nothing happens on {WEEKDAYS[weekday].label} yet.
        </p>
      ) : (
        <ol className="divide-y divide-[var(--app-border)]">
          {blocks.map((block, index) => (
            <li key={index} className="flex gap-4 px-5 py-3">
              <span className="w-[92px] shrink-0 pt-px text-[12px] tabular-nums text-[var(--app-text-3)]">
                {clockLabel(block.from)}–{clockLabel(block.to)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] leading-snug text-[var(--app-text)]">
                  {block.what || "—"}
                </span>
                <span className="mt-0.5 block text-[11.5px] text-[var(--app-text-4)]">
                  {PLACE_LABEL[block.place]} · {durationLabel(block.to - block.from)} ·{" "}
                  {paceLabel(block.pace)}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

/** Násobič späť na vetu, ktorú klient v editore vybral. */
export function paceLabel(pace: number): string {
  const match = PACE_OPTIONS.find((option) => option.value === nearestPace(pace));
  return match ? match.label.toLowerCase() : `×${pace}`;
}
