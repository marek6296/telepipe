/**
 * Fanvue konverzácie — spoločné typy a štítky (client-safe).
 *
 * Dvojča `lib/chats.ts`, ale iná tabuľka a iný svet: v Telegrame človek ešte
 * nezaplatil a celý funnel je o tom dostať ho na Fanvue (`cold → converted`).
 * Tu už zaplatil — fázy sú len dve (`discovery` → `known`, viď
 * `worker/src/fanvue_agent.phase`) a to zaujímavé číslo nie je fáza, ale koľko
 * u nej minul.
 *
 * Čítanie je výhradne na pozeranie: `fv_users`/`fv_messages` majú pre
 * `authenticated` iba SELECT policy majiteľa (migrácia 012). Zapísať do histórie
 * by znamenalo podsunúť jej slová, ktoré nikdy nepovedala.
 */

export const FV_STAGE_LABEL: Record<string, string> = {
  discovery: "Getting to know him",
  known: "Knows him",
};

export const FV_STAGE_STYLE: Record<string, string> = {
  discovery: "border-[#1f1f1f] text-[#71717a]",
  known: "border-[#3f3f46] text-[#d4d4d8]",
};

export const FV_STAGE_HINT: Record<string, string> = {
  discovery: "Still asking what he is here for.",
  known: "She knows what he wants and leads the conversation by it.",
};

export type FvUserRow = {
  fan_uuid: string;
  handle: string;
  display_name: string;
  tg_id: number | null;
  ai_enabled: boolean;
  human_takeover: boolean;
  msg_count: number;
  spent_cents: number;
  bought_count: number;
  offers_sent: number;
  free_photos: number;
  voices_sent: number;
  summary: string;
  facts: string;
  wants: string;
  stage: string;
  first_seen: string;
  last_incoming_at: string | null;
  last_reply_at: string | null;
  last_bought_at: string | null;
};

/**
 * Stĺpce vymenované ručne — `select('*')` je tu síce priechodný (grant je na
 * celú tabuľku), ale zoznam drží stránku a typ v zhode. `avatar_url` chýba
 * zámerne: obrázky sú na ich CDN a `next/image` má povolený len náš storage.
 */
export const FV_USER_COLUMNS =
  "fan_uuid, handle, display_name, tg_id, ai_enabled, human_takeover, msg_count, " +
  "spent_cents, bought_count, offers_sent, free_photos, voices_sent, summary, " +
  "facts, wants, stage, first_seen, last_incoming_at, last_reply_at, last_bought_at";

export type FvMessageRow = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

/** Meno do zoznamu: ako sa volá → @handle → skrátené uuid. */
export function fvChatTitle(user: FvUserRow): string {
  return (
    user.display_name?.trim() ||
    (user.handle ? `@${user.handle}` : `Fan ${user.fan_uuid.slice(0, 8)}`)
  );
}

/** `1250` → `$12.50`. Fanvue drží sumy v centoch, nie v numericu ako usage. */
export function centsToUsd(cents: number | null | undefined): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format((cents ?? 0) / 100);
}

/**
 * Fakty sú tu jeden textový stĺpec (nie tabuľka `facts` ako v Telegrame) —
 * worker ich zlieva `merge_facts` do riadkov `kľúč: hodnota`.
 */
export function parseFvFacts(facts: string): { key: string; value: string }[] {
  return facts
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const at = line.indexOf(":");
      return at === -1
        ? { key: "", value: line }
        : { key: line.slice(0, at).trim(), value: line.slice(at + 1).trim() };
    });
}
