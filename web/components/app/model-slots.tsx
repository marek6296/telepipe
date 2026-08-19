"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2, Plus } from "lucide-react";

import { buyModelSlotAction } from "@/app/app/actions";
import { Callout } from "@/components/app/ui";
import { cn } from "@/lib/utils";

/**
 * Sloty na modelky — koľko ich účet má, koľko je obsadených, a kúpa ďalšieho.
 *
 * Slot je KAPACITA, nie vlastníctvo konkrétnej modelky: zmazanie modelky
 * miesto uvoľní a klient si môže spraviť novú bez ďalšej platby. Preto sa tu
 * hovorí „in use", nie „bought" — inak by ľudia čakali, že zmazaním o slot
 * prídu.
 *
 * Účty s neobmedzeným počtom (admin, superadmin, VIP) tento panel nevidia
 * vôbec — strop na ne neplatí a číslo by ich len mýlilo.
 */
export function ModelSlots({
  slots,
  used,
  balanceUsd,
  slotPriceUsd,
  maxSlots,
}: {
  slots: number;
  used: number;
  balanceUsd: number;
  slotPriceUsd: number;
  maxSlots: number;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const free = Math.max(0, slots - used);
  const atMax = slots >= maxSlots;
  const affordable = balanceUsd >= slotPriceUsd;

  const buy = () => {
    setError(null);
    startTransition(async () => {
      const result = await buyModelSlotAction();
      if (result.error) {
        setError(result.error);
        return;
      }
      router.refresh();
    });
  };

  return (
    <div className="app-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-[20px] font-semibold tracking-tight text-[var(--app-text)]">
              {used} / {slots}
            </span>
            <span className="text-[12.5px] text-[var(--app-text-3)]">
              model {slots === 1 ? "slot" : "slots"} in use
            </span>
          </div>
          <p className="mt-1 max-w-[60ch] text-[12px] leading-relaxed text-[var(--app-text-4)]">
            {free > 0
              ? `You can add ${free} more ${free === 1 ? "model" : "models"}. Deleting a model frees its slot again — you never pay twice for the same one.`
              : "Every slot is taken. Delete a model to free one up, or add another slot below."}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Body: obsadené plné, voľné duté. Na prvý pohľad koľko je miesta. */}
          <div className="flex items-center gap-1" aria-hidden>
            {Array.from({ length: slots }).map((_, i) => (
              <span
                key={i}
                className={cn(
                  "h-2 w-2 rounded-full",
                  i < used
                    ? "bg-[var(--app-text)]"
                    : "border border-[var(--app-border-strong)]",
                )}
              />
            ))}
          </div>

          {!atMax && (
            <button
              type="button"
              onClick={buy}
              disabled={pending || !affordable}
              title={
                affordable
                  ? undefined
                  : `You need $${slotPriceUsd} in Pipe Coins to add a slot.`
              }
              className="app-btn app-btn-ghost h-9 shrink-0 px-3"
            >
              {pending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Add slot · ${slotPriceUsd}
            </button>
          )}
        </div>
      </div>

      {atMax && (
        <p className="mt-3 text-[11.5px] text-[var(--app-text-4)]">
          You have the maximum of {maxSlots} slots.
        </p>
      )}

      {!atMax && !affordable && (
        <p className="mt-3 text-[11.5px] text-[var(--app-text-4)]">
          Adding a slot costs ${slotPriceUsd} in Pipe Coins. Top up on the Billing page.
        </p>
      )}

      {error && (
        <div className="mt-4">
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
          </Callout>
        </div>
      )}
    </div>
  );
}
