"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AudioLines, Heart, Send, UserRound, type LucideIcon } from "lucide-react";

import {
  MODEL_TYPE_TABS,
  activeModelTab,
  asModelType,
  subTabHref,
  type ModelSubTabSlug,
  type ModelTabSlug,
} from "@/lib/model-types";
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
  voice: { label: "Voice", icon: AudioLines },
};

/**
 * Názvy podkariet. Prvá („index") je samotná karta a volá sa inak podľa toho,
 * čo na nej je: Telegram sa pripája sprievodcom, Fanvue jedným preklikom,
 * Persona je jej identita.
 */
const SUB_TAB_LABEL: Partial<Record<ModelTabSlug, Partial<Record<ModelSubTabSlug, string>>>> =
  {
    telegram: {
      index: "Connection",
      settings: "Settings",
      photos: "Photos",
      chats: "Chats",
    },
    fanvue: {
      index: "Connect",
      settings: "Settings",
      photos: "Photos",
      chats: "Chats",
    },
    persona: {
      index: "Identity",
      behavior: "Behavior",
      day: "Daily life",
    },
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

  const {
    tab: activeTab,
    sub: activeSub,
    subTabs,
  } = activeModelTab(pathname, modelId, modelType);

  return (
    <div className="mb-8">
      <nav className="-mx-1 flex gap-1 overflow-x-auto border-b border-[var(--app-border)] pb-px">
        {tabs.map((slug) => {
          const meta = TAB_META[slug];
          const href = `/app/m/${modelId}/${slug}`;
          const active = slug === activeTab;
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

      {/* Druhý rad — o stupeň tichší: bez ikon, menšie písmo, tenšia čiara.
          Je to podmenu jednej karty, nie druhá navigácia rovnakej váhy. */}
      {activeTab && subTabs.length > 1 && (
        <nav className="-mx-1 mt-px flex gap-0.5 overflow-x-auto border-b border-[var(--app-border)] pb-px">
          {subTabs.map((sub) => {
            const label = SUB_TAB_LABEL[activeTab]?.[sub] ?? sub;
            const active = sub === activeSub;
            return (
              <Link
                key={sub}
                href={subTabHref(modelId, activeTab, sub)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "app-tap relative shrink-0 px-3 py-2 text-[12px] transition-colors",
                  active
                    ? "font-medium text-[var(--app-text-2)]"
                    : "text-[var(--app-text-4)] hover:text-[var(--app-text-3)]",
                )}
              >
                {label}
                {active && (
                  <span className="absolute inset-x-2 -bottom-px h-px bg-[var(--app-text-2)]" />
                )}
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}
