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
import { HelpGuideButton, WelcomeDialog } from "@/components/app/onboarding/guide";
import { ResetStatsButton } from "@/components/app/reset-stats-button";
import { Card, CardHeader, EmptyState, PageHeader, StatTile } from "@/components/app/ui";
import { COINS_PER_USD, coinsPrecise, toCoins } from "@/lib/coins";
import { compactNumber, toNumber } from "@/lib/format";
import { modelTypeHasTab } from "@/lib/model-types";
import { getAccount, getModelStats, getPausedMap, listModels, type ModelRow } from "@/lib/models";
import { getAppConfig } from "@/lib/slots";
import { getConnectedMap } from "@/lib/telegram";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Dashboard",
};

/* --------------------------------------------------------------------------
   Rozsah pohľadu. „Today" kreslí grafy po hodinách, zvyšok po dňoch — deň
   rozsekaný na jediný stĺpec nie je graf, a mesiac po hodinách je 720 stĺpcov.
-------------------------------------------------------------------------- */

type Range = { key: string; label: string; days: number; hint: string };

const RANGES: Range[] = [
  { key: "1", label: "Today", days: 1, hint: "since midnight UTC" },
  { key: "7", label: "7 days", days: 7, hint: "last 7 days" },
  { key: "30", label: "30 days", days: 30, hint: "last 30 days" },
];

const DEFAULT_RANGE = RANGES[1];

function pickRange(value: unknown): Range {
  return RANGES.find((range) => range.key === value) ?? DEFAULT_RANGE;
}

export default async function DashboardPage({ searchParams }: PageProps<"/app">) {
  const query = await searchParams;
  const range = pickRange(typeof query?.range === "string" ? query.range : undefined);

  const [account, models, config] = await Promise.all([
    getAccount(),
    listModels(),
    getAppConfig(),
  ]);
  const startCoins = Math.round(config.signup_credit_usd * COINS_PER_USD);
  // Hranica z „Reset stats" (027). Klient ňou vynuluje SVOJE prehľady; riadky
  // v `usage_events` ostávajú a admin ich vidí ďalej.
  const baseline = account?.stats_since ? new Date(account.stats_since).getTime() : null;

  const modelIds = models.map((model) => model.id);
  // Dopyty bežia paralelne, ale nová route sa vymení až ako hotový celok.
  // Používateľ tak zostáva na starej obrazovke namiesto prebliknutia skeletonov.
  const [stats, connected, paused, events] = await Promise.all([
    getModelStats(modelIds),
    getConnectedMap(models),
    getPausedMap(modelIds),
    recentUsage(range.days * 2, baseline),
  ]);

  /*
   * Uvítanie visí na JEDINEJ otázke: má už niektorá modelka prihlásený
   * Telegram?
   *
   * Kým nie, okno vyskočí pri každom príchode na dashboard — je to prvá vec,
   * bez ktorej appka nerobí vôbec nič, takže pripomenúť ju je užitočnejšie než
   * decentné. Len čo je čo i len jedna prihlásená, prestane navždy.
   *
   * Zamknutý účet sa sem nedostane (`app/app/layout.tsx` ho posiela na
   * `/locked`), takže nový človek pred schválením okno nevidí — dostane ho až
   * po odomknutí.
   *
   * Počítajú sa len modelky, ktoré Telegram vôbec MAJÚ. Dnes je to každá, ale
   * Fanvue-only agent by inak dostal nápovedu, ktorú nemá kde splniť.
   */
  const telegramCapable = models.filter((model) =>
    modelTypeHasTab(model.model_type, "telegram"),
  );
  const showWelcome = !telegramCapable.some((model) => connected[model.id]);

  return (
    <>
      <WelcomeDialog show={showWelcome} startCoins={startCoins} />

      <PageHeader
        title="Dashboard"
        description="Everything your models did while you were away."
        actions={
          <>
            {/* Kým nemá prihlásený Telegram, je návod užitočnejší než prehľad
                spotreby — vtedy stojí na jeho mieste. Rovnaká podmienka ako
                uvítanie, aby si tlačidlo a okno neodporovali. */}
            {showWelcome ? (
              <HelpGuideButton startCoins={startCoins} className="h-9 px-3.5" />
            ) : (
              <Link href="/app/usage" className="app-btn app-btn-ghost h-9 px-3.5">
                View usage
              </Link>
            )}
            {models.length > 0 && <AddModelDialog className="h-9 px-3.5" />}
          </>
        }
      />

      {/* --- Rozsah + reset --------------------------------------------------- */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {RANGES.map((option) => (
            <RangeChip
              key={option.key}
              href={option.key === DEFAULT_RANGE.key ? "/app" : `/app?range=${option.key}`}
              active={option.key === range.key}
            >
              {option.label}
            </RangeChip>
          ))}
        </div>
        <ResetStatsButton since={account?.stats_since ?? null} />
      </div>

      <DashboardStats models={models} range={range} stats={stats} events={events} />
      <DashboardCharts models={models} range={range} events={events} />
      <DashboardModels models={models} stats={stats} connected={connected} paused={paused} />
    </>
  );
}

function DashboardStats({
  models,
  range,
  stats,
  events,
}: {
  models: ModelRow[];
  range: Range;
  stats: Awaited<ReturnType<typeof getModelStats>>;
  events: UsageRow[];
}) {
  const totalChats = models.reduce((sum, model) => sum + (stats[model.id]?.chats ?? 0), 0);
  const totalConverted = models.reduce(
    (sum, model) => sum + (stats[model.id]?.converted ?? 0),
    0,
  );
  const spendThis = sumCharged(events, 0, range.days);
  const spendPrev = sumCharged(events, range.days, range.days * 2);
  const repliesThis = countKind(events, "chat", 0, range.days);
  const repliesPrev = countKind(events, "chat", range.days, range.days * 2);

  return (
    <div className="grid grid-cols-1 gap-3 min-[460px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
      <StatTile
        label="Replies sent"
        value={compactNumber(repliesThis)}
        delta={percentDelta(repliesThis, repliesPrev)}
        hint={`messages she wrote, ${range.hint}`}
      />
      <StatTile
        label="Conversations"
        value={compactNumber(totalChats)}
        hint="fans she is talking to"
      />
      <StatTile
        label="Converted"
        value={compactNumber(totalConverted)}
        hint={conversionHint(totalConverted, totalChats)}
      />
      <StatTile
        label="Pipe Coins spent"
        value={coinsPrecise(spendThis)}
        delta={percentDelta(spendThis, spendPrev)}
        hint={range.hint}
      />
    </div>
  );
}

function DashboardCharts({
  models,
  range,
  events,
}: {
  models: ModelRow[];
  range: Range;
  events: UsageRow[];
}) {
  const buckets = bucketsFor(range);
  const spendSeries = dailySpend(events, buckets);
  const { data: messageSeries, series } = dailyMessagesByModel(events, models, buckets);

  return (
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader title="Usage spend" description={`Pipe Coins spent, ${range.hint}`} />
        <SpendChart data={spendSeries} />
      </Card>
      <Card>
        <CardHeader title="Messages by model" description={`Replies sent, ${range.hint}`} />
        {series.length === 0 ? (
          <p className="px-5 py-[92px] text-center text-[12.5px] text-[var(--app-text-4)]">
            No replies in this period.
          </p>
        ) : (
          <MessagesChart data={messageSeries} series={series} />
        )}
      </Card>
    </div>
  );
}

function DashboardModels({
  models,
  stats,
  connected,
  paused,
}: {
  models: ModelRow[];
  stats: Awaited<ReturnType<typeof getModelStats>>;
  connected: Awaited<ReturnType<typeof getConnectedMap>>;
  paused: Awaited<ReturnType<typeof getPausedMap>>;
}) {
  if (models.length === 0) {
    return (
      <div className="mt-10">
        <EmptyState
          icon={<Bot className="h-[18px] w-[18px]" strokeWidth={1.5} />}
          title="No models yet"
          description="Add your first model, connect her Telegram account, and she starts replying to fans within 30 seconds."
          action={<AddModelDialog label="Add your first model" className="h-9 px-4" />}
        />
      </div>
    );
  }

  return (
    <div className="mt-10">
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
    </div>
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

/**
 * `baseline` je hranica z „Reset stats" — filtruje sa v dopyte, nie až v UI,
 * nech sa vynulované obdobie ani neprenáša po sieti.
 */
async function recentUsage(days: number, baseline: number | null): Promise<UsageRow[]> {
  const supabase = await createClient();
  const windowFrom = windowStart(days);
  const from = baseline === null ? windowFrom : Math.max(windowFrom, baseline);

  const { data } = await supabase
    .from("usage_events")
    .select("model_id, kind, charged_usd, created_at")
    .gte("created_at", new Date(from).toISOString())
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

/* --------------------------------------------------------------------------
   Koše grafov. Kľúč je predpona ISO reťazca, takže sa riadok zaradí bez
   parsovania dátumu: `2026-08-18` pre deň, `2026-08-18T05` pre hodinu.
-------------------------------------------------------------------------- */

type Bucket = { key: string; label: string };

function bucketsFor(range: Range): Bucket[] {
  return range.days === 1 ? hourBuckets() : dayBuckets(range.days);
}

/** Dnešok po hodinách (UTC), od polnoci po aktuálnu hodinu. */
function hourBuckets(): Bucket[] {
  const now = new Date();
  const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Array.from({ length: now.getUTCHours() + 1 }, (_, index) => {
    const date = new Date(midnight + index * 3_600_000);
    return {
      key: date.toISOString().slice(0, 13),
      label: `${String(date.getUTCHours()).padStart(2, "0")}:00`,
    };
  });
}

/** Posledných `days` dní ako popisky `12 Aug`. */
function dayBuckets(days: number): Bucket[] {
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

/** Do ktorého koša riadok patrí — dĺžka kľúča rozhodne, či deň či hodina. */
function bucketKey(iso: string, width: number): string {
  return iso.slice(0, width);
}

/** Ledger je v USD, graf kreslí Pipe Coiny — prepočet je posledný krok. */
function dailySpend(rows: UsageRow[], buckets: Bucket[]): SpendPoint[] {
  const width = buckets[0]?.key.length ?? 10;
  const totals = new Map(buckets.map((bucket) => [bucket.key, 0]));
  for (const row of rows) {
    const key = bucketKey(row.created_at, width);
    if (totals.has(key)) totals.set(key, (totals.get(key) ?? 0) + toNumber(row.charged_usd));
  }
  return buckets.map((bucket) => ({
    label: bucket.label,
    value: Number(toCoins(totals.get(bucket.key) ?? 0).toFixed(1)),
  }));
}

/** Počty odpovedí po košoch pre max. 4 najaktívnejšie modelky. */
function dailyMessagesByModel(
  rows: UsageRow[],
  models: ModelRow[],
  buckets: Bucket[],
): { data: SeriesPoint[]; series: { key: string; label: string }[] } {
  const width = buckets[0]?.key.length ?? 10;
  const window = new Set(buckets.map((bucket) => bucket.key));
  const chats = rows.filter(
    (row) => row.kind === "chat" && window.has(bucketKey(row.created_at, width)),
  );

  const totals = new Map<string, number>();
  const counts = new Map<string, number>();
  for (const row of chats) {
    totals.set(row.model_id, (totals.get(row.model_id) ?? 0) + 1);
    const cell = `${bucketKey(row.created_at, width)}|${row.model_id}`;
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

  const data: SeriesPoint[] = buckets.map((bucket) => {
    const point: SeriesPoint = { label: bucket.label };
    for (const model of top) {
      point[model.id] = counts.get(`${bucket.key}|${model.id}`) ?? 0;
    }
    return point;
  });

  return { data, series };
}

function conversionHint(converted: number, conversations: number): string {
  if (conversations <= 0) return "no conversations yet";
  return `${((converted / conversations) * 100).toFixed(1)}% of conversations`;
}

function RangeChip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-full border px-3 py-1.5 text-[12px] transition-colors",
        active
          ? "border-[#3f3f46] bg-[#161616] text-[var(--app-text)]"
          : "border-[var(--app-border)] text-[var(--app-text-3)] hover:text-[var(--app-text)]",
      )}
    >
      {children}
    </Link>
  );
}
