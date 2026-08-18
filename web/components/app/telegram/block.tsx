"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Jeden z troch blokov telegramovej obrazovky.
 *
 * PREČO VÔBEC EXISTUJE. Marek — ktorý ten systém postavil — sa v ňom prestal
 * vyznať: „nechápem to prepojenie kontrolného bota". Príčinou nebolo, že by
 * niečo chýbalo, ale že tri rôzne veci vyzerali ako jedna. Sú to:
 *
 *   1. JEJ účet        — z neho odpisuje fanúšikom. Povinný.
 *   2. TVOJ bot        — malý BotFather bot, ktorý ten účet stráži. Nepovinný.
 *   3. TVOJ Telegram   — komu ten bot píše a kto vidí menu. Nepovinný, a je to
 *                        NIEČO INÉ než bod 2.
 *
 * Blok preto vždy nesie štyri veci na jednom mieste a v tomto poradí: číslo
 * (aby sa dalo ukázať prstom), názov, povinnosť, a JEDEN riadok stavu. Až pod
 * tým je „čo to odomkne" — jedna veta, nie odstavec. Kto stránku vidí prvýkrát,
 * musí z hlavičiek prečítať, čo je hotové, čo je nepovinné a čo ešte chýba,
 * bez toho, aby čokoľvek rozklikol.
 */

export type BlockStatus = "on" | "off" | "waiting";

const DOT: Record<BlockStatus, string> = {
  on: "bg-[#4ade80]",
  off: "bg-[var(--app-text-4)]",
  waiting: "bg-[var(--app-text-4)]",
};

export function TelegramBlock({
  index,
  title,
  optional = false,
  status,
  statusLabel,
  statusDetail,
  unlocks,
  action,
  children,
}: {
  /** Poradie v trojici. Vo sprievodcovi sa nepoužíva — tam číslujú kroky. */
  index?: number;
  title: string;
  optional?: boolean;
  status: BlockStatus;
  /** Krátko: „Connected", „Not set up". Nie veta. */
  statusLabel: string;
  /** Podrobnosť za pomlčkou: telefón, `@meno`, chat id. */
  statusDetail?: string | null;
  /** Jedna veta o tom, čo tento blok odomyká. */
  unlocks: string;
  /** Hlavná akcia bloku, vpravo v hlavičke. */
  action?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="app-card">
      <div className="flex flex-col gap-3 border-b border-[var(--app-border)] px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {index !== undefined && (
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[10.5px] font-medium tabular-nums text-[var(--app-text-3)]">
                {index}
              </span>
            )}
            <h2 className="text-[14px] font-medium tracking-[-0.01em] text-[var(--app-text)]">
              {title}
            </h2>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10.5px] tracking-tight",
                optional
                  ? "border-[var(--app-border)] text-[var(--app-text-4)]"
                  : "border-[var(--app-border-strong)] text-[var(--app-text-3)]",
              )}
            >
              {optional ? "Optional" : "Required"}
            </span>
          </div>

          <p className="mt-2 flex items-center gap-2 text-[12.5px] text-[var(--app-text-2)]">
            <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[status])} />
            <span className="min-w-0">
              {statusLabel}
              {statusDetail && (
                <span className="text-[var(--app-text-3)]"> — {statusDetail}</span>
              )}
            </span>
          </p>

          <p className="mt-1.5 max-w-xl text-[12px] leading-relaxed text-[var(--app-text-4)]">
            {unlocks}
          </p>
        </div>

        {action && <div className="flex shrink-0 flex-wrap gap-2">{action}</div>}
      </div>

      {children && <div className="space-y-4 p-5">{children}</div>}
    </div>
  );
}

/**
 * Rozbaľovacia sekcia vnútri bloku — „Advanced", „How do I get a bot".
 * `<details>` zámerne: funguje bez JS a nedrží stav, ktorý by sa mohol rozísť.
 */
export function BlockDetails({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="group rounded-lg border border-[var(--app-border)] bg-[#0c0c0c]">
      <summary className="cursor-pointer list-none px-3.5 py-2.5 text-[12px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]">
        {summary}
      </summary>
      <div className="space-y-3 border-t border-[var(--app-border)] px-3.5 py-3">{children}</div>
    </details>
  );
}
