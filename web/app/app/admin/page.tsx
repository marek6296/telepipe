import type { Metadata } from "next";
import {
  Activity,
  Bot,
  Server,
  Signal,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";

import { ReplicaBadge } from "@/components/app/admin/badges";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, CardHeader, PageHeader, StatTile } from "@/components/app/ui";
import {
  adminUsageSummary,
  listAdminAccounts,
  listAdminModels,
  listAdminReplicas,
  requireAdmin,
} from "@/lib/admin";
import { shortId } from "@/lib/admin-ui";
import { compactNumber, usd, usdPrecise } from "@/lib/format";

export const metadata: Metadata = {
  title: "Overview",
};

const WINDOW_DAYS = 30;

export default async function AdminOverviewPage() {
  await requireAdmin();

  const [accounts, models, replicas, usage] = await Promise.all([
    listAdminAccounts(),
    listAdminModels(),
    listAdminReplicas(),
    adminUsageSummary(WINDOW_DAYS),
  ]);

  const activeModels = models.filter((model) => model.status === "active").length;
  const creditsTotal = accounts.reduce((sum, account) => sum + account.creditBalance, 0);
  // „Live bots" = tenanti, ktorých práve drží replika s čerstvým heartbeatom.
  const liveBots = replicas
    .filter((replica) => !replica.stale)
    .reduce((sum, replica) => sum + replica.tenantCount, 0);
  const liveReplicas = replicas.filter((replica) => !replica.stale).length;

  const spendToday = models.reduce((sum, model) => sum + model.spendToday, 0);
  const charged30 = usage.reduce((sum, day) => sum + day.charged, 0);
  const atlas30 = usage.reduce((sum, day) => sum + day.atlasCost, 0);
  const margin30 = usage.reduce((sum, day) => sum + day.margin, 0);
  const marginPct = charged30 > 0 ? Math.round((margin30 / charged30) * 100) : 0;

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        title="Overview"
        description="Everything running on Telepipe right now — accounts, bots, workers and what the platform earns."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Users"
          value={compactNumber(accounts.length)}
          hint={`${accounts.filter((account) => account.modelsCount > 0).length} with models`}
          icon={<Users className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile
          label="Active models"
          value={compactNumber(activeModels)}
          hint={`${models.length} total`}
          icon={<Bot className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile
          label="Live bots"
          value={compactNumber(liveBots)}
          hint={`${liveReplicas} of ${replicas.length} replicas live`}
          icon={<Signal className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile
          label="Credits"
          value={usd(creditsTotal)}
          hint="outstanding balance"
          icon={<Wallet className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Spend today"
          value={usdPrecise(spendToday)}
          hint="charged, since midnight UTC"
          icon={<Activity className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile label="Charged 30d" value={usdPrecise(charged30)} hint="what clients paid" />
        <StatTile label="Atlas cost 30d" value={usdPrecise(atlas30)} hint="what we paid" />
        <StatTile
          label="Margin 30d"
          value={usdPrecise(margin30)}
          hint={`${marginPct}% of charged`}
          icon={<TrendingUp className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
      </div>

      <div className="mt-5">
        <Card>
          <CardHeader
            icon={<Server className="h-4 w-4" />}
            title="Worker replicas"
            description="Each replica claims a slice of the active models and beats every 30 seconds. Stale means no heartbeat for over 2 minutes."
          />

          {replicas.length === 0 ? (
            <p className="px-5 py-8 text-center text-[13px] text-white/35">
              No replica has reported in yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[36rem] text-left text-[13px]">
                <thead>
                  <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-[0.12em] text-white/30">
                    <th className="px-5 py-2.5 font-medium">Replica</th>
                    <th className="px-5 py-2.5 font-medium">Bots</th>
                    <th className="px-5 py-2.5 font-medium">Last seen</th>
                    <th className="px-5 py-2.5 font-medium">Started</th>
                    <th className="px-5 py-2.5 text-right font-medium">State</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {replicas.map((replica) => (
                    <tr key={replica.name} className="transition-colors hover:bg-white/[0.02]">
                      <td className="px-5 py-3">
                        <span
                          title={replica.name}
                          className="font-mono text-[12px] text-white/70"
                        >
                          {shortId(replica.name)}
                        </span>
                      </td>
                      <td className="px-5 py-3 tabular-nums text-white/70">
                        {replica.tenantCount}
                      </td>
                      <td className="px-5 py-3 text-white/45">
                        <RelativeTime iso={replica.lastSeen} />
                      </td>
                      <td className="px-5 py-3 text-white/45">
                        <RelativeTime iso={replica.startedAt} />
                      </td>
                      <td className="px-5 py-3 text-right">
                        <ReplicaBadge stale={replica.stale} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <p className="mt-6 px-1 text-[11.5px] leading-relaxed text-white/25">
        Numbers come straight from the database through admin-only functions — nothing here is
        cached, refresh to re-read.
      </p>
    </>
  );
}
