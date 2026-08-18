import type { Metadata } from "next";

import { FanvueSettingsForm } from "@/components/app/fanvue/settings-form";
import { ReplyModeForm } from "@/components/app/reply-mode-form";
import { PageHeader } from "@/components/app/ui";
import { getFanvueConnection, getFanvueSettings } from "@/lib/fanvue";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Fanvue settings",
};

/**
 * Nastavenia FANVUE agenta — tabuľka `fanvue`, nie `behavior`.
 *
 * Sú to dvaja agenti tej istej modelky: telegramový sa riadi kartou Persona,
 * tento týmto formulárom. Spoločná je persona, pamäť a časová zóna — je to tá
 * istá osoba a nesmie si protirečiť.
 */
export default async function FanvueSettingsPage({
  params,
}: PageProps<"/app/m/[id]/fanvue/settings">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "fanvue", "settings");

  const supabase = await createClient();
  const [connection, settings, { data: reply }] = await Promise.all([
    getFanvueConnection(model.id),
    getFanvueSettings(model.id),
    supabase
      .from("fanvue")
      .select("reply_mode, fallback_minutes")
      .eq("model_id", model.id)
      .maybeSingle(),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Fanvue agent"
        title="Fanvue settings"
        description="How she behaves on Fanvue: tempo, openness, when she offers content and when she stays quiet. Telegram has its own set on the Persona tab — same person, different register."
      />
      <div className="mb-5">
        <ReplyModeForm
          modelId={model.id}
          channel="fanvue"
          mode={String(reply?.reply_mode ?? "auto")}
          fallbackMinutes={
            reply?.fallback_minutes == null ? null : Number(reply.fallback_minutes)
          }
        />
      </div>
      <FanvueSettingsForm
        modelId={model.id}
        settings={settings}
        connected={connection.connected}
      />
    </>
  );
}
