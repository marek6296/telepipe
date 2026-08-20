"use client";

import Link, { useLinkStatus } from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import {
  AudioLines,
  Heart,
  Loader2,
  Send,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { useBackgroundPrefetch } from "@/components/app/use-background-prefetch";
import {
  MODEL_TYPE_TABS,
  activeModelTab,
  asModelType,
  modelTypeSubTabs,
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
  const reduceMotion = useReducedMotion();

  const {
    tab: activeTab,
    sub: activeSub,
    subTabs,
  } = activeModelTab(pathname, modelId, modelType);

  const routesForTab = (tab: ModelTabSlug) => {
    const subTabsForTab = modelTypeSubTabs(modelType, tab);
    return subTabsForTab.length > 0
      ? subTabsForTab.map((sub) => subTabHref(modelId, tab, sub))
      : [`/app/m/${modelId}/${tab}`];
  };

  const currentTabRoutes = activeTab ? routesForTab(activeTab) : [];
  const otherTabEntries = tabs
    .filter((tab) => tab !== activeTab)
    .map((tab) => routesForTab(tab)[0]);
  const remainingRoutes = tabs.flatMap(routesForTab);
  const backgroundRoutes = Array.from(
    new Set([...currentTabRoutes, ...otherTabEntries, ...remainingRoutes]),
  ).filter((href) => href !== pathname);

  // Aktívna karta je už na obrazovke. Po prvom vykreslení potichu zahrejeme
  // ostatné karty modelky, aby ďalší preklik pôsobil ako v natívnej aplikácii.
  useBackgroundPrefetch(backgroundRoutes, 0, false);

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
              <TabIcon Icon={Icon} />
              {meta.label}
              {slug === "telegram" && needsSetup && (
                <span
                  className="h-1.5 w-1.5 rounded-full bg-[var(--app-text-3)]"
                  title="Setup not finished"
                />
              )}
              {active && (
                <motion.span
                  layoutId={`model-primary-tab-${modelId}`}
                  className="absolute inset-x-0 -bottom-px h-px bg-[var(--app-text)]"
                  transition={
                    reduceMotion
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 470, damping: 38, mass: 0.7 }
                  }
                  aria-hidden
                />
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
                  <motion.span
                    layoutId={`model-sub-tab-${modelId}`}
                    className="absolute inset-x-2 -bottom-px h-px bg-[var(--app-text-2)]"
                    transition={
                      reduceMotion
                        ? { duration: 0 }
                        : { type: "spring", stiffness: 500, damping: 40, mass: 0.65 }
                    }
                    aria-hidden
                  />
                )}
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}

/**
 * Ikona tabu, ktorá sa počas navigácie točí.
 *
 * `useLinkStatus` číta stav NAJBLIŽŠIEHO `<Link>`, takže musí byť vnútri neho
 * — preto samostatný komponent. Podčiarknutie sa hýbe hneď (`layoutId`), ale
 * to je len presun; toto hovorí „naozaj sa niečo načítava".
 */
function TabIcon({ Icon }: { Icon: LucideIcon }) {
  const { pending } = useLinkStatus();
  if (pending) return <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />;
  return <Icon className="h-4 w-4" strokeWidth={1.75} />;
}
