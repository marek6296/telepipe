import type { Metadata } from "next";

import { pollControlBotAction } from "@/app/app/m/[id]/telegram/actions";
import { ControlBotCard } from "@/components/app/telegram/control-bot-card";
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

  // Token je šifrovaný a klient naň nemá grant — stav bota (uložený token,
  // spárovaný chat, čakajúci kód) skladá server action so service kľúčom.
  const controlBot = await pollControlBotAction(model.id);

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
        {/* Ten istý komponent, aký je štvrtým krokom sprievodcu — bota si tu
            klient dorába, mení alebo odpája aj rok po spustení. */}
        <ControlBotCard modelId={model.id} initial={controlBot} />

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
