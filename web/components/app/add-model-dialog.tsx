"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Briefcase,
  ChevronLeft,
  Lock,
  Plus,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";

import { createModelAction } from "@/app/app/actions";
import { AppErrorMessage, AppSubmitButton } from "@/components/app/forms/parts";
import {
  DEFAULT_MODEL_TYPE,
  MODEL_TYPES,
  modelTypeInfo,
  type ModelType,
} from "@/lib/model-types";
import { cn } from "@/lib/utils";

/**
 * „Add model" — dva kroky: najprv TYP agenta, potom meno.
 *
 * Typ je prvá otázka zámerne: rozhoduje o tom, čo modelka vôbec bude vedieť
 * (Fanvue má len persona agent) a po založení sa už nemení. Meno sa premenovať
 * dá kedykoľvek, typ nie — poradie otázok kopíruje ich váhu.
 *
 * Kroky sú samostatné komponenty a zakladá vždy JEDNA server action. Ďalší krok
 * (napr. asistovaná tvorba persony) sa tak dá vložiť medzi ne bez toho, aby sa
 * čokoľvek prepisovalo — pribudne komponent a jedna hodnota do stavu.
 */

const TYPE_ICON: Record<ModelType, LucideIcon> = {
  persona: Sparkles,
  business: Briefcase,
  private: Lock,
};

type Step = "type" | "name";

/* --------------------------------------------------------------------------
   Krok 1 — typ agenta
-------------------------------------------------------------------------- */

function ModelTypeStep({
  value,
  onSelect,
  onContinue,
}: {
  value: ModelType;
  onSelect: (type: ModelType) => void;
  onContinue: () => void;
}) {
  return (
    <>
      <h2 className="text-[16px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
        What kind of agent?
      </h2>
      <p className="mt-2 text-[13px] leading-relaxed text-[var(--app-text-3)]">
        This decides how it talks and which settings it gets. You cannot change it
        later.
      </p>

      <div
        role="radiogroup"
        aria-label="Agent type"
        className="mt-5 flex flex-col gap-2"
      >
        {MODEL_TYPES.map((info) => {
          const Icon = TYPE_ICON[info.value];
          const selected = info.enabled && value === info.value;
          return (
            <button
              key={info.value}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-disabled={!info.enabled}
              disabled={!info.enabled}
              onClick={() => onSelect(info.value)}
              className={cn(
                "app-tap flex w-full items-start gap-3 rounded-lg border px-3.5 py-3 text-left transition-colors",
                info.enabled
                  ? selected
                    ? "border-[var(--app-text-3)] bg-[var(--app-surface-hover)]"
                    : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]"
                  : "cursor-not-allowed border-[var(--app-border)] opacity-55",
              )}
            >
              <Icon
                className="mt-0.5 h-4 w-4 shrink-0 text-[var(--app-text-3)]"
                strokeWidth={1.5}
              />
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[13.5px] font-medium text-[var(--app-text)]">
                    {info.label}
                  </span>
                  {!info.enabled && (
                    <span className="rounded border border-[var(--app-border)] px-1.5 py-px text-[10.5px] uppercase tracking-[0.08em] text-[var(--app-text-4)]">
                      Coming soon
                    </span>
                  )}
                </span>
                <span className="mt-1 block text-[12px] leading-relaxed text-[var(--app-text-3)]">
                  {info.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onContinue}
        className="app-btn app-btn-primary mt-5 h-10 w-full"
      >
        Continue
      </button>
    </>
  );
}

/* --------------------------------------------------------------------------
   Krok 2 — meno
-------------------------------------------------------------------------- */

function ModelNameStep({
  type,
  onBack,
  formAction,
  error,
  inputRef,
}: {
  type: ModelType;
  onBack: () => void;
  formAction: (formData: FormData) => void;
  error?: string;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const info = modelTypeInfo(type);

  return (
    <>
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1 text-[12.5px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
      >
        <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
        {info.label}
      </button>

      <h2 className="mt-2.5 text-[16px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
        Give it a name
      </h2>
      <p className="mt-2 text-[13px] leading-relaxed text-[var(--app-text-3)]">
        You can connect the Telegram account on the next screen.
      </p>

      <form action={formAction} className="mt-6 space-y-4">
        {/* Typ ide na server ako hodnota formulára; akcia si ho aj tak overí
            proti allowlistu a DB má vlastný guard. */}
        <input type="hidden" name="model_type" value={type} />
        <div>
          <label htmlFor="new-model-name" className="app-label mb-2">
            Name
          </label>
          <input
            ref={inputRef}
            id="new-model-name"
            name="name"
            type="text"
            required
            maxLength={60}
            placeholder="e.g. Simona"
            className="app-input"
          />
          <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
            Only you see this — it is how it shows up in your dashboard.
          </p>
        </div>

        {error && <AppErrorMessage>{error}</AppErrorMessage>}

        <AppSubmitButton>Create agent</AppSubmitButton>
      </form>
    </>
  );
}

/* --------------------------------------------------------------------------
   Dialóg
-------------------------------------------------------------------------- */

export function AddModelDialog({
  variant = "gold",
  label = "Add model",
  className,
}: {
  variant?: "gold" | "dark";
  label?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("type");
  const [type, setType] = useState<ModelType>(DEFAULT_MODEL_TYPE);
  const [state, formAction] = useActionState(createModelAction, undefined);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Focus až po animácii, inak prehliadač scrollne na polovicu prechodu.
  useEffect(() => {
    if (!open || step !== "name") return;
    const timer = window.setTimeout(() => inputRef.current?.focus(), 120);
    return () => window.clearTimeout(timer);
  }, [open, step]);

  const openDialog = () => {
    setStep("type");
    setType(DEFAULT_MODEL_TYPE);
    setOpen(true);
  };

  return (
    <>
      <button
        type="button"
        onClick={openDialog}
        className={cn(
          variant === "gold" ? "app-btn app-btn-primary" : "app-btn app-btn-ghost",
          "h-9 px-4",
          className,
        )}
      >
        <Plus className="h-3.5 w-3.5" strokeWidth={1.75} />
        {label}
      </button>

      <AnimatePresence>
        {open && (
          <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              onClick={() => setOpen(false)}
              className="absolute inset-0 bg-black/70"
            />
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Add an agent"
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.97, y: 8 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="app-panel relative max-h-[90vh] w-full max-w-[26rem] overflow-y-auto p-6"
            >
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="app-tap absolute right-3 top-3 rounded-md p-1.5 text-[var(--app-text-4)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
              >
                <X className="h-4 w-4" strokeWidth={1.75} />
              </button>

              {step === "type" ? (
                <ModelTypeStep
                  value={type}
                  onSelect={setType}
                  onContinue={() => setStep("name")}
                />
              ) : (
                <ModelNameStep
                  type={type}
                  onBack={() => setStep("type")}
                  formAction={formAction}
                  error={state?.error}
                  inputRef={inputRef}
                />
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
