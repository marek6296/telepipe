import { FV_STAGE_LABEL, FV_STAGE_STYLE } from "@/lib/fv-chats";
import { cn } from "@/lib/utils";

/**
 * Fáza fanvue rozhovoru: discovery → known. Monochróm ako `FunnelBadge`, ale
 * vlastný číselník — na Fanvue už zaplatil, takže „converted" tu nedáva zmysel.
 */
export function FvStageBadge({ stage }: { stage: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium",
        FV_STAGE_STYLE[stage] ?? FV_STAGE_STYLE.discovery,
      )}
    >
      {FV_STAGE_LABEL[stage] ?? stage}
    </span>
  );
}
