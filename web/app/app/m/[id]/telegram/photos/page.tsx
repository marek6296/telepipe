import type { Metadata } from "next";

import { PhotoLibrary } from "@/components/app/photos/photo-library";
import { requireModelSubTab } from "@/lib/models";
import { PHOTO_COLUMNS, type PhotoRow } from "@/lib/photos";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Photos",
};

/**
 * Fotky sedia pod Telegramom, lebo tam a nikde inde odchádzajú — Fanvue má
 * vlastný vault (`/fanvue/photos`) a fotku z neho posiela ich API.
 */
export default async function PhotosPage({
  params,
}: PageProps<"/app/m/[id]/telegram/photos">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "telegram", "photos");

  const supabase = await createClient();
  const [{ data }, { data: behavior }] = await Promise.all([
    supabase
      .from("photos")
      .select(PHOTO_COLUMNS)
      .eq("model_id", model.id)
      .order("created_at", { ascending: false }),
    supabase.from("behavior").select("photos_enabled").eq("model_id", model.id).maybeSingle(),
  ]);

  return (
    <PhotoLibrary
      modelId={model.id}
      photos={(data ?? []) as unknown as PhotoRow[]}
      photosEnabled={Boolean(behavior?.photos_enabled)}
    />
  );
}
