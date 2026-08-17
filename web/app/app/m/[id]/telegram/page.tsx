import type { Metadata } from "next";

import { controlBotConfigured } from "@/app/app/m/[id]/telegram/actions";
import { TelegramWizard } from "@/components/app/telegram/wizard";
import { requireModel } from "@/lib/models";
import { getTelegramConnection } from "@/lib/telegram";

export const metadata: Metadata = {
  title: "Telegram setup",
};

export default async function TelegramPage({ params }: PageProps<"/app/m/[id]/telegram">) {
  const { id } = await params;
  const model = await requireModel(id);
  const connection = await getTelegramConnection(model);
  // Token je šifrovaný a klient naň nemá grant — či existuje, zistí server
  // action so service kľúčom (po kontrole vlastníctva).
  const controlBotReady = await controlBotConfigured(model.id);

  return (
    <TelegramWizard
      modelId={model.id}
      modelName={model.name || "your model"}
      status={model.status}
      statusReason={model.status_reason}
      apiId={model.tg_api_id ? String(model.tg_api_id) : ""}
      apiHash={model.tg_api_hash ?? ""}
      ownerChatId={model.owner_chat_id ? String(model.owner_chat_id) : ""}
      connected={connection.connected}
      connectedPhone={connection.phone}
      controlBotReady={controlBotReady}
      initialJob={connection.latestJob}
    />
  );
}
