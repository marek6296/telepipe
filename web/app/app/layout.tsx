import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app/app-shell";
import { PageTransition } from "@/components/app/page-transition";
import { ChatDockMount } from "@/components/chat/chat-dock-mount";
import { isUnlocked } from "@/lib/access";
import { isAdminRole } from "@/lib/admin-ui";
import { toNumber } from "@/lib/format";
import { getAccount, listModels } from "@/lib/models";
import { unreadNotificationCount } from "@/lib/notifications";
import { getUser } from "@/lib/supabase/server";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
    noarchive: true,
    nocache: true,
  },
};

/**
 * Layout klientskej appky. Guard je síce už v `proxy.ts`, ale na dáta sa
 * spoliehať nemôžeme na middleware — každé čítanie ide user-scoped klientom
 * a RLS.
 */
export default async function AppLayout({ children }: LayoutProps<"/app">) {
  // Auth, účet aj sidebar sú od seba nezávislé a RLS chráni oba dátové dotazy.
  // Spustíme ich naraz, aby layout nevytváral sekvenčný waterfall.
  const [user, account, models, unread] = await Promise.all([
    getUser(),
    getAccount(),
    listModels(),
    unreadNotificationCount(),
  ]);
  if (!user) redirect("/login");

  // Zamknutý účet nemá v `/app` čo hľadať. Skutočný zámok je v RLS — toto je
  // len to, aby naň človek nenarazil ako na chybu z databázy.
  if (!isUnlocked(account)) redirect("/locked");

  return (
    <AppShell
      email={account?.email ?? user.email ?? "your account"}
      creditBalance={toNumber(account?.credit_balance_usd)}
      isAdmin={isAdminRole(account?.role)}
      unreadNotifications={unread}
      models={models.map((model) => ({
        id: model.id,
        name: model.name,
        status: model.status,
      }))}
    >
      <PageTransition>{children}</PageTransition>
      <ChatDockMount />
    </AppShell>
  );
}
