"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BadgeCheck, CreditCard, ExternalLink, Loader2 } from "lucide-react";

import { customBonusPct, customCoinsForUsd, formatCoins } from "@/lib/coins";
import { cn } from "@/lib/utils";

/**
 * Platba kartou (OnRamp) — pre ľudí, ktorí krypto poslať nevedia.
 *
 * Checkout sa otvára v NOVOM tabe, lebo služba nemá návratovú URL — a práve
 * preto sa tu potom polluje: tento tab čaká a v momente, keď callback platbu
 * pripíše, ukáže to aj bez toho, aby klient čokoľvek stlačil. Zavrieť ho môže
 * kedykoľvek, pripísanie beží na serveri (callback + cron), nie tu.
 */

const QUICK = [20, 50, 100, 250];
const POLL_MS = 8_000;

type Phase = "idle" | "starting" | "waiting" | "credited";

export function CardTopUp() {
  const router = useRouter();
  const [amount, setAmount] = useState("50");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [coins, setCoins] = useState(0);
  const pid = useRef<string | null>(null);

  const usd = Number.parseFloat(amount) || 0;
  const valid = usd >= 5 && usd <= 1000;
  const estimate = valid ? customCoinsForUsd(usd) : 0;
  const bonus = valid ? customBonusPct(usd) : 0;

  // Poll beží len kým sa čaká; po pripísaní alebo odchode zo stránky končí.
  useEffect(() => {
    if (phase !== "waiting" || !pid.current) return;
    const timer = setInterval(async () => {
      try {
        const response = await fetch(`/api/payments/card?pid=${pid.current}`, { cache: "no-store" });
        if (!response.ok) return;
        const body = (await response.json()) as { credited?: boolean; coins?: number };
        if (body.credited) {
          setCoins(Number(body.coins ?? 0));
          setPhase("credited");
          router.refresh();
        }
      } catch {
        // sieťový výpadok pollu nič neznamená — skúsi sa o 8 s znova
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [phase, router]);

  const start = async () => {
    setError(null);
    setPhase("starting");
    try {
      const response = await fetch("/api/payments/card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ usd }),
      });
      const body = (await response.json()) as { error?: string; url?: string; paymentId?: string };
      if (!response.ok || !body.url || !body.paymentId) {
        setError(body.error ?? "Could not start the payment. Try again.");
        setPhase("idle");
        return;
      }
      pid.current = body.paymentId;
      // Nový tab: checkout nemá návrat späť, takže Billing ostáva otvorený
      // a hlási pripísanie sám.
      window.open(body.url, "_blank", "noopener");
      setPhase("waiting");
    } catch {
      setError("Could not start the payment. Try again.");
      setPhase("idle");
    }
  };

  if (phase === "credited") {
    return (
      <div className="flex flex-col items-center gap-2 px-5 py-8 text-center">
        <BadgeCheck className="h-6 w-6 text-[#86efac]" strokeWidth={1.5} />
        <p className="text-[14px] font-medium text-[var(--app-text)]">
          {formatCoins(coins)} Pipe Coins credited
        </p>
        <p className="text-[12.5px] text-[var(--app-text-3)]">
          The balance is updated. Thanks!
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0">
          <label htmlFor="card-usd" className="app-label mb-2 block">
            Amount (USD)
          </label>
          <div className="flex items-center gap-1.5">
            {QUICK.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setAmount(String(value))}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-[12px] transition-colors",
                  Number(amount) === value
                    ? "border-[#3f3f46] bg-[#161616] text-[var(--app-text)]"
                    : "border-[var(--app-border)] text-[var(--app-text-3)] hover:text-[var(--app-text)]",
                )}
              >
                ${value}
              </button>
            ))}
            <input
              id="card-usd"
              type="number"
              min={5}
              max={1000}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              className="app-input h-9 w-24 text-[13px]"
            />
          </div>
        </div>
        <button
          type="button"
          onClick={start}
          disabled={!valid || phase !== "idle"}
          className="app-btn app-btn-primary h-11 px-5"
        >
          {phase === "starting" ? (
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
          ) : (
            <CreditCard className="h-4 w-4" strokeWidth={1.75} />
          )}
          Pay by card
          <ExternalLink className="h-3.5 w-3.5 opacity-60" strokeWidth={1.75} />
        </button>
      </div>

      <p className="text-[12.5px] text-[var(--app-text-3)]">
        {valid ? (
          <>
            You&apos;ll get <span className="text-[var(--app-text)]">{formatCoins(estimate)} Pipe Coins</span>
            {bonus > 0 && <span className="text-[#86efac]"> · +{bonus}% volume bonus</span>}
          </>
        ) : (
          "Enter between $5 and $1,000."
        )}
      </p>

      {phase === "waiting" && (
        <div className="flex items-center gap-2 rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3 text-[12.5px] text-[var(--app-text-3)]">
          <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
          Finish the payment in the checkout tab. Coins land here automatically — you can even
          close this page.
        </div>
      )}

      {error && (
        <p className="text-[12.5px] text-[#fca5a5]" role="alert">
          {error}
        </p>
      )}

      <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        Card, PayPal, Revolut and more via OnRamp — the exact options depend on your country.
        Processed by licensed third-party providers; we never see your card details.
      </p>
    </div>
  );
}
