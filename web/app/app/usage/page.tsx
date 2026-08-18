import type { Metadata } from "next";
import Link from "next/link";
import { BarChart3 } from "lucide-react";

import { RelativeTime } from "@/components/app/relative-time";
import { UsageChart } from "@/components/app/usage-chart";
import { Card, CardHeader, EmptyState, PageHeader, StatTile } from "@/components/app/ui";
import { coins, coinsPrecise, COIN_NAME_PLURAL } from "@/lib/coins";
import { compactNumber, isoDaysAgo, toNumber } from "@/lib/format";
import { getAccount, listModels } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import {
  byKind,
  dailyTotals,
  KIND_COLOR,
  KIND_HINT,
  KIND_LABEL,
  sumSince,
  USAGE_COLUMNS,
  type UsageEvent,
} from "@/lib/usage";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Usage",
};

const WINDOW_DAYS = 30;

export default async function UsagePage({ searchParams }: PageProps<"/app/usage">) {
  const query = await searchParams;
  const selected = typeof query?.model === "string" ? query.model : "";

  const [account, models] = await Promise.all([getAccount(), listModels()]);
  const modelName = new Map(models.map((model) => [model.id, model.name || "Untitled"]));

  const supabase = await createClient();
  const since = isoDaysAgo(WINDOW_DAYS);

  let request = supabase
    .from("usage_events")
    .select(USAGE_COLUMNS)
    .gte("created_at", since)
    .order("created_at", { ascending: false })
    .limit(5000);

  if (selected) request = request.eq("model_id", selected);

  const { data } = await request;
  const events = (data ?? []) as unknown as UsageEvent[];

  const days = dailyTotals(events, WINDOW_DAYS);
  const kinds = byKind(events);
  const total30 = sumSince(events, 30);
  const total7 = sumSince(events, 7);
  const total1 = sumSince(events, 1);
  const balance = toNumber(account?.credit_balance_usd);
  const kindMax = Math.max(...kinds.map((kind) => kind.total), 0.0001);

  return (
    <>
      <PageHeader
        eyebrow={COIN_NAME_PLURAL}
        title="Usage"
        description="What your agents spend, day by day, in Pipe Coins. The price already includes everything — there is no separate model bill."
      />

      {/* --- Filter modelky --------------------------------------------------- */}
      {models.length > 1 && (
        <div className="mb-6 flex flex-wrap gap-1.5">
          <FilterChip href="/app/usage" active={!selected}>
            All models
          </FilterChip>
          {models.map((model) => (
            <FilterChip
              key={model.id}
              href={`/app/usage?model=${model.id}`}
              active={selected === model.id}
            >
              {model.name || "Untitled"}
            </FilterChip>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 min-[460px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
        <StatTile label="Balance" value={coins(balance)} hint="Pipe Coins left" />
        <StatTile label="Today" value={coinsPrecise(total1)} hint="spent since midnight UTC" />
        <StatTile label="Last 7 days" value={coinsPrecise(total7)} hint="Pipe Coins spent" />
        <StatTile label="Last 30 days" value={coinsPrecise(total30)} hint="Pipe Coins spent" />
      </div>

      {events.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            icon={<BarChart3 className="h-[18px] w-[18px]" strokeWidth={1.5} />}
            title="Nothing spent yet"
            description="Once your agents start replying, every reply, summary and voice note shows up here with what it cost in Pipe Coins."
          />
        </div>
      ) : (
        <>
          <div className="mt-4">
            <Card>
              <CardHeader
                title="Daily spend"
                description={`Pipe Coins, last ${WINDOW_DAYS} days${
                  selected ? ` · ${modelName.get(selected) ?? "model"}` : ""
                }`}
              />
              <UsageChart days={days} />
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader
                title="Where it goes"
                description="Pipe Coins split by what she was doing."
              />
              <ul className="space-y-4 p-5">
                {kinds.map((kind) => (
                  <li key={kind.kind}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[13px] text-[var(--app-text-2)]">
                        {KIND_LABEL[kind.kind] ?? kind.kind}
                      </span>
                      <span className="tabular-nums text-[13px] font-medium text-[var(--app-text)]">
                        {coinsPrecise(kind.total)}
                      </span>
                    </div>
                    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-[#1a1a1a]">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max(2, (kind.total / kindMax) * 100)}%`,
                          background: KIND_COLOR[kind.kind] ?? "#a1a1aa",
                        }}
                      />
                    </div>
                    <p className="mt-1.5 text-[11.5px] text-[var(--app-text-4)]">
                      {KIND_HINT[kind.kind] ?? ""} {compactNumber(kind.count)}×
                      {kind.tokens > 0 ? ` · ${compactNumber(kind.tokens)} tokens` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              <CardHeader
                title="Recent activity"
                description="The last 25 things your agents did, and what each one cost in Pipe Coins."
              />
              <ul className="divide-y divide-[var(--app-border)]">
                {events.slice(0, 25).map((event) => (
                  <li
                    key={event.id}
                    className="flex items-center gap-3 px-5 py-2.5 text-[12.5px]"
                  >
                    <span
                      className="h-1.5 w-1.5 shrink-0 rounded-full"
                      style={{ background: KIND_COLOR[event.kind] ?? "#a1a1aa" }}
                    />
                    <span className="min-w-0 flex-1 truncate text-[var(--app-text-2)]">
                      {KIND_LABEL[event.kind] ?? event.kind}
                      {!selected && (
                        <span className="text-[var(--app-text-4)]">
                          {" "}
                          · {modelName.get(event.model_id) ?? "model"}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 text-[var(--app-text-4)]">
                      <RelativeTime iso={event.created_at} />
                    </span>
                    <span
                      title={`${coinsPrecise(event.charged_usd)} ${COIN_NAME_PLURAL}`}
                      className="w-16 shrink-0 text-right tabular-nums text-[var(--app-text-2)]"
                    >
                      {coinsPrecise(event.charged_usd)}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      )}

      <p className="mt-8 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        Pipe Coins are deducted the moment work happens — there is no subscription and nothing
        expires. When the balance hits zero your models pause themselves; nothing is lost, they
        pick up where they left off after a top-up.
      </p>
    </>
  );
}

function FilterChip({
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
        "rounded-md border px-3 py-1.5 text-[12.5px] transition-colors",
        active
          ? "border-[var(--app-border-strong)] bg-[var(--app-active)] text-[var(--app-text)]"
          : "border-[var(--app-border)] text-[var(--app-text-3)] hover:border-[var(--app-border-strong)] hover:text-[var(--app-text)]",
      )}
    >
      {children}
    </Link>
  );
}
