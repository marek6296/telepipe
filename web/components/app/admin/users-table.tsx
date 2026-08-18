"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Search, Wallet, X } from "lucide-react";

import {
  addCreditAction,
  setPlanAction,
  setRoleAction,
} from "@/app/app/admin/users/actions";
import { RoleBadge } from "@/components/app/admin/badges";
import { useToast } from "@/components/app/admin/toast";
import { RelativeTime } from "@/components/app/relative-time";
import { Card } from "@/components/app/ui";
import {
  PLANS,
  PLAN_LABEL,
  ROLES,
  ROLE_LABEL,
  type AccountRole,
  type Plan,
} from "@/lib/admin-ui";
import { COINS_PER_USD, coins, coinsLabel } from "@/lib/coins";
import { compactNumber, usd, usdPrecise } from "@/lib/format";
import { cn } from "@/lib/utils";

export type UserRow = {
  id: string;
  email: string;
  role: AccountRole;
  plan: Plan;
  creditBalance: number;
  createdAt: string;
  modelsCount: number;
  spend30d: number;
};

type Override = { plan?: Plan; role?: AccountRole; balance?: number };

/**
 * Tabuľka účtov s admin akciami. Optimistický stav držíme len ako prekryv nad
 * serverovými dátami — po `revalidatePath` sa props dorovnajú a prekryv sedí.
 */
export function UsersTable({
  accounts,
  viewerRole,
  viewerId,
}: {
  accounts: UserRow[];
  /** Rolu určil server (layout + page guard) — klient si ju nikdy nevymyslí. */
  viewerRole: "admin" | "superadmin";
  viewerId: string;
}) {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [overrides, setOverrides] = useState<Record<string, Override>>({});
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const [creditFor, setCreditFor] = useState<UserRow | null>(null);
  const [roleChange, setRoleChange] = useState<{ row: UserRow; next: AccountRole } | null>(
    null,
  );

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return accounts
      .map((account) => ({ ...account, ...overrides[account.id] }))
      .filter(
        (account) =>
          !needle ||
          account.email.toLowerCase().includes(needle) ||
          account.id.toLowerCase().includes(needle),
      );
  }, [accounts, overrides, query]);

  const patch = (id: string, value: Override) =>
    setOverrides((current) => ({ ...current, [id]: { ...current[id], ...value } }));

  const changePlan = (row: UserRow, plan: Plan) => {
    const previous = row.plan;
    patch(row.id, { plan });
    setPendingId(row.id);
    startTransition(async () => {
      const result = await setPlanAction(row.id, plan);
      setPendingId(null);
      if (result.error) {
        patch(row.id, { plan: previous });
        toast.error(result.error);
        return;
      }
      toast.success(
        plan === "vip"
          ? `${row.email} is now VIP — billed at cost, no margin.`
          : `${row.email} is now on ${PLAN_LABEL[plan]}.`,
      );
    });
  };

  const changeRole = (row: UserRow, next: AccountRole) => {
    const previous = row.role;
    patch(row.id, { role: next });
    setPendingId(row.id);
    setRoleChange(null);
    startTransition(async () => {
      const result = await setRoleAction(row.id, next);
      setPendingId(null);
      if (result.error) {
        patch(row.id, { role: previous });
        toast.error(result.error);
        return;
      }
      toast.success(`${row.email} is now ${ROLE_LABEL[next]}.`);
    });
  };

  const addCredit = (row: UserRow, amount: number, note: string) => {
    setPendingId(row.id);
    setCreditFor(null);
    startTransition(async () => {
      const result = await addCreditAction(row.id, amount, note);
      setPendingId(null);
      if (result.error) {
        toast.error(result.error);
        return;
      }
      patch(row.id, { balance: result.balance });
      // Suma sa zadáva v dolároch (tak beží `admin_add_credit` aj ledger úprav),
      // zostatok hlásime v coinoch — v tých ho klient uvidí.
      toast.success(
        `${amount > 0 ? "Added" : "Removed"} ${usdPrecise(Math.abs(amount))} — ${
          row.email
        } now has ${coinsLabel(result.balance ?? 0)}.`,
      );
    });
  };

  return (
    <>
      <div className="relative mb-4 max-w-sm">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-text-4)]" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by email or id"
          aria-label="Search accounts"
          className="app-input pl-9! text-[13px]!"
        />
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[54rem] text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--app-border)] text-[11px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
                <th className="px-5 py-2.5 font-medium">Account</th>
                <th className="px-5 py-2.5 font-medium">Models</th>
                {/* Spend je NAŠA tržba (USD), Coins je to, čo drží klient. */}
                <th className="px-5 py-2.5 font-medium">Spend 30d</th>
                <th className="px-5 py-2.5 font-medium">Pipe Coins</th>
                <th className="px-5 py-2.5 font-medium">Plan</th>
                {viewerRole === "superadmin" && (
                  <th className="px-5 py-2.5 font-medium">Role</th>
                )}
                <th className="px-5 py-2.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--app-border)]">
              {rows.map((row) => {
                const busy = pendingId === row.id;
                return (
                  <tr
                    key={row.id}
                    className={cn(
                      "transition-colors hover:bg-[var(--app-surface-hover)]",
                      busy && "opacity-60",
                    )}
                  >
                    <td className="px-5 py-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-[var(--app-text)]" title={row.id}>
                          {row.email || "—"}
                        </span>
                        {row.id === viewerId && (
                          <span className="shrink-0 rounded-full border border-[var(--app-border)] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-[var(--app-text-4)]">
                            You
                          </span>
                        )}
                        {viewerRole !== "superadmin" && <RoleBadge role={row.role} />}
                      </div>
                      <p className="mt-0.5 text-[11.5px] text-[var(--app-text-4)]">
                        joined <RelativeTime iso={row.createdAt} />
                      </p>
                    </td>
                    <td className="px-5 py-3 tabular-nums text-[var(--app-text-2)]">
                      {compactNumber(row.modelsCount)}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-[var(--app-text-2)]">
                      {usdPrecise(row.spend30d)}
                    </td>
                    <td
                      title={usd(row.creditBalance)}
                      className="px-5 py-3 tabular-nums font-medium text-[var(--app-text)]"
                    >
                      {coins(row.creditBalance)}
                    </td>
                    <td className="px-5 py-3">
                      <AdminSelect
                        label={`Plan for ${row.email}`}
                        value={row.plan}
                        disabled={busy}
                        onChange={(value) => changePlan(row, value as Plan)}
                        /* VIP ponúkame len superadminovi — obyčajnému adminovi
                           by ho aj tak odmietla akcia aj RPC, tak nech ho
                           nevidí. Účtu, ktorý VIP UŽ má, ho do zoznamu
                           doplníme, inak by select nemal čo zobraziť. */
                        options={(viewerRole === "superadmin"
                          ? PLANS
                          : PLANS.filter((plan) => plan !== "vip" || row.plan === "vip")
                        ).map((plan) => ({
                          value: plan,
                          label: PLAN_LABEL[plan],
                        }))}
                      />
                    </td>
                    {viewerRole === "superadmin" && (
                      <td className="px-5 py-3">
                        <AdminSelect
                          label={`Role for ${row.email}`}
                          value={row.role}
                          disabled={busy}
                          onChange={(value) =>
                            setRoleChange({ row, next: value as AccountRole })
                          }
                          options={ROLES.map((role) => ({
                            value: role,
                            label: ROLE_LABEL[role],
                          }))}
                        />
                      </td>
                    )}
                    <td className="px-5 py-3 text-right">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setCreditFor(row)}
                        className="app-btn app-btn-ghost h-8 px-3 text-[12px]"
                      >
                        {busy ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Wallet className="h-3.5 w-3.5" />
                        )}
                        Credit
                      </button>
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td
                    colSpan={viewerRole === "superadmin" ? 7 : 6}
                    className="px-5 py-10 text-center text-[13px] text-[var(--app-text-4)]"
                  >
                    No account matches “{query}”.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* --- Kredit ---------------------------------------------------------- */}
      <Modal
        open={Boolean(creditFor)}
        onClose={() => setCreditFor(null)}
        title="Add credit"
        description={
          creditFor
            ? `${creditFor.email} — balance ${coinsLabel(creditFor.creditBalance)}. ` +
              `Amounts are in dollars ($1 = ${COINS_PER_USD.toLocaleString("en-US")} Pipe Coins). ` +
              "Negative amounts subtract."
            : ""
        }
      >
        {creditFor && (
          <CreditForm
            key={creditFor.id}
            onSubmit={(amount, note) => addCredit(creditFor, amount, note)}
          />
        )}
      </Modal>

      {/* --- Potvrdenie zmeny roly -------------------------------------------- */}
      <Modal
        open={Boolean(roleChange)}
        onClose={() => setRoleChange(null)}
        title="Change role"
        description={
          roleChange
            ? `${roleChange.row.email} becomes ${ROLE_LABEL[roleChange.next]}. ${
                roleChange.next === "user"
                  ? "They lose access to the admin section immediately."
                  : "They get access to every account, model and credit balance."
              }`
            : ""
        }
      >
        {roleChange && (
          <div className="mt-6 flex gap-2.5">
            <button
              type="button"
              onClick={() => changeRole(roleChange.row, roleChange.next)}
              className="app-btn app-btn-primary h-9 flex-1"
            >
              Yes, make {ROLE_LABEL[roleChange.next]}
            </button>
            <button
              type="button"
              onClick={() => setRoleChange(null)}
              className="app-btn app-btn-ghost h-9 px-4"
            >
              Cancel
            </button>
          </div>
        )}
      </Modal>
    </>
  );
}

/* -------------------------------------------------------------------------- */

function AdminSelect({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className="app-input app-select w-auto! py-1.5! pl-3! text-[12.5px]! disabled:opacity-50"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value} className="bg-[#0d0d0d]">
          {option.label}
        </option>
      ))}
    </select>
  );
}

/** Suma + poznámka. Poznámka ide do `credit_adjustments` — audit stopa. */
function CreditForm({
  onSubmit,
}: {
  onSubmit: (amount: number, note: string) => void;
}) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const parsed = Number.parseFloat(amount.replace(",", "."));
  const valid = Number.isFinite(parsed) && parsed !== 0;

  return (
    <form
      className="mt-6 space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (valid) onSubmit(parsed, note.trim());
      }}
    >
      <div>
        <label
          htmlFor="credit-amount"
          className="mb-2 block text-[12.5px] font-medium tracking-tight text-[var(--app-text-2)]"
        >
          Amount (USD)
        </label>
        <input
          id="credit-amount"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          inputMode="decimal"
          autoFocus
          placeholder="50"
          className="app-input"
        />
        {/* Dolár je jednotka RPC aj ledgeru; coiny sú to, čo klient uvidí. */}
        <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
          {valid
            ? `${parsed > 0 ? "Adds" : "Removes"} ${coinsLabel(Math.abs(parsed))}.`
            : `$1 = ${COINS_PER_USD.toLocaleString("en-US")} Pipe Coins.`}
        </p>
      </div>
      <div>
        <label
          htmlFor="credit-note"
          className="mb-2 block text-[12.5px] font-medium tracking-tight text-[var(--app-text-2)]"
        >
          Note
        </label>
        <input
          id="credit-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={200}
          placeholder="e.g. bank transfer #1042"
          className="app-input"
        />
        <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
          Stored with your name in the credit ledger.
        </p>
      </div>
      <button type="submit" disabled={!valid} className="app-btn app-btn-primary h-10 w-full">
        Apply
      </button>
    </form>
  );
}

/** Dialóg v štýle `AddModelDialog` — backdrop, escape, spring. */
function Modal({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/70"
          />
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="app-panel relative w-full max-w-[24rem] p-6"
          >
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="app-tap absolute right-3 top-3 rounded-md p-1.5 text-[var(--app-text-4)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
            >
              <X className="h-4 w-4" />
            </button>
            <h2 className="text-[19px] font-semibold tracking-tight text-white">{title}</h2>
            {description && (
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--app-text-3)]">{description}</p>
            )}
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
