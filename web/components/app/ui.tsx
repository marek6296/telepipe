import type { ReactNode } from "react";

import { asStatus, STATUS_DOT, STATUS_LABEL, type ModelStatus } from "@/lib/status";
import { cn } from "@/lib/utils";

/**
 * Primitívy /app sekcie — monochróm podľa Efferd referencie (invertovanej).
 * Farba je výhradne signál: zelená/červená delta a status bodky. Zlatá nikde.
 *
 * Triedy `app-*` sú definované v `globals.css` v app-scoped bloku; landing
 * a auth používajú vlastnú (zlatú) sadu a tento súbor sa ich nedotýka.
 */

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
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="app-group-label mb-2">{eyebrow}</p>}
        <h1 className="sr-only text-[24px] font-semibold tracking-[-0.02em] text-[var(--app-text)] sm:not-sr-only">
          {title}
        </h1>
        {description && (
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-[var(--app-text-3)]">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 sm:shrink-0">{actions}</div>}
    </div>
  );
}

/**
 * Základná karta appky. `gold` ostáva v API kvôli volajúcim, ale v monochróme
 * znamená len o stupeň výraznejší lem — žiadny farebný akcent.
 */
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
    <div className={cn("app-card", gold && "border-[var(--app-border-strong)]", className)}>
      {children}
    </div>
  );
}

/** Hlavička sekcie vnútri karty — titulok, popis, akcie. Žiadne ikonové chipy. */
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
    <div className="flex items-start justify-between gap-4 border-b border-[var(--app-border)] px-5 py-4">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-[14px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
          {icon && <span className="text-[var(--app-text-4)]">{icon}</span>}
          {title}
        </h2>
        {description && (
          <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--app-text-3)]">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}

/**
 * Delta oproti minulému týždňu — jediné miesto v appke, kde smie byť farba.
 * `null` znamená „nedá sa spočítať" a nevykreslíme nič.
 */
export function Delta({
  value,
  caption = "vs last week",
}: {
  value: number | null;
  caption?: string;
}) {
  if (value === null || !Number.isFinite(value)) return null;
  const up = value >= 0;
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px]">
      <span
        className="tabular-nums"
        style={{ color: up ? "var(--app-up)" : "var(--app-down)" }}
      >
        {up ? "▲" : "▼"} {Math.abs(value).toFixed(1)}%
      </span>
      <span className="text-[var(--app-text-4)]">{caption}</span>
    </span>
  );
}

/**
 * Dlaždica so štatistikou: malý label, veľké čisté číslo, drobná poznámka
 * alebo delta pod ním — presne ako referencia.
 */
export function StatTile({
  label,
  value,
  hint,
  icon,
  delta,
  deltaCaption,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: ReactNode;
  /** Percentuálna zmena; `null`/`undefined` = nezobrazovať. */
  delta?: number | null;
  deltaCaption?: string;
}) {
  return (
    <div className="app-card px-5 py-4">
      <div className="flex items-center gap-2 text-[12px] font-normal text-[var(--app-text-3)]">
        {icon && <span className="text-[var(--app-text-4)]">{icon}</span>}
        {label}
      </div>
      <p
        className="mt-2.5 overflow-hidden text-ellipsis whitespace-nowrap text-[clamp(1.45rem,5vw,1.75rem)] font-semibold leading-none tracking-[-0.03em] tabular-nums text-[var(--app-text)]"
        title={typeof value === "string" || typeof value === "number" ? String(value) : undefined}
      >
        {value}
      </p>
      <div className="mt-2.5 min-h-[17px]">
        {delta !== undefined && delta !== null ? (
          <Delta value={delta} caption={deltaCaption} />
        ) : (
          hint && <span className="text-[11.5px] text-[var(--app-text-4)]">{hint}</span>
        )}
      </div>
    </div>
  );
}

/** Stav modelky — bodka + text, žiadny farebný obdĺžnik. */
export function StatusBadge({ status }: { status: string }) {
  const value: ModelStatus = asStatus(status);
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-[var(--app-text-2)]">
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", STATUS_DOT[value])} />
      {STATUS_LABEL[value]}
    </span>
  );
}

/** Prázdny stav — čistý rám, tichá ikona, jedna akcia. */
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
    <div className="app-card px-6 py-16 text-center">
      <div className="mx-auto flex max-w-md flex-col items-center">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--app-border)] text-[var(--app-text-4)]">
          {icon}
        </span>
        <h3 className="mt-5 text-[15px] font-medium text-[var(--app-text)]">{title}</h3>
        <p className="mt-2 text-[13px] leading-relaxed text-[var(--app-text-3)]">
          {description}
        </p>
        {action && <div className="mt-6">{action}</div>}
      </div>
    </div>
  );
}

/** Bloček s vysvetlením / upozornením. Tón mení len farbu textu a lemu. */
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
    neutral: "border-[var(--app-border)] bg-[#0c0c0c] text-[var(--app-text-2)]",
    // `gold` ostáva v API kvôli volajúcim — v monochróme je to neutrálny dôraz.
    gold: "border-[var(--app-border-strong)] bg-[#0e0e0e] text-[var(--app-text-2)]",
    danger: "border-[rgba(248,113,113,0.28)] bg-[rgba(248,113,113,0.05)] text-[#fca5a5]",
    success: "border-[rgba(74,222,128,0.24)] bg-[rgba(74,222,128,0.04)] text-[#86efac]",
  } as const;

  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-[12.5px] leading-relaxed",
        tones[tone],
      )}
    >
      {icon && <span className="mt-px shrink-0 opacity-70">{icon}</span>}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Tabuľky — čisté riadky, tenké deliace čiary, žiadne zebra farby.
-------------------------------------------------------------------------- */

export function TableWrap({
  children,
  minWidth,
}: {
  children: ReactNode;
  minWidth?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table
        className="w-full text-left text-[13px]"
        style={minWidth ? { minWidth } : undefined}
      >
        {children}
      </table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
  className,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      className={cn(
        "px-5 py-2.5 text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--app-text-4)]",
        align === "right" && "text-right",
        className,
      )}
    >
      {children}
    </th>
  );
}
