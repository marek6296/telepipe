import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowUpRight,
  Bot,
  MessageSquare,
  Sparkles,
  TrendingUp,
  Wallet,
} from "lucide-react";

import { AddModelDialog } from "@/components/app/add-model-dialog";
import { ModelCard } from "@/components/app/model-card";
import { Card, EmptyState, PageHeader, StatTile } from "@/components/app/ui";
import { compactNumber, toNumber, usd, usdPrecise } from "@/lib/format";
import { getAccount, getModelStats, listModels } from "@/lib/models";
import { getConnectedMap } from "@/lib/telegram";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Dashboard",
};

const DAY_MS = 24 * 60 * 60 * 1000;

export default async function DashboardPage() {
  const [account, models] = await Promise.all([getAccount(), listModels()]);
  const [stats, connected, weekSpend] = await Promise.all([
    getModelStats(models.map((model) => model.id)),
    getConnectedMap(models),
    sumChargedSince(new Date(Date.now() - 7 * DAY_MS).toISOString()),
  ]);

  const balance = toNumber(account?.credit_balance_usd);
  const activeCount = models.filter((model) => model.status === "active").length;
  const totalChats = models.reduce((sum, model) => sum + (stats[model.id]?.chats ?? 0), 0);
  const totalConverted = models.reduce(
    (sum, model) => sum + (stats[model.id]?.converted ?? 0),
    0,
  );
  const spentToday = models.reduce(
    (sum, model) => sum + (stats[model.id]?.spentToday ?? 0),
    0,
  );

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="Everything your models did while you were away."
        actions={models.length > 0 ? <AddModelDialog /> : undefined}
      />

      {/* --- Kredit ---------------------------------------------------------- */}
      <Card gold className="relative overflow-hidden p-6 sm:p-7">
        <div className="gold-halo pointer-events-none absolute -right-24 -top-32 h-[380px] w-[380px]" />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--gold)]/75">
              <Wallet className="h-3.5 w-3.5" />
              Credit balance
            </p>
            <p className="mt-3 text-[44px] font-semibold leading-none tracking-tight text-gradient-gold sm:text-[52px]">
              {usd(balance)}
            </p>
            <p className="mt-3 text-[13px] text-white/45">
              {balance <= 0
                ? "Out of credits — your models pause until you top up."
                : `Roughly ${estimateReplies(balance)} more replies at current rates.`}
            </p>
          </div>

          <div className="flex flex-col items-start gap-3 sm:items-end">
            <a
              href="mailto:support@telepipe.app?subject=Telepipe%20top-up"
              className="btn-modern-light h-11 px-6 text-[13.5px]"
            >
              Contact us to top up
              <ArrowUpRight className="h-4 w-4" />
            </a>
            <Link
              href="/app/usage"
              className="text-[12.5px] text-white/40 transition-colors hover:text-[var(--gold-light)]"
            >
              See what you spent →
            </Link>
          </div>
        </div>
      </Card>

      {/* --- Dlaždice --------------------------------------------------------- */}
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Models"
          value={models.length}
          hint={`${activeCount} active`}
          icon={<Bot className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile
          label="Chats"
          value={compactNumber(totalChats)}
          hint="fans in the pipeline"
          icon={<MessageSquare className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile
          label="Converted"
          value={compactNumber(totalConverted)}
          hint="subscribed after chatting"
          icon={<TrendingUp className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
        <StatTile
          label="Spent"
          value={usdPrecise(spentToday)}
          hint={`${usdPrecise(weekSpend)} last 7 days`}
          icon={<Sparkles className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
      </div>

      {/* --- Modelky ---------------------------------------------------------- */}
      <div className="mt-9">
        {models.length === 0 ? (
          <EmptyState
            icon={<Bot className="h-6 w-6" />}
            title="No models yet"
            description="Add your first model, connect her Telegram account, and she starts replying to fans within 30 seconds."
            action={<AddModelDialog label="Add your first model" />}
          />
        ) : (
          <>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-[15px] font-semibold tracking-tight text-white/85">
                Your models
              </h2>
              <Link
                href="/app/models"
                className="text-[12.5px] text-white/40 transition-colors hover:text-[var(--gold-light)]"
              >
                Manage all →
              </Link>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              {models.map((model) => (
                <ModelCard
                  key={model.id}
                  model={model}
                  stats={stats[model.id] ?? { chats: 0, converted: 0, spentToday: 0 }}
                  connected={connected[model.id] ?? false}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}

/** Súčet `charged_usd` od danej chvíle. Atlas cost sa klientovi nezobrazuje. */
async function sumChargedSince(since: string): Promise<number> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("usage_events")
    .select("charged_usd")
    .gte("created_at", since);

  return (data ?? []).reduce((sum, row) => sum + toNumber(row.charged_usd as string), 0);
}

/** Hrubý odhad — priemerná odpoveď vyjde na ~$0.005 pri našej marži. */
function estimateReplies(balance: number): string {
  return compactNumber(Math.max(0, Math.round(balance / 0.005)));
}
