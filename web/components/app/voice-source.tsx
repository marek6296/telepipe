"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Check, KeyRound, Loader2, Sparkles } from "lucide-react";

import { saveBehaviorAction } from "@/app/app/m/[id]/persona/behavior/actions";
import { Callout } from "@/components/app/ui";
import { cn } from "@/lib/utils";

export type ManagedVoiceOption = {
  id: string;
  label: string;
  description: string;
};

/**
 * Odkiaľ berie modelka hlas — z nášho účtu, alebo z klientovho kľúča.
 *
 * Vždy je vybraná práve jedna možnosť. Prepnutie NEZAHODÍ druhú voľbu:
 * `voice_source` a `managed_voice_id` sú samostatné stĺpce od
 * `eleven_voice_id`, takže návrat k vlastnému kľúču vráti aj jeho pôvodný hlas.
 *
 * Cena sa píše rovno na kartu. Klient musí vedieť, čo ho stojí každá odoslaná
 * hlasovka, skôr než si možnosť zapne — nie až keď mu klesne zostatok.
 */
export function VoiceSource({
  modelId,
  source,
  managedVoiceId,
  voices,
  managedPriceUsd,
  hasOwnKey,
}: {
  modelId: string;
  source: string;
  managedVoiceId: string | null;
  voices: ManagedVoiceOption[];
  managedPriceUsd: number;
  hasOwnKey: boolean;
}) {
  const router = useRouter();
  const [value, setValue] = useState(source === "managed" ? "managed" : "own");
  const [picked, setPicked] = useState(managedVoiceId);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const save = (patch: Record<string, unknown>) => {
    setError(null);
    startTransition(async () => {
      const result = await saveBehaviorAction(modelId, patch);
      if (result.error) {
        setError(result.error);
        return;
      }
      router.refresh();
    });
  };

  const chooseManaged = (voiceId: string) => {
    setPicked(voiceId);
    setValue("managed");
    save({ voice_source: "managed", managed_voice_id: voiceId });
  };

  const chooseOwn = () => {
    setValue("own");
    save({ voice_source: "own" });
  };

  return (
    <div className="app-panel overflow-hidden">
      <div className="border-b border-[var(--app-border)] px-5 py-4">
        <div className="flex items-center gap-2">
          <h2 className="text-[14px] font-medium tracking-tight text-[var(--app-text)]">
            Where her voice comes from
          </h2>
          {pending && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--app-text-4)]" />
          )}
        </div>
        <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-4)]">
          Use one of our ready-made voices, or connect your own ElevenLabs account and
          use any voice on it.
        </p>
      </div>

      {/* --- Naše hlasy ---------------------------------------------------- */}
      <div className="border-b border-[var(--app-border)] px-5 py-4">
        <div className="flex items-start gap-2">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-[var(--app-text-3)]" />
          <div className="min-w-0">
            <p className="text-[13px] text-[var(--app-text)]">Use one of our voices</p>
            <p className="mt-0.5 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
              Nothing to set up. Every voice note she sends costs{" "}
              <strong className="font-semibold text-[var(--app-text-2)]">
                ${managedPriceUsd.toFixed(2)}
              </strong>{" "}
              on top of the reply itself.
            </p>
          </div>
        </div>

        {voices.length === 0 ? (
          <p className="mt-3 text-[11.5px] text-[var(--app-text-4)]">
            No ready-made voices are available right now.
          </p>
        ) : (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {voices.map((voice) => {
              const active = value === "managed" && picked === voice.id;
              return (
                <button
                  key={voice.id}
                  type="button"
                  onClick={() => chooseManaged(voice.id)}
                  disabled={pending}
                  className={cn(
                    "flex items-start justify-between gap-2 rounded-lg border px-3 py-2.5 text-left transition-colors",
                    active
                      ? "border-[var(--app-border-strong)] bg-[var(--app-active)]"
                      : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block text-[12.5px] text-[var(--app-text)]">
                      {voice.label}
                    </span>
                    {voice.description && (
                      <span className="mt-0.5 block text-[11px] leading-snug text-[var(--app-text-4)]">
                        {voice.description}
                      </span>
                    )}
                  </span>
                  {active && (
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--app-text)]" />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* --- Vlastný kľúč --------------------------------------------------- */}
      <button
        type="button"
        onClick={chooseOwn}
        disabled={pending || value === "own"}
        className={cn(
          "flex w-full items-start gap-2 px-5 py-4 text-left transition-colors",
          value === "own" ? "bg-[var(--app-active)]" : "hover:bg-[var(--app-surface-hover)]",
        )}
      >
        <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-[var(--app-text-3)]" />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="text-[13px] text-[var(--app-text)]">
              Use my own ElevenLabs key
            </span>
            {value === "own" && <Check className="h-3.5 w-3.5 text-[var(--app-text)]" />}
          </span>
          <span className="mt-0.5 block text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            {hasOwnKey
              ? "Your account pays ElevenLabs directly and you can use any voice on it."
              : "Connect a key in Account settings first — until then she sends text instead."}
          </span>
        </span>
      </button>

      {error && (
        <div className="px-5 pb-4">
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
          </Callout>
        </div>
      )}
    </div>
  );
}
