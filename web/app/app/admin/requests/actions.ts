"use server";

import { revalidatePath } from "next/cache";

import { requireAdmin } from "@/lib/admin";
import { adminErrorText } from "@/lib/admin-ui";
import { createClient } from "@/lib/supabase/server";

export type DecideResult = { error?: string; status?: string };

/**
 * Schválenie / zamietnutie žiadosti.
 *
 * Guard je tu aj v layoute aj vnútri RPC — layout sa pri client navigácii
 * nemusí prerátať, takže sa naň nespoliehame ako na jedinú obranu (vzor z 009).
 */
export async function decideRequestAction(
  requestId: string,
  approve: boolean,
  note: string,
): Promise<DecideResult> {
  await requireAdmin();

  const supabase = await createClient();
  const { data, error } = await supabase.rpc("admin_decide_access_request", {
    p_id: requestId,
    p_approve: approve,
    p_note: note.slice(0, 500),
  });

  if (error) return { error: adminErrorText(error.message) };

  revalidatePath("/app/admin/requests");
  revalidatePath("/app/admin/users");
  return { status: String(data) };
}
