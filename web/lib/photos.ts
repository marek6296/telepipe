/** Fotoknižnica — hodnoty zdieľané klientom aj server actions. */

/**
 * Časti dňa, na ktoré sa fotka hodí. Hodnoty MUSIA sedieť s workerom
 * (`behavior.part_of_day`) — sú v slovenčine, lebo tak ich číta predloha;
 * do UI ich prekladáme.
 */
export const DAY_PARTS = ["poobede", "podvecer", "vecer", "noc"] as const;

export type DayPart = (typeof DAY_PARTS)[number];

export const DAY_PART_LABEL: Record<DayPart, string> = {
  poobede: "Afternoon",
  podvecer: "Early evening",
  vecer: "Evening",
  noc: "Night",
};

export const DAY_PART_HOURS: Record<DayPart, string> = {
  poobede: "11:00–16:00",
  podvecer: "16:00–20:00",
  vecer: "20:00–24:00",
  noc: "00:00–11:00",
};

export type PhotoRow = {
  id: number;
  model_id: string;
  url: string;
  caption: string;
  situation: string;
  parts: string[];
  spicy: boolean;
  active: boolean;
  collection: string;
  sent_count: number;
  created_at: string;
};

export const PHOTO_COLUMNS =
  "id, model_id, url, caption, situation, parts, spicy, active, collection, sent_count, created_at";
