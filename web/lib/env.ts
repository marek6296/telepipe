/**
 * Prístup k env premenným s jasnou chybou keď niečo chýba.
 *
 * NEXT_PUBLIC_* sa musia čítať doslovným `process.env.NEXT_PUBLIC_X` zápisom —
 * Next ich nahrádza staticky pri builde, dynamický prístup by nefungoval.
 */

function required(value: string | undefined, name: string): string {
  if (!value) {
    throw new Error(
      `Chýba env premenná ${name}. Skopíruj web/.env.example do web/.env.local a doplň hodnoty.`,
    );
  }
  return value;
}

/** Verejná Supabase URL — bezpečná aj v client bundle. */
export function supabaseUrl(): string {
  return required(process.env.NEXT_PUBLIC_SUPABASE_URL, "NEXT_PUBLIC_SUPABASE_URL");
}

/** Verejný anon kľúč — RLS je jediná obrana, preto smie ísť do prehliadača. */
export function supabaseAnonKey(): string {
  return required(
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
  );
}

/** Service role kľúč — SERVER ONLY, nikdy sa nesmie dostať do client bundle. */
export function supabaseServiceKey(): string {
  return required(process.env.SUPABASE_SERVICE_KEY, "SUPABASE_SERVICE_KEY");
}

/** AES-256-GCM kľúč (base64) — SERVER ONLY, zhodný s workerom. */
export function encryptionKey(): string {
  return required(process.env.ENCRYPTION_KEY, "ENCRYPTION_KEY");
}

/** Absolútna URL aplikácie pre auth redirecty. */
export function siteUrl(): string {
  return process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
}

/**
 * Signing secret webhookov z Fanvue — SERVER ONLY. Prázdne = webhook nemá čím
 * overiť podpis, takže každé doručenie odmietne (401). Radšej ticho odmietať
 * než ticho dôverovať komukoľvek, kto nájde našu adresu.
 */
export function fanvueWebhookSecret(): string {
  return process.env.FANVUE_WEBHOOK_SECRET ?? "";
}

/** Je Fanvue appka nakonfigurovaná? (UI podľa toho skrýva „Connect“.) */
export function fanvueConfigured(): boolean {
  return Boolean(process.env.FANVUE_CLIENT_ID && process.env.FANVUE_CLIENT_SECRET);
}

/**
 * Plisio secret key — SERVER ONLY. Prázdne = krypto platby vypnuté:
 * `plisioEnabled()` je false, checkout vráti „unavailable" a nič sa nezaloží.
 */
export function plisioSecretKey(): string {
  return process.env.PLISIO_SECRET_KEY ?? "";
}

/**
 * Ochrana cron endpointov (`/api/payments/reconcile`). Vercel cron posiela
 * `Authorization: Bearer $CRON_SECRET` automaticky, keď je env nastavená.
 * Prázdne = endpoint pustí kohokoľvek (dev) — reconcile je aj tak neškodný,
 * len číta pravdu z Plisia.
 */
export function cronSecret(): string {
  return process.env.CRON_SECRET ?? "";
}

/** VRNUM API token — SERVER ONLY. Pouziva sa vyhradne na Telegram OTP route. */
export function vrnumApiToken(): string {
  return required(process.env.VRNUM_API_TOKEN, "VRNUM_API_TOKEN");
}

/** Minimalne 50 % nad aktualnou VRNUM nakupnou cenou. */
export function vrnumOtpPriceMultiplier(): number {
  const value = Number(process.env.VRNUM_OTP_PRICE_MULTIPLIER ?? "1.50");
  return Number.isFinite(value) ? Math.max(value, 1.5) : 1.5;
}

/**
 * Marekov SÚKROMNÝ admin bot (@TelePipe_help_bot) — SERVER ONLY.
 *
 * Nemá nič spoločné s control botmi modeliek vo workeri; je to samostatný bot
 * a samostatný kanál pre notifikácie o žiadostiach o prístup.
 *
 * Voliteľná integrácia: keď premenné chýbajú, žiadosti stále pribúdajú v admin
 * paneli, len sa neozve Telegram. Preto `?? ""` a `telegramAdminConfigured()`,
 * nie tvrdý `required()` — žiadosť sa nesmie stratiť kvôli chýbajúcej env.
 */
export function telegramAdminBotToken(): string {
  return process.env.TELEGRAM_ADMIN_BOT_TOKEN ?? "";
}

/** Marekov súkromný chat id. Webhook ním overuje, že klik prišiel od neho. */
export function telegramAdminChatId(): string {
  return process.env.TELEGRAM_ADMIN_CHAT_ID ?? "";
}

/** Secret token z `setWebhook` — Telegram ho posiela v hlavičke každého update. */
export function telegramAdminWebhookSecret(): string {
  return process.env.TELEGRAM_ADMIN_WEBHOOK_SECRET ?? "";
}

export function telegramAdminConfigured(): boolean {
  return Boolean(telegramAdminBotToken() && telegramAdminChatId());
}

/**
 * VEREJNÝ obchodný bot — predaj Pipe Coinov za Telegram Stars.
 *
 * ZÁMERNE iný bot než admin: adminovi smie písať len Marek (webhook kontroluje
 * chat id), obchodnému musí vedieť napísať ktokoľvek. Zlúčiť ich by tú kontrolu
 * zrušilo.
 */
export function telegramShopBotToken(): string {
  return process.env.TELEGRAM_SHOP_BOT_TOKEN ?? "";
}

export function telegramShopWebhookSecret(): string {
  return process.env.TELEGRAM_SHOP_WEBHOOK_SECRET ?? "";
}

export function telegramShopConfigured(): boolean {
  return Boolean(telegramShopBotToken());
}

// Feature flagy žijú v `lib/flags.ts` (client-safe) — tu ich len reexportujeme
export { googleAuthEnabled } from "@/lib/flags";
