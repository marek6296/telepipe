import type { Metadata } from "next";

import { PhotoLibrary } from "@/components/app/photos/photo-library";
import { requireModelTab } from "@/lib/models";
import { PHOTO_COLUMNS, type PhotoRow } from "@/lib/photos";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Photos",
};

export default async function PhotosPage({ params }: PageProps<"/app/m/[id]/photos">) {
  const { id } = await params;
  const model = await requireModelTab(id, "photos");

  const supabase = await createClient();
  const { data } = await supabase
    .from("photos")
    .select(PHOTO_COLUMNS)
    .eq("model_id", model.id)
    .order("created_at", { ascending: false });

  return (
    <PhotoLibrary modelId={model.id} photos={(data ?? []) as unknown as PhotoRow[]} />
  );
}
