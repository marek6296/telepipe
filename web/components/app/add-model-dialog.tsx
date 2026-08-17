"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Plus, X } from "lucide-react";

import { createModelAction } from "@/app/app/actions";
import { AppErrorMessage, AppSubmitButton } from "@/components/app/forms/parts";
import { cn } from "@/lib/utils";

/**
 * „Add model" — meno je jediné, čo pri založení treba (RLS pustí len
 * account_id + name). Po uložení nás akcia presmeruje rovno do wizardu.
 */
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
  const [state, formAction] = useActionState(createModelAction, undefined);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    // Focus až po animácii, inak prehliadač scrollne na polovicu prechodu
    const timer = window.setTimeout(() => inputRef.current?.focus(), 120);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(timer);
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
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
              aria-label="Add a model"
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.97, y: 8 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="app-panel relative w-full max-w-[24rem] p-6"
            >
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="app-tap absolute right-3 top-3 rounded-md p-1.5 text-[var(--app-text-4)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
              >
                <X className="h-4 w-4" strokeWidth={1.75} />
              </button>

              <h2 className="text-[16px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
                Add a model
              </h2>
              <p className="mt-2 text-[13px] leading-relaxed text-[var(--app-text-3)]">
                Start with her name — you can connect her Telegram account on the next
                screen.
              </p>

              <form action={formAction} className="mt-6 space-y-4">
                <div>
                  <label
                    htmlFor="new-model-name"
                    className="app-label mb-2"
                  >
                    Model name
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
                    Only you see this — it is how she shows up in your dashboard.
                  </p>
                </div>

                {state?.error && <AppErrorMessage>{state.error}</AppErrorMessage>}

                <AppSubmitButton>Create model</AppSubmitButton>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
