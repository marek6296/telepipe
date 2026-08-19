import { adminErrorText } from "@/lib/admin-ui";
import { createClient } from "@/lib/supabase/server";

/**
 * Čítanie žiadostí o prístup pre admin panel.
 *
 * Ide cez RPC `admin_list_access_requests` volanú USER-scoped klientom — rovnaký
 * vzor ako `lib/admin.ts`. Funkcia je security definer s `where is_admin()`,
 * takže cudziemu vráti prázdno, nie cudzie dáta.
 */

export type AdminAccessRequest = {
  id: string;
  accountId: string;
  email: string;
  plan: string;
  status: "pending" | "approved" | "rejected";
  message: string;
  createdAt: string;
  decidedAt: string | null;
  decidedNote: string;
  decidedByEmail: string | null;
};

type Raw = {
  id: string;
  account_id: string;
  email: string | null;
  plan: string;
  status: string;
  message: string | null;
  created_at: string;
  decided_at: string | null;
  decided_note: string | null;
  decided_by_email: string | null;
};

export async function listAccessRequests(): Promise<AdminAccessRequest[]> {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_list_access_requests");
  if (error) throw new Error(adminErrorText(error.message));

  return ((data ?? []) as Raw[]).map((row) => ({
    id: row.id,
    accountId: row.account_id,
    email: row.email ?? "",
    plan: row.plan,
    status: row.status as AdminAccessRequest["status"],
    message: row.message ?? "",
    createdAt: row.created_at,
    decidedAt: row.decided_at,
    decidedNote: row.decided_note ?? "",
    decidedByEmail: row.decided_by_email,
  }));
}
