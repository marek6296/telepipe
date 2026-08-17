"use client";

import { useId, useState } from "react";
import { useFormStatus } from "react-dom";
import { AlertCircle, CheckCircle2, Eye, EyeOff, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/** Sklenený input s labelom — základ všetkých auth formulárov. */
export function Field({
  label,
  name,
  type = "text",
  placeholder,
  defaultValue,
  autoComplete,
  required = true,
  className,
}: {
  label: string;
  name: string;
  type?: string;
  placeholder?: string;
  defaultValue?: string;
  autoComplete?: string;
  required?: boolean;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="lp-label mb-2">
        {label}
      </label>
      <input
        id={id}
        name={name}
        type={type}
        placeholder={placeholder}
        defaultValue={defaultValue}
        autoComplete={autoComplete}
        required={required}
        className="lp-input"
      />
    </div>
  );
}

/** Heslo so show/hide prepínačom. */
export function PasswordField({
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
      <label htmlFor={id} className="lp-label mb-2">
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
          className="lp-input pr-12!"
        />
        <button
          type="button"
          onClick={() => setVisible((value) => !value)}
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-white/35 transition-colors hover:text-white"
        >
          {visible ? (
            <EyeOff className="h-4 w-4" strokeWidth={1.5} />
          ) : (
            <Eye className="h-4 w-4" strokeWidth={1.5} />
          )}
        </button>
      </div>
      {hint && <p className="mt-2 text-[11.5px] text-white/30">{hint}</p>}
    </div>
  );
}

/** Submit s pending stavom z `useFormStatus`. */
export function SubmitButton({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className={cn("lp-btn lp-btn-primary h-12 w-full text-[14.5px]", className)}
    >
      {pending && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

/** Inline chybová hláška (zlé heslo, existujúci email…).
    Červená je signálová farba z dashboardu — jediná povolená výnimka. */
export function ErrorMessage({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      aria-live="polite"
      className="flex items-start gap-2 rounded-[10px] border border-[rgba(248,113,113,0.32)] bg-[rgba(248,113,113,0.08)] px-3.5 py-3 text-[13px] leading-snug text-[#f87171]"
    >
      <AlertCircle className="mt-px h-4 w-4 shrink-0" strokeWidth={1.5} />
      {children}
    </p>
  );
}

/** Informačná hláška (odoslaný reset link…) — neutrálne sklo, bez farby. */
export function NoticeMessage({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 rounded-[10px] border border-white/12 bg-white/[0.045] px-3.5 py-3 text-[13px] leading-snug text-white/75"
    >
      <CheckCircle2 className="mt-px h-4 w-4 shrink-0 text-white/50" strokeWidth={1.5} />
      {children}
    </p>
  );
}

/** Oddeľovač „or continue with". */
export function OrDivider({ label = "or continue with" }: { label?: string }) {
  return (
    <div className="flex items-center gap-4">
      <span className="h-px flex-1 bg-white/[0.09]" />
      <span className="text-[11px] uppercase tracking-[0.18em] text-white/25">
        {label}
      </span>
      <span className="h-px flex-1 bg-white/[0.09]" />
    </div>
  );
}
