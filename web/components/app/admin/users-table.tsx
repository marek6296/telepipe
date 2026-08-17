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
      toast.success(`${row.email} is now on ${PLAN_LABEL[plan]}.`);
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
      toast.success(
        `${amount > 0 ? "Added" : "Removed"} ${usdPrecise(Math.abs(amount))} — ${
          row.email
        } now has ${usd(result.balance ?? 0)}.`,
      );
    });
  };

  return (
    <>
      <div className="relative mb-4 max-w-sm">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-white/25" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by email or id"
          aria-label="Search accounts"
          className="glass-input py-2.5! pl-10! text-[13px]!"
        />
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[54rem] text-left text-[13px]">
            <thead>
              <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-[0.12em] text-white/30">
                <th className="px-5 py-2.5 font-medium">Account</th>
                <th className="px-5 py-2.5 font-medium">Models</th>
                <th className="px-5 py-2.5 font-medium">Spend 30d</th>
                <th className="px-5 py-2.5 font-medium">Credit</th>
                <th className="px-5 py-2.5 font-medium">Plan</th>
                {viewerRole === "superadmin" && (
                  <th className="px-5 py-2.5 font-medium">Role</th>
                )}
                <th className="px-5 py-2.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {rows.map((row) => {
                const busy = pendingId === row.id;
                return (
                  <tr
                    key={row.id}
                    className={cn(
                      "transition-colors hover:bg-white/[0.02]",
                      busy && "opacity-60",
                    )}
                  >
                    <td className="px-5 py-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-white/85" title={row.id}>
                          {row.email || "—"}
                        </span>
                        {row.id === viewerId && (
                          <span className="shrink-0 rounded-full border border-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-white/35">
                            You
                          </span>
                        )}
                        {viewerRole !== "superadmin" && <RoleBadge role={row.role} />}
                      </div>
                      <p className="mt-0.5 text-[11.5px] text-white/25">
                        joined <RelativeTime iso={row.createdAt} />
                      </p>
                    </td>
                    <td className="px-5 py-3 tabular-nums text-white/70">
                      {compactNumber(row.modelsCount)}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-white/70">
                      {usdPrecise(row.spend30d)}
                    </td>
                    <td className="px-5 py-3 tabular-nums font-medium text-[var(--gold-light)]">
                      {usd(row.creditBalance)}
                    </td>
                    <td className="px-5 py-3">
                      <AdminSelect
                        label={`Plan for ${row.email}`}
                        value={row.plan}
                        disabled={busy}
                        onChange={(value) => changePlan(row, value as Plan)}
                        options={PLANS.map((plan) => ({
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
                        className="btn-modern-dark h-8 px-3 text-[12px]"
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
                    className="px-5 py-10 text-center text-[13px] text-white/35"
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
            ? `${creditFor.email} — balance ${usd(creditFor.creditBalance)}. Negative amounts subtract.`
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
              className="btn-modern-light h-11 flex-1 text-[13.5px]"
            >
              Yes, make {ROLE_LABEL[roleChange.next]}
            </button>
            <button
              type="button"
              onClick={() => setRoleChange(null)}
              className="btn-modern-dark h-11 px-5 text-[13.5px]"
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
      className="glass-input w-auto! cursor-pointer appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 fill=%22none%22 stroke=%22%23d4af37%22 stroke-width=%222%22><path d=%22M2 4l4 4 4-4%22/></svg>')] bg-[length:10px] bg-[right_0.7rem_center] bg-no-repeat py-1.5! pl-3! pr-8! text-[12.5px]! disabled:opacity-50"
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
          className="mb-2 block text-[12.5px] font-medium tracking-tight text-white/60"
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
          className="glass-input"
        />
      </div>
      <div>
        <label
          htmlFor="credit-note"
          className="mb-2 block text-[12.5px] font-medium tracking-tight text-white/60"
        >
          Note
        </label>
        <input
          id="credit-note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={200}
          placeholder="e.g. bank transfer #1042"
          className="glass-input"
        />
        <p className="mt-2 text-[11.5px] text-white/30">
          Stored with your name in the credit ledger.
        </p>
      </div>
      <button type="submit" disabled={!valid} className="btn-modern-light h-11 w-full text-[14px]">
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
            className="absolute inset-0 bg-black/75 backdrop-blur-sm"
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
            className="glass-panel relative w-full max-w-[26rem] rounded-3xl p-7"
          >
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="absolute right-4 top-4 rounded-full p-1.5 text-white/35 transition-colors hover:text-[var(--gold-light)]"
            >
              <X className="h-4 w-4" />
            </button>
            <h2 className="text-[19px] font-semibold tracking-tight text-white">{title}</h2>
            {description && (
              <p className="mt-1.5 text-[13px] leading-relaxed text-white/45">{description}</p>
            )}
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
