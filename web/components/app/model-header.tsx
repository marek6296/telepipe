"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ChevronLeft, Loader2, Pencil, Trash2, X } from "lucide-react";

import { deleteModelAction, renameModelAction } from "@/app/app/actions";
import { ModelPowerButton } from "@/components/app/model-power-button";
import { StatusBadge } from "@/components/app/ui";
import { statusReasonText } from "@/lib/status";

/**
 * Hlavička detailu modelky — meno sa dá premenovať priamo tu, vpravo je
 * prepínač stavu. Zmazanie je za potvrdením (kaskáda zmaže aj konverzácie).
 */
export function ModelHeader({
  modelId,
  name,
  status,
  statusReason,
  connected,
}: {
  modelId: string;
  name: string;
  status: string;
  statusReason: string;
  connected: boolean;
}) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const reason = statusReasonText(statusReason);

  const save = () => {
    setError(null);
    startTransition(async () => {
      const result = await renameModelAction(modelId, draft);
      if (result.error) {
        setError(result.error);
        return;
      }
      setEditing(false);
      router.refresh();
    });
  };

  const remove = () => {
    startTransition(async () => {
      const result = await deleteModelAction(modelId);
      if (result?.error) setError(result.error);
    });
  };

  return (
    <div className="mb-6">
      <Link
        href="/app/models"
        className="inline-flex items-center gap-1 text-[12.5px] text-white/35 transition-colors hover:text-[var(--gold-light)]"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        All models
      </Link>

      <div className="mt-2.5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          {editing ? (
            <div className="flex items-center gap-2">
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") save();
                  if (event.key === "Escape") {
                    setDraft(name);
                    setEditing(false);
                  }
                }}
                maxLength={60}
                autoFocus
                aria-label="Model name"
                className="glass-input h-11 max-w-xs !py-2 text-[20px] font-semibold"
              />
              <button
                type="button"
                onClick={save}
                disabled={pending}
                aria-label="Save name"
                className="rounded-xl border border-[rgba(212,175,55,0.3)] bg-[rgba(212,175,55,0.08)] p-2.5 text-[var(--gold-light)]"
              >
                {pending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft(name);
                  setEditing(false);
                }}
                aria-label="Cancel"
                className="rounded-xl border border-white/[0.08] p-2.5 text-white/45"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-balance-tight text-[26px] font-semibold text-white sm:text-[30px]">
                {name || "Untitled model"}
              </h1>
              <StatusBadge status={status} />
              <button
                type="button"
                onClick={() => setEditing(true)}
                aria-label="Rename model"
                className="rounded-lg p-1.5 text-white/25 transition-colors hover:text-[var(--gold-light)]"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {reason && <p className="mt-2 max-w-xl text-[12.5px] text-[#ffb3a7]">{reason}</p>}
          {error && <p className="mt-2 text-[12.5px] text-[#ffb3a7]">{error}</p>}
        </div>

        <div className="flex items-center gap-2">
          <ModelPowerButton
            modelId={modelId}
            status={status}
            statusReason={statusReason}
            connected={connected}
          />
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            aria-label="Delete model"
            className="rounded-full border border-white/[0.08] p-2.5 text-white/30 transition-colors hover:border-[#7a2b23] hover:text-[#ffb3a7]"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/75 backdrop-blur-sm"
            onClick={() => setConfirmDelete(false)}
          />
          <div className="glass-panel relative w-full max-w-md rounded-3xl p-7">
            <h2 className="text-[18px] font-semibold text-white">
              Delete {name || "this model"}?
            </h2>
            <p className="mt-2 text-[13px] leading-relaxed text-white/50">
              Her persona, photos, conversations and memory are deleted with her. This
              cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="btn-modern-dark h-10 px-5 text-[13px]"
              >
                Keep her
              </button>
              <button
                type="button"
                onClick={remove}
                disabled={pending}
                className="inline-flex h-10 items-center gap-2 rounded-full border border-[#7a2b23] bg-[#3a1512] px-5 text-[13px] font-semibold text-[#ff9b8f] transition-colors hover:bg-[#4a1a16]"
              >
                {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Delete for good
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
