import { redirect } from "next/navigation";

import { AppShell } from "@/components/app/app-shell";
import { toNumber } from "@/lib/format";
import { getAccount, listModels } from "@/lib/models";
import { getUser } from "@/lib/supabase/server";

/**
 * Layout klientskej appky. Guard je síce už v `proxy.ts`, ale na dáta sa
 * spoliehať nemôžeme na middleware — každé čítanie ide user-scoped klientom
 * a RLS.
 */
export default async function AppLayout({ children }: LayoutProps<"/app">) {
  const user = await getUser();
  if (!user) redirect("/login");

  const [account, models] = await Promise.all([getAccount(), listModels()]);

  return (
    <AppShell
      email={account?.email ?? user.email ?? "your account"}
      creditBalance={toNumber(account?.credit_balance_usd)}
      models={models.map((model) => ({
        id: model.id,
        name: model.name,
        status: model.status,
      }))}
    >
      {children}
    </AppShell>
  );
}
