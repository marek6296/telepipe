import type { Metadata } from "next";

import { BotSettingsForm, type BotSettingsRow } from "@/components/app/bot-settings-form";
import { PageHeader } from "@/components/app/ui";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Bot notifications" };

const COLUMNS =
  "model_id, notify_fanvue_subscribe, notify_fanvue_payment, notify_fanvue_follow, " +
  "notify_fanvue_like, notify_fanvue_comment, notify_credits_low, notify_startup, daily_report";

/**
 * Čo má control bot hlásiť.
 *
 * Karta patrí pod Telegram, lebo control bot je vec KONKRÉTNEJ modelky —
 * každá má vlastného. Nastavenie v globálnom menu by nútilo v ňom prepínať
 * medzi modelkami.
 */
export default async function BotPage({ params }: PageProps<"/app/m/[id]/telegram/bot">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "telegram", "bot");

  const supabase = await createClient();
  // Riadok nastavení, stav Fanvue a spárovanie bota sú nezávislé — sériovo by
  // to boli tri okruhy do databázy pri každom otvorení karty.
  const [{ data }, { data: fanvue }] = await Promise.all([
    supabase.from("control_bot_settings").select(COLUMNS).eq("model_id", model.id).maybeSingle(),
    supabase.from("fanvue").select("connected").eq("model_id", model.id).maybeSingle(),
  ]);

  // Chýbajúci riadok nie je chyba: modelka mohla vzniknúť pred migráciou.
  // Formulár dostane defaulty a prvé prepnutie ho `upsert`-om založí.
  const settings: BotSettingsRow = (data as BotSettingsRow | null) ?? {
    model_id: model.id,
    notify_fanvue_subscribe: true,
    notify_fanvue_payment: true,
    notify_fanvue_follow: false,
    notify_fanvue_like: false,
    notify_fanvue_comment: false,
    notify_credits_low: true,
    notify_startup: true,
    daily_report: false,
  };

  return (
    <>
      <PageHeader
        eyebrow="Control bot"
        title="Notifications"
        description="What your control bot tells you. This is your own bot — the one you paired — not her account."
      />
      <BotSettingsForm
        settings={settings}
        fanvueConnected={Boolean((fanvue as { connected?: boolean } | null)?.connected)}
        paired={Boolean(model.owner_chat_id)}
      />
    </>
  );
}
