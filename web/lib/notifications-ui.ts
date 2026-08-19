/**
 * Notifikačné typy, ktoré musia fungovať aj v prehliadači (zvonček, live-unlock).
 * Serverová časť (čítanie cez `next/headers`) žije v `lib/notifications.ts` —
 * rovnaké rozdelenie ako `admin-ui.ts` vs `admin.ts`.
 *
 * Keby tu čokoľvek importovalo `@/lib/supabase/server`, build spadne na
 * „You're importing a module that depends on next/headers".
 */

export type NotificationKind =
  | "access_approved"
  | "access_rejected"
  | "model_error"
  | "model_muted"
  | "credits_low";

export type NotificationRow = {
  id: string;
  kind: NotificationKind;
  title: string;
  body: string;
  href: string;
  read_at: string | null;
  created_at: string;
};

/** Stĺpce vymenované ručne — `authenticated` má na tabuľke column-scoped grant,
 *  takže `select('*')` by skončil na „permission denied for column". */
export const NOTIFICATION_COLUMNS =
  "id, kind, title, body, href, read_at, created_at";
