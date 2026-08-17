/** Konverzácie — spoločné typy a preklady funnel stavov (client-safe). */

export type FunnelStage = "cold" | "warm" | "link_sent" | "converted";

export const FUNNEL_LABEL: Record<string, string> = {
  cold: "Cold",
  warm: "Warm",
  link_sent: "Link sent",
  converted: "Converted",
};

export const FUNNEL_STYLE: Record<string, string> = {
  cold: "border-white/12 bg-white/[0.04] text-white/50",
  warm: "border-[#8a6d1f]/45 bg-[#241d0e] text-[#f2cd6b]",
  link_sent: "border-[#3b6fa8]/45 bg-[#0e1b2a] text-[#8ec1f0]",
  converted:
    "border-[rgba(212,175,55,0.55)] bg-[rgba(212,175,55,0.14)] text-[var(--gold-light)]",
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
