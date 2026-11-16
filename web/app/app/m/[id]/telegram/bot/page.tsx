import type { Metadata } from "next";

import { BotSettingsForm, type BotSettingsRow } from "@/components/app/bot-settings-form";
import { PageHeader } from "@/components/app/ui";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Bot notifications" };

const COLUMNS = "model_id, notify_social_inbound";

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
  const { data, error } = await supabase.from("control_bot_settings")
    .select(COLUMNS).eq("model_id", model.id).maybeSingle();
  if (error) throw new Error("Could not load notification settings. Please try again.");

  // Chýbajúci riadok nie je chyba: modelka mohla vzniknúť pred migráciou.
  // Formulár dostane defaulty a prvé prepnutie ho `upsert`-om založí.
  const settings: BotSettingsRow = (data as BotSettingsRow | null) ?? {
    model_id: model.id,
    notify_social_inbound: true,
  };

  return (
    <>
      <PageHeader
        eyebrow="Control bot"
        title="Notifications"
        description="New-message alerts in Telegram, with a direct link to the conversation in Social sites."
      />
      <BotSettingsForm
        settings={settings}
        paired={Boolean(model.owner_chat_id)}
      />
    </>
  );
}
