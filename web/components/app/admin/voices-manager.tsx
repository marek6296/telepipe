"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2, Mic, Plus, Trash2 } from "lucide-react";

import { deleteVoiceAction, saveVoiceAction } from "@/app/app/admin/voices/actions";
import { Switch } from "@/components/app/forms/fields";
import { Callout, EmptyState } from "@/components/app/ui";

export type ManagedVoice = {
  id: string;
  label: string;
  eleven_voice_id: string;
  description: string;
  active: boolean;
};

const EMPTY = { label: "", eleven_voice_id: "", description: "", active: true };

/**
 * Katalóg našich hlasov. Jeden riadok = jeden hlas, ktorý si klient uvidí
 * v ponuke, keď nechce pripájať vlastný ElevenLabs kľúč.
 *
 * Vypnutie (`active`) je preferované pred mazaním: hlas zmizne z ponuky, ale
 * modelke, ktorá ho už má vybraný, prestane fungovať až keď si vyberie iný —
 * a väzba v databáze sa nerozbije.
 */
export function VoicesManager({ voices }: { voices: ManagedVoice[] }) {
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-4">
      {voices.length === 0 && !adding ? (
        <EmptyState
          icon={<Mic className="h-[18px] w-[18px]" strokeWidth={1.5} />}
          title="No voices yet"
          description="Add a voice from your own ElevenLabs account. Clients who do not connect their own key will pick from these."
          action={
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="app-btn app-btn-primary h-9 px-4"
            >
              <Plus className="h-4 w-4" />
              Add the first voice
            </button>
          }
        />
      ) : (
        <>
          <div className="space-y-3">
            {voices.map((voice) => (
              <VoiceRow key={voice.id} voice={voice} />
            ))}
            {adding && <VoiceRow onDone={() => setAdding(false)} />}
          </div>

          {!adding && (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="app-btn app-btn-ghost h-9 px-3"
            >
              <Plus className="h-4 w-4" />
              Add voice
            </button>
          )}
        </>
      )}
    </div>
  );
}

function VoiceRow({
  voice,
  onDone,
}: {
  voice?: ManagedVoice;
  onDone?: () => void;
}) {
  const router = useRouter();
  const [form, setForm] = useState(voice ?? EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [pending, startTransition] = useTransition();

  const isNew = !voice;
  const dirty =
    isNew ||
    form.label !== voice.label ||
    form.eleven_voice_id !== voice.eleven_voice_id ||
    form.description !== voice.description ||
    form.active !== voice.active;

  const save = () => {
    setError(null);
    startTransition(async () => {
      const result = await saveVoiceAction(voice?.id ?? null, form);
      if (result.error) {
        setError(result.error);
        return;
      }
      onDone?.();
      router.refresh();
    });
  };

  const remove = () => {
    setError(null);
    startTransition(async () => {
      const result = await deleteVoiceAction(voice!.id);
      if (result.error) {
        setError(result.error);
        setConfirming(false);
        return;
      }
      router.refresh();
    });
  };

  return (
    <div className="app-panel p-4">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <Field
          label="Name the client sees"
          value={form.label}
          placeholder="Soft"
          onChange={(v) => setForm({ ...form, label: v })}
        />
        <Field
          label="ElevenLabs voice ID"
          value={form.eleven_voice_id}
          placeholder="21m00Tcm4TlvDq8ikWAM"
          mono
          onChange={(v) => setForm({ ...form, eleven_voice_id: v })}
        />
      </div>

      <div className="mt-3">
        <Field
          label="Short description"
          value={form.description}
          placeholder="Warm, slightly husky, unhurried"
          onChange={(v) => setForm({ ...form, description: v })}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--app-border)] pt-3">
        <div className="flex items-center gap-2.5">
          <Switch
            checked={form.active}
            label="Offered to clients"
            onCheckedChange={(next) => setForm({ ...form, active: next })}
          />
          <span className="text-[12px] text-[var(--app-text-4)]">
            {form.active ? "Shown in the picker" : "Hidden from the picker"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {!isNew &&
            (confirming ? (
              <>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  className="text-[12.5px] text-[var(--app-text-3)] hover:text-[var(--app-text)]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={remove}
                  disabled={pending}
                  className="app-btn app-btn-danger h-9 px-3"
                >
                  Delete for good
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--app-text-4)] transition-colors hover:text-[#fca5a5]"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </button>
            ))}

          {isNew && onDone && (
            <button
              type="button"
              onClick={onDone}
              className="text-[12.5px] text-[var(--app-text-3)] hover:text-[var(--app-text)]"
            >
              Cancel
            </button>
          )}

          <button
            type="button"
            onClick={save}
            disabled={!dirty || pending}
            className="app-btn app-btn-primary h-9 px-4 disabled:opacity-40"
          >
            {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {isNew ? "Add voice" : "Save"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3">
          <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
            {error}
          </Callout>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  placeholder,
  mono,
  onChange,
}: {
  label: string;
  value: string;
  placeholder?: string;
  mono?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-medium tracking-tight text-[var(--app-text-2)]">
        {label}
      </span>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={`h-9 w-full rounded-md border border-[var(--app-border-strong)] bg-[#0c0c0c] px-3 text-[13px] text-[var(--app-text)] placeholder:text-[var(--app-text-4)] focus:outline focus:outline-2 focus:outline-offset-1 focus:outline-white/40 ${
          mono ? "font-mono text-[12px]" : ""
        }`}
      />
    </label>
  );
}
