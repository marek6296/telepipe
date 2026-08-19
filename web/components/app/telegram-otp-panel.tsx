"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronRight,
  Clock3,
  Copy,
  LoaderCircle,
  MessageSquareText,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  Smartphone,
  X,
} from "lucide-react";

import {
  cancelTelegramOtpAction,
  completeTelegramOtpAction,
  purchaseTelegramOtpAction,
  refreshTelegramOtpAction,
  resendTelegramOtpAction,
  type OtpActionResult,
} from "@/app/app/virtual-sim/actions";
import { Callout, Card, CardHeader, PageHeader } from "@/components/app/ui";
import { COIN_NAME_PLURAL, coins } from "@/lib/coins";
import { dateTime } from "@/lib/format";
import type {
  TelegramOtpCountry,
  TelegramOtpOrder,
  TelegramOtpStatus,
} from "@/lib/vrnum";
import { cn } from "@/lib/utils";

const ACTIVE = new Set<TelegramOtpStatus>([
  "reserved",
  "provisioning",
  "waiting",
  "code_received",
]);

const STATUS: Record<TelegramOtpStatus, { label: string; dot: string }> = {
  reserved: { label: "Reserved", dot: "bg-sky-400" },
  provisioning: { label: "Provisioning", dot: "bg-sky-400" },
  waiting: { label: "Waiting for SMS", dot: "bg-amber-300" },
  code_received: { label: "Code received", dot: "bg-emerald-400" },
  completed: { label: "Completed", dot: "bg-emerald-400" },
  cancelled: { label: "Cancelled", dot: "bg-[var(--app-text-4)]" },
  expired: { label: "Expired", dot: "bg-[var(--app-text-4)]" },
  failed: { label: "Failed · refunded", dot: "bg-red-400" },
};

export function TelegramOtpPanel({
  countries,
  initialOrders,
  initialBalance,
  catalogError,
  service = "telegram",
  serviceName = "Telegram",
}: {
  countries: TelegramOtpCountry[];
  initialOrders: TelegramOtpOrder[];
  initialBalance: number;
  catalogError: string;
  /** Ktorú platformu klient overuje. Ide do nákupu a musí sedieť s katalógom. */
  service?: string;
  serviceName?: string;
}) {
  // Tri pokusy sú v cene (viď `OTP_ATTEMPTS_INCLUDED`). Klient to musí vidieť
  // PRED nákupom, nie až keď mu SMS nepríde.
  const attemptsLabel = "3 numbers included";

  const firstAvailable =
    countries.find(
      (country) => country.code === "usa" && country.available > 0,
    ) ??
    countries.find((country) => country.available > 0) ??
    null;
  const [selectedCode, setSelectedCode] = useState(firstAvailable?.code ?? "");
  const [query, setQuery] = useState("");
  const [orders, setOrders] = useState(initialOrders);
  const [balance, setBalance] = useState(initialBalance);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "success" | "danger" | "neutral";
    text: string;
  } | null>(null);
  const [pendingPurchaseKey, setPendingPurchaseKey] = useState<string | null>(
    null,
  );
  const [isPending, startTransition] = useTransition();
  const polling = useRef(false);
  const router = useRouter();

  const selected =
    countries.find((country) => country.code === selectedCode) ??
    firstAvailable;
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return countries;
    return countries.filter(
      (country) =>
        country.name.toLowerCase().includes(needle) ||
        country.code.includes(needle),
    );
  }, [countries, query]);
  const activeOrder = orders.find((order) => ACTIVE.has(order.status)) ?? null;
  const canBuy = Boolean(
    selected && selected.available > 0 && balance >= selected.priceCredits,
  );
  const activeOrderId = activeOrder?.id ?? null;
  const shouldPoll = Boolean(
    activeOrder && activeOrder.status !== "code_received",
  );

  const applyResult = useCallback((result: OtpActionResult, silent = false) => {
    if (result.order) {
      setOrders((current) => [
        result.order!,
        ...current.filter((item) => item.id !== result.order!.id),
      ]);
    }
    if (result.ok) {
      if (result.balance !== null) setBalance(result.balance);
      if (!silent && result.message)
        setNotice({ tone: "success", text: result.message });
      return;
    }
    if (!silent) setNotice({ tone: "danger", text: result.error });
  }, []);

  useEffect(() => {
    if (!activeOrderId || !shouldPoll) return;
    const timer = window.setInterval(() => {
      if (polling.current) return;
      polling.current = true;
      void refreshTelegramOtpAction(activeOrderId)
        .then((result) => applyResult(result, true))
        .finally(() => {
          polling.current = false;
        });
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [activeOrderId, applyResult, shouldPoll]);

  function buy() {
    if (!selected) return;
    const idempotencyKey = pendingPurchaseKey ?? crypto.randomUUID();
    setPendingPurchaseKey(idempotencyKey);
    setConfirming(false);
    setNotice(null);
    startTransition(async () => {
      const result = await purchaseTelegramOtpAction({
        countryCode: selected.code,
        idempotencyKey,
        service,
      });
      applyResult(result);
      if (result.ok) router.refresh();
      if (result.ok || !result.retryable) setPendingPurchaseKey(null);
    });
  }

  function run(action: () => Promise<OtpActionResult>, refreshLayout = false) {
    setNotice(null);
    startTransition(async () => {
      const result = await action();
      applyResult(result);
      if (result.ok && refreshLayout) router.refresh();
    });
  }

  return (
    <>
      <PageHeader
        eyebrow="Telegram OTP"
        title="Virtual SIM"
        description="A one-time Telegram number, delivered inside Telepipe. Choose a country, receive the SMS code, and finish registration before the activation window closes."
        actions={
          <div className="rounded-md border border-[var(--app-border)] px-3.5 py-2 text-right">
            <p className="text-[10px] uppercase tracking-[0.12em] text-[var(--app-text-4)]">
              Your balance
            </p>
            <p className="mt-1 text-[14px] font-medium tabular-nums text-[var(--app-text)]">
              {coins(balance)}{" "}
              <span className="text-[11px] font-normal text-[var(--app-text-4)]">
                {COIN_NAME_PLURAL}
              </span>
            </p>
          </div>
        }
      />

      {notice && (
        <div className="mb-4">
          <Callout tone={notice.tone}>{notice.text}</Callout>
        </div>
      )}

      {activeOrder && (
        <div className="mb-4">
          <ActiveOrder
            order={activeOrder}
            busy={isPending}
            onRefresh={() =>
              run(() => refreshTelegramOtpAction(activeOrder.id))
            }
            onResend={() => run(() => resendTelegramOtpAction(activeOrder.id))}
            onComplete={() =>
              run(() => completeTelegramOtpAction(activeOrder.id))
            }
            onCancel={() =>
              run(() => cancelTelegramOtpAction(activeOrder.id), true)
            }
          />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(310px,0.75fr)]">
        <Card>
          <CardHeader
            title="Choose a destination"
            description={`${countries.length} Telegram destinations in the live catalog. Sold-out routes remain visible.`}
            icon={<Smartphone className="h-4 w-4" strokeWidth={1.6} />}
          />
          <div className="p-5">
            {catalogError ? (
              <Callout tone="danger" icon={<RefreshCw className="h-4 w-4" />}>
                {catalogError} Reload this page to try again.
              </Callout>
            ) : (
              <>
                <label className="relative block">
                  <span className="sr-only">Search countries</span>
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-text-4)]" />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search all countries"
                    className="h-10 w-full rounded-md border border-[var(--app-border)] bg-[#090909] pl-9 pr-3 text-[13px] text-[var(--app-text)] outline-none transition-colors placeholder:text-[var(--app-text-4)] focus:border-[var(--app-border-strong)]"
                  />
                </label>

                <div className="mt-3 max-h-[352px] overflow-y-auto rounded-lg border border-[var(--app-border)]">
                  {filtered.map((country) => {
                    const soldOut = country.available <= 0;
                    const active = country.code === selected?.code;
                    return (
                      <button
                        key={country.code}
                        type="button"
                        disabled={soldOut}
                        onClick={() => setSelectedCode(country.code)}
                        className={cn(
                          "flex w-full items-center gap-3 border-b border-[var(--app-border)] px-3.5 py-3 text-left transition-colors last:border-b-0",
                          active
                            ? "bg-[var(--app-active)]"
                            : "hover:bg-[var(--app-surface-hover)]",
                          soldOut && "cursor-not-allowed opacity-40",
                        )}
                      >
                        <span
                          className="w-7 text-center text-[20px]"
                          aria-hidden="true"
                        >
                          {country.flag || "🌐"}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium text-[var(--app-text)]">
                            {country.name}
                          </span>
                          <span className="mt-0.5 block text-[11px] text-[var(--app-text-4)]">
                            {soldOut
                              ? "Temporarily sold out"
                              : `${country.available.toLocaleString("en-US")} available`}
                          </span>
                        </span>
                        <span className="text-right">
                          <span className="block text-[13px] font-medium tabular-nums text-[var(--app-text)]">
                            {coins(country.priceCredits)}
                          </span>
                          <span className="block text-[10px] text-[var(--app-text-4)]">
                            coins
                          </span>
                        </span>
                        {!soldOut &&
                          (active ? (
                            <Check className="h-4 w-4 text-[var(--app-text-2)]" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-[var(--app-text-4)]" />
                          ))}
                      </button>
                    );
                  })}
                  {filtered.length === 0 && (
                    <p className="px-4 py-12 text-center text-[12.5px] text-[var(--app-text-4)]">
                      No country matches “{query}”.
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        </Card>

        <Card className="h-fit xl:sticky xl:top-[76px]">
          <CardHeader
            title={`${serviceName} number`}
            description={`${attemptsLabel} · one activation · 20-minute window`}
            icon={<MessageSquareText className="h-4 w-4" strokeWidth={1.6} />}
          />
          <div className="p-5">
            <div className="flex items-center gap-3 rounded-lg border border-[var(--app-border)] bg-[#090909] p-4">
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#229ED9] text-white">
                <MessageSquareText className="h-5 w-5" strokeWidth={1.8} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13.5px] font-medium text-[var(--app-text)]">
                  Telegram
                </p>
                <p className="mt-0.5 truncate text-[12px] text-[var(--app-text-3)]">
                  {selected
                    ? `${selected.flag} ${selected.name}`
                    : "Choose a country"}
                </p>
              </div>
              <p className="text-right">
                <span className="block text-[17px] font-semibold tabular-nums text-[var(--app-text)]">
                  {selected ? coins(selected.priceCredits) : "—"}
                </span>
                <span className="text-[10px] text-[var(--app-text-4)]">
                  {COIN_NAME_PLURAL}
                </span>
              </p>
            </div>

            <ol className="my-5 space-y-3">
              <Step number="1" text="We reserve the displayed Pipe Coins." />
              <Step
                number="2"
                text="Your Telegram phone number appears here."
              />
              <Step
                number="3"
                text="The incoming OTP code is shown automatically."
              />
            </ol>

            <button
              type="button"
              disabled={!canBuy || isPending || Boolean(activeOrder)}
              onClick={() => setConfirming(true)}
              className="app-btn app-btn-primary h-10 w-full justify-center disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isPending && <LoaderCircle className="h-4 w-4 animate-spin" />}
              {activeOrder
                ? "Finish your active number first"
                : pendingPurchaseKey
                  ? "Retry safe purchase"
                  : `Buy ${serviceName} number`}
            </button>
            {selected && balance < selected.priceCredits && (
              <p className="mt-2.5 text-center text-[11.5px] text-[#fca5a5]">
                You need {coins(selected.priceCredits - balance)} more{" "}
                {COIN_NAME_PLURAL} to continue.
              </p>
            )}
            <div className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-[var(--app-text-4)]">
              <ShieldCheck className="mt-px h-3.5 w-3.5 shrink-0" />
              <p>
                Prices are locked server-side. A confirmed cancellation returns
                the full displayed coin charge exactly once.
              </p>
            </div>
          </div>
        </Card>
      </div>

      {orders.length > 0 && <OrderHistory orders={orders} />}

      {confirming && selected && (
        <ConfirmPurchase
          serviceName={serviceName}
          country={selected}
          balance={balance}
          onClose={() => setConfirming(false)}
          onConfirm={buy}
        />
      )}
    </>
  );
}

function ActiveOrder({
  order,
  busy,
  onRefresh,
  onResend,
  onComplete,
  onCancel,
}: {
  order: TelegramOtpOrder;
  busy: boolean;
  onRefresh: () => void;
  onResend: () => void;
  onComplete: () => void;
  onCancel: () => void;
}) {
  const [now, setNow] = useState(0);
  const [copied, setCopied] = useState<"phone" | "code" | null>(null);
  useEffect(() => {
    const immediate = window.setTimeout(() => setNow(Date.now()), 0);
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      window.clearTimeout(immediate);
      window.clearInterval(timer);
    };
  }, []);
  const remaining =
    order.expiresAt && now
      ? Math.max(0, new Date(order.expiresAt).getTime() - now)
      : 0;

  function copy(value: string, kind: "phone" | "code") {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(kind);
      window.setTimeout(() => setCopied(null), 1_600);
    });
  }

  return (
    <Card className="overflow-hidden border-[var(--app-border-strong)]">
      <div className="flex flex-col gap-5 p-5 lg:flex-row lg:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3.5">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[var(--app-border)] bg-[#090909] text-xl">
            {order.countryFlag || "🌐"}
          </span>
          <div className="min-w-0">
            <StatusLine status={order.status} />
            <p className="mt-1 text-[11.5px] text-[var(--app-text-4)]">
              Telegram · {order.countryName} · {coins(order.chargedCredits)}{" "}
              coins
            </p>
          </div>
        </div>

        <ValueBlock
          label="Phone number"
          value={order.phoneNumber ?? "Assigning…"}
          onCopy={
            order.phoneNumber
              ? () => copy(order.phoneNumber!, "phone")
              : undefined
          }
          copied={copied === "phone"}
        />
        <ValueBlock
          label="Telegram code"
          value={order.otpCode ?? "Waiting for SMS"}
          strong={Boolean(order.otpCode)}
          onCopy={
            order.otpCode ? () => copy(order.otpCode!, "code") : undefined
          }
          copied={copied === "code"}
        />

        <div className="min-w-[116px] text-left lg:text-right">
          <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
            Time remaining
          </p>
          <p className="mt-1.5 flex items-center gap-1.5 text-[13px] tabular-nums text-[var(--app-text-2)] lg:justify-end">
            <Clock3 className="h-3.5 w-3.5" />
            {formatRemaining(remaining)}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-[var(--app-border)] bg-[#090909] px-5 py-3">
        <button
          type="button"
          disabled={busy}
          onClick={onRefresh}
          className="app-btn app-btn-ghost h-8 px-3"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} />{" "}
          Refresh
        </button>
        <button
          type="button"
          disabled={busy || !order.phoneNumber}
          onClick={onResend}
          className="app-btn app-btn-ghost h-8 px-3 disabled:opacity-40"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Resend SMS
        </button>
        {order.otpCode && (
          <button
            type="button"
            disabled={busy}
            onClick={onComplete}
            className="app-btn app-btn-primary h-8 px-3"
          >
            <Check className="h-3.5 w-3.5" /> Done
          </button>
        )}
        <button
          type="button"
          disabled={busy || !order.phoneNumber}
          onClick={onCancel}
          className="app-btn app-btn-ghost ml-auto h-8 px-3 text-[#fca5a5] disabled:opacity-40"
        >
          Cancel & refund
        </button>
      </div>
    </Card>
  );
}

function ValueBlock({
  label,
  value,
  strong,
  onCopy,
  copied,
}: {
  label: string;
  value: string;
  strong?: boolean;
  onCopy?: () => void;
  copied: boolean;
}) {
  return (
    <div className="min-w-[190px] rounded-md border border-[var(--app-border)] bg-[#080808] px-3 py-2.5">
      <p className="text-[9.5px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
        {label}
      </p>
      <div className="mt-1.5 flex items-center gap-2">
        <p
          className={cn(
            "min-w-0 flex-1 truncate text-[13px] tabular-nums text-[var(--app-text-2)]",
            strong &&
              "text-[17px] font-semibold tracking-[0.08em] text-[var(--app-text)]",
          )}
        >
          {value}
        </p>
        {onCopy && (
          <button
            type="button"
            onClick={onCopy}
            aria-label={`Copy ${label}`}
            className="text-[var(--app-text-4)] transition-colors hover:text-[var(--app-text)]"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}

function OrderHistory({ orders }: { orders: TelegramOtpOrder[] }) {
  return (
    <Card className="mt-8 overflow-hidden">
      <CardHeader
        title="Recent numbers"
        description="Your last 30 Telegram OTP purchases and refunds."
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] text-left text-[12.5px]">
          <thead>
            <tr className="border-b border-[var(--app-border)] text-[10px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
              <th className="px-5 py-3 font-medium">Destination</th>
              <th className="px-5 py-3 font-medium">Number</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 text-right font-medium">Coins</th>
              <th className="px-5 py-3 text-right font-medium">Created</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr
                key={order.id}
                className="border-b border-[var(--app-border)] last:border-b-0"
              >
                <td className="px-5 py-3.5 text-[var(--app-text-2)]">
                  {order.countryFlag} {order.countryName}
                </td>
                <td className="px-5 py-3.5 tabular-nums text-[var(--app-text-3)]">
                  {order.phoneNumber ?? "—"}
                </td>
                <td className="px-5 py-3.5">
                  <StatusLine status={order.status} />
                </td>
                <td className="px-5 py-3.5 text-right tabular-nums text-[var(--app-text-2)]">
                  {order.refundedCredits > 0
                    ? `${coins(order.refundedCredits)} refunded`
                    : coins(order.chargedCredits)}
                </td>
                <td className="px-5 py-3.5 text-right text-[var(--app-text-4)]">
                  {dateTime(order.createdAt)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ConfirmPurchase({
  serviceName,
  country,
  balance,
  onClose,
  onConfirm,
}: {
  serviceName: string;
  country: TelegramOtpCountry;
  balance: number;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[80] flex items-end justify-center bg-black/75 p-0 backdrop-blur-sm sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="otp-confirm-title"
    >
      <div className="w-full max-w-md rounded-t-xl border border-[var(--app-border-strong)] bg-[var(--app-bg)] p-5 shadow-2xl sm:rounded-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="app-group-label">Confirm purchase</p>
            <h2
              id="otp-confirm-title"
              className="mt-2 text-[18px] font-semibold text-[var(--app-text)]"
            >
              {country.flag} {serviceName} number · {country.name}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close confirmation"
            className="rounded-md p-1.5 text-[var(--app-text-4)] hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="my-5 divide-y divide-[var(--app-border)] rounded-lg border border-[var(--app-border)] bg-[#090909] px-4">
          <SummaryRow
            label={`${serviceName} number`}
            value={`${coins(country.priceCredits)} coins`}
          />
          <SummaryRow
            label="Current balance"
            value={`${coins(balance)} coins`}
          />
          <SummaryRow
            label="Balance after purchase"
            value={`${coins(balance - country.priceCredits)} coins`}
            strong
          />
        </div>
        <Callout icon={<Clock3 className="h-4 w-4" />}>
          Start Telegram registration immediately. The activation is intended
          for one SMS and expires after roughly 20 minutes.
        </Callout>
        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="app-btn app-btn-ghost h-10 flex-1 justify-center"
          >
            Back
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="app-btn app-btn-primary h-10 flex-1 justify-center"
          >
            Confirm & buy
          </button>
        </div>
      </div>
    </div>
  );
}

function SummaryRow({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 text-[12.5px]">
      <span className="text-[var(--app-text-3)]">{label}</span>
      <span
        className={cn(
          "tabular-nums text-[var(--app-text-2)]",
          strong && "font-medium text-[var(--app-text)]",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function Step({ number, text }: { number: string; text: string }) {
  return (
    <li className="flex items-start gap-3 text-[12px] leading-relaxed text-[var(--app-text-3)]">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--app-border)] text-[9px] tabular-nums text-[var(--app-text-4)]">
        {number}
      </span>
      {text}
    </li>
  );
}

function StatusLine({ status }: { status: TelegramOtpStatus }) {
  const value = STATUS[status];
  return (
    <span className="inline-flex items-center gap-2 text-[12.5px] font-medium text-[var(--app-text-2)]">
      <span className={cn("h-1.5 w-1.5 rounded-full", value.dot)} />
      {value.label}
    </span>
  );
}

function formatRemaining(milliseconds: number): string {
  if (milliseconds <= 0) return "00:00";
  const seconds = Math.ceil(milliseconds / 1_000);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
