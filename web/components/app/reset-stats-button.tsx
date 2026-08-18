"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { RotateCcw } from "lucide-react";

import { resetStatsAction } from "@/app/app/actions";

import { cn } from "@/lib/utils";

/**
 * „Reset stats" — čistý štart na dashboarde.
 *
 * DVA KROKY SCHVÁLNE. Prvý klik len odkryje potvrdenie s vetou o tom, čo sa
 * naozaj stane; až druhý to vykoná. Bez toho by sa to dalo trafiť omylom
 * a človek by nevedel, či práve prišiel o históriu faktúr.
 *
 * A práve preto tá veta hovorí, že sa NIČ nemaže: `usage_events` ostávajú,
 * mení sa len hranica, od ktorej klientove prehľady počítajú (migrácia 027).
 * Sľubovať „vymazané", keď riadky ostávajú, by bolo klamstvo — a naopak,
 * zamlčať, že spotreba je stále v účtovníctve, tiež.
 */
export function ResetStatsButton({ since }: { since: string | null }) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const run = () => {
    setError(null);
    startTransition(async () => {
      const result = await resetStatsAction();
      if (result.error) {
        setError(result.error);
        return;
      }
      setAsking(false);
      router.refresh();
    });
  };

  if (!asking) {
    return (
      <div className="flex flex-wrap items-center gap-2.5">
        {since && (
          <span className="text-[11.5px] text-[var(--app-text-4)]">
            counting since {formatSince(since)}
          </span>
        )}
        <button
          type="button"
          onClick={() => setAsking(true)}
          className="inline-flex items-center gap-1.5 text-[12px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
        >
          <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.5} />
          Reset stats
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2.5">
      <p className="max-w-md text-right text-[11.5px] leading-relaxed text-[var(--app-text-3)]">
        {error ?? (
          <>
            Your dashboard starts counting from now. Nothing is deleted — every charge stays on
            the Usage page and on your invoices.
          </>
        )}
      </p>
      <button
        type="button"
        onClick={() => {
          setAsking(false);
          setError(null);
        }}
        className="app-btn app-btn-ghost h-8 px-3 text-[12px]"
        disabled={pending}
      >
        Cancel
      </button>
      <button
        type="button"
        onClick={run}
        disabled={pending}
        className={cn("app-btn app-btn-primary h-8 px-3 text-[12px]", pending && "opacity-60")}
      >
        {pending ? "Resetting…" : "Start from now"}
      </button>
    </div>
  );
}

/** `18 Aug, 06:41` — hranica je v UTC ako celý zvyšok dashboardu. */
function formatSince(iso: string): string {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return "your last reset";
  return date.toLocaleString("en-US", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
}
