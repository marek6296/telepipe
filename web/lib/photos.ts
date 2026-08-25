/** Fotoknižnica — hodnoty zdieľané klientom aj server actions. */

/**
 * Šesť pevných albumov. Slugy MUSIA sedieť s workerom (`photos.FOLDERS`
 * a `photos.folder_for`) — modelka posiela z albumu podľa toho, kde je práve
 * v harmonograme (v gyme → gym, v posteli ráno → bed_morning …). Klient len
 * naplní priečinky; priečinky samotné pridať ani ubrať nevie.
 */
export const FOLDERS = [
  "home",
  "gym",
  "city",
  "bed_morning",
  "bed_night",
  "universal",
] as const;

export type Folder = (typeof FOLDERS)[number];

export const FOLDER_LABEL: Record<Folder, string> = {
  home: "At home",
  gym: "At the gym",
  city: "Out in the city",
  bed_morning: "In bed — morning",
  bed_night: "In bed — at night",
  universal: "Universal",
};

export const FOLDER_HINT: Record<Folder, string> = {
  home: "Couch, kitchen, bathroom mirror — everyday indoor shots.",
  gym: "Workout, gym mirror, sporty outfits.",
  city: "Outside, in a café, in the car — anywhere she is out.",
  bed_morning: "Sleepy, just woke up, soft morning light.",
  bed_night: "Evening in bed, low light, winding down.",
  universal: "Fits any moment — sent when nothing more specific matches.",
};

export function isFolder(value: unknown): value is Folder {
  return typeof value === "string" && (FOLDERS as readonly string[]).includes(value);
}

export type PhotoRow = {
  id: number;
  model_id: string;
  url: string;
  caption: string;
  /** Kedy sa fotka hodí — poznámka pre modelku, nie text do chatu. */
  situation: string;
  folder: string;
  spicy: boolean;
  active: boolean;
  sent_count: number;
  created_at: string;
};

export const PHOTO_COLUMNS =
  "id, model_id, url, caption, situation, folder, spicy, active, sent_count, created_at";
