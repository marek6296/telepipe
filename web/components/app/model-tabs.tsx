"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AudioLines,
  Heart,
  Images,
  MessageSquare,
  Send,
  SlidersHorizontal,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { MODEL_TYPE_TABS, asModelType, type ModelTabSlug } from "@/lib/model-types";
import { cn } from "@/lib/utils";

/**
 * Vzhľad jednej karty. Ktoré karty modelka má, hovorí `MODEL_TYPE_TABS` —
 * tu je len ich podoba. Rozdelené zámerne: pridať typ agenta má znamenať jeden
 * riadok v `lib/model-types.ts`, nie hľadanie `if`-ov po komponentoch.
 */
const TAB_META: Record<ModelTabSlug, { label: string; icon: LucideIcon }> = {
  telegram: { label: "Telegram", icon: Send },
  fanvue: { label: "Fanvue", icon: Heart },
  persona: { label: "Persona", icon: UserRound },
  behavior: { label: "Behavior", icon: SlidersHorizontal },
  voice: { label: "Voice", icon: AudioLines },
  photos: { label: "Photos", icon: Images },
  chats: { label: "Chats", icon: MessageSquare },
};

/** Podmenu jednej modelky — vodorovné taby, na mobile scrollovateľné. */
export function ModelTabs({
  modelId,
  modelType,
  needsSetup,
}: {
  modelId: string;
  modelType: string;
  needsSetup: boolean;
}) {
  const pathname = usePathname();
  const tabs = MODEL_TYPE_TABS[asModelType(modelType)];

  return (
    <nav className="-mx-1 mb-8 flex gap-1 overflow-x-auto border-b border-[var(--app-border)] pb-px">
      {tabs.map((slug) => {
        const meta = TAB_META[slug];
        const href = `/app/m/${modelId}/${slug}`;
        const active = pathname === href || pathname.startsWith(`${href}/`);
        const Icon = meta.icon;
        return (
          <Link
            key={slug}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "app-tap relative flex shrink-0 items-center gap-2 px-3 py-2.5 text-[13px] transition-colors",
              active
                ? "font-medium text-[var(--app-text)]"
                : "text-[var(--app-text-3)] hover:text-[var(--app-text-2)]",
            )}
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} />
            {meta.label}
            {slug === "telegram" && needsSetup && (
              <span
                className="h-1.5 w-1.5 rounded-full bg-[var(--app-text-3)]"
                title="Setup not finished"
              />
            )}
            {active && (
              <span className="absolute inset-x-0 -bottom-px h-px bg-[var(--app-text)]" />
            )}
          </Link>
        );
      })}
    </nav>
  );
}
