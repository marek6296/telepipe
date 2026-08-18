"use client";

import { cn } from "@/lib/utils";

/**
 * Obyčajné riadené políčko telegramových obrazoviek.
 *
 * Nie je to `components/app/forms/fields.tsx` — tie polia sa samy ukladajú do
 * `behavior`/`persona` cez `AutoSaveForm`. Tu sa nič neukladá priebežne: api
 * kľúče, kód z Telegramu ani token bota nemajú riadok, do ktorého by sa dal
 * zapísať polovičný stav.
 */
export function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  inputMode,
  mono = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  inputMode?: "numeric" | "tel";
  mono?: boolean;
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
        autoComplete="off"
        spellCheck={false}
        className={cn("app-input", mono && "font-mono text-[13px] tracking-tight")}
      />
    </label>
  );
}
