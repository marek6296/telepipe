import type { Metadata } from "next";

import { UsersTable } from "@/components/app/admin/users-table";
import { PageHeader, StatTile } from "@/components/app/ui";
import { listAdminAccounts, requireAdmin } from "@/lib/admin";
import { compactNumber, usd, usdPrecise } from "@/lib/format";
import { requireUser } from "@/lib/models";

export const metadata: Metadata = {
  title: "Users",
};

export default async function AdminUsersPage() {
  // Guard je aj v layoute — tu znovu, lebo stránka sa môže vyrenderovať sama.
  const viewerRole = await requireAdmin();
  const [viewer, accounts] = await Promise.all([requireUser(), listAdminAccounts()]);

  const credits = accounts.reduce((sum, account) => sum + account.creditBalance, 0);
  const spend30 = accounts.reduce((sum, account) => sum + account.spend30d, 0);
  const admins = accounts.filter((account) => account.role !== "user").length;

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        title="Users"
        description="Every account on the platform — plan, credit and role. Changes take effect immediately."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Accounts" value={compactNumber(accounts.length)} />
        <StatTile label="Admins" value={compactNumber(admins)} hint="admin or superadmin" />
        <StatTile label="Credits" value={usd(credits)} hint="outstanding balance" />
        <StatTile label="Spend 30d" value={usdPrecise(spend30)} hint="charged to clients" />
      </div>

      <UsersTable
        accounts={accounts.map((account) => ({
          id: account.id,
          email: account.email,
          role: account.role,
          plan: account.plan,
          creditBalance: account.creditBalance,
          createdAt: account.createdAt,
          modelsCount: account.modelsCount,
          spend30d: account.spend30d,
        }))}
        viewerRole={viewerRole}
        viewerId={viewer.id}
      />
    </>
  );
}
