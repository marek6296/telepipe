"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Plus, X } from "lucide-react";

import { createModelAction } from "@/app/app/actions";
import { ErrorMessage, SubmitButton } from "@/components/auth/form-parts";
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
          variant === "gold" ? "btn-modern-light" : "btn-modern-dark",
          "h-10 px-5 text-[13px]",
          className,
        )}
      >
        <Plus className="h-4 w-4" />
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
              className="absolute inset-0 bg-black/75 backdrop-blur-sm"
            />
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Add a model"
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.97, y: 8 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="glass-panel relative w-full max-w-[26rem] rounded-3xl p-7"
            >
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="absolute right-4 top-4 rounded-full p-1.5 text-white/35 transition-colors hover:text-[var(--gold-light)]"
              >
                <X className="h-4 w-4" />
              </button>

              <h2 className="text-[19px] font-semibold tracking-tight text-white">
                Add a model
              </h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-white/45">
                Start with her name — you can connect her Telegram account on the next
                screen.
              </p>

              <form action={formAction} className="mt-6 space-y-4">
                <div>
                  <label
                    htmlFor="new-model-name"
                    className="mb-2 block text-[12.5px] font-medium tracking-tight text-white/60"
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
                    className="glass-input"
                  />
                  <p className="mt-2 text-[11.5px] text-white/30">
                    Only you see this — it is how she shows up in your dashboard.
                  </p>
                </div>

                {state?.error && <ErrorMessage>{state.error}</ErrorMessage>}

                <SubmitButton className="h-11">Create model</SubmitButton>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
