"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Minimalistický toast pre admin akcie — žiadna knižnica, len context + fronta.
 * Zmiznú samé po 5 s, kliknutím skôr.
 */

type Toast = { id: number; tone: "success" | "error"; text: string };

type ToastApi = {
  success: (text: string) => void;
  error: (text: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

const LIFETIME_MS = 5000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const remove = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (tone: Toast["tone"], text: string) => {
      // Date.now() nestačí — dve akcie v tej istej milisekunde by mali rovnaký key.
      const id = Date.now() + Math.random();
      setToasts((current) => [...current.slice(-3), { id, tone, text }]);
      window.setTimeout(() => remove(id), LIFETIME_MS);
    },
    [remove],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (text: string) => push("success", text),
      error: (text: string) => push("error", text),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[95] flex w-[min(22rem,calc(100vw-2.5rem))] flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.button
              key={toast.id}
              type="button"
              onClick={() => remove(toast.id)}
              layout
              initial={{ opacity: 0, y: 14, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className={cn(
                "app-panel pointer-events-auto flex items-start gap-2.5 px-4 py-3 text-left text-[12.5px] leading-snug",
                toast.tone === "success"
                  ? "text-[var(--app-text)]"
                  : "border-[rgba(248,113,113,0.3)] text-[#fca5a5]",
              )}
            >
              {toast.tone === "success" ? (
                <CheckCircle2 className="mt-px h-4 w-4 shrink-0" />
              ) : (
                <AlertCircle className="mt-px h-4 w-4 shrink-0" />
              )}
              <span className="min-w-0">{toast.text}</span>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>");
  return context;
}
