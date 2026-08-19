import { RequestsTable } from "@/components/app/admin/requests-table";
import { PageHeader } from "@/components/app/ui";
import { listAccessRequests } from "@/lib/access-admin";
import { requireAdmin } from "@/lib/admin";

export const metadata = { title: "Requests" };

export default async function AdminRequestsPage() {
  await requireAdmin();
  const rows = await listAccessRequests();
  const pending = rows.filter((row) => row.status === "pending").length;

  return (
    <>
      <PageHeader
        title="Access requests"
        description={
          pending === 0 ? "Nothing waiting." : `${pending} waiting for a decision.`
        }
      />
      <RequestsTable rows={rows} />
    </>
  );
}
