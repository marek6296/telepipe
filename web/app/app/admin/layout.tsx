import type { Metadata } from "next";

import { AdminTabs } from "@/components/app/admin/admin-tabs";
import { ToastProvider } from "@/components/app/admin/toast";
import { requireAdmin } from "@/lib/admin";

export const metadata: Metadata = {
  title: { default: "Admin", template: "%s · Admin" },
};

/**
 * Admin layout. Guard je tu aj v každej podstránke a v každej server action —
 * layout sa v Next.js pri client navigácii nemusí prerátať, takže sa naň
 * nespoliehame ako na jedinú obranu.
 */
export default async function AdminLayout({ children }: LayoutProps<"/app/admin">) {
  await requireAdmin();

  return (
    <ToastProvider>
      <AdminTabs />
      {children}
    </ToastProvider>
  );
}
