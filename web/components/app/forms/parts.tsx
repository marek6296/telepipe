"use client";

import { useId, useState, type ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { Eye, EyeOff, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Formulárové časti /app sekcie — monochróm.
 *
 * Auth stránky majú vlastné (zlaté) v `components/auth/form-parts.tsx` a tie sa
 * pri redizajne nesmeli meniť. Appka preto používa tieto; API je zámerne
 * rovnaké, aby sa dali zameniť jedným importom.
 */

/** Heslo so show/hide prepínačom. */
export function AppPasswordField({
  label,
  name,
  placeholder = "••••••••",
  autoComplete = "current-password",
  hint,
}: {
  label: string;
  name: string;
  placeholder?: string;
  autoComplete?: string;
  hint?: string;
}) {
  const id = useId();
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <label htmlFor={id} className="app-label mb-2">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          name={name}
          type={visible ? "text" : "password"}
          placeholder={placeholder}
          autoComplete={autoComplete}
          required
          className="app-input pr-11!"
        />
        <button
          type="button"
          onClick={() => setVisible((value) => !value)}
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-[var(--app-text-4)] transition-colors hover:text-[var(--app-text)]"
        >
          {visible ? (
            <EyeOff className="h-4 w-4" strokeWidth={1.75} />
          ) : (
            <Eye className="h-4 w-4" strokeWidth={1.75} />
          )}
        </button>
      </div>
      {hint && <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">{hint}</p>}
    </div>
  );
}

/** Submit s pending stavom z `useFormStatus`. */
export function AppSubmitButton({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className={cn("app-btn app-btn-primary h-10 w-full", className)}
    >
      {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />}
      {children}
    </button>
  );
}

/** Inline chybová hláška. */
export function AppErrorMessage({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      aria-live="polite"
      className="rounded-lg border border-[rgba(248,113,113,0.28)] bg-[rgba(248,113,113,0.05)] px-3.5 py-2.5 text-[12.5px] leading-snug text-[#fca5a5]"
    >
      {children}
    </p>
  );
}

/** Informačná hláška (heslo zmenené…). */
export function AppNoticeMessage({ children }: { children: ReactNode }) {
  return (
    <p
      role="status"
      aria-live="polite"
      className="rounded-lg border border-[rgba(74,222,128,0.24)] bg-[rgba(74,222,128,0.04)] px-3.5 py-2.5 text-[12.5px] leading-snug text-[#86efac]"
    >
      {children}
    </p>
  );
}
