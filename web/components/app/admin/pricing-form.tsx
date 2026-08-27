"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2 } from "lucide-react";

import { setConfigAction } from "@/app/app/admin/pricing/actions";
import { cn } from "@/lib/utils";

export type ConfigRow = { key: string; value: number; note: string };

/**
 * Jedno nastavenie = jeden riadok s políčkom a tlačidlom Save.
 *
 * Zámerne BEZ auto-save: toto sú ceny celej platformy. Preklep pri
 * automatickom ukladaní by prepísal maržu všetkým klientom skôr, než si to
 * človek stihne všimnúť. Tu sa musí kliknúť.
 */
function ConfigField({
  row,
  label,
  suffix,
  step,
  hint,
}: {
  row: ConfigRow;
  label: string;
  suffix?: string;
  step: string;
  hint?: string;
}) {
  const router = useRouter();
  const [value, setValue] = useState(String(row.value));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, startTransition] = useTransition();

  const dirty = value !== String(row.value);

  const save = () => {
    setError(null);
    setSaved(false);
    startTransition(async () => {
      const result = await setConfigAction(row.key, Number(value));
      if (result.error) {
        setError(result.error);
        return;
      }
      setSaved(true);
      router.refresh();
    });
  };

  return (
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--app-border)] px-5 py-4 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-[13px] text-[var(--app-text)]">{label}</p>
        <p className="mt-0.5 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
          {hint ?? row.note}
        </p>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative">
          <input
            type="number"
            step={step}
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setSaved(false);
            }}
            className={cn(
              "h-9 w-[110px] rounded-md border bg-[#0c0c0c] px-3 text-right text-[13px] tabular-nums text-[var(--app-text)]",
              "focus:outline focus:outline-2 focus:outline-offset-1 focus:outline-white/40",
              error ? "border-[#7a3b3b]" : "border-[var(--app-border-strong)]",
            )}
          />
          {suffix && (
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-[var(--app-text-4)]">
              {suffix}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={save}
          disabled={!dirty || pending}
          className="app-btn app-btn-ghost h-9 px-3 disabled:opacity-40"
        >
          {pending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : saved && !dirty ? (
            <Check className="h-3.5 w-3.5" />
          ) : null}
          {saved && !dirty ? "Saved" : "Save"}
        </button>
      </div>

      {error && (
        <p className="w-full text-[11.5px] text-[#fca5a5]">{error}</p>
      )}
    </div>
  );
}

export function PricingForm({ config }: { config: ConfigRow[] }) {
  const byKey = Object.fromEntries(config.map((row) => [row.key, row]));
  const get = (key: string): ConfigRow =>
    byKey[key] ?? { key, value: 0, note: "" };

  return (
    <div className="space-y-5">
      <section className="app-panel overflow-hidden">
        <div className="border-b border-[var(--app-border)] px-5 py-4">
          <h2 className="text-[14px] font-medium tracking-tight text-[var(--app-text)]">
            Margin per tier
          </h2>
          <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-4)]">
            What a client pays for every dollar of Atlas tokens we buy. 2.0 means we
            charge double — half of it is margin. 1.0 means at cost, no margin. The same
            number also scales the per-item fees below, so one tier is one number.
          </p>
        </div>
        <ConfigField
          row={get("margin_free_plus")}
          label="Standard+"
          step="0.1"
          hint="Normal paying clients. This is where the money is."
        />
        <ConfigField
          row={get("margin_vip_lite")}
          label="VIP Lite"
          step="0.1"
          hint="Covers our cost and leaves a smaller cut. Sits between Standard+ and VIP."
        />
        <ConfigField
          row={get("margin_vip")}
          label="VIP"
          step="0.1"
          hint="1.1 = our cost plus 10%, so a VIP never costs us money. Not free, just no real margin."
        />
        <ConfigField
          row={get("margin_free")}
          label="Standard (locked)"
          step="0.1"
          hint="Accounts that were never approved. They cannot run models anyway."
        />
      </section>

      <section className="app-panel overflow-hidden">
        <div className="border-b border-[var(--app-border)] px-5 py-4">
          <h2 className="text-[14px] font-medium tracking-tight text-[var(--app-text)]">
            Per-item fees
          </h2>
          <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-4)]">
            Charged on top of tokens, only after the item actually reaches the fan. Lower
            tiers pay proportionally less — a VIP on a 1.1 margin pays 55% of these.
          </p>
        </div>
        <ConfigField
          row={get("voice_managed_usd")}
          label="Voice note — our voice"
          suffix="$"
          step="0.01"
          hint="Sent with one of our voices on our ElevenLabs key. We pay for the audio."
        />
        <ConfigField
          row={get("voice_own_usd")}
          label="Voice note — client's key"
          suffix="$"
          step="0.01"
          hint="The client's own ElevenLabs key pays for the audio, so this is all margin."
        />
        <ConfigField
          row={get("photo_usd")}
          label="Photo sent"
          suffix="$"
          step="0.01"
          hint="Costs us almost nothing beyond storage."
        />
      </section>

      <section className="app-panel overflow-hidden">
        <div className="border-b border-[var(--app-border)] px-5 py-4">
          <h2 className="text-[14px] font-medium tracking-tight text-[var(--app-text)]">
            Model slots
          </h2>
          <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-4)]">
            The first slot comes free with approval. Admins, superadmins and VIP have no
            limit at all.
          </p>
        </div>
        <ConfigField
          row={get("model_slot_usd")}
          label="Price of an extra slot"
          suffix="$"
          step="1"
        />
        <ConfigField
          row={get("max_model_slots")}
          label="Maximum slots per account"
          step="1"
        />
      </section>
    </div>
  );
}
