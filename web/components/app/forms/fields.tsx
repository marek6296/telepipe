"use client";

import { useId, useState, type ReactNode } from "react";

import { useAutoSaveField } from "@/components/app/forms/auto-save";
import { hhMmToMinutes, minutesToHhMm } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Polia formulárov s auto-save. Každé si drží vlastnú hodnotu a pri zmene ju
 * pošle do bufferu (`set`); pri opustení poľa vynúti zápis (`flush`).
 */

function Shell({
  label,
  help,
  htmlFor,
  children,
  className,
  action,
}: {
  label: string;
  help?: string;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <div className={className}>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <label
          htmlFor={htmlFor}
          className="app-label"
        >
          {label}
        </label>
        {action}
      </div>
      {children}
      {help && <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">{help}</p>}
    </div>
  );
}

export function TextField({
  name,
  label,
  help,
  defaultValue,
  placeholder,
  type = "text",
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: string;
  placeholder?: string;
  type?: string;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          setValue(event.target.value);
          set(name, event.target.value);
        }}
        onBlur={flush}
        className="app-input"
      />
    </Shell>
  );
}

export function TextAreaField({
  name,
  label,
  help,
  defaultValue,
  placeholder,
  rows = 4,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: string;
  placeholder?: string;
  rows?: number;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <textarea
        id={id}
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          setValue(event.target.value);
          set(name, event.target.value);
        }}
        onBlur={flush}
        className="app-input resize-y leading-relaxed"
      />
    </Shell>
  );
}

export function NumberField({
  name,
  label,
  help,
  defaultValue,
  min,
  max,
  step = 1,
  suffix,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: number | null;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue === null ? "" : String(defaultValue));

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <div className="relative">
        <input
          id={id}
          type="number"
          inputMode="numeric"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(event) => {
            const raw = event.target.value;
            setValue(raw);
            if (raw === "") {
              set(name, null);
              return;
            }
            const parsed = Number(raw);
            if (Number.isFinite(parsed)) set(name, clamp(parsed, min, max));
          }}
          onBlur={flush}
          className={cn("app-input", suffix && "pr-16!")}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-[var(--app-text-4)]">
            {suffix}
          </span>
        )}
      </div>
    </Shell>
  );
}

export function SliderField({
  name,
  label,
  help,
  defaultValue,
  min = 0,
  max = 1,
  step = 0.01,
  format = (value: number) => `${Math.round(value * 100)}%`,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: number;
  min?: number;
  max?: number;
  step?: number;
  format?: (value: number) => string;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <Shell
      label={label}
      help={help}
      htmlFor={id}
      className={className}
      action={
        <span className="tabular-nums text-[12.5px] font-medium text-[var(--app-text)]">
          {format(value)}
        </span>
      }
    >
      <input
        id={id}
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          const next = Number(event.target.value);
          setValue(next);
          set(name, next);
        }}
        onPointerUp={flush}
        onBlur={flush}
        className="h-1 w-full cursor-pointer appearance-none rounded-full bg-[#26262a] accent-white"
        style={{ accentColor: "#fafafa" }}
      />
    </Shell>
  );
}

export function SwitchField({
  name,
  label,
  help,
  defaultValue,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: boolean;
  className?: string;
}) {
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3",
        className,
      )}
    >
      <div className="min-w-0">
        <p className="text-[13px] text-[var(--app-text)]">{label}</p>
        {help && <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">{help}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        aria-label={label}
        onClick={() => {
          const next = !value;
          setValue(next);
          set(name, next);
          flush();
        }}
        className={cn(
          "relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors",
          value ? "bg-[var(--app-text)]" : "bg-[#2e2e2e]",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full transition-transform",
            value ? "translate-x-[18px] bg-[#0a0a0a]" : "translate-x-0.5 bg-[#a1a1aa]",
          )}
        />
      </button>
    </div>
  );
}

export function SelectField({
  name,
  label,
  help,
  defaultValue,
  options,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: string;
  options: { value: string; label: string }[];
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          set(name, event.target.value);
          flush();
        }}
        className="app-input app-select"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Shell>
  );
}

/** Čas ako `hh:mm`, do DB ide počet minút od polnoci. */
export function TimeField({
  name,
  label,
  help,
  defaultValue,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: number;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(minutesToHhMm(defaultValue));

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <input
        id={id}
        type="time"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          const minutes = hhMmToMinutes(event.target.value);
          if (minutes !== null) set(name, minutes);
        }}
        onBlur={flush}
        className="app-input"
      />
    </Shell>
  );
}

/** Dvojica min/max v jednom riadku — v chovaní je takých párov veľa. */
export function RangeRow({
  label,
  help,
  minField,
  maxField,
  suffix,
  step = 1,
}: {
  label: string;
  help?: string;
  minField: { name: string; value: number };
  maxField: { name: string; value: number };
  suffix?: string;
  step?: number;
}) {
  return (
    <div>
      <p className="app-label mb-2">{label}</p>
      <div className="grid grid-cols-2 gap-3">
        <NumberField
          name={minField.name}
          label="from"
          defaultValue={minField.value}
          min={0}
          step={step}
          suffix={suffix}
        />
        <NumberField
          name={maxField.name}
          label="to"
          defaultValue={maxField.value}
          min={0}
          step={step}
          suffix={suffix}
        />
      </div>
      {help && <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">{help}</p>}
    </div>
  );
}

/** Zamknutá sekcia — fáza 3 (ElevenLabs). */
export function LockedSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-[14px] font-medium text-[var(--app-text-2)]">{title}</h3>
          <p className="mt-1.5 max-w-lg text-[12.5px] leading-relaxed text-[var(--app-text-4)]">
            {description}
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-[var(--app-border-strong)] px-2.5 py-1 text-[10.5px] font-medium text-[var(--app-text-3)]">
          Coming soon
        </span>
      </div>
      {children && <div className="pointer-events-none mt-4 opacity-35">{children}</div>}
    </div>
  );
}

function clamp(value: number, min?: number, max?: number): number {
  if (typeof min === "number" && value < min) return min;
  if (typeof max === "number" && value > max) return max;
  return value;
}
