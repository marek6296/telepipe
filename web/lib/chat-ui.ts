/**
 * Chat typy, ktoré musia fungovať aj v prehliadači. Serverová časť je
 * v `lib/chat.ts` — rovnaké rozdelenie ako `admin-ui.ts` vs `admin.ts`.
 * Nič odtiaľto nesmie importovať `@/lib/supabase/server`.
 */

export type RoomKind = "community" | "community_plus" | "admin_dm";

export type ChatRoom = {
  id: string;
  kind: RoomKind;
  owner_account_id: string | null;
};

export type ChatMessage = {
  id: string;
  room_id: string;
  sender_id: string;
  body: string;
  image_path: string;
  deleted_at: string | null;
  created_at: string;
};

export const CHAT_MESSAGE_COLUMNS =
  "id, room_id, sender_id, body, image_path, deleted_at, created_at";

/**
 * Telegram support. Je to druhá cesta k nám, nie náhrada chatu: kto má zavretú
 * appku (a hlavne kto čaká na schválenie a nevie, či ho niekto vidí), napíše
 * radšej tam, kde už aj tak je.
 */
export const TELEGRAM_SUPPORT = "https://t.me/telepipeme";

export const ROOM_LABEL: Record<RoomKind, string> = {
  community: "Community",
  community_plus: "Community+",
  admin_dm: "Support",
};

export const ROOM_HINT: Record<RoomKind, string> = {
  community: "Everyone on TelePipe",
  community_plus: "Approved members only",
  admin_dm: "Private — we usually reply within minutes",
};

/** Výzva v prázdnej miestnosti — v DM ide o pomoc, v komunite o zoznámenie. */
export const ROOM_EMPTY_PROMPT: Record<RoomKind, string> = {
  community: "Say hello.",
  community_plus: "Say hello.",
  admin_dm: "Ask us anything — including how to get your account opened.",
};

/** Fotky sú len v DM (spec 2026-08-19). RLS to vynucuje aj v databáze. */
export function roomAllowsPhotos(kind: RoomKind): boolean {
  return kind === "admin_dm";
}

/** „14:32" pre dnešok, inak „19 Aug 14:32" — v okne chatu je dátum šum. */
export function messageTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  const time = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (sameDay) return time;
  return `${date.toLocaleDateString(undefined, { day: "numeric", month: "short" })} ${time}`;
}

/** Iniciálka do avataru. E-mail je jediné, čo o cudzom človeku vieme. */
export function initialOf(label: string): string {
  return (label.trim()[0] ?? "?").toUpperCase();
}
