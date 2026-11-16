import type { Metadata } from "next";
import Link from "next/link";

import { ConversationControls, type SharedIdentity, type QueueAction, type ApprovedPhoto } from "@/components/app/instagram/conversation-controls";
import { InstagramSettingsForm } from "@/components/app/instagram/settings-form";
import { PageHeader } from "@/components/app/ui";
import {
  INSTAGRAM_COLUMNS,
  INSTAGRAM_DEFAULTS,
  type InstagramRow,
} from "@/lib/instagram";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Instagram settings" };

/**
 * Nastavenia Instagram agenta — čo je na Instagrame iné než inde.
 *
 * Persona, jazyky a denný život tu zámerne nie sú: je to tá istá osoba na
 * tretej platforme, nie tretia osoba. Rozdiel je v tom, ako ďaleko smie zájsť
 * a kam ľudí posiela.
 */
export default async function InstagramSettingsPage({
  params,
}: PageProps<"/app/m/[id]/instagram/settings">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "instagram", "settings");

  const supabase = await createClient();
  const { data } = await supabase
    .from("instagram")
    .select(INSTAGRAM_COLUMNS)
    .eq("model_id", model.id)
    .maybeSingle();

  const row: InstagramRow = {
    ...INSTAGRAM_DEFAULTS,
    ...((data as Partial<InstagramRow>) ?? {}),
    model_id: model.id,
  };

  const [identities, queue, takeovers, photos] = await Promise.all([
    supabase.from("conversation_identities").select("id,platform,external_id,username,display_name,status,candidate_id").eq("model_id", model.id).order("updated_at", {ascending: false}).limit(200),
    supabase.from("instagram_actions").select("id,kind,igsid,state,due_at,reason,text").eq("model_id", model.id).order("created_at", {ascending: false}).limit(50),
    supabase.from("ig_users").select("igsid,username").eq("model_id", model.id).eq("human_takeover", true).limit(100),
    supabase.from("photos").select("id,url,caption,instagram_approved").eq("model_id", model.id).eq("active", true).eq("spicy", false).limit(200),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Instagram agent"
        title="Instagram settings"
        description="How she behaves on Instagram and where she sends people. Who she is — her story, her languages, her day — is shared with her other agents and lives on the Persona tab."
      />
      <InstagramSettingsForm row={row} />
      <ConversationControls modelId={model.id} identities={(identities.data ?? []) as SharedIdentity[]}
        queue={(queue.data ?? []) as QueueAction[]} takeovers={takeovers.data ?? []} photos={(photos.data ?? []) as ApprovedPhoto[]}
        syncStatus={row.sync_status} testUntil={row.test_until} circuitUntil={row.circuit_until} />

      <p className="mt-5 px-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        Not connected yet, or need to reconnect?{" "}
        <Link
          href={`/app/m/${model.id}/instagram`}
          className="underline underline-offset-2 transition-colors hover:text-[var(--app-text-2)]"
        >
          The Connect tab
        </Link>{" "}
        has the setup steps.
      </p>
    </>
  );
}
