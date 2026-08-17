"use client";

import {
  FRESHNESS_DOT,
  FRESHNESS_LABEL,
  FRESHNESS_STYLE,
  ROLE_LABEL,
  ROLE_STYLE,
  asRole,
  freshness,
} from "@/lib/admin-ui";
import { dateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Badge-e admin tabuliek. Čerstvosť sa počíta z `Date.now()`, takže server aj
 * klient môžu vyrátať iný text — preto client komponent a `suppressHydrationWarning`.
 */

export function HeartbeatBadge({ iso }: { iso: string | null | undefined }) {
  const state = freshness(iso);
  return (
    <span
      title={iso ? dateTime(iso) : "no heartbeat yet"}
      suppressHydrationWarning
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        FRESHNESS_STYLE[state],
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", FRESHNESS_DOT[state])} />
      {FRESHNESS_LABEL[state]}
    </span>
  );
}

/** Replika je „stale" podľa DB (>2 min bez heartbeatu), nie podľa hodín klienta. */
export function ReplicaBadge({ stale }: { stale: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        stale ? FRESHNESS_STYLE.dead : FRESHNESS_STYLE.live,
      )}
    >
      <span
        className={cn("h-1.5 w-1.5 rounded-full", stale ? FRESHNESS_DOT.dead : FRESHNESS_DOT.live)}
      />
      {stale ? "Stale" : "Live"}
    </span>
  );
}

export function RoleBadge({ role }: { role: string }) {
  const value = asRole(role);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em]",
        ROLE_STYLE[value],
      )}
    >
      {ROLE_LABEL[value]}
    </span>
  );
}
