import type { Metadata } from "next";
import Link from "next/link";
import { Bot } from "lucide-react";

import { AddModelDialog } from "@/components/app/add-model-dialog";
import {
  MessagesChart,
  SpendChart,
  type SeriesPoint,
  type SpendPoint,
} from "@/components/app/dashboard-charts";
import { ModelCard } from "@/components/app/model-card";
import { Card, CardHeader, EmptyState, PageHeader, StatTile } from "@/components/app/ui";
import { compactNumber, isoDaysAgo, toNumber, usdPrecise } from "@/lib/format";
import { getModelStats, getPausedMap, listModels, type ModelRow } from "@/lib/models";
import { getConnectedMap } from "@/lib/telegram";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Dashboard",
};

/** Okno grafov aj delty. Referencia: „last 7 days" + „vs last week". */
const WINDOW = 7;

export default async function DashboardPage() {
  const models = await listModels();
  const [stats, connected, paused, events] = await Promise.all([
    getModelStats(models.map((model) => model.id)),
    getConnectedMap(models),
    getPausedMap(models.map((model) => model.id)),
    recentUsage(WINDOW * 2),
  ]);

  const totalChats = models.reduce((sum, model) => sum + (stats[model.id]?.chats ?? 0), 0);
  const totalConverted = models.reduce(
    (sum, model) => sum + (stats[model.id]?.converted ?? 0),
    0,
  );

  // Delty počítame len z toho, čo v `usage_events` naozaj máme.
  const spendThis = sumCharged(events, 0, WINDOW);
  const spendPrev = sumCharged(events, WINDOW, WINDOW * 2);
  const repliesThis = countKind(events, "chat", 0, WINDOW);
  const repliesPrev = countKind(events, "chat", WINDOW, WINDOW * 2);

  const spendSeries = dailySpend(events, WINDOW);
  const { data: messageSeries, series } = dailyMessagesByModel(events, models, WINDOW);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Everything your models did while you were away."
        actions={
          <>
            <Link href="/app/usage" className="app-btn app-btn-ghost h-9 px-3.5">
              View usage
            </Link>
            {models.length > 0 && <AddModelDialog className="h-9 px-3.5" />}
          </>
        }
      />

      {/* --- Dlaždice --------------------------------------------------------- */}
      <div className="grid grid-cols-1 gap-3 min-[460px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
        <StatTile
          label="Replies sent"
          value={compactNumber(repliesThis)}
          delta={percentDelta(repliesThis, repliesPrev)}
          hint="last 7 days"
        />
        <StatTile
          label="Conversations"
          value={compactNumber(totalChats)}
          hint="all-time conversations"
        />
        <StatTile
          label="Converted"
          value={compactNumber(totalConverted)}
          hint={conversionHint(totalConverted, totalChats)}
        />
        <StatTile
          label="Usage spend"
          value={usdPrecise(spendThis)}
          delta={percentDelta(spendThis, spendPrev)}
          hint="last 7 days"
        />
      </div>

      {/* --- Grafy ------------------------------------------------------------ */}
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Usage spend" description="Daily charged, last 7 days" />
          <SpendChart data={spendSeries} />
        </Card>

        <Card>
          <CardHeader title="Messages by model" description="Replies sent, last 7 days" />
          {series.length === 0 ? (
            <p className="px-5 py-[92px] text-center text-[12.5px] text-[var(--app-text-4)]">
              No replies in the last 7 days.
            </p>
          ) : (
            <MessagesChart data={messageSeries} series={series} />
          )}
        </Card>
      </div>

      {/* --- Modelky ---------------------------------------------------------- */}
      <div className="mt-10">
        {models.length === 0 ? (
          <EmptyState
            icon={<Bot className="h-[18px] w-[18px]" strokeWidth={1.5} />}
            title="No models yet"
            description="Add your first model, connect her Telegram account, and she starts replying to fans within 30 seconds."
            action={<AddModelDialog label="Add your first model" className="h-9 px-4" />}
          />
        ) : (
          <>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="app-group-label">Your models</h2>
              <Link
                href="/app/models"
                className="text-[12.5px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
              >
                Manage all
              </Link>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              {models.map((model) => (
                <ModelCard
                  key={model.id}
                  model={model}
                  stats={stats[model.id] ?? { chats: 0, converted: 0, spentToday: 0 }}
                  connected={connected[model.id] ?? false}
                  aiPaused={paused[model.id] ?? false}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}

/* --------------------------------------------------------------------------
   Dáta pre dlaždice a grafy. Klient vidí VÝHRADNE `charged_usd` — nákupná
   cena (`atlas_cost_usd`) sa sem nesmie dostať, preto ju ani nevyberáme.
-------------------------------------------------------------------------- */

type UsageRow = {
  model_id: string;
  kind: string;
  charged_usd: number | string;
  created_at: string;
};

async function recentUsage(days: number): Promise<UsageRow[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("usage_events")
    .select("model_id, kind, charged_usd, created_at")
    .gte("created_at", isoDaysAgo(days))
    .limit(20000);

  return (data ?? []) as unknown as UsageRow[];
}

/** Polnoc UTC pred `daysAgo` dňami vrátane dneška (1 = dnešná polnoc). */
function windowStart(daysAgo: number): number {
  const now = new Date();
  const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return midnight - (daysAgo - 1) * 86_400_000;
}

/**
 * Okno `[toDaysAgo, fromDaysAgo)`: `fromDaysAgo = 0` znamená „až po teraz".
 * Zarovnané na polnoc UTC, nech sa tento a minulý týždeň neprekrývajú.
 */
function inRange(iso: string, fromDaysAgo: number, toDaysAgo: number): boolean {
  const ms = new Date(iso).getTime();
  if (!Number.isFinite(ms)) return false;
  const start = windowStart(toDaysAgo);
  const end = fromDaysAgo === 0 ? Date.now() + 1 : windowStart(fromDaysAgo);
  return ms >= start && ms < end;
}

function sumCharged(rows: UsageRow[], fromDaysAgo: number, toDaysAgo: number): number {
  return rows
    .filter((row) => inRange(row.created_at, fromDaysAgo, toDaysAgo))
    .reduce((sum, row) => sum + toNumber(row.charged_usd), 0);
}

function countKind(
  rows: UsageRow[],
  kind: string,
  fromDaysAgo: number,
  toDaysAgo: number,
): number {
  return rows.filter(
    (row) => row.kind === kind && inRange(row.created_at, fromDaysAgo, toDaysAgo),
  ).length;
}

function percentDelta(current: number, previous: number): number | null {
  if (previous <= 0) return null;
  return ((current - previous) / previous) * 100;
}

/** Posledných `days` dní ako popisky `12 Aug` — spoločná os oboch grafov. */
function dayKeys(days: number): { key: string; label: string }[] {
  const start = windowStart(days);
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(start + index * 86_400_000);
    return {
      key: date.toISOString().slice(0, 10),
      label: date.toLocaleDateString("en-US", {
        day: "numeric",
        month: "short",
        timeZone: "UTC",
      }),
    };
  });
}

function dailySpend(rows: UsageRow[], days: number): SpendPoint[] {
  const keys = dayKeys(days);
  const buckets = new Map(keys.map((day) => [day.key, 0]));
  for (const row of rows) {
    const key = row.created_at.slice(0, 10);
    if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + toNumber(row.charged_usd));
  }
  return keys.map((day) => ({
    label: day.label,
    value: Number((buckets.get(day.key) ?? 0).toFixed(4)),
  }));
}

/** Počty odpovedí po dňoch pre max. 4 najaktívnejšie modelky. */
function dailyMessagesByModel(
  rows: UsageRow[],
  models: ModelRow[],
  days: number,
): { data: SeriesPoint[]; series: { key: string; label: string }[] } {
  const keys = dayKeys(days);
  const window = new Set(keys.map((day) => day.key));
  const chats = rows.filter(
    (row) => row.kind === "chat" && window.has(row.created_at.slice(0, 10)),
  );

  const totals = new Map<string, number>();
  const counts = new Map<string, number>();
  for (const row of chats) {
    totals.set(row.model_id, (totals.get(row.model_id) ?? 0) + 1);
    const cell = `${row.created_at.slice(0, 10)}|${row.model_id}`;
    counts.set(cell, (counts.get(cell) ?? 0) + 1);
  }

  const top = models
    .filter((model) => (totals.get(model.id) ?? 0) > 0)
    .sort((a, b) => (totals.get(b.id) ?? 0) - (totals.get(a.id) ?? 0))
    .slice(0, 4);

  const series = top.map((model) => ({
    key: model.id,
    label: model.name || "Untitled model",
  }));

  const data: SeriesPoint[] = keys.map((day) => {
    const point: SeriesPoint = { label: day.label };
    for (const model of top) {
      point[model.id] = counts.get(`${day.key}|${model.id}`) ?? 0;
    }
    return point;
  });

  return { data, series };
}

function conversionHint(converted: number, conversations: number): string {
  if (conversations <= 0) return "no conversations yet";
  return `${((converted / conversations) * 100).toFixed(1)}% of conversations`;
}
