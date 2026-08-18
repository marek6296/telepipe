"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Obyčajné riadené políčko telegramových obrazoviek.
 *
 * Nie je to `components/app/forms/fields.tsx` — tie polia sa samy ukladajú do
 * `behavior`/`persona` cez `AutoSaveForm`. Tu sa nič neukladá priebežne: api
 * kľúče, kód z Telegramu ani token bota nemajú riadok, do ktorého by sa dal
 * zapísať polovičný stav.
 *
 * `error` a `hint` sú tu preto, že hláška musí vyjsť POD tým políčkom, ktoré ju
 * spôsobilo. Prvý platiaci klient videl vetu o `api_id` pod políčkom s
 * telefónom, o dva kroky ďalej — a nemal ako vedieť, kam sa vrátiť.
 */
export function Field({
  label,
  value,
  onChange,
  onBlur,
  placeholder,
  type = "text",
  inputMode,
  mono = false,
  error,
  hint,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  placeholder?: string;
  type?: string;
  inputMode?: "numeric" | "tel";
  mono?: boolean;
  /** Text chyby, alebo uzol s odkazom „Back to API keys". */
  error?: ReactNode;
  /** Aký tvar sa čaká — vidno vždy, aj keď je políčko prázdne. */
  hint?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[12.5px] font-medium tracking-tight text-[var(--app-text-2)]">
        {label}
      </span>
      <input
        type={type}
        value={value}
        inputMode={inputMode}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        autoComplete="off"
        spellCheck={false}
        className={cn("app-input", mono && "font-mono text-[13px] tracking-tight")}
      />
      {error ? (
        <span className="mt-1.5 block text-[11.5px] leading-relaxed text-[#fca5a5]">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
          {hint}
        </span>
      ) : null}
    </label>
  );
}
