import Link from "next/link";
import { Images, MessageSquare, Send, Settings2 } from "lucide-react";

import { ModelPowerButton } from "@/components/app/model-power-button";
import { RepliesPausedChip } from "@/components/app/replies-paused-chip";
import { Callout, StatusBadge } from "@/components/app/ui";
import { coinsPrecise } from "@/lib/coins";
import { compactNumber } from "@/lib/format";
import { modelTypeInfo } from "@/lib/model-types";
import type { ModelRow, ModelStats } from "@/lib/models";
import { asStatus, statusHint, statusReasonText } from "@/lib/status";

/** Karta modelky — stav, mini štatistiky a skratky do jej nastavení. */
export function ModelCard({
  model,
  stats,
  connected,
  aiPaused = false,
}: {
  model: ModelRow;
  stats: ModelStats;
  connected: boolean;
  /** `settings.ai_paused` — beží, ale mlčí. Viď `RepliesPausedChip`. */
  aiPaused?: boolean;
}) {
  const status = asStatus(model.status);
  const reason = statusReasonText(model.status_reason);
  const type = modelTypeInfo(model.model_type);

  return (
    <div className="app-card app-card-interactive p-5 transition-[border-color,box-shadow,transform] hover:border-[var(--app-border-strong)]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            href={`/app/m/${model.id}/persona`}
            className="block truncate text-[15px] font-medium tracking-[-0.01em] text-[var(--app-text)] transition-colors hover:text-white"
          >
            {model.name || "Untitled model"}
          </Link>
          {/* `min-w-0` na riadku aj na dlhom texte, inak sa nezmenší pod svoj
              obsah — a keďže karta je položka mriežky (`min-width: auto`),
              tiahla celú stránku na 454 px pri 390 px okne. Namerané: to bol
              ten čierny pruh vpravo, prehliadač zmenšil celú stránku, aby sa
              pretečenie zmestilo. `truncate` samo nestačí, musí mať kam. */}
          <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
            <StatusBadge status={model.status} />
            <span className="text-[var(--app-text-4)]">·</span>
            <span className="text-[12px] text-[var(--app-text-4)]">{type.shortLabel}</span>
            <span className="hidden text-[var(--app-text-4)] min-[420px]:inline">·</span>
            <span className="w-full min-w-0 truncate text-[12px] text-[var(--app-text-3)] min-[420px]:w-auto">
              {connected ? statusHint(status) : "Telegram not connected yet."}
            </span>
          </div>
          {aiPaused && <RepliesPausedChip modelId={model.id} className="mt-2.5" />}
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
        <div className="mt-4">
          <Callout tone={status === "error" ? "danger" : "neutral"}>{reason}</Callout>
        </div>
      )}

      {/* Tri stĺpce od najmenšieho telefónu. Hranica 420 px sa na bežnom
          Androide (360–412) nikdy nezapla, takže „Coins today" visela sama na
          druhom riadku — namerané na 360, 375 aj 393 px. Popisky sú krátke a
          do ~85 px stĺpca sa zmestia. */}
      <dl className="mt-5 grid grid-cols-3 gap-3 min-[420px]:gap-6">
        <Metric label="Chats" value={compactNumber(stats.chats)} />
        <Metric label="Converted" value={compactNumber(stats.converted)} />
        <Metric label="Coins today" value={coinsPrecise(stats.spentToday)} />
      </dl>

      {/* Na úzkych telefónoch mriežka 2×2, od 412 px jeden riadok. Predtým to
          bol `flex-wrap`, ktorý sa pri 360–393 px zalomil na TRI riadky (2+1+1)
          — namerané. Mriežka je symetrická v oboch prípadoch. */}
      <div className="-mx-1.5 mt-5 grid grid-cols-2 gap-0.5 border-t border-[var(--app-border)] pt-3 min-[412px]:flex min-[412px]:flex-wrap min-[412px]:items-center">
        <QuickLink
          href={`/app/m/${model.id}/telegram`}
          icon={<Send className="h-3.5 w-3.5" strokeWidth={1.75} />}
        >
          {connected ? "Telegram" : "Set up"}
        </QuickLink>
        <QuickLink
          href={`/app/m/${model.id}/persona`}
          icon={<Settings2 className="h-3.5 w-3.5" strokeWidth={1.75} />}
        >
          Persona
        </QuickLink>
        <QuickLink
          href={`/app/m/${model.id}/telegram/photos`}
          icon={<Images className="h-3.5 w-3.5" strokeWidth={1.75} />}
        >
          Photos
        </QuickLink>
        <QuickLink
          href={`/app/m/${model.id}/telegram/chats`}
          icon={<MessageSquare className="h-3.5 w-3.5" strokeWidth={1.75} />}
        >
          Chats
        </QuickLink>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11.5px] text-[var(--app-text-4)]">{label}</dt>
      <dd className="mt-1 text-[18px] font-semibold tabular-nums tracking-[-0.02em] text-[var(--app-text)]">
        {value}
      </dd>
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
      className="app-tap inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12.5px] text-[var(--app-text-3)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
    >
      {icon}
      {children}
    </Link>
  );
}
