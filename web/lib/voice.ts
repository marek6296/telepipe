/**
 * Čo hlasový reťazec naozaj vie — jedno miesto pre kartu Voice aj pre štúdio.
 *
 * Každá hodnota tu má proťajšok vo workeri a keby sa rozišli, klient by si
 * nastavil niečo, čo sa nikdy neprehrá:
 *
 *   miestnosti  → `eleven.AMBIENCES` (prompt na pozadie)
 *                 ∩ `livevoice._AMBIENCE_MIX` (filter pod hlasom)
 *   kvalita     → `livevoice._RECIPES` (pásmo, bitrate, bit-crush, sykot)
 *   tempo       → `livevoice._tempo_filter` reže na 0.5–2.0, čo je presne
 *                 rozsah jedného ffmpeg `atempo`
 *   pozadie     → `livevoice.ambience_mix` násobí nastavenú hodnotu ziskom
 *                 miestnosti; 0 je ticho, 1 je strop
 *
 * Overené v `docs/settings-audit.md` (sekcia Voice tab). Kto sem pridá
 * ďalšiu miestnosť alebo posunie rozsah, musí to spraviť aj tam — inak
 * ElevenLabs dostane prázdny prompt a hlas pôjde bez pozadia.
 *
 * ZÁMERNE TU NIE JE nič, čo pipeline nevie: emócie, pauzy, výška hlasu ani
 * hlasitosť samotného hlasu. Tie sa nastaviť nedajú a políčko na ne by bolo
 * len sľub, ktorý nikto nesplní.
 */

export const VOICE_AMBIENCES = [
  { value: "home", label: "At home" },
  { value: "bedroom", label: "Bedroom" },
  { value: "kitchen", label: "Kitchen" },
  { value: "bathroom", label: "Bathroom" },
  { value: "car", label: "In the car" },
  { value: "outside", label: "Outside" },
  { value: "cafe", label: "Café" },
  { value: "gym", label: "Gym" },
  { value: "none", label: "Silent" },
] as const;

export const VOICE_STRENGTHS = [
  { value: "soft", label: "Soft — clean studio" },
  { value: "real", label: "Real — like a phone" },
  { value: "rough", label: "Rough — noisy room" },
] as const;

/** `livevoice._tempo_filter` reže presne sem; mimo toho `atempo` neprejde. */
export const TEMPO_MIN = 0.5;
export const TEMPO_MAX = 2;
export const TEMPO_DEFAULT = 1.12;

/** Strop hlasitosti miestnosti. Worker si z nej ešte uberá (jitter 0.6–1.0). */
export const AMBIENCE_LEVEL_MIN = 0;
export const AMBIENCE_LEVEL_MAX = 1;
export const AMBIENCE_LEVEL_DEFAULT = 0.05;

export const AMBIENCE_DEFAULT = "home";
export const STRENGTH_DEFAULT = "rough";

/**
 * Strop textu v ukážke hlasu.
 *
 * Pôvodných 400 znakov vychádzalo z toho, aká dlhá býva SKUTOČNÁ hlasovka
 * v chate — tie sú krátke a to je správne. Lenže tu sa hlas ladí, a ladiace
 * scenáre sú dlhšie: samotné značky (`[whispers]`, `[long pause]`, `[sighs]`)
 * zožerú polovicu miesta bez toho, aby pribudlo hovorené slovo.
 *
 * Nejaký strop tu ostáva zámerne. Nie kvôli ElevenLabs (ten znesie rádovo
 * viac), ale preto, že dlhší text = dlhšia nahrávka, väčší súbor a viac
 * minútovaného kreditu za jedno kliknutie. 1500 znakov je ~3–4 minúty
 * scenára so značkami, čo na doladenie hlasu bohato stačí.
 *
 * Platí LEN na ukážky. Dĺžku hlasoviek, ktoré modelka naozaj posiela,
 * riadi prompt, nie táto konštanta.
 */
export const PREVIEW_TEXT_MAX = 1500;

export type VoiceSound = {
  ambience: string;
  strength: string;
  tempo: number;
  ambience_level: number;
};

export function ambienceLabel(value: string): string {
  return VOICE_AMBIENCES.find((row) => row.value === value)?.label ?? value;
}

export function strengthLabel(value: string): string {
  // V zozname ukážok je miesto len na jedno slovo — dlhý popis patrí k poľu.
  return value ? value[0].toUpperCase() + value.slice(1) : "—";
}

export function isAmbience(value: string): boolean {
  return VOICE_AMBIENCES.some((row) => row.value === value);
}

export function isStrength(value: string): boolean {
  return VOICE_STRENGTHS.some((row) => row.value === value);
}

/* --------------------------------------------------------------------------
   Vety na ukážku
--------------------------------------------------------------------------- */
/**
 * Prázdne pole by znamenalo, že si klient musí vetu vymyslieť skôr, než vôbec
 * počuje, ako znie. Sú tri, lebo každá skúša inú vec: prvá pokoj, druhá to,
 * čo naozaj chodí do chatu, tretia krátku vetu, na ktorej je najlepšie počuť
 * pozadie a telefónny zvuk.
 */
export const SAMPLE_LINES = [
  "haha i dont even know, i was on my feet all day and now im just laying here doing nothing",
  "hey you, i was literally just thinking about you and then your message popped up",
  "okay im heading out but text me later, i wanna hear how your day went",
] as const;

/* --------------------------------------------------------------------------
   Prečo ukážka nevznikla
--------------------------------------------------------------------------- */
/**
 * Kódy píše worker (`userbot.VOICE_JOB_*`), vety patria sem — worker hovorí
 * po slovensky a klient číta po anglicky. Neznámy kód sa ukáže tak, ako
 * prišiel: surová chyba z ffmpegu je vždy užitočnejšia než „something went
 * wrong", aj keď vyzerá škaredo.
 */
const JOB_ERRORS: Record<string, string> = {
  no_eleven_key:
    "ElevenLabs is not connected on this account. Add the key in Account settings and try again.",
  no_voice_selected: "No voice picked yet. Choose one above, then generate again.",
  no_audio:
    "ElevenLabs did not return any audio. That is usually a rejected key or an empty quota — check your ElevenLabs account.",
};

export function voiceJobError(code: string): string {
  const raw = (code ?? "").trim();
  if (!raw) return "";
  return JOB_ERRORS[raw] ?? raw;
}
