import { FUNNEL_LABEL, FUNNEL_STYLE } from "@/lib/chats";
import { cn } from "@/lib/utils";

/** Fáza funnelu: cold → warm → link_sent → converted. Monochróm. */
export function FunnelBadge({ stage }: { stage: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium",
        FUNNEL_STYLE[stage] ?? FUNNEL_STYLE.cold,
      )}
    >
      {FUNNEL_LABEL[stage] ?? stage}
    </span>
  );
}
