"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3,
  Bot,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  Settings,
  Wallet,
  X,
} from "lucide-react";

import { signOutAction } from "@/app/(auth)/actions";
import { usd } from "@/lib/format";
import { asStatus, STATUS_DOT } from "@/lib/status";
import { cn } from "@/lib/utils";

export type ShellModel = {
  id: string;
  name: string;
  status: string;
};

const NAV = [
  { href: "/app", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/app/models", label: "Models", icon: Bot, exact: false },
  { href: "/app/usage", label: "Usage", icon: BarChart3, exact: false },
  { href: "/app/account", label: "Account", icon: Settings, exact: false },
];

function isActive(pathname: string, href: string, exact: boolean): boolean {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * AppShell v štýle Efferd dashboardu — fixný sidebar s lucide ikonami, zlatý
 * aktívny item, dole účet a odhlásenie. Na mobile sa sidebar mení na sheet.
 */
export function AppShell({
  email,
  models,
  creditBalance,
  children,
}: {
  email: string;
  models: ShellModel[];
  creditBalance: number;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  // Prechod na inú stránku zavrie mobilné menu
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  const sidebar = (
    <SidebarContent
      email={email}
      models={models}
      pathname={pathname}
      onNavigate={() => setMenuOpen(false)}
    />
  );

  return (
    <div className="relative flex min-h-svh w-full">
      <div className="pointer-events-none fixed inset-0 bg-grid-fine opacity-70" />

      {/* --- Desktop sidebar ---------------------------------------------- */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[252px] flex-col border-r border-white/[0.07] bg-[#050505]/95 backdrop-blur-xl lg:flex">
        {sidebar}
      </aside>

      {/* --- Mobile sheet -------------------------------------------------- */}
      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setMenuOpen(false)}
              className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm lg:hidden"
            />
            <motion.aside
              key="sheet"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
              className="fixed inset-y-0 left-0 z-50 flex w-[272px] flex-col border-r border-white/[0.08] bg-[#070707] lg:hidden"
            >
              <button
                type="button"
                onClick={() => setMenuOpen(false)}
                aria-label="Close menu"
                className="absolute right-3 top-4 rounded-full p-2 text-white/45 transition-colors hover:text-[var(--gold-light)]"
              >
                <X className="h-4.5 w-4.5" />
              </button>
              {sidebar}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* --- Obsah ---------------------------------------------------------- */}
      <div className="relative flex min-w-0 flex-1 flex-col lg:pl-[252px]">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-white/[0.06] bg-black/70 px-4 backdrop-blur-xl sm:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
              className="rounded-xl border border-white/[0.08] p-2 text-white/70 transition-colors hover:border-[rgba(212,175,55,0.35)] hover:text-[var(--gold-light)] lg:hidden"
            >
              <Menu className="h-4.5 w-4.5" />
            </button>
            <Link href="/app" className="flex items-center lg:hidden" aria-label="Telepipe">
              <Image
                src="/logo-white.png"
                alt="Telepipe"
                width={132}
                height={42}
                className="h-6 w-auto"
              />
            </Link>
          </div>

          <div className="flex items-center gap-2.5">
            <Link
              href="/app/usage"
              className="widget-depth widget-depth-gold flex items-center gap-2 rounded-full px-3.5 py-2 text-[12.5px] font-medium text-white/75 transition-colors hover:text-[var(--gold-light)]"
            >
              <Wallet className="h-3.5 w-3.5 text-[var(--gold)]" />
              <span className="tabular-nums">{usd(creditBalance)}</span>
              <span className="hidden text-white/35 sm:inline">credit</span>
            </Link>
          </div>
        </header>

        <main className="relative flex-1 px-4 pb-16 pt-6 sm:px-6 lg:px-9">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              className="mx-auto w-full max-w-[1180px]"
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

function SidebarContent({
  email,
  models,
  pathname,
  onNavigate,
}: {
  email: string;
  models: ShellModel[];
  pathname: string;
  onNavigate: () => void;
}) {
  return (
    <>
      <div className="flex h-16 shrink-0 items-center px-5">
        <Link href="/app" className="flex items-center" aria-label="Telepipe">
          <Image
            src="/logo-white.png"
            alt="Telepipe"
            width={148}
            height={47}
            priority
            className="h-6 w-auto"
          />
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-4">
        <ul className="space-y-1">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href, item.exact);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px] font-medium transition-all",
                    active
                      ? "bg-[rgba(212,175,55,0.1)] text-[var(--gold-light)]"
                      : "text-white/55 hover:bg-white/[0.04] hover:text-white/85",
                  )}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--gold)]" />
                  )}
                  <Icon
                    className={cn(
                      "h-[17px] w-[17px] shrink-0 transition-colors",
                      active ? "text-[var(--gold)]" : "text-white/40 group-hover:text-white/70",
                    )}
                  />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="mt-7">
          <p className="px-3 text-[10.5px] font-semibold uppercase tracking-[0.16em] text-white/25">
            Your models
          </p>
          <ul className="mt-2 space-y-0.5">
            {models.map((model) => {
              const active = pathname.startsWith(`/app/m/${model.id}`);
              return (
                <li key={model.id}>
                  <Link
                    href={`/app/m/${model.id}/persona`}
                    onClick={onNavigate}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors",
                      active
                        ? "bg-white/[0.05] text-white"
                        : "text-white/45 hover:bg-white/[0.03] hover:text-white/80",
                    )}
                  >
                    <span
                      className={cn(
                        "h-1.5 w-1.5 shrink-0 rounded-full",
                        STATUS_DOT[asStatus(model.status)],
                      )}
                    />
                    <span className="truncate">{model.name || "Untitled model"}</span>
                  </Link>
                </li>
              );
            })}
            <li>
              <Link
                href="/app/models"
                onClick={onNavigate}
                className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-white/35 transition-colors hover:text-[var(--gold-light)]"
              >
                <Plus className="h-3.5 w-3.5" />
                Add model
              </Link>
            </li>
          </ul>
        </div>
      </nav>

      <div className="shrink-0 border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-3 rounded-xl px-2.5 py-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[linear-gradient(180deg,var(--gold-light),var(--gold-dark))] text-[12px] font-bold text-black">
            {email.slice(0, 1).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-white/55" title={email}>
            {email}
          </span>
        </div>
        <form action={signOutAction}>
          <button
            type="submit"
            className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium text-white/45 transition-colors hover:bg-white/[0.04] hover:text-[#ffb3a7]"
          >
            <LogOut className="h-[16px] w-[16px]" />
            Sign out
          </button>
        </form>
      </div>
    </>
  );
}
