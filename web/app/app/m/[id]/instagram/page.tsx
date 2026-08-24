import type { Metadata } from "next";

import { InstagramConnect } from "@/components/app/instagram/connect";
import { Callout, PageHeader } from "@/components/app/ui";
import {
  INSTAGRAM_COLUMNS,
  INSTAGRAM_DEFAULTS,
  instagramConfigured,
  type InstagramRow,
} from "@/lib/instagram";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Instagram" };

/**
 * Pripojenie Instagramu — tretí agent modelky.
 *
 * Karta je zatiaľ len pre superadmina; stráži to `requireModelSubTab`
 * (`SUPERADMIN_TABS`), nie skrytie v tab bare. Cudziemu účtu sa tvári, že
 * neexistuje.
 *
 * Dôvod, prečo sa nedá pripojiť, sa zisťuje TU (server): chýbajúca konfigurácia
 * Meta appky je vec nasadenia, o ktorej prehliadač nič nevie a vedieť nemá.
 */
export default async function InstagramPage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/instagram">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "instagram", "index");
  const query = await searchParams;

  const supabase = await createClient();
  const { data } = await supabase
    .from("instagram")
    .select(INSTAGRAM_COLUMNS)
    .eq("model_id", model.id)
    .maybeSingle();

  // Chýbajúci riadok nie je chyba: modelka mohla vzniknúť pred migráciou.
  const row: InstagramRow = {
    ...INSTAGRAM_DEFAULTS,
    ...((data as Partial<InstagramRow>) ?? {}),
    model_id: model.id,
  };

  const chyba = typeof query.error === "string" ? query.error : "";
  const prave_pripojene = query.connected === "1";

  return (
    <>
      <PageHeader
        eyebrow="Instagram agent"
        title="Connect Instagram"
        description="The same persona as her Telegram agent, but writing the way Instagram allows — and pointing people to your Telegram or your link in bio, never straight to your paid page."
      />

      {chyba && (
        <div className="mb-4">
          <Callout tone="danger">{chyba}</Callout>
        </div>
      )}
      {prave_pripojene && (
        <div className="mb-4">
          <Callout tone="success">
            Connected. Her Instagram agent stays off until you switch it on in Settings.
          </Callout>
        </div>
      )}

      <InstagramConnect
        modelId={model.id}
        row={row}
        configured={instagramConfigured()}
      />
    </>
  );
}
