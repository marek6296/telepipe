"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Heart, Images, MessageSquare, Send, SlidersHorizontal, UserRound } from "lucide-react";

import { cn } from "@/lib/utils";

const TABS = [
  { slug: "telegram", label: "Telegram", icon: Send },
  { slug: "fanvue", label: "Fanvue", icon: Heart },
  { slug: "persona", label: "Persona", icon: UserRound },
  { slug: "behavior", label: "Behavior", icon: SlidersHorizontal },
  { slug: "photos", label: "Photos", icon: Images },
  { slug: "chats", label: "Chats", icon: MessageSquare },
];

/** Podmenu jednej modelky — vodorovné taby, na mobile scrollovateľné. */
export function ModelTabs({ modelId, needsSetup }: { modelId: string; needsSetup: boolean }) {
  const pathname = usePathname();

  return (
    <nav className="-mx-1 mb-7 flex gap-1 overflow-x-auto border-b border-white/[0.07] pb-px">
      {TABS.map((tab) => {
        const href = `/app/m/${modelId}/${tab.slug}`;
        const active = pathname === href || pathname.startsWith(`${href}/`);
        const Icon = tab.icon;
        return (
          <Link
            key={tab.slug}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative flex shrink-0 items-center gap-2 rounded-t-lg px-3.5 py-2.5 text-[13px] font-medium transition-colors",
              active
                ? "text-[var(--gold-light)]"
                : "text-white/45 hover:text-white/80",
            )}
          >
            <Icon className="h-[15px] w-[15px]" />
            {tab.label}
            {tab.slug === "telegram" && needsSetup && (
              <span
                className="h-1.5 w-1.5 rounded-full bg-[var(--gold)]"
                title="Setup not finished"
              />
            )}
            {active && (
              <span className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-[var(--gold)]" />
            )}
          </Link>
        );
      })}
    </nav>
  );
}
