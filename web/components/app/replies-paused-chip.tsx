"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Loader2, PauseCircle } from "lucide-react";

import { setAiPausedAction } from "@/app/app/actions";
import { cn } from "@/lib/utils";

/**
 * „Replies paused" — `settings.ai_paused`.
 *
 * PREČO EXISTUJE: pauzu zapína worker sám pri `PeerFloodError` (userbot.py) a
 * Telegram control bot. Obe cesty vedú mimo dashboardu, takže klient doteraz
 * videl zelené „Active" pri modelke, ktorá nikomu neodpisovala. Toto je jediné
 * miesto v appke, kde sa ten stav dá vidieť aj zrušiť.
 *
 * PREČO TO NIE JE POWER BUTTON (a nesmie s ním splynúť):
 *   power button → `models.status`     → beží agent vôbec? (Telethon session)
 *   tento chip   → `settings.ai_paused` → beží, ale mlčí?
 * Sú to dve nezávislé osi. Zlúčené do jedného prepínača by „chcem zase
 * odpovedať" znamenalo reštart session — po flood warningu presne to, čo účet
 * stojí život.
 */
export function RepliesPausedChip({
  modelId,
  withAction = false,
  className,
}: {
  modelId: string;
  /** Hlavička modelky má aj tlačidlo; karta v zozname je len štítok. */
  withAction?: boolean;
  className?: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const resume = () => {
    setError(null);
    startTransition(async () => {
      const result = await setAiPausedAction(modelId, false);
      if (result?.error) {
        setError(result.error);
        return;
      }
      router.refresh();
    });
  };

  const tooltip =
    "Paused from the Telegram control bot or automatically after a Telegram flood warning.";

  return (
    <span className={cn("inline-flex flex-wrap items-center gap-2", className)}>
      <span
        title={tooltip}
        className="inline-flex items-center gap-1.5 rounded-md border border-[rgba(250,204,21,0.26)] bg-[rgba(250,204,21,0.05)] px-2 py-1 text-[11.5px] text-[#fde047]"
      >
        <PauseCircle className="h-3.5 w-3.5" strokeWidth={1.75} />
        Replies paused
      </span>

      {withAction && (
        <button
          type="button"
          onClick={resume}
          disabled={pending}
          className="app-btn app-btn-quiet h-7 px-2.5 text-[11.5px]"
        >
          {pending && <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />}
          Resume replies
        </button>
      )}

      {error && (
        <span role="alert" className="text-[11.5px] text-[#fca5a5]">
          {error}
        </span>
      )}
    </span>
  );
}
