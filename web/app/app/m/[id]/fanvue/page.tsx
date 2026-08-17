import type { Metadata } from "next";

import { FanvueConnectCard } from "@/components/app/fanvue/connect-card";
import { FanvueSettingsForm } from "@/components/app/fanvue/settings-form";
import { FanvueVault } from "@/components/app/fanvue/vault";
import { PageHeader } from "@/components/app/ui";
import { fanvueConfigured } from "@/lib/env";
import {
  getFanvueConnection,
  getFanvueSettings,
  getLatestSyncRequest,
  listFvFolders,
  listFvMedia,
} from "@/lib/fanvue";
import { requireModelTab } from "@/lib/models";

export const metadata: Metadata = {
  title: "Fanvue",
};

/**
 * Karta Fanvue: pripojenie, nastavenia agenta a vault.
 *
 * Stav aj nastavenia sa čítajú user-scoped klientom, takže RLS cudzí riadok
 * nevráti a šifrované tokeny sa do prehliadača nedostanú ani omylom — na
 * `*_enc` stĺpce `authenticated` grant nemá (migrácia 011). Nastavenia,
 * priečinky a médiá zapisuje tou istou cestou (migrácia 015).
 *
 * `?error=` sem posiela `/api/fanvue/callback`, keď prihlásenie neprejde.
 *
 * Fanvue je vec `persona` agenta — firemný ani osobný ho mať nebudú. Tab sa im
 * nevykreslí (`MODEL_TYPE_TABS`), ale ručne zadaná URL musí skončiť rovnako,
 * inak by tá mapa bola len kozmetika.
 */
export default async function FanvuePage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/fanvue">) {
  const { id } = await params;
  const { error } = await searchParams;
  const model = await requireModelTab(id, "fanvue");

  const fanvue = await getFanvueConnection(model.id);
  const [settings, folders, media, lastSync] = await Promise.all([
    getFanvueSettings(model.id),
    listFvFolders(model.id),
    listFvMedia(model.id),
    getLatestSyncRequest(model.id),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Fanvue agent"
        title={fanvue.connected ? "Fanvue is connected" : "Connect Fanvue"}
        description="Her second agent. Telegram brings people in; here they have already paid, so she never mentions Fanvue and sells content instead. Same persona and memory, separate settings."
      />

      <div className="flex flex-col gap-5">
        <FanvueConnectCard
          modelId={model.id}
          fanvue={fanvue}
          configured={fanvueConfigured()}
          error={typeof error === "string" ? error : ""}
        />

        <FanvueVault
          modelId={model.id}
          connected={fanvue.connected}
          folders={folders}
          media={media}
          lastSync={lastSync}
          mediaSyncedAt={settings.media_synced_at}
        />

        <FanvueSettingsForm
          modelId={model.id}
          settings={settings}
          connected={fanvue.connected}
        />
      </div>
    </>
  );
}
