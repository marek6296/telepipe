import type { Metadata } from "next";
import { BarChart3, TrendingUp } from "lucide-react";

import { MarginChart } from "@/components/app/admin/margin-chart";
import { Card, CardHeader, PageHeader, StatTile } from "@/components/app/ui";
import { adminUsageSummary, requireAdmin } from "@/lib/admin";
import { compactNumber, usdPrecise } from "@/lib/format";

export const metadata: Metadata = {
  title: "Usage",
};

const WINDOW_DAYS = 30;

export default async function AdminUsagePage() {
  await requireAdmin();
  const days = await adminUsageSummary(WINDOW_DAYS);

  const charged = days.reduce((sum, day) => sum + day.charged, 0);
  const atlasCost = days.reduce((sum, day) => sum + day.atlasCost, 0);
  const margin = days.reduce((sum, day) => sum + day.margin, 0);
  const events = days.reduce((sum, day) => sum + day.events, 0);
  const marginPct = charged > 0 ? Math.round((margin / charged) * 100) : 0;
  const perEvent = events > 0 ? margin / events : 0;

  // Tabuľka od najnovšieho dňa; prázdne dni nezobrazujeme, len ich graf drží.
  const rows = [...days].reverse().filter((day) => day.events > 0);

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        title="Usage & margin"
        description="What clients were charged against what Atlas cost us, day by day."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Charged 30d"
          value={usdPrecise(charged)}
          hint="what clients paid"
          icon={<BarChart3 className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile label="Atlas cost 30d" value={usdPrecise(atlasCost)} hint="what we paid" />
        <StatTile
          label="Margin 30d"
          value={usdPrecise(margin)}
          hint={`${marginPct}% of charged`}
          icon={<TrendingUp className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile
          label="Events 30d"
          value={compactNumber(events)}
          hint={`${usdPrecise(perEvent)} margin each`}
        />
      </div>

      <div className="mt-5">
        <Card>
          <CardHeader
            icon={<BarChart3 className="h-4 w-4" />}
            title="Charged vs. cost"
            description={`Last ${WINDOW_DAYS} days. The dark base of each bar is what Atlas billed us — the gold above it is margin.`}
          />
          <MarginChart days={days} />
        </Card>
      </div>

      <div className="mt-4">
        <Card>
          <CardHeader title="Day by day" description="Only days with activity." />
          {rows.length === 0 ? (
            <p className="px-5 py-8 text-center text-[13px] text-white/35">
              Nothing was charged in the last {WINDOW_DAYS} days.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[38rem] text-left text-[13px]">
                <thead>
                  <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-[0.12em] text-white/30">
                    <th className="px-5 py-2.5 font-medium">Day</th>
                    <th className="px-5 py-2.5 font-medium">Events</th>
                    <th className="px-5 py-2.5 font-medium">Charged</th>
                    <th className="px-5 py-2.5 font-medium">Atlas cost</th>
                    <th className="px-5 py-2.5 text-right font-medium">Margin</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {rows.map((day) => (
                    <tr key={day.day} className="transition-colors hover:bg-white/[0.02]">
                      <td className="px-5 py-2.5 text-white/70">
                        {new Date(`${day.day}T00:00:00Z`).toLocaleDateString("en-US", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                          timeZone: "UTC",
                        })}
                      </td>
                      <td className="px-5 py-2.5 tabular-nums text-white/45">
                        {compactNumber(day.events)}
                      </td>
                      <td className="px-5 py-2.5 tabular-nums text-white/70">
                        {usdPrecise(day.charged)}
                      </td>
                      <td className="px-5 py-2.5 tabular-nums text-white/45">
                        {usdPrecise(day.atlasCost)}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums font-medium text-[var(--gold-light)]">
                        {usdPrecise(day.margin)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-white/[0.08] text-[12.5px] font-semibold">
                    <td className="px-5 py-3 text-white/60">Total</td>
                    <td className="px-5 py-3 tabular-nums text-white/60">
                      {compactNumber(events)}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-white/85">
                      {usdPrecise(charged)}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-white/60">
                      {usdPrecise(atlasCost)}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums text-[var(--gold-light)]">
                      {usdPrecise(margin)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
