"use server";

import { revalidatePath } from "next/cache";

import { supabaseUrl } from "@/lib/env";
import { getModel } from "@/lib/models";
import { DAY_PARTS } from "@/lib/photos";
import { createClient } from "@/lib/supabase/server";

/**
 * Fotoknižnica. Súbor nahráva prehliadač priamo do bucketu `photos`
 * (storage policy z migrácie 007b pustí zápis len do priečinka vlastnej
 * modelky), tu už len evidujeme riadok a jeho metadáta.
 */

export type PhotoResult = { error?: string; ok?: boolean };

const BUCKET = "photos";

export async function createPhotoAction(
  modelId: string,
  input: { url: string; caption?: string },
): Promise<PhotoResult> {
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  // Klient nahráva priamo do bucketu a sem posiela public URL. Tá musí smerovať
  // na NÁŠ storage a do priečinka TEJTO modelky — inak by šlo do evidencie
  // podstrčiť cudziu/externú URL (leak, alebo cudzí obsah pod menom modelky).
  const allowedPrefix = `${supabaseUrl()}/storage/v1/object/public/${BUCKET}/${model.id}/`;
  if (!input.url.startsWith(allowedPrefix)) {
    return { error: "The upload did not return a usable link. Try again." };
  }

  const supabase = await createClient();
  const { error } = await supabase.from("photos").insert({
    model_id: model.id,
    url: input.url,
    caption: (input.caption ?? "").slice(0, 500),
  });

  if (error) return { error: error.message };
  revalidatePath(`/app/m/${model.id}/photos`);
  return { ok: true };
}

export async function updatePhotoAction(
  modelId: string,
  photoId: number,
  patch: Record<string, unknown>,
): Promise<PhotoResult> {
  const update: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(patch)) {
    switch (key) {
      case "caption":
      case "situation":
      case "collection":
        update[key] = typeof value === "string" ? value.slice(0, 500) : "";
        break;
      case "spicy":
      case "active":
        update[key] = Boolean(value);
        break;
      case "parts": {
        if (!Array.isArray(value)) return { error: "Unexpected value for parts." };
        const parts = value.filter(
          (part): part is string =>
            typeof part === "string" && (DAY_PARTS as readonly string[]).includes(part),
        );
        update.parts = Array.from(new Set(parts));
        break;
      }
      default:
        return { error: `Unknown field: ${key}` };
    }
  }

  if (Object.keys(update).length === 0) return {};

  const supabase = await createClient();
  const { error } = await supabase
    .from("photos")
    .update(update)
    .eq("id", photoId)
    .eq("model_id", modelId);

  if (error) return { error: error.message };
  revalidatePath(`/app/m/${modelId}/photos`);
  return { ok: true };
}

export async function deletePhotoAction(
  modelId: string,
  photoId: number,
): Promise<PhotoResult> {
  const supabase = await createClient();

  // Cestu v buckete si vytiahneme z URL — samostatný stĺpec na ňu nemáme.
  const { data: photo } = await supabase
    .from("photos")
    .select("id, url")
    .eq("id", photoId)
    .eq("model_id", modelId)
    .maybeSingle();

  if (!photo) return { error: "Photo not found." };

  const { error } = await supabase
    .from("photos")
    .delete()
    .eq("id", photoId)
    .eq("model_id", modelId);
  if (error) return { error: error.message };

  const path = storagePath(photo.url as string);
  if (path) {
    // Zlyhanie mazania súboru nesmie zhodiť akciu — riadok je preč, to je
    // to podstatné; osirelý objekt vieme upratať dávkovo.
    await supabase.storage.from(BUCKET).remove([path]);
  }

  revalidatePath(`/app/m/${modelId}/photos`);
  return { ok: true };
}

/** `…/object/public/photos/<model>/<file>.jpg` → `<model>/<file>.jpg` */
function storagePath(url: string): string | null {
  const marker = `/object/public/${BUCKET}/`;
  const index = url.indexOf(marker);
  if (index === -1) return null;
  return decodeURIComponent(url.slice(index + marker.length));
}
