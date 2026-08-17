"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";

/**
 * Auto-save s debounce 800 ms.
 *
 * Worker číta personu aj chovanie pri každej odpovedi, takže „Save" tlačidlo
 * netreba — zmena platí od najbližšej správy. Zmeny sa zlievajú do jedného
 * patchu, aby posúvanie slidera neposlalo dvadsať requestov.
 */

const DEBOUNCE_MS = 800;

export type SavePatch = Record<string, unknown>;
export type SaveFn = (patch: SavePatch) => Promise<{ error?: string } | void>;

type Status = "idle" | "pending" | "saving" | "saved" | "error";

type AutoSaveApi = {
  /** Zapíš zmenu poľa (zlúči sa do najbližšieho patchu). */
  set: (name: string, value: unknown) => void;
  /** Ulož hneď — voláme pri opustení poľa. */
  flush: () => void;
};

const AutoSaveContext = createContext<AutoSaveApi | null>(null);

export function useAutoSaveField(): AutoSaveApi {
  const context = useContext(AutoSaveContext);
  if (!context) {
    throw new Error("Pole formulára musí byť vnútri <AutoSaveForm>.");
  }
  return context;
}

export function AutoSaveForm({
  save,
  children,
  sticky = true,
}: {
  save: SaveFn;
  children: ReactNode;
  /** V modáli sa indikátor nelepí na vrch stránky, ale plynie s obsahom. */
  sticky?: boolean;
}) {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  const buffer = useRef<SavePatch>({});
  const timer = useRef<number | null>(null);
  const inflight = useRef(false);
  const saveRef = useRef(save);
  saveRef.current = save;

  const flush = useCallback(async () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    if (inflight.current) return; // dobehne po skončení práve bežiaceho zápisu
    const patch = buffer.current;
    if (Object.keys(patch).length === 0) return;

    buffer.current = {};
    inflight.current = true;
    setStatus("saving");

    let failure: string | null = null;
    try {
      const result = await saveRef.current(patch);
      failure = result?.error ?? null;
    } catch (exception) {
      failure = exception instanceof Error ? exception.message : "Could not save.";
    }
    inflight.current = false;

    if (failure) {
      // Neuložené hodnoty vrátime do bufferu — ďalšia zmena ich vezme so sebou.
      buffer.current = { ...patch, ...buffer.current };
      setError(failure);
      setStatus("error");
      return;
    }

    setError(null);
    if (Object.keys(buffer.current).length > 0) {
      setStatus("pending");
      timer.current = window.setTimeout(() => void flush(), DEBOUNCE_MS);
    } else {
      setStatus("saved");
    }
  }, []);

  const set = useCallback(
    (name: string, value: unknown) => {
      buffer.current[name] = value;
      setStatus("pending");
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void flush(), DEBOUNCE_MS);
    },
    [flush],
  );

  // Rozpísaná zmena sa nesmie stratiť pri prechode na inú stránku.
  useEffect(() => {
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      if (Object.keys(buffer.current).length > 0) void saveRef.current(buffer.current);
    };
  }, []);

  return (
    <AutoSaveContext.Provider value={{ set, flush }}>
      {sticky ? (
        <div className="relative">
          <div className="pointer-events-none sticky top-[76px] z-20 flex justify-end">
            <SaveIndicator status={status} error={error} />
          </div>
          <div className="-mt-8 space-y-5">{children}</div>
        </div>
      ) : (
        <div className="space-y-4">
          {children}
          <div className="flex justify-end">
            <SaveIndicator status={status} error={error} />
          </div>
        </div>
      )}
    </AutoSaveContext.Provider>
  );
}

function SaveIndicator({ status, error }: { status: Status; error: string | null }) {
  if (status === "idle") return null;

  const map = {
    pending: {
      className: "border-white/[0.09] bg-black/70 text-white/45",
      icon: <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--gold)]" />,
      label: "Editing…",
    },
    saving: {
      className: "border-white/[0.09] bg-black/70 text-white/55",
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
      label: "Saving…",
    },
    saved: {
      className: "border-[#2e7d52]/40 bg-[#0f2a1d]/90 text-[#8ff0bb]",
      icon: <Check className="h-3 w-3" />,
      label: "Saved",
    },
    error: {
      className: "border-[#7a2b23] bg-[#2a100d]/95 text-[#ffb3a7]",
      icon: <AlertCircle className="h-3 w-3" />,
      label: error ?? "Could not save",
    },
  } as const;

  const view = map[status];

  return (
    <span
      role="status"
      aria-live="polite"
      className={`pointer-events-auto inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11.5px] font-medium backdrop-blur-md ${view.className}`}
    >
      {view.icon}
      {view.label}
    </span>
  );
}
