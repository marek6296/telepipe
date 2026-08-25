"use server";

import { revalidatePath } from "next/cache";

import { OUT_OF_CREDITS_MSG, creditState, hasCredit, recordUsage } from "@/lib/credits";
import { supabaseUrl } from "@/lib/env";
import { chatVisionJson, llmConfigured, llmVisionModel, parseJsonish, type VisionPart } from "@/lib/llm";
import { getModel } from "@/lib/models";
import {
  MAX_PHOTOS,
  mapCaptions,
  systemPrompt,
  type PhotoForCaption,
} from "@/lib/photo-captions";
import { isFolder } from "@/lib/photos";
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
  input: { url: string; folder: string; caption?: string },
): Promise<PhotoResult> {
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };

  // Album je pevný — fotka musí padnúť do jedného zo šiestich priečinkov,
  // inak by ju modelka nikdy nevytiahla (`photos.folder_for`).
  if (!isFolder(input.folder)) return { error: "Unknown album." };

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
    folder: input.folder,
    caption: (input.caption ?? "").slice(0, 500),
  });

  if (error) return { error: error.message };
  revalidatePath(`/app/m/${model.id}/telegram/photos`);
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
        update[key] = typeof value === "string" ? value.slice(0, 500) : "";
        break;
      case "situation":
        update[key] = typeof value === "string" ? value.slice(0, 300) : "";
        break;
      case "spicy":
      case "active":
        update[key] = Boolean(value);
        break;
      case "folder":
        if (!isFolder(value)) return { error: "Unknown album." };
        update.folder = value;
        break;
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
  revalidatePath(`/app/m/${modelId}/telegram/photos`);
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

  revalidatePath(`/app/m/${modelId}/telegram/photos`);
  return { ok: true };
}

/** `…/object/public/photos/<model>/<file>.jpg` → `<model>/<file>.jpg` */
function storagePath(url: string): string | null {
  const marker = `/object/public/${BUCKET}/`;
  const index = url.indexOf(marker);
  if (index === -1) return null;
  return decodeURIComponent(url.slice(index + marker.length));
}

/* --------------------------------------------------------------------------
   Popisky celého albumu naraz
-------------------------------------------------------------------------- */

export type CaptionsResult = {
  error?: string;
  written?: number;
  shared?: string;
  warnings?: string[];
};

/**
 * Napíše popisky VŠETKÝM fotkám jedného albumu naraz.
 *
 * Naraz zámerne: v jednom albume má modelka spravidla to isté oblečenie a to
 * isté prostredie, a po jednej by z toho vyšli tri rôzne pyžamá v jednom
 * večeri. Podrobnosti a formát → `lib/photo-captions.ts`.
 *
 * Popisky sú poznámky PRE AGENTA (čo je na fotke, kedy sa hodí), nikdy nie
 * text do chatu — vetu k fotke si agent napíše sám.
 */
export async function generateFolderCaptionsAction(
  modelId: string,
  folder: string,
  options: { overwrite?: boolean } = {},
): Promise<CaptionsResult> {
  const model = await getModel(modelId);
  if (!model) return { error: "Model not found." };
  if (!isFolder(folder)) return { error: "Unknown album." };
  if (!llmConfigured()) {
    return { error: "The AI helper is not switched on for this deployment." };
  }

  // Zostatok sa kontroluje PRED volaním — inak by účet bez kreditu popisky
  // vygeneroval a dozvedel sa o tom až z faktúry.
  const credit = await creditState();
  if (!hasCredit(credit)) return { error: OUT_OF_CREDITS_MSG };

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("photos")
    .select("id, url, caption")
    .eq("model_id", model.id)
    .eq("folder", folder)
    .order("id", { ascending: true });

  if (error) return { error: error.message };

  const vsetky = (data ?? []) as { id: number; url: string; caption: string }[];
  // Bez `overwrite` sa ručne napísaný popis nechá tak — klient si ho mohol
  // opraviť práve preto, že model netrafil.
  const cielove = options.overwrite
    ? vsetky
    : vsetky.filter((photo) => !(photo.caption || "").trim());

  if (cielove.length === 0) {
    return vsetky.length === 0
      ? { error: "This album is empty." }
      : { error: "Every photo here already has a caption." };
  }

  const davka: PhotoForCaption[] = cielove.slice(0, MAX_PHOTOS);
  const parts: VisionPart[] = [
    {
      type: "text",
      text: `Album: ${folder}. ${davka.length} photo(s), numbered in order.`,
    },
  ];
  davka.forEach((photo, index) => {
    parts.push({ type: "text", text: `Photo ${index + 1}:` });
    parts.push({ type: "image_url", image_url: { url: photo.url } });
  });

  const result = await chatVisionJson(systemPrompt(model.name, folder), parts, {
    maxTokens: 2000,
    // Nízka teplota: toto je katalogizácia, nie písanie. Pri vysokej si model
    // vymýšľa detaily, ktoré na fotke nie sú — a agent ich potom povie nahlas.
    temperature: 0.3,
  });

  // Účtujeme vždy, aj pri páde: poskytovateľ si tokeny z každého pokusu berie.
  await recordUsage(model.id, "builder", llmVisionModel(), result.usage);

  if (!result.ok) return { error: result.error ?? "The AI helper did not answer." };

  const parsed = parseJsonish(result.content);
  if (parsed === undefined) return { error: "The answer was not valid JSON." };

  const { drafts, shared, errors } = mapCaptions(parsed, davka);
  if (drafts.length === 0) {
    return { error: errors[0] ?? "Nothing came back. Try again." };
  }

  // Zapisuje sa po jednej: PostgREST hromadný update by musel ísť cez upsert
  // a ten na tabuľke so stĺpcovými grantmi padá aj bez konfliktu.
  let written = 0;
  for (const draft of drafts) {
    const { error: writeError } = await supabase
      .from("photos")
      .update({ caption: draft.caption, situation: draft.situation })
      .eq("id", draft.id)
      .eq("model_id", model.id);
    if (writeError) {
      errors.push(writeError.message);
      continue;
    }
    written += 1;
  }

  if (written === 0) return { error: errors[0] ?? "Could not save the captions." };

  const zvysok = cielove.length - davka.length;
  if (zvysok > 0) {
    errors.push(`${zvysok} more photo(s) left — run it again for those.`);
  }

  revalidatePath(`/app/m/${model.id}/telegram/photos`);
  return { written, shared, warnings: errors };
}
