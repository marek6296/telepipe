"use client";

import { useState, useTransition } from "react";
import { Check, Loader2, PenLine, Wand2 } from "lucide-react";

import { setSetupModeAction } from "@/app/app/m/[id]/persona/actions";
import { cn } from "@/lib/utils";

/**
 * Personal vs Easy.
 *
 * Personal je pôvodné správanie a default — kto si personu napísal sám, nemá o
 * čom rozhodovať a nič sa mu nemení.
 *
 * Easy doplní šesť textových polí presetom. Robí to LEN do prázdnych polí a pri
 * vypnutí nemaže nič, takže prepnutie tam a späť je bezpečné. Preto tu nie je
 * žiadne potvrdzovacie okno — nie je čo stratiť.
 */
export function SetupModeSwitch({
  modelId,
  mode: initial,
}: {
  modelId: string;
  mode: "personal" | "easy";
}) {
  const [mode, setMode] = useState(initial);
  const [error, setError] = useState("");
  const [pending, startTransition] = useTransition();

  function prepni(next: "personal" | "easy") {
    if (next === mode || pending) return;
    setError("");
    // Optimisticky: klik má prepnúť hneď, nie po odpovedi servera. Pri chybe sa
    // vráti späť — inak by človek klikal druhýkrát na niečo, čo neprešlo.
    setMode(next);
    startTransition(async () => {
      const result = await setSetupModeAction(modelId, next);
      if (result?.error) {
        setMode(mode);
        setError(result.error);
      }
    });
  }

  return (
    <div className="app-card p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] tracking-[0.12em] text-[var(--app-text-4)] uppercase">
          How much do you want to set up
        </p>
        {pending && (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--app-text-4)]" strokeWidth={1.75} />
        )}
      </div>

      <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
        <ModeCard
          active={mode === "personal"}
          onClick={() => prepni("personal")}
          icon={<PenLine className="h-4 w-4" strokeWidth={1.75} />}
          title="Personal agent"
          hint="You write who she is — every field, in your words."
        />
        <ModeCard
          active={mode === "easy"}
          onClick={() => prepni("easy")}
          icon={<Wand2 className="h-4 w-4" strokeWidth={1.75} />}
          title="Easy agent"
          hint="Fill in her name, age and city. We write the rest."
        />
      </div>

      {error && (
        <p className="mt-3 text-[13px] text-[#fca5a5]" role="alert">
          {error}
        </p>
      )}

      <p className="mt-3 text-[12px] leading-relaxed text-[var(--app-text-4)]">
        {mode === "easy"
          ? "Her personality, style, boundaries and how she leads to your page are filled in for you. Switch back to Personal any time — nothing gets deleted and you can edit everything."
          : "Switching to Easy only fills in the fields you left empty. Anything you wrote stays exactly as it is."}
      </p>
    </div>
  );
}

function ModeCard({
  active,
  onClick,
  icon,
  title,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "app-tap group flex items-start gap-3 rounded-xl border p-3.5 text-left transition-colors",
        active
          ? "border-[var(--app-text)] bg-[var(--app-surface)]"
          : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
          active ? "bg-[var(--app-active)] text-[var(--app-text)]" : "text-[var(--app-text-4)]",
        )}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-medium text-[var(--app-text)]">{title}</span>
        <span className="mt-0.5 block text-[12px] leading-relaxed text-[var(--app-text-3)]">
          {hint}
        </span>
      </span>
      <span
        className={cn(
          "mt-1 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border transition-colors",
          active ? "border-transparent bg-[var(--app-text)]" : "border-[var(--app-border-strong)]",
        )}
      >
        {active && <Check className="h-3 w-3 text-[var(--app-bg)]" strokeWidth={3} />}
      </span>
    </button>
  );
}
