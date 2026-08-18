"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Sparkles, Wand2 } from "lucide-react";

import {
  applyScheduleDraftAction,
  generateScheduleDraftAction,
} from "@/app/app/m/[id]/persona/day/actions";
import { DayPreview } from "@/components/app/schedule-preview";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { WEEKDAYS } from "@/lib/schedule";
import type { ScheduleDraft } from "@/lib/schedule-draft";

/**
 * „Opíš jej deň vlastnými slovami" — druhá cesta k tomu istému rozvrhu.
 *
 * Nič sa neuloží, kým klient neklikne Apply: najprv uvidí ukážku dňa, ktorý
 * mu z popisu vznikol. Je to rovnaký sľub aj rovnaký postup ako pri asistovanej
 * persone (`persona-wizard.tsx`) — vygenerovať, ukázať, až potom zapísať.
 */

const PLACEHOLDER =
  "She gets up around noon, later at weekends. Gym three afternoons a week, " +
  "shoots content on Tuesdays and Thursdays, errands and a café in between. " +
  "Evenings at home on the couch, out with friends on Friday and Saturday night.";

export function ScheduleDescribe({ modelId }: { modelId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [draft, setDraft] = useState<ScheduleDraft | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"generate" | "apply" | null>(null);

  async function generate() {
    setBusy("generate");
    setError(null);
    const result = await generateScheduleDraftAction(modelId, description);
    setBusy(null);
    if (result.error || !result.draft) {
      setError(result.error ?? "The AI helper did not answer.");
      return;
    }
    setDraft(result.draft);
    setWarnings(result.warnings ?? []);
  }

  async function apply() {
    if (!draft) return;
    setBusy("apply");
    setError(null);
    const result = await applyScheduleDraftAction(modelId, draft);
    setBusy(null);
    if (result.error) {
      setError(result.error);
      return;
    }
    // Editor pod tým drží vlastný stav — po zápise ho treba postaviť nanovo
    // z databázy, inak by klient upravoval deň, ktorý už neplatí.
    router.refresh();
    setDraft(null);
    setOpen(false);
    setDescription("");
  }

  if (!open) {
    return (
      <div className="mb-12 flex flex-col gap-3 rounded-lg border border-[var(--app-border-strong)] bg-[#0e0e0e] px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[13px] font-medium text-[var(--app-text)]">
            <Sparkles className="h-3.5 w-3.5 text-[var(--app-text-4)]" strokeWidth={1.75} />
            Describe her day instead
          </p>
          <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-3)]">
            Write her week in your own words, in any language, and we turn it into the
            schedule below — you can still edit every line of it afterwards.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="app-btn app-btn-primary h-9 shrink-0 px-4"
        >
          <Wand2 className="h-3.5 w-3.5" strokeWidth={1.75} />
          Describe her day
        </button>
      </div>
    );
  }

  return (
    <div className="mb-12 space-y-5">
      <Card>
        <CardHeader
          title="Describe her day"
          description="When she gets up, what her weekdays look like, what changes at the weekend. Write it however you like — we fill in whatever you leave out."
          actions={
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setDraft(null);
                setError(null);
              }}
              className="app-btn app-btn-quiet h-8 px-3 text-[12px]"
            >
              Close
            </button>
          }
        />
        <div className="space-y-4 p-5">
          <textarea
            rows={6}
            value={description}
            placeholder={PLACEHOLDER}
            maxLength={4000}
            onChange={(event) => setDescription(event.target.value)}
            className="app-input resize-y leading-relaxed"
          />
          {error && <Callout tone="danger">{error}</Callout>}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy !== null}
              onClick={generate}
              className="app-btn app-btn-primary h-9 px-4"
            >
              {busy === "generate" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
              ) : (
                <Wand2 className="h-3.5 w-3.5" strokeWidth={1.75} />
              )}
              {draft ? "Try again" : "Build her day"}
            </button>
            <p className="text-[11.5px] text-[var(--app-text-4)]">
              Nothing is saved until you apply it.
            </p>
          </div>
        </div>
      </Card>

      {draft && (
        <>
          {warnings.length > 0 && (
            <Callout>
              <p className="font-medium">We tidied a few things up:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </Callout>
          )}

          <DayPreview
            day={draft}
            seed={`draft:${modelId}`}
            title="Here is her week"
            description={`${draft.activities.length} things across the week. Click through the days — each one has its own shape. Applying this replaces her current schedule.`}
          />

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy !== null}
              onClick={apply}
              className="app-btn app-btn-primary h-9 px-4"
            >
              {busy === "apply" && (
                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
              )}
              Apply this schedule
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => setDraft(null)}
              className="app-btn app-btn-quiet h-9 px-4"
            >
              Discard
            </button>
            <p className="text-[11.5px] text-[var(--app-text-4)]">
              Wakes {clock(draft.wake_weekday_start_min)}–{clock(draft.wake_weekday_end_min)} on
              weekdays, {clock(draft.wake_weekend_start_min)}–
              {clock(draft.wake_weekend_end_min)} at the weekend · every one of the{" "}
              {WEEKDAYS.length} days has its own shape.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function clock(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}
