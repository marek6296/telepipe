"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Check,
  CircleCheck,
  Clock,
  Copy,
  Loader2,
  Mail,
  TriangleAlert,
} from "lucide-react";

import { Callout } from "@/components/app/ui";
import { cn } from "@/lib/utils";

/**
 * Nákup Pipe Coinov cez Plisio — celý checkout beží v appke (white-label):
 * klient si vyberie balík a mincu, my mu ukážeme adresu + presnú sumu + QR
 * a živý stav platby. Pripísanie robí server (webhook/poll/cron) — tento
 * komponent stav LEN zobrazuje, nikdy nerozhoduje o kredite.
 */

export type PackOption = {
  id: string;
  name: string;
  priceUsd: number;
  coins: number;
  bonusPct: number;
  featured?: boolean;
};

export type CurrencyOption = {
  cid: string;
  label: string;
  network: string;
};

type Invoice = {
  paymentId: string;
  payAddress: string;
  payAmount: number;
  payCurrency: string;
  qrCode: string;
  invoiceUrl: string;
  expireAt: string | null;
  status: string;
  coins: number;
  usd: number;
};

type PollState = {
  status: string;
  credited: boolean;
};

const POLL_MS = 8_000;

/** Presná krypto suma bez zbytočných núl — presne to, čo treba odoslať. */
function formatAmount(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  return value.toFixed(8).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard môže byť zakázaný — tlačidlo je len skratka, text je vedľa */
    }
  }, [value]);

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={label}
      className="app-tap inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-[var(--app-border)] px-2 text-[11.5px] text-[var(--app-text-2)] transition-colors hover:border-[var(--app-border-strong)] hover:text-[var(--app-text)]"
    >
      {copied ? (
        <Check className="h-3 w-3" strokeWidth={2} aria-hidden />
      ) : (
        <Copy className="h-3 w-3" strokeWidth={1.75} aria-hidden />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/** Odpočet do vypršania faktúry. Po nule ho prekryje reálny stav z Plisia. */
function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const left = Math.max(0, new Date(until).getTime() - now);
  const mins = Math.floor(left / 60_000);
  const secs = Math.floor((left % 60_000) / 1000);
  return (
    <span className="tabular-nums">
      {String(mins).padStart(2, "0")}:{String(secs).padStart(2, "0")}
    </span>
  );
}

export function BillingPanel({
  packs,
  currencies,
  available,
  initialPackId,
  supportEmail,
}: {
  packs: PackOption[];
  currencies: CurrencyOption[];
  available: boolean;
  initialPackId?: string;
  supportEmail: string;
}) {
  const router = useRouter();
  const [packId, setPackId] = useState(() =>
    packs.some((p) => p.id === initialPackId) ? (initialPackId as string) : packs[0]?.id ?? "",
  );
  const [currency, setCurrency] = useState(currencies[0]?.cid ?? "BTC");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [poll, setPoll] = useState<PollState | null>(null);
  // `router.refresh()` po pripísaní má zmysel len raz.
  const refreshed = useRef(false);

  const pack = useMemo(() => packs.find((p) => p.id === packId), [packs, packId]);
  const coin = useMemo(() => currencies.find((c) => c.cid === currency), [currencies, currency]);

  const start = useCallback(async () => {
    if (!pack || creating) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch("/api/payments/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ packId: pack.id, currency }),
      });
      const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      if (!res.ok) {
        setError(String(data.error ?? "Could not start the payment. Please try again."));
        return;
      }
      setInvoice(data as unknown as Invoice);
      setPoll({ status: String(data.status ?? "new"), credited: false });
      refreshed.current = false;
    } catch {
      setError("Could not start the payment. Check your connection and try again.");
    } finally {
      setCreating(false);
    }
  }, [pack, currency, creating]);

  // Poller — každých 8 s, kým je checkout otvorený a coiny nie sú pripísané.
  // Server sa pri každom ticku doptá Plisia, takže zmeškaný webhook dobehne.
  useEffect(() => {
    if (!invoice || poll?.credited) return;
    let stopped = false;
    const tick = async () => {
      try {
        const res = await fetch(
          `/api/payments/topup?payment_id=${encodeURIComponent(invoice.paymentId)}`,
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const data = (await res.json()) as PollState;
        if (!stopped) setPoll({ status: data.status, credited: data.credited });
      } catch {
        /* výpadok siete — ďalší tick to skúsi znova */
      }
    };
    const id = setInterval(tick, POLL_MS);
    tick();
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, [invoice, poll?.credited]);

  // Coiny dorazili → obnov serverové dáta (zostatok v hlavičke, história).
  useEffect(() => {
    if (poll?.credited && !refreshed.current) {
      refreshed.current = true;
      router.refresh();
    }
  }, [poll?.credited, router]);

  const reset = useCallback(() => {
    setInvoice(null);
    setPoll(null);
    setError(null);
  }, []);

  if (!available) {
    return (
      <div className="p-5">
        <Callout tone="neutral" icon={<Mail className="h-4 w-4" strokeWidth={1.75} />}>
          Crypto checkout is temporarily unavailable. Email us at{" "}
          <a className="underline" href={`mailto:${supportEmail}`}>
            {supportEmail}
          </a>{" "}
          and we will top you up by hand, usually the same day.
        </Callout>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Krok 2 — faktúra: adresa, suma, QR, odpočet, živý stav           */
  /* ---------------------------------------------------------------- */
  if (invoice) {
    const credited = Boolean(poll?.credited);
    const status = poll?.status ?? invoice.status;
    const pendingDetected = status === "pending" || status === "pending internal";
    const failed = !credited && (status === "cancelled" || status === "error");
    const expired = !credited && status === "expired";
    const mismatch = !credited && status === "mismatch";
    const amountText = formatAmount(invoice.payAmount);
    const qrSrc =
      invoice.qrCode ||
      `https://api.qrserver.com/v1/create-qr-code/?size=440x440&data=${encodeURIComponent(invoice.payAddress)}`;

    if (credited) {
      return (
        <div className="flex flex-col items-center px-6 py-12 text-center">
          <CircleCheck className="h-10 w-10 text-[#86efac]" strokeWidth={1.5} aria-hidden />
          <h3 className="mt-4 text-[17px] font-semibold text-[var(--app-text)]">
            Payment received
          </h3>
          <p className="mt-2 max-w-sm text-[13px] leading-relaxed text-[var(--app-text-3)]">
            {invoice.coins.toLocaleString("en-US")} Pipe Coins were added to your balance.
            They never expire — your models can spend them right away.
          </p>
          <button type="button" onClick={reset} className="app-btn app-btn-primary mt-6 h-9 px-4">
            Done
          </button>
        </div>
      );
    }

    return (
      <div className="p-5">
        <button
          type="button"
          onClick={reset}
          className="app-tap mb-4 inline-flex items-center gap-1.5 text-[12px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          Choose a different pack or coin
        </button>

        <div className="grid gap-6 md:grid-cols-[200px_1fr]">
          <div className="mx-auto w-[200px] shrink-0">
            {/* Plisiov QR nesie adresu AJ presnú sumu; fallback len adresu. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={qrSrc}
              alt={`QR code for the ${invoice.payCurrency} payment address`}
              width={200}
              height={200}
              className="rounded-lg border border-[var(--app-border)] bg-white p-2"
            />
            {invoice.expireAt && !expired && (
              <p className="mt-3 flex items-center justify-center gap-1.5 text-[12px] text-[var(--app-text-3)]">
                <Clock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                Expires in <Countdown until={invoice.expireAt} />
              </p>
            )}
          </div>

          <div className="min-w-0">
            <p className="text-[12px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
              Send exactly
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2.5">
              <p className="break-all text-[22px] font-semibold leading-tight tracking-[-0.02em] tabular-nums text-[var(--app-text)]">
                {amountText} {invoice.payCurrency}
              </p>
              <CopyButton value={amountText} label="Copy the exact amount" />
            </div>

            <p className="mt-5 text-[12px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
              To this address · {coin?.network ?? invoice.payCurrency}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2.5">
              <p className="break-all font-mono text-[13px] leading-relaxed text-[var(--app-text)]">
                {invoice.payAddress}
              </p>
              <CopyButton value={invoice.payAddress} label="Copy the payment address" />
            </div>

            <div className="mt-5 space-y-3">
              {failed ? (
                <Callout tone="danger" icon={<TriangleAlert className="h-4 w-4" strokeWidth={1.75} />}>
                  This payment was {status === "error" ? "marked as failed" : "cancelled"}. No coins
                  were charged — start a new payment. If you already sent funds, email{" "}
                  <a className="underline" href={`mailto:${supportEmail}`}>{supportEmail}</a>.
                </Callout>
              ) : expired ? (
                <Callout tone="neutral" icon={<Clock className="h-4 w-4" strokeWidth={1.75} />}>
                  The invoice expired. <strong>Already sent the payment?</strong> Don&apos;t worry —
                  we keep watching the address and credit your coins automatically once the network
                  confirms it, even hours later. Nothing sent yet? Just start a new payment.
                </Callout>
              ) : mismatch ? (
                <Callout tone="neutral" icon={<TriangleAlert className="h-4 w-4" strokeWidth={1.75} />}>
                  We received a different amount than requested and are verifying it. Overpayments
                  are credited automatically. If this doesn&apos;t resolve in a few minutes, email{" "}
                  <a className="underline" href={`mailto:${supportEmail}`}>{supportEmail}</a> with
                  your transaction ID.
                </Callout>
              ) : pendingDetected ? (
                <Callout tone="success" icon={<Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />}>
                  <strong>Payment detected!</strong> Waiting for network confirmations — this
                  usually takes a few minutes. You can close this page; the coins will land in
                  your balance automatically.
                </Callout>
              ) : (
                <Callout tone="neutral" icon={<Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />}>
                  Waiting for your payment… Send <strong>one transaction</strong> with the exact
                  amount on the <strong>{coin?.network ?? invoice.payCurrency}</strong> network.
                  This page updates by itself.
                </Callout>
              )}

              <p className="text-[12px] leading-relaxed text-[var(--app-text-4)]">
                You are buying {invoice.coins.toLocaleString("en-US")} Pipe Coins for ${invoice.usd}.
                Network fees charged by your wallet are not part of the amount above.
                {invoice.invoiceUrl && !failed && (
                  <>
                    {" "}
                    Paying from your phone?{" "}
                    <a
                      href={invoice.invoiceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="underline hover:text-[var(--app-text-2)]"
                    >
                      Open the hosted payment page
                    </a>
                    {" "}— it&apos;s the same invoice.
                  </>
                )}
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* ---------------------------------------------------------------- */
  /*  Krok 1 — výber balíka a mince                                    */
  /* ---------------------------------------------------------------- */
  return (
    <div className="p-5">
      <p className="text-[12px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">1 · Pick a pack</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Coin pack">
        {packs.map((item) => {
          const active = item.id === packId;
          return (
            <button
              key={item.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setPackId(item.id)}
              className={cn(
                "app-tap rounded-lg border px-4 py-3.5 text-left transition-colors",
                active
                  ? "border-[var(--app-text-4)] bg-[var(--app-surface-hover)]"
                  : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
              )}
            >
              <span className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-medium text-[var(--app-text)]">{item.name}</span>
                {item.bonusPct > 0 && (
                  <span className="rounded-full border border-[var(--app-border)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--app-text-2)]">
                    +{item.bonusPct}%
                  </span>
                )}
              </span>
              <span className="mt-2 block text-[17px] font-semibold tabular-nums tracking-[-0.02em] text-[var(--app-text)]">
                {item.coins.toLocaleString("en-US")}
              </span>
              <span className="mt-0.5 block text-[11.5px] text-[var(--app-text-3)]">
                Pipe Coins · ${item.priceUsd}
              </span>
            </button>
          );
        })}
      </div>

      <p className="mt-6 text-[12px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
        2 · Pay with
      </p>
      <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label="Cryptocurrency">
        {currencies.map((item) => {
          const active = item.cid === currency;
          return (
            <button
              key={item.cid}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setCurrency(item.cid)}
              className={cn(
                "app-tap rounded-md border px-3 py-2 text-[12.5px] transition-colors",
                active
                  ? "border-[var(--app-text-4)] bg-[var(--app-surface-hover)] text-[var(--app-text)]"
                  : "border-[var(--app-border)] text-[var(--app-text-2)] hover:border-[var(--app-border-strong)] hover:text-[var(--app-text)]",
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {coin && (
        <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
          Network: {coin.network}. Send only {coin.label} on this network.
        </p>
      )}

      {error && (
        <div className="mt-4">
          <Callout tone="danger" icon={<TriangleAlert className="h-4 w-4" strokeWidth={1.75} />}>
            {error}
          </Callout>
        </div>
      )}

      <button
        type="button"
        onClick={start}
        disabled={creating || !pack}
        className={cn("app-btn app-btn-primary mt-6 h-10 px-5", creating && "opacity-70")}
      >
        {creating && <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden />}
        {pack
          ? `Continue — ${pack.coins.toLocaleString("en-US")} coins for $${pack.priceUsd}`
          : "Continue"}
      </button>
      <p className="mt-2.5 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        You&apos;ll get the deposit address and exact amount on the next screen. The rate is locked
        for the whole payment window.
      </p>
    </div>
  );
}
