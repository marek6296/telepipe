import type { Metadata } from "next";
import { Bot } from "lucide-react";

import { HeartbeatBadge } from "@/components/app/admin/badges";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, EmptyState, PageHeader, StatTile, StatusBadge } from "@/components/app/ui";
import { listAdminModels, requireAdmin } from "@/lib/admin";
import { shortId } from "@/lib/admin-ui";
import { compactNumber, usdPrecise } from "@/lib/format";
import { statusReasonText } from "@/lib/status";

export const metadata: Metadata = {
  title: "Models",
};

export default async function AdminModelsPage() {
  await requireAdmin();
  const models = await listAdminModels();

  const active = models.filter((model) => model.status === "active").length;
  const claimed = models.filter((model) => model.claimedBy).length;
  const msgsToday = models.reduce((sum, model) => sum + model.msgsToday, 0);
  const spendToday = models.reduce((sum, model) => sum + model.spendToday, 0);

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        title="Models"
        description="Every bot on the platform with the worker that runs it. Metadata only — conversations stay private to the client."
      />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Models" value={compactNumber(models.length)} hint={`${active} active`} />
        <StatTile label="Claimed" value={compactNumber(claimed)} hint="held by a worker" />
        <StatTile label="Messages today" value={compactNumber(msgsToday)} />
        <StatTile label="Spend today" value={usdPrecise(spendToday)} hint="charged" />
      </div>

      {models.length === 0 ? (
        <EmptyState
          icon={<Bot className="h-6 w-6" />}
          title="No models yet"
          description="Once a client adds their first model it shows up here with its worker and heartbeat."
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[58rem] text-left text-[13px]">
              <thead>
                <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-[0.12em] text-white/30">
                  <th className="px-5 py-2.5 font-medium">Model</th>
                  <th className="px-5 py-2.5 font-medium">Account</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                  <th className="px-5 py-2.5 font-medium">Heartbeat</th>
                  <th className="px-5 py-2.5 font-medium">Worker</th>
                  <th className="px-5 py-2.5 font-medium">Msgs today</th>
                  <th className="px-5 py-2.5 text-right font-medium">Spend today</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {models.map((model) => {
                  const reason = statusReasonText(model.statusReason);
                  return (
                    <tr key={model.id} className="transition-colors hover:bg-white/[0.02]">
                      <td className="px-5 py-3">
                        <p className="truncate text-white/85" title={model.id}>
                          {model.name || "Untitled model"}
                        </p>
                        {reason && (
                          <p className="mt-0.5 max-w-[18rem] truncate text-[11.5px] text-white/25">
                            {reason}
                          </p>
                        )}
                      </td>
                      <td className="px-5 py-3">
                        <span className="truncate text-white/55" title={model.accountId}>
                          {model.accountEmail || "—"}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <StatusBadge status={model.status} />
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <HeartbeatBadge iso={model.heartbeatAt} />
                          <span className="text-[11.5px] text-white/25">
                            <RelativeTime iso={model.heartbeatAt} />
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        <span
                          title={model.claimedBy ?? "not claimed"}
                          className="font-mono text-[12px] text-white/45"
                        >
                          {shortId(model.claimedBy)}
                        </span>
                      </td>
                      <td className="px-5 py-3 tabular-nums text-white/70">
                        {compactNumber(model.msgsToday)}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums text-white/70">
                        {usdPrecise(model.spendToday)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <p className="mt-6 px-1 text-[11.5px] leading-relaxed text-white/25">
        Heartbeat is live under 90 seconds, stale under 10 minutes, dead after that. An active
        model without a heartbeat means no worker picked it up.
      </p>
    </>
  );
}
