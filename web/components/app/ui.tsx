import type { ReactNode } from "react";

import { asStatus, STATUS_LABEL, STATUS_STYLE, type ModelStatus } from "@/lib/status";
import { cn } from "@/lib/utils";

/** Nadpis stránky s podnadpisom a miestom na akcie vpravo. */
export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-[var(--gold)]/70">
            {eyebrow}
          </p>
        )}
        <h1 className="text-balance-tight text-[26px] font-semibold text-white sm:text-[30px]">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-[13.5px] leading-relaxed text-white/45">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2.5">{actions}</div>}
    </div>
  );
}

/** Základná karta appky — tmavý povrch, jemný lem, hlboký tieň. */
export function Card({
  className,
  children,
  gold = false,
}: {
  className?: string;
  children: ReactNode;
  gold?: boolean;
}) {
  return (
    <div
      className={cn(
        "widget-depth rounded-2xl",
        gold && "widget-depth-gold",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Hlavička sekcie vnútri karty. */
export function CardHeader({
  title,
  description,
  icon,
  actions,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/[0.06] px-5 py-4">
      <div className="flex min-w-0 items-start gap-3">
        {icon && (
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[rgba(212,175,55,0.22)] bg-[rgba(212,175,55,0.07)] text-[var(--gold)]">
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-tight text-white">{title}</h2>
          {description && (
            <p className="mt-1 text-[12.5px] leading-relaxed text-white/40">{description}</p>
          )}
        </div>
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}

/** Malá dlaždica s číslom. */
export function StatTile({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="widget-depth rounded-2xl px-4 py-3.5">
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-white/35">
        {icon}
        {label}
      </div>
      <p className="mt-2 text-[22px] font-semibold tabular-nums text-white">{value}</p>
      {hint && <p className="mt-0.5 text-[11.5px] text-white/30">{hint}</p>}
    </div>
  );
}

/** Badge stavu modelky. */
export function StatusBadge({ status }: { status: string }) {
  const value: ModelStatus = asStatus(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        STATUS_STYLE[value],
      )}
    >
      {STATUS_LABEL[value]}
    </span>
  );
}

/** Prázdny stav s ikonou, textom a jednou akciou. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/[0.07] bg-[linear-gradient(160deg,rgba(24,24,24,0.75),rgba(6,6,6,0.9))] px-6 py-16 text-center">
      <div className="gold-halo pointer-events-none absolute left-1/2 top-0 h-[320px] w-[320px] -translate-x-1/2 -translate-y-1/2 opacity-60" />
      <div className="relative mx-auto flex max-w-md flex-col items-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[rgba(212,175,55,0.28)] bg-[rgba(212,175,55,0.08)] text-[var(--gold)]">
          {icon}
        </span>
        <h3 className="mt-5 text-[18px] font-semibold text-white">{title}</h3>
        <p className="mt-2 text-[13.5px] leading-relaxed text-white/45">{description}</p>
        {action && <div className="mt-7">{action}</div>}
      </div>
    </div>
  );
}

/** Bloček s vysvetlením / upozornením. */
export function Callout({
  tone = "neutral",
  children,
  icon,
}: {
  tone?: "neutral" | "gold" | "danger" | "success";
  children: ReactNode;
  icon?: ReactNode;
}) {
  const tones = {
    neutral: "border-white/[0.08] bg-white/[0.03] text-white/55",
    gold: "border-[rgba(212,175,55,0.28)] bg-[rgba(212,175,55,0.07)] text-[var(--gold-light)]",
    danger: "border-[#7a2b23] bg-[#2a100d] text-[#ffb3a7]",
    success: "border-[#2e7d52]/45 bg-[#0f2a1d] text-[#8ff0bb]",
  } as const;

  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-[12.5px] leading-relaxed",
        tones[tone],
      )}
    >
      {icon && <span className="mt-px shrink-0">{icon}</span>}
      <div className="min-w-0">{children}</div>
    </div>
  );
}
