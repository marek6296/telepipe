import Link from "next/link";
import {
  Images,
  MessageSquare,
  Send,
  Settings2,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { ModelPowerButton } from "@/components/app/model-power-button";
import { Callout, StatusBadge } from "@/components/app/ui";
import { compactNumber, usdPrecise } from "@/lib/format";
import type { ModelRow, ModelStats } from "@/lib/models";
import { asStatus, statusHint, statusReasonText } from "@/lib/status";

/** Karta modelky — stav, mini štatistiky a skratky do jej nastavení. */
export function ModelCard({
  model,
  stats,
  connected,
}: {
  model: ModelRow;
  stats: ModelStats;
  connected: boolean;
}) {
  const status = asStatus(model.status);
  const reason = statusReasonText(model.status_reason);

  return (
    <div className="widget-depth group relative overflow-hidden rounded-2xl p-5 transition-all duration-300 hover:border-[rgba(212,175,55,0.28)]">
      <div className="pointer-events-none absolute -right-20 -top-24 h-52 w-52 rounded-full bg-[radial-gradient(circle,rgba(212,175,55,0.12),transparent_65%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100" />

      <div className="relative flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <Link
              href={`/app/m/${model.id}/persona`}
              className="truncate text-[17px] font-semibold tracking-tight text-white transition-colors hover:text-[var(--gold-light)]"
            >
              {model.name || "Untitled model"}
            </Link>
            <StatusBadge status={model.status} />
          </div>
          <p className="mt-1.5 text-[12.5px] text-white/40">
            {connected ? statusHint(status) : "Telegram account not connected yet."}
          </p>
        </div>

        <ModelPowerButton
          modelId={model.id}
          status={model.status}
          statusReason={model.status_reason}
          connected={connected}
          size="sm"
        />
      </div>

      {reason && (
        <div className="relative mt-4">
          <Callout tone={status === "error" ? "danger" : "gold"}>{reason}</Callout>
        </div>
      )}

      <dl className="relative mt-5 grid grid-cols-3 gap-2">
        <Metric
          icon={<MessageSquare className="h-3.5 w-3.5" />}
          label="Chats"
          value={compactNumber(stats.chats)}
        />
        <Metric
          icon={<TrendingUp className="h-3.5 w-3.5" />}
          label="Converted"
          value={compactNumber(stats.converted)}
        />
        <Metric
          icon={<Sparkles className="h-3.5 w-3.5" />}
          label="Today"
          value={usdPrecise(stats.spentToday)}
        />
      </dl>

      <div className="relative mt-5 flex flex-wrap items-center gap-1.5 border-t border-white/[0.06] pt-4">
        <QuickLink href={`/app/m/${model.id}/telegram`} icon={<Send className="h-3.5 w-3.5" />}>
          {connected ? "Telegram" : "Set up"}
        </QuickLink>
        <QuickLink
          href={`/app/m/${model.id}/persona`}
          icon={<Settings2 className="h-3.5 w-3.5" />}
        >
          Persona
        </QuickLink>
        <QuickLink href={`/app/m/${model.id}/photos`} icon={<Images className="h-3.5 w-3.5" />}>
          Photos
        </QuickLink>
        <QuickLink
          href={`/app/m/${model.id}/chats`}
          icon={<MessageSquare className="h-3.5 w-3.5" />}
        >
          Chats
        </QuickLink>
      </div>
    </div>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2.5">
      <dt className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-[0.1em] text-white/30">
        <span className="text-[var(--gold)]/70">{icon}</span>
        {label}
      </dt>
      <dd className="mt-1 text-[15px] font-semibold tabular-nums text-white/90">{value}</dd>
    </div>
  );
}

function QuickLink({
  href,
  icon,
  children,
}: {
  href: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12.5px] font-medium text-white/45 transition-colors hover:bg-white/[0.05] hover:text-[var(--gold-light)]"
    >
      {icon}
      {children}
    </Link>
  );
}
