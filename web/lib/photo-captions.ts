/**
 * Popisky fotiek — poznámky PRE AGENTA, nie texty do chatu.
 *
 * PREČO CELÝ ALBUM NARAZ. Popisky sa nedajú písať po jednej: v jednom albume
 * má modelka spravidla to isté oblečenie, to isté prostredie a tú istú dennú
 * dobu. Keby sa každá fotka opisovala zvlášť, vznikli by tri rôzne pyžamá
 * v jednom večeri — a agent by na ne písal tri rôzne vety, ktoré si protirečia.
 * Model preto vidí VŠETKY fotky albumu naraz a najprv pomenuje, čo majú
 * spoločné.
 *
 * ČO JE `caption` A ČO `situation`
 * --------------------------------
 * `caption` = čo je na fotke. Ide do promptu ako „Je na nej: …", takže z toho
 * agent vie, čo poslal, a napíše k tomu vetu, ktorá na to sedí.
 * `situation` = kedy sa hodí. Z toho agent vie, či fotka sadne do chvíle,
 * v ktorej práve je.
 *
 * ANI JEDNO SA NIKDY NEPOŠLE FANÚŠIKOVI. Sú to interné poznámky; vetu do chatu
 * píše agent sám. Preto sú vecné a nie zvodné — „lying on the bed in a black
 * silk slip, warm lamp light" je dobrý popis, „mmm feeling naughty tonight 😈"
 * je nepoužiteľný.
 */

// Relatívne s príponou, nie cez `@/`: tento súbor spúšťa aj testovací skript
// obyčajným Node-om, ktorý alias z tsconfigu nepozná (rovnako `persona-wizard`).
import { FOLDERS, type Folder } from "./photos.ts";

/** Viac fotiek v jednom volaní už model prestáva držať konzistentne. */
export const MAX_PHOTOS = 12;

export const MAX_CAPTION = 200;
export const MAX_SITUATION = 120;

export type PhotoForCaption = { id: number; url: string };

export type CaptionDraft = { id: number; caption: string; situation: string };

/** Čo album znamená — bez toho model háda podľa obrázka, aj keď to vieme. */
const FOLDER_MEANING: Record<Folder, string> = {
  home: "at home during the day — living room, kitchen, bathroom, relaxed",
  gym: "at the gym or right after training",
  city: "out of the house — street, café, car, shopping",
  bed_morning: "in bed in the morning, just woke up",
  bed_night: "in bed late at night, winding down",
  universal: "anything that fits no matter where she is",
};

export function folderMeaning(folder: string): string {
  return FOLDER_MEANING[folder as Folder] ?? FOLDER_MEANING.universal;
}

export function isKnownFolder(value: string): value is Folder {
  return (FOLDERS as readonly string[]).includes(value);
}

export function systemPrompt(modelName: string, folder: string): string {
  const name = modelName.trim() || "the model";
  return [
    `You are cataloguing photos of ${name} so that her chat agent knows what it`,
    "is sending. These notes are INTERNAL. They are never shown to anyone and",
    "never sent as a message — the agent writes its own line when it sends the",
    `photo. Write plain, factual English, no flirting, no emoji, no first person.`,
    "",
    `All of these photos belong to one album: ${folderMeaning(folder)}.`,
    "",
    "Look at every photo before you write anything, then:",
    "",
    "1. Work out what the photos SHARE — same outfit, same room, same light,",
    "   same time of day. Photos in one album are usually one session.",
    "2. Describe each photo so the shared things are described the SAME WAY in",
    "   each one. If she wears a black silk slip in three of them, all three say",
    "   a black silk slip — not 'lingerie', 'nightwear' and 'a black top'.",
    "3. Then name what makes each photo different (pose, framing, what she does).",
    "",
    "For every photo return:",
    '- "caption": what is in the picture — outfit, place, light, what she is',
    `  doing. Max ${MAX_CAPTION} characters. This is how the agent knows what it`,
    "  just sent, so be concrete.",
    '- "situation": when this photo fits in a conversation — time of day and',
    `  mood. Max ${MAX_SITUATION} characters. Example: "late evening, already in`,
    '  bed, talking softly".',
    "",
    "If a photo does not belong to this album at all (a gym selfie in a night-in-",
    'bed album), say so plainly in the caption — the owner needs to see it.',
    "",
    "Answer as JSON only:",
    '{"shared":"one sentence about what the album has in common",',
    ' "photos":[{"index":1,"caption":"…","situation":"…"}]}',
    "",
    "Use the index numbers exactly as they are labelled. Return every photo.",
  ].join("\n");
}

function text(value: unknown, limit: number): string {
  if (typeof value !== "string") return "";
  return value.replace(/\s+/g, " ").trim().slice(0, limit);
}

/**
 * Odpoveď modelu → popisky pripravené na zápis.
 *
 * Fotky sa páruje cez INDEX, ktorý sme sami očíslovali, nie cez id: keby model
 * dostal skutočné id, mohol by si ho vymyslieť a popis by sadol na cudziu
 * fotku. Index mimo rozsahu sa zahodí.
 */
export function mapCaptions(
  parsed: unknown,
  photos: PhotoForCaption[],
): { drafts: CaptionDraft[]; shared: string; errors: string[] } {
  const errors: string[] = [];
  if (!parsed || typeof parsed !== "object") {
    return { drafts: [], shared: "", errors: ["The answer was not an object."] };
  }
  const root = parsed as Record<string, unknown>;
  const rows = root.photos;
  if (!Array.isArray(rows)) {
    return { drafts: [], shared: "", errors: ["The answer had no photos."] };
  }

  const drafts: CaptionDraft[] = [];
  const pouzite = new Set<number>();

  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const item = row as Record<string, unknown>;
    const index = Number(item.index);
    if (!Number.isInteger(index) || index < 1 || index > photos.length) {
      errors.push(`Photo ${item.index} is not in this album.`);
      continue;
    }
    if (pouzite.has(index)) continue;
    const caption = text(item.caption, MAX_CAPTION);
    if (!caption) {
      errors.push(`Photo ${index} came back without a caption.`);
      continue;
    }
    pouzite.add(index);
    drafts.push({
      id: photos[index - 1].id,
      caption,
      situation: text(item.situation, MAX_SITUATION),
    });
  }

  // Chýbajúca fotka nie je dôvod zahodiť celý album — zapíšeme, čo prišlo, a
  // povieme, čo chýba. Klient inak platí za volanie a nedostane nič.
  if (drafts.length < photos.length) {
    errors.push(`${photos.length - drafts.length} photo(s) came back empty.`);
  }
  return { drafts, shared: text(root.shared, 300), errors };
}
