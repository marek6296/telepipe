/**
 * Fanvue helpery a tvary, ktoré musia fungovať aj v prehliadači.
 *
 * Serverová časť (OAuth, volania do Fanvue API, čítanie z DB) žije v
 * `lib/fanvue.ts` — tá cez `lib/supabase/server` importuje `next/headers`,
 * takže do client komponentu sa dostať nesmie. Rovnaké delenie ako
 * `lib/admin.ts` ↔ `lib/admin-ui.ts`.
 */

/** Na čo je priečinok vaultu. Hodnoty sú `fvmedia.ROLES` vo workeri — mená
 *  diktuje kód, ktorý podľa nich vyberá fotky, nie dashboard. */
export const FOLDER_ROLES = ["ignore", "sfw", "nsfw", "post"] as const;
export type FolderRole = (typeof FOLDER_ROLES)[number];

export const FOLDER_ROLE_LABEL: Record<FolderRole, string> = {
  ignore: "Not used",
  sfw: "Free photos",
  nsfw: "Paid photos",
  post: "Feed posts",
};

export type FanvueSettings = {
  greet_new: boolean;
  discovery_msgs: number;
  summary_every: number;
  heat: string;
  extra_rules: string;
  reply_min_s: number;
  reply_max_s: number;
  active_start_min: number;
  active_end_min: number;
  sell_content: boolean;
  offer_after_msgs: number;
  offer_cooldown_h: number;
  nudge_after_msgs: number;
  thank_purchases: boolean;
  voices_enabled: boolean;
  voice_price_cents: number;
  send_photos: boolean;
  free_photo_max: number;
  posting_enabled: boolean;
  post_every_h: number;
  post_audience: string;
  /** Píše ich worker; formulár ich len ukazuje. */
  last_post_at: string | null;
  media_synced_at: string | null;
};

export type FvFolder = {
  name: string;
  role: string;
  price_cents: number;
  media_count: number;
};

export type FvMedia = {
  media_uuid: string;
  folder: string;
  kind: string;
  thumb_url: string;
  caption: string;
  fits: string;
  spicy: boolean;
  price_cents: number;
  active: boolean;
  sent_count: number;
  posted_at: string | null;
};

export type FanvueSyncRequest = {
  id: number;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
  ok: boolean | null;
  folders: number;
  media_new: number;
  media_seen: number;
  error: string;
};
