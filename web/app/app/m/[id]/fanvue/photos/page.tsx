import type { Metadata } from "next";

import { FanvueVault } from "@/components/app/fanvue/vault";
import { PageHeader } from "@/components/app/ui";
import {
  getFanvueConnection,
  getFanvueSettings,
  getLatestSyncRequest,
  listFvFolders,
  listFvMedia,
} from "@/lib/fanvue";
import { requireModelSubTab } from "@/lib/models";

export const metadata: Metadata = {
  title: "Fanvue photos",
};

/**
 * Vault — fotky, ktoré na Fanvue už sú.
 *
 * Zámerne to NIE JE tá istá obrazovka ako Telegram → Photos: tam si klient
 * knižnicu nahráva k nám, tu len hovorí, na čo je ktorý priečinok, čo na fotke
 * je a koľko stojí. Vlastnú kópiu vaultu by sme aj tak neposielali — do správy
 * na Fanvue sa dá priložiť len médium, ktoré u nich existuje.
 */
export default async function FanvuePhotosPage({
  params,
}: PageProps<"/app/m/[id]/fanvue/photos">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "fanvue", "photos");

  const [connection, settings, folders, media, lastSync] = await Promise.all([
    getFanvueConnection(model.id),
    getFanvueSettings(model.id),
    listFvFolders(model.id),
    listFvMedia(model.id),
    getLatestSyncRequest(model.id),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Fanvue agent"
        title="Vault"
        description="Her Fanvue media, as she sees it. You upload on Fanvue; here you say what each folder is for, what is in the photo and what it costs — without a price, a paid photo never gets sent."
      />
      <FanvueVault
        modelId={model.id}
        connected={connection.connected}
        folders={folders}
        media={media}
        lastSync={lastSync}
        mediaSyncedAt={settings.media_synced_at}
      />
    </>
  );
}
