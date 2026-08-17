/** Konverzácie — spoločné typy a preklady funnel stavov (client-safe). */

export type FunnelStage = "cold" | "warm" | "link_sent" | "converted";

export const FUNNEL_LABEL: Record<string, string> = {
  cold: "Cold",
  warm: "Warm",
  link_sent: "Link sent",
  converted: "Converted",
};

/** Monochróm — jediná farba je tlmená zelená na „converted". */
export const FUNNEL_STYLE: Record<string, string> = {
  cold: "border-[#1f1f1f] text-[#71717a]",
  warm: "border-[#2e2e2e] text-[#a1a1aa]",
  link_sent: "border-[#3f3f46] text-[#d4d4d8]",
  converted: "border-[rgba(74,222,128,0.3)] text-[#86efac]",
};

export const FUNNEL_HINT: Record<string, string> = {
  cold: "Just started talking.",
  warm: "Engaged — she can start steering towards your link.",
  link_sent: "She sent your link. Waiting to see if he subscribes.",
  converted: "He subscribed. Selling is switched off for this chat.",
};

export type DmUserRow = {
  tg_id: number;
  username: string | null;
  first_name: string | null;
  partner_name: string;
  funnel_stage: string;
  msg_count: number;
  paid: boolean;
  ai_enabled: boolean;
  human_takeover: boolean;
  link_sent_at: string | null;
  last_incoming_at: string | null;
  last_reply_at: string | null;
  summary: string;
  style_note: string;
  created_at: string;
};

export const DM_USER_COLUMNS =
  "tg_id, username, first_name, partner_name, funnel_stage, msg_count, paid, " +
  "ai_enabled, human_takeover, link_sent_at, last_incoming_at, last_reply_at, " +
  "summary, style_note, created_at";

export type DmMessageRow = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

/** Meno do zoznamu: ako ju oslovuje on → meno z Telegramu → username → id. */
export function chatTitle(user: DmUserRow): string {
  return (
    user.partner_name?.trim() ||
    user.first_name?.trim() ||
    (user.username ? `@${user.username}` : `Fan ${user.tg_id}`)
  );
}
