"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Bot, LayoutDashboard, Users } from "lucide-react";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/app/admin", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/app/admin/users", label: "Users", icon: Users, exact: false },
  { href: "/app/admin/models", label: "Models", icon: Bot, exact: false },
  { href: "/app/admin/usage", label: "Usage", icon: BarChart3, exact: false },
];

/** Podnavigácia admin sekcie — o prístupe nerozhoduje, ten je v layoute. */
export function AdminTabs() {
  const pathname = usePathname();

  return (
    <div className="mb-6 flex flex-wrap gap-1.5">
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
              "flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-[12.5px] font-medium transition-colors",
              active
                ? "border-[rgba(212,175,55,0.45)] bg-[rgba(212,175,55,0.1)] text-[var(--gold-light)]"
                : "border-white/[0.08] text-white/45 hover:text-white/80",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}
