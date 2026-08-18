import type { Metadata } from "next";

import { controlBotConfigured } from "@/app/app/m/[id]/telegram/actions";
import { ControlBotForm } from "@/components/app/telegram/control-bot-form";
import {
  TelegramLimitsForm,
  type TelegramLimitsRow,
} from "@/components/app/telegram/limits-form";
import { Callout, PageHeader } from "@/components/app/ui";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Telegram settings",
};

/**
 * Nastavenia telegramového účtu — nie jej povahy.
 *
 * Sú tu dve veci, ktoré patria k účtu a nie k osobe: kontrolný bot (diaľkové
 * ovládanie majiteľa) a tri anti-ban stropy. Pripojenie samotné je vedľa na
 * podkarte Connection; kto je a ako píše, je na karte Persona.
 */
export default async function TelegramSettingsPage({
  params,
}: PageProps<"/app/m/[id]/telegram/settings">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "telegram", "settings");

  // Token je šifrovaný a klient naň nemá grant — či existuje, zistí server
  // action so service kľúčom (po kontrole vlastníctva).
  const controlBotReady = await controlBotConfigured(model.id);

  const supabase = await createClient();
  const { data } = await supabase
    .from("behavior")
    .select("model_id, max_active_chats, chat_slot_min, max_outreach_per_hour")
    .eq("model_id", model.id)
    .maybeSingle();

  return (
    <>
      <PageHeader
        eyebrow="Telegram agent"
        title="Telegram settings"
        description="The account side of her Telegram agent: who gets the notifications, and the caps that keep the account out of Telegram's sights. How she talks lives on the Persona tab."
      />

      <div className="flex flex-col gap-5">
        <ControlBotForm
          modelId={model.id}
          ownerChatId={model.owner_chat_id ? String(model.owner_chat_id) : ""}
          alreadySaved={controlBotReady}
        />

        {data ? (
          <TelegramLimitsForm limits={data as unknown as TelegramLimitsRow} />
        ) : (
          <Callout tone="danger">
            Her behaviour row is missing, so the limits cannot be shown. Reload the page,
            and contact us if it stays empty.
          </Callout>
        )}
      </div>
    </>
  );
}
