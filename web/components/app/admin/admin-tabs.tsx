"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Bot, LayoutDashboard, UserPlus, Users } from "lucide-react";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/app/admin", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/app/admin/requests", label: "Requests", icon: UserPlus, exact: false },
  { href: "/app/admin/users", label: "Users", icon: Users, exact: false },
  { href: "/app/admin/models", label: "Models", icon: Bot, exact: false },
  { href: "/app/admin/usage", label: "Usage", icon: BarChart3, exact: false },
];

/** Podnavigácia admin sekcie — o prístupe nerozhoduje, ten je v layoute. */
export function AdminTabs() {
  const pathname = usePathname();

  return (
    <div className="-mx-1 mb-8 flex gap-1 overflow-x-auto border-b border-[var(--app-border)] pb-px">
      {TABS.map((tab) => {
        const active = tab.exact
          ? pathname === tab.href
          : pathname === tab.href || pathname.startsWith(`${tab.href}/`);
        const Icon = tab.icon;
        return (
          <Link
            key={tab.href}
            href={tab.href}
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
            {active && (
              <span className="absolute inset-x-0 -bottom-px h-px bg-[var(--app-text)]" />
            )}
          </Link>
        );
      })}
    </div>
  );
}
