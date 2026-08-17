"use client";

import { dateTime, relativeTime } from "@/lib/format";

/**
 * Relatívny čas počítaný z `Date.now()` — na serveri aj v prehliadači vyjde
 * o chvíľu iný text, preto `suppressHydrationWarning`. Presný čas je v tooltipe.
 */
export function RelativeTime({
  iso,
  className,
}: {
  iso: string | null | undefined;
  className?: string;
}) {
  if (!iso) return <span className={className}>never</span>;
  return (
    <time dateTime={iso} title={dateTime(iso)} className={className} suppressHydrationWarning>
      {relativeTime(iso)}
    </time>
  );
}
