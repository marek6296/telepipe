import { TrendingUp } from "lucide-react";

import { FUNNEL_LABEL, FUNNEL_STYLE } from "@/lib/chats";
import { cn } from "@/lib/utils";

/** Fáza funnelu: cold → warm → link_sent → converted (zlatý). */
export function FunnelBadge({ stage }: { stage: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.07em]",
        FUNNEL_STYLE[stage] ?? FUNNEL_STYLE.cold,
      )}
    >
      {stage === "converted" && <TrendingUp className="h-3 w-3" />}
      {FUNNEL_LABEL[stage] ?? stage}
    </span>
  );
}
