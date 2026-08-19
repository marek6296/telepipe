"use client";

// DOČASNÝ harness na overenie vypínača. Zmazať po kontrole.

import { useState } from "react";

import { Switch } from "@/components/app/forms/fields";

function Row({ id, initial, disabled }: { id: string; initial: boolean; disabled?: boolean }) {
  const [on, setOn] = useState(initial);
  return (
    <div
      id={`row-${id}`}
      className="flex items-start justify-between gap-4 rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3"
    >
      <div className="min-w-0">
        <p className="text-[13px] text-[var(--app-text)]">Greet new subscribers</p>
        <p id={`help-${id}`} className="mt-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
          Writes first the moment someone subscribes.
        </p>
      </div>
      <Switch
        id={`sw-${id}`}
        checked={on}
        onCheckedChange={setOn}
        label="Greet new subscribers"
        describedBy={`help-${id}`}
        disabled={disabled}
        className="mt-0.5"
      />
    </div>
  );
}

export default function SwitchHarness() {
  return (
    <div className="app-scope min-h-svh p-10">
      <div className="flex max-w-xl flex-col gap-3">
        <Row id="off" initial={false} />
        <Row id="on" initial />
        <Row id="offdis" initial={false} disabled />
        <Row id="ondis" initial disabled />
      </div>
    </div>
  );
}
