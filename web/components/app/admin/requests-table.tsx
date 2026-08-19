"use client";

import { useState, useTransition } from "react";

import { decideRequestAction } from "@/app/app/admin/requests/actions";
import { useToast } from "@/components/app/admin/toast";
import type { AdminAccessRequest } from "@/lib/access-admin";

const STATUS_STYLE: Record<AdminAccessRequest["status"], string> = {
  pending: "border-[rgba(250,204,21,0.26)] text-[#fde047]",
  approved: "border-[rgba(74,222,128,0.28)] text-[#86efac]",
  rejected: "border-[#3f3f46] text-[#a1a1aa]",
};

export function RequestsTable({ rows }: { rows: AdminAccessRequest[] }) {
  const toast = useToast();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  function decide(row: AdminAccessRequest, approve: boolean) {
    setPendingId(row.id);
    startTransition(async () => {
      const result = await decideRequestAction(row.id, approve, "");
      setPendingId(null);
      if (result.error) toast.error(result.error);
      else if (result.status === "approved") toast.success(`${row.email} approved`);
      else toast.success(`${row.email} rejected`);
    });
  }

  if (rows.length === 0) {
    return (
      <p className="py-10 text-center text-[13.5px] text-[var(--app-text-3)]">
        No access requests yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-[var(--app-border)] text-left text-[var(--app-text-4)]">
            <th className="py-2 pr-4 font-normal">Account</th>
            <th className="py-2 pr-4 font-normal">Message</th>
            <th className="py-2 pr-4 font-normal">Status</th>
            <th className="py-2 pr-4 font-normal">Requested</th>
            <th className="py-2 font-normal" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const busy = pendingId === row.id;
            return (
              <tr key={row.id} className="border-b border-[var(--app-border)] align-top">
                <td className="py-3 pr-4">
                  <div className="text-[var(--app-text)]">{row.email}</div>
                  <div className="text-[12px] text-[var(--app-text-4)]">{row.plan}</div>
                </td>
                <td className="max-w-sm py-3 pr-4 text-[var(--app-text-2)]">
                  {row.message || "—"}
                </td>
                <td className="py-3 pr-4">
                  <span
                    className={`inline-flex rounded border px-2 py-0.5 text-[11.5px] ${STATUS_STYLE[row.status]}`}
                  >
                    {row.status}
                  </span>
                </td>
                <td className="py-3 pr-4 text-[var(--app-text-3)]">
                  {new Date(row.createdAt).toLocaleDateString()}
                </td>
                <td className="py-3">
                  {row.status === "pending" && (
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => decide(row, true)}
                        className="app-btn app-btn-primary px-3! py-1.5! text-[12.5px]!"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => decide(row, false)}
                        className="app-btn app-btn-ghost px-3! py-1.5! text-[12.5px]!"
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
