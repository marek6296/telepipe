"use client";

import { useCallback, useEffect, useMemo, useState, type SyntheticEvent } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  BarChart3,
  Bot,
  ChevronsUpDown,
  Coins,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  Settings,
  Shield,
  Smartphone,
  Users,
  X,
} from "lucide-react";

import { signOutAction } from "@/app/(auth)/actions";
import { useBackgroundPrefetch } from "@/components/app/use-background-prefetch";
import { coins } from "@/lib/coins";
import { asStatus, STATUS_DOT } from "@/lib/status";
import { cn } from "@/lib/utils";

export type ShellModel = {
  id: string;
  name: string;
  status: string;
};

type NavItem = {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  exact: boolean;
};

const OVERVIEW: NavItem[] = [
  { href: "/app", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/app/usage", label: "Usage", icon: BarChart3, exact: false },
  { href: "/app/virtual-sim", label: "Virtual SIM", icon: Smartphone, exact: false },
];

const WORKSPACE: NavItem[] = [
  { href: "/app/billing", label: "Billing", icon: Coins, exact: false },
  { href: "/app/account", label: "Account", icon: Settings, exact: false },
];

const ADMIN: NavItem[] = [
  { href: "/app/admin", label: "Overview", icon: Shield, exact: true },
  { href: "/app/admin/users", label: "Users", icon: Users, exact: false },
  { href: "/app/admin/models", label: "Models", icon: Bot, exact: false },
  { href: "/app/admin/usage", label: "Usage", icon: BarChart3, exact: false },
];

function isActive(pathname: string, href: string, exact: boolean): boolean {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

const MODEL_TAB_LABEL: Record<string, string> = {
  telegram: "Telegram",
  fanvue: "Fanvue",
  persona: "Persona",
  behavior: "Behavior",
  photos: "Photos",
  chats: "Chats",
};

/** Titulok v topbare — odvodený z cesty, aby ho stránky nemuseli posielať. */
function pageTitle(pathname: string, models: ShellModel[]): string {
  if (pathname === "/app") return "Dashboard";
  if (pathname.startsWith("/app/models")) return "Models";
  if (pathname.startsWith("/app/usage")) return "Usage";
  if (pathname.startsWith("/app/virtual-sim")) return "Virtual SIM";
  if (pathname.startsWith("/app/billing")) return "Billing";
  if (pathname.startsWith("/app/account")) return "Account";

  if (pathname.startsWith("/app/admin")) {
    const rest = pathname.slice("/app/admin".length).split("/").filter(Boolean);
    const leaf = rest[0];
    if (!leaf) return "Admin · Overview";
    return `Admin · ${leaf.charAt(0).toUpperCase()}${leaf.slice(1)}`;
  }

  const match = /^\/app\/m\/([^/]+)(?:\/([^/]+))?/.exec(pathname);
  if (match) {
    const model = models.find((item) => item.id === match[1]);
    const name = model?.name || "Model";
    const tab = match[2] ? MODEL_TAB_LABEL[match[2]] : undefined;
    return tab ? `${name} · ${tab}` : name;
  }

  return "Telepipe";
}

/**
 * AppShell v štýle Efferd dashboardu, invertovanom do čiernej: zoskupený
 * sidebar s tenkými ikonami, aktívna položka ako jemný #1A1A1A pill, dole
 * účet v dropdowne. Na mobile sa sidebar mení na sheet.
 */
export function AppShell({
  email,
  models,
  creditBalance,
  isAdmin = false,
  children,
}: {
  email: string;
  models: ShellModel[];
  creditBalance: number;
  /** Rozhodnuté v serverovom layoute z `accounts.role` — klient sa nepýta. */
  isAdmin?: boolean;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  const backgroundRoutes = useMemo(() => {
    const routes = ["/app", "/app/models", "/app/usage", "/app/virtual-sim", "/app/account"];
    if (isAdmin) routes.push("/app/admin", "/app/admin/users", "/app/admin/models");

    // Modelky sa zo sidebaru otvárajú na Personu. Zahrejeme len vstupnú
    // kartu; jej vlastný tab bar po vykreslení prednačíta zvyšok.
    routes.push(...models.slice(0, 8).map((model) => `/app/m/${model.id}/persona`));
    return routes.filter((href) => href !== pathname);
  }, [isAdmin, models, pathname]);

  useBackgroundPrefetch(backgroundRoutes);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  const prefetchNavigationIntent = useCallback((event: SyntheticEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    const anchor = target.closest("a");
    if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) return;

    const href = anchor.getAttribute("href");
    if (!href || href.startsWith("#")) return;

    const next = new URL(anchor.href, window.location.href);
    const current = new URL(window.location.href);
    if (next.origin !== current.origin || !next.pathname.startsWith("/app")) return;
    router.prefetch(`${next.pathname}${next.search}`);
  }, [router]);

  const sidebar = (
    <SidebarContent
      email={email}
      models={models}
      isAdmin={isAdmin}
      pathname={pathname}
      onNavigate={() => setMenuOpen(false)}
    />
  );

  return (
    <div
      className="app-scope relative flex min-h-svh w-full"
      onPointerOverCapture={prefetchNavigationIntent}
      onFocusCapture={prefetchNavigationIntent}
    >
      {/* --- Desktop sidebar ---------------------------------------------- */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[240px] flex-col border-r border-[var(--app-border)] bg-[var(--app-bg-sidebar)] lg:flex">
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
              className="fixed inset-0 z-50 bg-black/70 lg:hidden"
            />
            <motion.aside
              key="sheet"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
              className="fixed inset-y-0 left-0 z-50 flex w-[264px] flex-col border-r border-[var(--app-border)] bg-[var(--app-bg-sidebar)] lg:hidden"
            >
              <button
                type="button"
                onClick={() => setMenuOpen(false)}
                aria-label="Close menu"
                className="app-tap absolute right-3 top-3.5 rounded-md p-2 text-[var(--app-text-3)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
              >
                <X className="h-4 w-4" strokeWidth={1.75} />
              </button>
              {sidebar}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* --- Obsah ---------------------------------------------------------- */}
      <div className="relative flex min-w-0 flex-1 flex-col lg:pl-[240px]">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-[var(--app-border)] bg-[var(--app-bg)]/90 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-label="Open menu"
              className="app-tap -ml-1 rounded-md p-2 text-[var(--app-text-2)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)] lg:hidden"
            >
              <Menu className="h-4 w-4" strokeWidth={1.75} />
            </button>
            <p className="truncate text-[13.5px] font-medium text-[var(--app-text)] sm:hidden">
              {pageTitle(pathname, models)}
            </p>
            <p className="app-group-label hidden sm:block">Workspace</p>
          </div>

          {/* Klik na zostatok = kúpiť coiny — presne to človek s nízkym zostatkom hľadá. */}
          <Link
            href="/app/billing"
            className="flex shrink-0 items-center gap-2 rounded-md border border-[var(--app-border)] px-2.5 py-1.5 text-[12px] text-[var(--app-text-2)] transition-colors hover:border-[var(--app-border-strong)] hover:text-[var(--app-text)]"
          >
            <span className="tabular-nums">{coins(creditBalance)}</span>
            <span className="hidden text-[var(--app-text-4)] sm:inline">Pipe Coins</span>
          </Link>
        </header>

        <main className="relative flex-1 px-4 pb-16 pt-8 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-[1140px]">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

function SidebarContent({
  email,
  models,
  isAdmin,
  pathname,
  onNavigate,
}: {
  email: string;
  models: ShellModel[];
  isAdmin: boolean;
  pathname: string;
  onNavigate: () => void;
}) {
  return (
    <>
      <div className="flex h-14 shrink-0 items-center border-b border-[var(--app-border)] px-5">
        <Link href="/app" className="flex items-center" aria-label="Telepipe">
          <Image
            src="/logo-white.png"
            alt="Telepipe"
            width={148}
            height={47}
            priority
            className="brand-logo-neutral h-5 w-auto"
          />
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <Group label="Overview">
          {OVERVIEW.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />
          ))}
        </Group>

        <Group label="Models">
          <NavLink
            item={{ href: "/app/models", label: "All models", icon: Bot, exact: true }}
            pathname={pathname}
            onNavigate={onNavigate}
          />
          {models.map((model) => {
            const active = pathname.startsWith(`/app/m/${model.id}`);
            return (
              <li key={model.id}>
                <Link
                  href={`/app/m/${model.id}/persona`}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "app-tap flex items-center gap-2.5 rounded-md py-1.5 pl-[26px] pr-2.5 text-[13px] transition-colors",
                    active
                      ? "bg-[var(--app-active)] text-[var(--app-text)]"
                      : "text-[var(--app-text-3)] hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text-2)]",
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
              className="app-tap flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] text-[var(--app-text-4)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text-2)]"
            >
              <Plus className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              Add model
            </Link>
          </li>
        </Group>

        <Group label="Workspace">
          {WORKSPACE.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />
          ))}
        </Group>

        {/* Admin vidí len ten, komu to server layout povolil (accounts.role). */}
        {isAdmin && (
          <Group label="Admin">
            {ADMIN.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />
            ))}
          </Group>
        )}
      </nav>

      <div className="shrink-0 border-t border-[var(--app-border)] p-3">
        <UserMenu email={email} onNavigate={onNavigate} />
        <p className="mt-3 px-2.5 text-[10.5px] text-[var(--app-text-4)]">
          © Telepipe
        </p>
      </div>
    </>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-5 last:mb-0">
      <p className="app-group-label mb-2 px-2.5">{label}</p>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

function NavLink({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  onNavigate: () => void;
}) {
  const active = isActive(pathname, item.href, item.exact);
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={cn(
          "app-tap flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
          active
            ? "bg-[var(--app-active)] font-medium text-[var(--app-text)]"
            : "text-[var(--app-text-2)] hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]",
        )}
      >
        <Icon
          className={cn(
            "h-4 w-4 shrink-0",
            active ? "text-[var(--app-text)]" : "text-[var(--app-text-4)]",
          )}
          strokeWidth={1.75}
        />
        {item.label}
      </Link>
    </li>
  );
}

/** Účet dole v sidebare — email a odhlásenie v dropdowne. */
function UserMenu({ email, onNavigate }: { email: string; onNavigate: () => void }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="app-tap flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors hover:bg-[var(--app-surface-hover)]"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-[var(--app-border-strong)] bg-[var(--app-surface)] text-[11px] font-medium text-[var(--app-text-2)]">
            {email.slice(0, 1).toUpperCase()}
          </span>
          <span
            className="min-w-0 flex-1 truncate text-[12.5px] text-[var(--app-text-2)]"
            title={email}
          >
            {email}
          </span>
          <ChevronsUpDown
            className="h-3.5 w-3.5 shrink-0 text-[var(--app-text-4)]"
            strokeWidth={1.75}
          />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          side="top"
          align="start"
          sideOffset={6}
          className="app-scope z-[100] w-[214px] rounded-lg border border-[var(--app-border-strong)] bg-[#0e0e0e] p-1 shadow-[0_16px_48px_rgba(0,0,0,0.7)]"
        >
          <div className="px-2.5 py-2">
            <p className="truncate text-[12px] text-[var(--app-text-3)]" title={email}>
              {email}
            </p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-[var(--app-border)]" />
          <DropdownMenu.Item asChild>
            <Link
              href="/app/account"
              onClick={onNavigate}
              className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] text-[var(--app-text-2)] outline-none transition-colors data-[highlighted]:bg-[var(--app-surface-hover)] data-[highlighted]:text-[var(--app-text)]"
            >
              <Settings className="h-4 w-4" strokeWidth={1.75} />
              Account
            </Link>
          </DropdownMenu.Item>
          <DropdownMenu.Item asChild>
            <form action={signOutAction}>
              <button
                type="submit"
                className="flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px] text-[var(--app-text-2)] outline-none transition-colors data-[highlighted]:bg-[var(--app-surface-hover)] data-[highlighted]:text-[var(--app-text)]"
              >
                <LogOut className="h-4 w-4" strokeWidth={1.75} />
                Sign out
              </button>
            </form>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
