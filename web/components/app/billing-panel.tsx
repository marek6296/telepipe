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
  InfinityIcon,
  Loader2,
  Mail,
  ScanLine,
  Send,
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
import { cn } from "@/lib/utils";

/**
 * Nákup Pipe Coinov cez permanentnú Plisio adresu: klient si zvolí sumu
 * (len odhad kreditu) a mincu, dostane SVOJU stálu adresu a pošle koľko chce.
 * Kredit počíta server z net USD hodnoty potvrdenej Plisiom — tento komponent
 * stav LEN zobrazuje, o kredite nikdy nerozhoduje.
 */

export type CurrencyOption = {
  cid: string;
  label: string;
  network: string;
};

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
const CARD_ONRAMP_URL = "https://guardarian.com/buy-crypto-with-card";

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

/** Číslovaný krokový label — drží obe polovice formulára vizuálne v jednej sade. */
function StepLabel({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-2 text-[12px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
      <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[10px] font-semibold leading-none text-[var(--app-text-2)]">
        {n}
      </span>
      {children}
    </p>
  );
}

/**
 * Sprievodca pre nováčika. Krypto vie väčšina klientov len z počutia — bez
 * tohto by pri QR kóde nevedeli, čo majú spraviť. `<details>` je natívny,
 * prístupný a nepotrebuje stav; kto krypto pozná, nechá ho zbalený.
 */
function NewToCrypto({ label }: { label: string }) {
  const wallets = [
    {
      icon: Smartphone,
      name: "Revolut",
      note: "Najjednoduchšie, ak ho už máš",
      how: "Karta → Krypto → kúp trochu (napr. USDT) → Poslať → vlož adresu nižšie.",
    },
    {
      icon: Wallet,
      name: "MetaMask",
      note: "Zadarmo, appka do mobilu za 5 minút",
      how: "Nainštaluj → v appke kúp krypto kartou → Send → vlož adresu nižšie.",
    },
    {
      icon: CreditCard,
      name: "Burza (Binance, Coinbase)",
      note: "Ak už niekde krypto máš",
      how: "Kúp krypto → Withdraw / Send → vlož adresu a vyber správnu sieť.",
    },
  ];

  return (
    <details className="group rounded-lg border border-[var(--app-border)] bg-[var(--app-surface-hover)]/40 open:bg-transparent">
      <summary className="app-tap flex cursor-pointer list-none items-center justify-between gap-3 p-4 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)]">
            <Wallet className="h-3.5 w-3.5 text-[var(--app-text-2)]" strokeWidth={1.75} aria-hidden />
          </span>
          <span>
            <span className="block text-[13px] font-medium text-[var(--app-text)]">
              Prvýkrát platíš kryptom? Zvládneš to za pár minút
            </span>
            <span className="block text-[11.5px] text-[var(--app-text-4)]">
              Ako si spraviť peňaženku a poslať platbu — krok za krokom
            </span>
          </span>
        </span>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-[var(--app-text-3)] transition-transform group-open:rotate-180"
          strokeWidth={1.75}
          aria-hidden
        />
      </summary>

      <div className="space-y-4 px-4 pb-4">
        <div>
          <p className="mb-2.5 text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
            1 · Kde krypto vezmeš
          </p>
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

        <div>
          <p className="mb-2.5 text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
            2 · Ako pošleš platbu
          </p>
          <ol className="space-y-2">
            {[
              { Icon: ScanLine, text: "V peňaženke daj Send / Poslať a naskenuj QR kód — alebo skopíruj adresu tlačidlom Copy." },
              { Icon: Wallet, text: `Vyber ${label} a správnu sieť (píše sa hneď pri adrese). Sieť musí sedieť, inak sa platba stratí.` },
              { Icon: Send, text: "Zadaj sumu a odošli. Coiny sa pripíšu samy, zvyčajne do pár minút — stránku môžeš zavrieť." },
            ].map(({ Icon, text }, index) => (
              <li key={index} className="flex items-start gap-2.5">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[10px] font-semibold text-[var(--app-text-2)]">
                  {index + 1}
                </span>
                <span className="flex items-center gap-2 text-[12.5px] leading-relaxed text-[var(--app-text-2)]">
                  <Icon className="hidden h-3.5 w-3.5 shrink-0 text-[var(--app-text-4)] sm:inline" strokeWidth={1.75} aria-hidden />
                  {text}
                </span>
              </li>
            ))}
          </ol>
        </div>

        <p className="rounded-md border border-[var(--app-border)] px-3 py-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
          Bez obáv: adresa je len tvoja a nikdy nevyprší. Keď sa pomýliš v sume, nič sa nedeje —
          coiny sa počítajú presne z toho, čo naozaj dorazí.
        </p>
      </div>
    </details>
  );
}

export function BillingPanel({
  currencies,
  available,
  supportEmail,
}: {
  currencies: CurrencyOption[];
  available: boolean;
  supportEmail: string;
}) {
  const router = useRouter();
  const [amount, setAmount] = useState("50");
  const [currency, setCurrency] = useState(currencies[0]?.cid ?? "BTC");
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
  const usd = Math.round((Number.parseFloat(amount) || 0) * 100) / 100;
  const amountValid = usd >= CUSTOM_MIN_USD && usd <= CUSTOM_MAX_USD;
  const expectedCoins = amountValid ? customCoinsForUsd(usd) : 0;
  const bonusPct = amountValid ? customBonusPct(usd) : 0;

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
        setError(String(data.error ?? "Could not load your permanent deposit address."));
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
        const query = new URLSearchParams({
          after: watchAfter.current,
          currency: address.payCurrency,
        });
        const response = await fetch(`/api/payments/topup?${query.toString()}`, {
          cache: "no-store",
        });
        if (!response.ok) return;
        const data = (await response.json()) as {
          credited?: boolean;
          deposit?: CreditedDeposit | null;
        };
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
          <a className="underline" href={`mailto:${supportEmail}`}>
            {supportEmail}
          </a>{" "}
          and we will help you.
        </Callout>
      </div>
    );
  }

  return (
    <div className="p-5">
      {/* Sprievodca pre nováčika — hore, aby ho videl skôr než začne. */}
      <div className="mb-4">
        <NewToCrypto label={selectedCurrency?.label ?? currency} />
      </div>

      {/* Krok 1 + 2 — dve rovnako široké polovice, rovnaká výška radu. */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col rounded-lg border border-[var(--app-border)] p-4">
          <div className="flex items-center justify-between gap-4">
            <StepLabel n={1}>Amount you plan to send</StepLabel>
            {bonusPct > 0 && (
              <span className="rounded-full border border-[var(--app-border)] px-2 py-0.5 text-[10.5px] font-semibold text-[var(--app-text-2)]">
                +{bonusPct}% coins
              </span>
            )}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-[20px] text-[var(--app-text-3)]">$</span>
            <input
              id="deposit-usd"
              aria-label="Amount in USD"
              type="number"
              inputMode="decimal"
              min={CUSTOM_MIN_USD}
              max={CUSTOM_MAX_USD}
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              className="h-11 min-w-0 flex-1 rounded-md border border-[var(--app-border)] bg-transparent px-3 text-[18px] font-semibold tabular-nums text-[var(--app-text)] outline-none transition-colors focus:border-[var(--app-border-strong)]"
            />
          </div>
          <p className="mt-3 text-[13px] text-[var(--app-text-2)]" aria-live="polite">
            {amountValid ? (
              <>
                Estimated credit:{" "}
                <strong className="tabular-nums text-[var(--app-text)]">
                  {expectedCoins.toLocaleString("en-US")} Pipe Coins
                </strong>
              </>
            ) : (
              `Enter $${CUSTOM_MIN_USD}–$${CUSTOM_MAX_USD.toLocaleString("en-US")}`
            )}
          </p>
          <p className="mt-auto pt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            +10% from $100 and +20% from $250. The final credit uses the net USD value that
            actually reaches the address after provider and network fees.
          </p>
        </div>

        <div className="flex flex-col rounded-lg border border-[var(--app-border)] p-4">
          <StepLabel n={2}>Deposit currency</StepLabel>
          <div
            className="mt-3 grid grid-cols-4 gap-2"
            role="radiogroup"
            aria-label="Cryptocurrency"
          >
            {currencies.map((item) => {
              const active = item.cid === currency;
              return (
                <button
                  key={item.cid}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => selectCurrency(item.cid)}
                  className={cn(
                    "app-tap w-full rounded-md border px-2 py-2 text-center text-[12.5px] transition-colors",
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
          {selectedCurrency && (
            <p className="mt-auto pt-3 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
              Network: <strong className="text-[var(--app-text-3)]">{selectedCurrency.network}</strong>.
              Send only {selectedCurrency.label} on this exact network.
            </p>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-4">
          <Callout tone="danger" icon={<TriangleAlert className="h-4 w-4" strokeWidth={1.75} />}>
            {error}
          </Callout>
        </div>
      )}

      {!address ? (
        <div className="mt-5 flex flex-col items-start gap-2.5">
          <button
            type="button"
            onClick={loadAddress}
            disabled={loading || !amountValid}
            className={cn(
              "app-btn app-btn-primary h-11 w-full px-5 sm:w-auto",
              (loading || !amountValid) && "opacity-70",
            )}
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} aria-hidden />}
            Show my permanent {selectedCurrency?.label ?? currency} address
          </button>
          <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            It is created once for your account and never expires. You can reuse it for every
            future top-up.
          </p>
        </div>
      ) : (
        <div className="mt-5 border-t border-[var(--app-border)] pt-5">
          {/* Krok 3 — hlavička sekcie s adresou. */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <StepLabel n={3}>
                Send to your permanent {selectedCurrency?.label ?? address.payCurrency} address
              </StepLabel>
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--app-border)] px-2 py-0.5 text-[10.5px] text-[var(--app-text-3)]">
                <InfinityIcon className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                No expiry
              </span>
            </div>
            <button
              type="button"
              onClick={() => setAddress(null)}
              className="app-tap text-[12px] text-[var(--app-text-3)] underline underline-offset-4 hover:text-[var(--app-text)]"
            >
              Choose another currency
            </button>
          </div>

          {/* QR vľavo v pevnom stĺpci, údaje vpravo — pod tým už len bloky na
              plnú šírku, aby sa pri žiadnej šírke nič nelámalo pod QR. */}
          <div className="mt-4 grid gap-5 md:grid-cols-[216px_minmax(0,1fr)]">
            <div className="mx-auto w-[216px]">
              {/* Data URI is generated on our server; the address is not sent to a public QR API. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={address.qrCode}
                alt={`QR code for the permanent ${address.payCurrency} deposit address`}
                width={216}
                height={216}
                className="w-full rounded-lg border border-[var(--app-border)] bg-white p-2"
              />
              <p className="mt-2 flex items-center justify-center gap-1.5 text-center text-[11px] text-[var(--app-text-4)]">
                <ScanLine className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                V peňaženke daj „Send“ a naskenuj
              </p>
            </div>

            <div className="flex min-w-0 flex-col gap-4">
              <div className="rounded-lg border border-[var(--app-border)] p-4">
                <p className="text-[12px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
                  Address · {selectedCurrency?.network ?? address.payCurrency}
                </p>
                <div className="mt-2.5 flex flex-wrap items-start gap-2.5">
                  <p className="min-w-0 flex-1 break-all font-mono text-[13px] leading-relaxed text-[var(--app-text)]">
                    {address.payAddress}
                  </p>
                  <CopyButton value={address.payAddress} label="Copy the permanent deposit address" />
                </div>
              </div>

              <div className="grid flex-1 gap-4 sm:grid-cols-2">
                <div className="flex flex-col justify-center rounded-lg border border-[var(--app-border)] px-4 py-3">
                  <p className="text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
                    Planned amount
                  </p>
                  <p className="mt-1.5 text-[20px] font-semibold leading-none tabular-nums text-[var(--app-text)]">
                    {amountValid ? `$${usd}` : "—"}
                  </p>
                </div>
                <div className="flex flex-col justify-center rounded-lg border border-[var(--app-border)] px-4 py-3">
                  <p className="text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
                    Estimated credit{bonusPct > 0 ? ` · +${bonusPct}%` : ""}
                  </p>
                  <p className="mt-1.5 text-[20px] font-semibold leading-none tabular-nums text-[var(--app-text)]">
                    {amountValid ? expectedCoins.toLocaleString("en-US") : "—"}
                    <span className="ml-1.5 text-[12px] font-normal text-[var(--app-text-3)]">
                      coins
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4">
            {credited ? (
              <Callout tone="success" icon={<CircleCheck className="h-4 w-4" strokeWidth={1.75} />}>
                <strong>Deposit confirmed.</strong>{" "}
                {Number(credited.coins).toLocaleString("en-US")} Pipe Coins were added from a net
                value of ${Number(credited.source_usd).toFixed(2)}
                {Number(credited.bonus_pct) > 0
                  ? `, including the +${Number(credited.bonus_pct)}% bonus.`
                  : "."}{" "}
                <button type="button" onClick={watchForAnother} className="underline">
                  Watch for another deposit
                </button>
              </Callout>
            ) : (
              <Callout tone="neutral" icon={<Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />}>
                Watching for a confirmed deposit. You may close this page — webhook and the
                automatic reconciler credit it even when you are offline.
              </Callout>
            )}
          </div>

          <div className="mt-4 rounded-lg border border-[var(--app-border)] p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-[13px] font-medium text-[var(--app-text)]">
                  <CreditCard className="h-4 w-4" strokeWidth={1.75} aria-hidden />
                  Nemáš žiadne krypto? Kúp ho kartou
                </p>
                <p className="mt-1 max-w-xl text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
                  Otvor Guardarian, vyber {address.payCurrency}, zadaj asi ${amountValid ? usd : 50} a
                  vlož adresu vyššie ako príjemcu. Dostupnosť karty, limity, poplatky a overenie
                  totožnosti závisia od providera a tvojej krajiny.
                </p>
              </div>
              <a
                href={CARD_ONRAMP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="app-btn app-btn-secondary h-9 shrink-0 px-3"
              >
                Buy with card
                <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              </a>
            </div>
          </div>

          <p className="mt-4 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            Never send another asset or use another network. A card on-ramp may deliver slightly
            less crypto than its fiat amount because of fees; Pipe Coins are always calculated
            from the net USD value confirmed by Plisio, so the balance stays exact.
          </p>
        </div>
      )}
    </div>
  );
}
