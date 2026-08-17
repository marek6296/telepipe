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
} from "lucide-react";

import { cn } from "@/lib/utils";

const TABS = [
  { slug: "telegram", label: "Telegram", icon: Send },
  { slug: "fanvue", label: "Fanvue", icon: Heart },
  { slug: "persona", label: "Persona", icon: UserRound },
  { slug: "behavior", label: "Behavior", icon: SlidersHorizontal },
  { slug: "voice", label: "Voice", icon: AudioLines },
  { slug: "photos", label: "Photos", icon: Images },
  { slug: "chats", label: "Chats", icon: MessageSquare },
];

/** Podmenu jednej modelky — vodorovné taby, na mobile scrollovateľné. */
export function ModelTabs({ modelId, needsSetup }: { modelId: string; needsSetup: boolean }) {
  const pathname = usePathname();

  return (
    <nav className="-mx-1 mb-8 flex gap-1 overflow-x-auto border-b border-[var(--app-border)] pb-px">
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
              "relative flex shrink-0 items-center gap-2 px-3 py-2.5 text-[13px] transition-colors",
              active
                ? "font-medium text-[var(--app-text)]"
                : "text-[var(--app-text-3)] hover:text-[var(--app-text-2)]",
            )}
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} />
            {tab.label}
            {tab.slug === "telegram" && needsSetup && (
              <span
                className="h-1.5 w-1.5 rounded-full bg-[#facc15]"
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
