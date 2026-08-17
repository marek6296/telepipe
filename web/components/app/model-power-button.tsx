"use client";

import { useState, useTransition } from "react";
import { Loader2, Pause, Play } from "lucide-react";

import { setModelStatusAction } from "@/app/app/actions";
import { asStatus, canActivate, canPause } from "@/lib/status";
import { cn } from "@/lib/utils";

/**
 * Zapnúť / uspať modelku. Prechody kopírujú whitelist v RPC `set_model_status`
 * — čo DB nedovolí, tu nie je ani ako tlačidlo.
 */
export function ModelPowerButton({
  modelId,
  status,
  statusReason,
  connected,
  size = "md",
}: {
  modelId: string;
  status: string;
  statusReason: string;
  connected: boolean;
  size?: "sm" | "md";
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const state = asStatus(status);

  const activate = canActivate(state, statusReason);
  const pause = canPause(state);
  if (!activate && !pause) return null;

  // Bez Telegram session nemá čo spustiť — najprv wizard.
  const blocked = activate && !connected;

  const run = () => {
    setError(null);
    startTransition(async () => {
      const result = await setModelStatusAction(modelId, activate ? "active" : "paused");
      if (result?.error) setError(result.error);
    });
  };

  const label = activate ? "Activate" : "Pause";
  const Icon = activate ? Play : Pause;

  return (
    <div className="flex flex-col items-end gap-1.5">
      <button
        type="button"
        onClick={run}
        disabled={pending || blocked}
        title={blocked ? "Connect her Telegram account first" : undefined}
        className={cn(
          activate ? "btn-modern-light" : "btn-modern-dark",
          size === "sm" ? "h-9 px-4 text-[12.5px]" : "h-10 px-5 text-[13px]",
        )}
      >
        {pending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Icon className="h-3.5 w-3.5" />
        )}
        {label}
      </button>
      {error && (
        <p role="alert" className="max-w-[15rem] text-right text-[11.5px] text-[#ffb3a7]">
          {error}
        </p>
      )}
    </div>
  );
}
