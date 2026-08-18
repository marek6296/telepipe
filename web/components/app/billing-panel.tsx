"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronDown,
  CircleCheck,
  Copy,
  CreditCard,
  ExternalLink,
  Loader2,
  Mail,
  ScanLine,
  Smartphone,
  TriangleAlert,
  Wallet,
} from "lucide-react";

import { Callout } from "@/components/app/ui";
import {
  CUSTOM_MAX_USD,
  CUSTOM_MIN_USD,
  customBonusPct,
  customCoinsForUsd,
} from "@/lib/coins";
import { cryptoAmountForUsd, cryptoMeta, type CryptoRates } from "@/lib/crypto-meta";
import { cn } from "@/lib/utils";

/**
 * Nákup Pipe Coinov cez permanentnú Plisio adresu. Klient zvolí sumu a mincu,
 * vidí ORIENTAČNE koľko krypta poslať (živý kurz) a dostane svoju stálu adresu
 * s QR. Kredit počíta server z net USD hodnoty potvrdenej Plisiom — tento
 * komponent stav len zobrazuje, o kredite nikdy nerozhoduje.
 */

export type CurrencyOption = { cid: string; label: string; network: string };

type PermanentAddress = {
  payAddress: string;
  payCurrency: string;
  qrCode: string;
  createdAt: string;
  permanent: true;
};

type CreditedDeposit = {
  payment_id: string;
  pay_currency: string;
  source_usd: number | string;
  bonus_pct: number | string;
  coins: number | string;
  status: string;
  credited: boolean;
  created_at: string;
};

const POLL_MS = 8_000;
const QUICK_AMOUNTS = [20, 50, 100, 250];
const CARD_ONRAMP_URL = "https://guardarian.com/buy-crypto-with-card";

/* -------------------------------------------------------------------------- */
/*  Značka mince — farba je to, čo z monochrómu spraví voľbu na klik           */
/* -------------------------------------------------------------------------- */

function CoinBadge({ cid, size = 30 }: { cid: string; size?: number }) {
  const meta = cryptoMeta(cid);
  const glyph = meta.symbol ?? meta.ticker;
  const fontSize = meta.symbol ? size * 0.5 : size * (meta.ticker.length >= 3 ? 0.3 : 0.42);
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold leading-none"
      style={{
        width: size,
        height: size,
        background: meta.color,
        color: meta.darkText ? "#0a0a0a" : "#ffffff",
        fontSize,
      }}
      aria-hidden
    >
      {glyph}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/*  Kopírovanie                                                                */
/* -------------------------------------------------------------------------- */

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // The address remains selectable when clipboard access is unavailable.
    }
  }, [value]);

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={label}
      className="app-tap inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-[var(--app-border)] px-2.5 text-[11.5px] text-[var(--app-text-2)] transition-colors hover:border-[var(--app-border-strong)] hover:text-[var(--app-text)]"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Sprievodca pre nováčika — zbalený cez natívny <details>                    */
/* -------------------------------------------------------------------------- */

function NewToCrypto({ label }: { label: string }) {
  const wallets = [
    { icon: Smartphone, name: "Revolut", note: "Easiest if you have it", how: "Card → Crypto → buy a little → Send → paste the address below." },
    { icon: Wallet, name: "MetaMask", note: "Free app, 5 minutes", how: "Install → buy crypto by card → Send → paste the address below." },
    { icon: CreditCard, name: "Exchange (Binance…)", note: "If you already hold crypto", how: "Buy → Withdraw / Send → paste the address and pick the network." },
  ];

  return (
    <details className="group rounded-xl border border-[var(--app-border)] bg-[var(--app-surface-hover)]/40 open:bg-transparent">
      <summary className="app-tap flex cursor-pointer list-none items-center justify-between gap-3 p-4 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)]">
            <Wallet className="h-4 w-4 text-[var(--app-text-2)]" strokeWidth={1.75} aria-hidden />
          </span>
          <span>
            <span className="block text-[13px] font-medium text-[var(--app-text)]">
              First time paying with crypto? It only takes a few minutes
            </span>
            <span className="block text-[11.5px] text-[var(--app-text-4)]">How to do it — step by step</span>
          </span>
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-[var(--app-text-3)] transition-transform group-open:rotate-180" strokeWidth={1.75} aria-hidden />
      </summary>

      <div className="space-y-4 px-4 pb-4">
        <div className="rounded-lg border border-[var(--app-text-4)] bg-[var(--app-surface-hover)] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="flex items-center gap-2 text-[13px] font-semibold text-[var(--app-text)]">
              <CreditCard className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              Easiest — pay by card
              <span className="rounded-full border border-[var(--app-border-strong)] px-2 py-0.5 text-[10px] font-medium text-[var(--app-text-3)]">
                no wallet, no account
              </span>
            </p>
            <a href={CARD_ONRAMP_URL} target="_blank" rel="noopener noreferrer" className="app-btn app-btn-secondary h-8 shrink-0 px-3 text-[12px]">
              Open Guardarian
              <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            </a>
          </div>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            No registration — just a quick identity check (required by law everywhere). The crypto
            goes straight to your address here.
          </p>
          <ol className="mt-3 space-y-2">
            {[
              `Below, pick ${label} and click “Show my address” — you get your permanent address.`,
              "Open Guardarian and paste that address as the recipient wallet address.",
              "Pick the same coin, enter an amount and pay by card. Verify your identity.",
              "The crypto arrives in a few minutes and coins are added automatically.",
            ].map((text, index) => (
              <li key={index} className="flex items-start gap-2.5">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[10px] font-semibold text-[var(--app-text-2)]">
                  {index + 1}
                </span>
                <span className="text-[12.5px] leading-relaxed text-[var(--app-text-2)]">{text}</span>
              </li>
            ))}
          </ol>
        </div>

        <div>
          <p className="mb-2.5 text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">Or if you already have crypto somewhere</p>
          <div className="grid gap-2.5 sm:grid-cols-3">
            {wallets.map((wallet) => (
              <div key={wallet.name} className="rounded-lg border border-[var(--app-border)] p-3">
                <p className="flex items-center gap-2 text-[13px] font-medium text-[var(--app-text)]">
                  <wallet.icon className="h-4 w-4 text-[var(--app-text-2)]" strokeWidth={1.75} aria-hidden />
                  {wallet.name}
                </p>
                <p className="mt-1 text-[11px] text-[var(--app-text-4)]">{wallet.note}</p>
                <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-2)]">{wallet.how}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </details>
  );
}

/* -------------------------------------------------------------------------- */
/*  Panel                                                                      */
/* -------------------------------------------------------------------------- */

export function BillingPanel({
  currencies,
  rates,
  available,
  supportEmail,
}: {
  currencies: CurrencyOption[];
  rates: CryptoRates;
  available: boolean;
  supportEmail: string;
}) {
  const router = useRouter();
  const [amount, setAmount] = useState("50");
  const [currency, setCurrency] = useState(currencies[0]?.cid ?? "USDT_TRX");
  const [address, setAddress] = useState<PermanentAddress | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [credited, setCredited] = useState<CreditedDeposit | null>(null);
  const watchAfter = useRef(new Date().toISOString());
  const refreshedPayment = useRef("");

  const selectedCurrency = useMemo(
    () => currencies.find((item) => item.cid === currency),
    [currencies, currency],
  );
  const meta = cryptoMeta(currency);
  const usd = Math.round((Number.parseFloat(amount) || 0) * 100) / 100;
  const amountValid = usd >= CUSTOM_MIN_USD && usd <= CUSTOM_MAX_USD;
  const expectedCoins = amountValid ? customCoinsForUsd(usd) : 0;
  const bonusPct = amountValid ? customBonusPct(usd) : 0;
  const sendAmount = amountValid ? cryptoAmountForUsd(currency, usd, rates[currency]) : null;

  const selectCurrency = useCallback((next: string) => {
    setCurrency(next);
    setAddress(null);
    setCredited(null);
    setError(null);
    watchAfter.current = new Date().toISOString();
  }, []);

  const loadAddress = useCallback(async () => {
    if (!amountValid || loading) return;
    setLoading(true);
    setError(null);
    setCredited(null);
    watchAfter.current = new Date(Date.now() - 1_000).toISOString();
    try {
      const response = await fetch("/api/payments/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ currency }),
      });
      const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
      if (!response.ok) {
        setError(String(data.error ?? "Could not load the deposit address."));
        return;
      }
      setAddress(data as unknown as PermanentAddress);
    } catch {
      setError("Could not load the address. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [amountValid, currency, loading]);

  useEffect(() => {
    if (!address || credited) return;
    let stopped = false;
    const tick = async () => {
      try {
        const query = new URLSearchParams({ after: watchAfter.current, currency: address.payCurrency });
        const response = await fetch(`/api/payments/topup?${query.toString()}`, { cache: "no-store" });
        if (!response.ok) return;
        const data = (await response.json()) as { credited?: boolean; deposit?: CreditedDeposit | null };
        if (!stopped && data.credited && data.deposit) setCredited(data.deposit);
      } catch {
        // A later tick or the five-minute reconciler will catch up.
      }
    };
    const id = window.setInterval(tick, POLL_MS);
    void tick();
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, [address, credited]);

  useEffect(() => {
    if (credited && refreshedPayment.current !== credited.payment_id) {
      refreshedPayment.current = credited.payment_id;
      router.refresh();
    }
  }, [credited, router]);

  const watchForAnother = useCallback(() => {
    watchAfter.current = new Date().toISOString();
    setCredited(null);
  }, []);

  if (!available) {
    return (
      <div className="p-5">
        <Callout tone="neutral" icon={<Mail className="h-4 w-4" strokeWidth={1.75} />}>
          Crypto deposits are temporarily unavailable. Email us at{" "}
          <a className="underline" href={`mailto:${supportEmail}`}>{supportEmail}</a> and we will help you.
        </Callout>
      </div>
    );
  }

  return (
    <div className="space-y-5 p-5">
      <NewToCrypto label={selectedCurrency?.label ?? currency} />

      {/* --- Suma ------------------------------------------------------------- */}
      <div>
        <div className="mb-2.5 flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
            How much to top up
          </span>
          {bonusPct > 0 && (
            <span className="rounded-full border border-[var(--app-border-strong)] px-2 py-0.5 text-[10.5px] font-semibold text-[var(--app-text-2)]">
              +{bonusPct}% bonus coins
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex h-12 flex-1 items-center rounded-lg border border-[var(--app-border)] px-3.5 transition-colors focus-within:border-[var(--app-border-strong)]">
            <span className="text-[19px] text-[var(--app-text-3)]">$</span>
            <input
              aria-label="Suma v USD"
              type="number"
              inputMode="decimal"
              min={CUSTOM_MIN_USD}
              max={CUSTOM_MAX_USD}
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              className="h-full min-w-0 flex-1 bg-transparent px-2 text-[19px] font-semibold tabular-nums text-[var(--app-text)] outline-none"
            />
          </div>
          <div className="flex items-center gap-1.5">
            {QUICK_AMOUNTS.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setAmount(String(value))}
                className={cn(
                  "app-tap h-12 rounded-lg border px-3.5 text-[13px] font-medium tabular-nums transition-colors",
                  usd === value
                    ? "border-[var(--app-text-4)] bg-[var(--app-surface-hover)] text-[var(--app-text)]"
                    : "border-[var(--app-border)] text-[var(--app-text-2)] hover:border-[var(--app-border-strong)] hover:text-[var(--app-text)]",
                )}
              >
                ${value}
              </button>
            ))}
          </div>
        </div>
        {!amountValid && (
          <p className="mt-2 text-[12px] text-[var(--app-text-4)]">
            Enter ${CUSTOM_MIN_USD}–${CUSTOM_MAX_USD.toLocaleString("en-US")}.
          </p>
        )}
      </div>

      {/* --- Mena ------------------------------------------------------------- */}
      <div>
        <span className="mb-2.5 block text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
          Pay with
        </span>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Cryptocurrency">
          {currencies.map((item) => {
            const active = item.cid === currency;
            const badge = cryptoMeta(item.cid);
            return (
              <button
                key={item.cid}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => selectCurrency(item.cid)}
                style={active ? { borderColor: badge.color } : undefined}
                className={cn(
                  "app-tap flex items-center gap-2.5 rounded-lg border p-2.5 text-left transition-all",
                  active
                    ? "bg-[var(--app-surface-hover)]"
                    : "border-[var(--app-border)] hover:border-[var(--app-border-strong)]",
                )}
              >
                <CoinBadge cid={item.cid} />
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium text-[var(--app-text)]">
                    {item.label}
                  </span>
                  <span className="block truncate text-[10.5px] text-[var(--app-text-4)]">
                    {item.network}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <Callout tone="danger" icon={<TriangleAlert className="h-4 w-4" strokeWidth={1.75} />}>
          {error}
        </Callout>
      )}

      {/* --- CTA / platba ----------------------------------------------------- */}
      {!address ? (
        <button
          type="button"
          onClick={loadAddress}
          disabled={loading || !amountValid}
          className={cn("app-btn app-btn-primary h-12 w-full px-5 text-[14px]", (loading || !amountValid) && "opacity-60")}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden />
          ) : (
            <CoinBadge cid={currency} size={22} />
          )}
          Pay with {selectedCurrency?.label ?? currency}
          {sendAmount && <span className="opacity-70">· send ≈ {sendAmount}</span>}
        </button>
      ) : (
        <div className="billing-reveal rounded-xl border border-[var(--app-border)] bg-[var(--app-surface-hover)]/30">
          {/* Hlavička s mincou a možnosťou zmeny */}
          <div className="flex items-center justify-between gap-3 border-b border-[var(--app-border)] px-4 py-3">
            <span className="flex items-center gap-2.5">
              <CoinBadge cid={address.payCurrency} size={26} />
              <span>
                <span className="block text-[13px] font-semibold text-[var(--app-text)]">
                  Send {selectedCurrency?.label ?? address.payCurrency}
                </span>
                <span className="block text-[10.5px] text-[var(--app-text-4)]">
                  {selectedCurrency?.network ?? address.payCurrency} network · address never expires
                </span>
              </span>
            </span>
            <button
              type="button"
              onClick={() => setAddress(null)}
              className="app-tap text-[12px] text-[var(--app-text-3)] underline underline-offset-4 hover:text-[var(--app-text)]"
            >
              Change
            </button>
          </div>

          <div className="grid gap-5 p-4 md:grid-cols-[200px_minmax(0,1fr)]">
            {/* QR */}
            <div className="mx-auto w-[200px]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={address.qrCode}
                alt={`QR pre ${address.payCurrency} adresu`}
                width={200}
                height={200}
                className="w-full rounded-xl border border-[var(--app-border)] bg-white p-2"
              />
              <p className="mt-2 flex items-center justify-center gap-1.5 text-center text-[11px] text-[var(--app-text-4)]">
                <ScanLine className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                Open Send in your wallet and scan
              </p>
            </div>

            {/* Suma na poslanie = hrdina + adresa */}
            <div className="flex min-w-0 flex-col gap-3">
              <div
                className="rounded-lg border p-4"
                style={{ borderColor: `${meta.color}55`, background: `${meta.color}0f` }}
              >
                <p className="text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
                  Send about
                </p>
                <p className="mt-1 flex items-baseline gap-2">
                  <span className="text-[26px] font-bold leading-none tabular-nums text-[var(--app-text)]">
                    {sendAmount ?? "—"}
                  </span>
                  <span className="text-[15px] font-semibold" style={{ color: meta.color }}>
                    {meta.ticker}
                  </span>
                </p>
                <p className="mt-1.5 text-[11.5px] text-[var(--app-text-3)]">
                  for ${usd} · you get{" "}
                  <strong className="text-[var(--app-text)]">{expectedCoins.toLocaleString("en-US")}</strong> coins
                  {bonusPct > 0 ? ` (+${bonusPct}%)` : ""}
                </p>
              </div>

              <div className="rounded-lg border border-[var(--app-border)] p-3">
                <p className="text-[10.5px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">Address</p>
                <div className="mt-1.5 flex items-start gap-2">
                  <p className="min-w-0 flex-1 break-all font-mono text-[12.5px] leading-relaxed text-[var(--app-text)]">
                    {address.payAddress}
                  </p>
                  <CopyButton value={address.payAddress} label="Copy address" />
                </div>
              </div>
            </div>
          </div>

          {/* Stav + drobný návod */}
          <div className="space-y-3 border-t border-[var(--app-border)] px-4 py-3.5">
            {credited ? (
              <Callout tone="success" icon={<CircleCheck className="h-4 w-4" strokeWidth={1.75} />}>
                <strong>Payment received.</strong> We credited{" "}
                {Number(credited.coins).toLocaleString("en-US")} Pipe Coins from ${Number(credited.source_usd).toFixed(2)}
                {Number(credited.bonus_pct) > 0 ? ` (+${Number(credited.bonus_pct)}%).` : "."}{" "}
                <button type="button" onClick={watchForAnother} className="underline">Watch for another</button>
              </Callout>
            ) : (
              <p className="flex items-center gap-2 text-[12.5px] text-[var(--app-text-3)]">
                <Loader2 className="h-4 w-4 shrink-0 animate-spin" strokeWidth={1.75} aria-hidden />
                Waiting for your payment. Coins are added automatically — you can close this page.
              </p>
            )}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-[var(--app-text-4)]">
              <span className="flex items-center gap-1.5">
                <TriangleAlert className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                Send only {meta.ticker} on the {selectedCurrency?.network} network.
              </span>
              <a href={CARD_ONRAMP_URL} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 underline hover:text-[var(--app-text-2)]">
                No crypto? Buy with card
                <ExternalLink className="h-3 w-3" strokeWidth={1.75} aria-hidden />
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
