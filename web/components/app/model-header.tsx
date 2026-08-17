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
    <div className="mb-7">
      <Link
        href="/app/models"
        className="inline-flex items-center gap-1 text-[12.5px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
      >
        <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
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
                className="app-input h-10 max-w-xs text-[18px] font-medium"
              />
              <button
                type="button"
                onClick={save}
                disabled={pending}
                aria-label="Save name"
                className="app-btn app-btn-ghost h-10 w-10 shrink-0"
              >
                {pending ? (
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
                ) : (
                  <Check className="h-4 w-4" strokeWidth={1.75} />
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft(name);
                  setEditing(false);
                }}
                aria-label="Cancel"
                className="app-btn app-btn-quiet h-10 w-10 shrink-0"
              >
                <X className="h-4 w-4" strokeWidth={1.75} />
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-[24px] font-semibold tracking-[-0.02em] text-[var(--app-text)]">
                {name || "Untitled model"}
              </h1>
              <StatusBadge status={status} />
              <button
                type="button"
                onClick={() => setEditing(true)}
                aria-label="Rename model"
                className="app-tap rounded-md p-1.5 text-[var(--app-text-4)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
              >
                <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />
              </button>
            </div>
          )}

          {reason && <p className="mt-2 max-w-xl text-[12.5px] text-[#fca5a5]">{reason}</p>}
          {error && <p className="mt-2 text-[12.5px] text-[#fca5a5]">{error}</p>}
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
            className="app-btn app-btn-quiet h-10 w-10 shrink-0 hover:text-[#fca5a5]"
          >
            <Trash2 className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/70"
            onClick={() => setConfirmDelete(false)}
          />
          <div className="app-panel relative w-full max-w-md p-6">
            <h2 className="text-[16px] font-medium text-[var(--app-text)]">
              Delete {name || "this model"}?
            </h2>
            <p className="mt-2 text-[13px] leading-relaxed text-[var(--app-text-3)]">
              Her persona, photos, conversations and memory are deleted with her. This
              cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="app-btn app-btn-ghost h-9 px-4"
              >
                Keep her
              </button>
              <button
                type="button"
                onClick={remove}
                disabled={pending}
                className="app-btn app-btn-danger h-9 px-4"
              >
                {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />}
                Delete for good
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
