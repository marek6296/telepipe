import type { Metadata } from "next";

import { FanvueSettingsForm } from "@/components/app/fanvue/settings-form";
import { PageHeader } from "@/components/app/ui";
import { getFanvueConnection, getFanvueSettings } from "@/lib/fanvue";
import { requireModelSubTab } from "@/lib/models";

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

  const [connection, settings] = await Promise.all([
    getFanvueConnection(model.id),
    getFanvueSettings(model.id),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Fanvue agent"
        title="Fanvue settings"
        description="How she behaves on Fanvue: tempo, openness, when she offers content and when she stays quiet. Telegram has its own set on the Persona tab — same person, different register."
      />
      <FanvueSettingsForm
        modelId={model.id}
        settings={settings}
        connected={connection.connected}
      />
    </>
  );
}
