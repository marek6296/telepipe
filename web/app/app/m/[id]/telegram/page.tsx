import type { Metadata } from "next";

import { pollControlBotAction } from "@/app/app/m/[id]/telegram/actions";
import { TelegramWizard } from "@/components/app/telegram/wizard";
import { PageHeader } from "@/components/app/ui";
import { requireModel } from "@/lib/models";
import { getTelegramConnection } from "@/lib/telegram";

export const metadata: Metadata = {
  title: "Telegram connection",
};

export default async function TelegramPage({ params }: PageProps<"/app/m/[id]/telegram">) {
  const { id } = await params;
  const model = await requireModel(id);
  const connection = await getTelegramConnection(model);
  // Stav kontrolného bota (uložený token, spárovaný chat, čakajúci kód) skladá
  // server action so service kľúčom — token je šifrovaný a klient naň nevidí.
  const controlBot = await pollControlBotAction(model.id);

  return (
    <>
      {/* Modelka má dvoch agentov a každý má vlastné nastavenia. Tento vypínač,
          časy a limity platia LEN pre Telegram — Fanvue má svoje na svojej karte. */}
      <PageHeader
        eyebrow="Telegram agent"
        title="Telegram connection"
        description="Her first agent: it talks to people in Telegram and moves them towards her Fanvue. This page signs her account in — the control bot and the anti-ban caps sit one tab over in Settings. Fanvue is a separate agent on its own tab, with its own settings; only the persona and memory are shared."
      />
      <TelegramWizard
        modelId={model.id}
        modelName={model.name || "your model"}
        status={model.status}
        statusReason={model.status_reason}
        apiId={model.tg_api_id ? String(model.tg_api_id) : ""}
        apiHash={model.tg_api_hash ?? ""}
        connected={connection.connected}
        connectedPhone={connection.phone}
        controlBot={controlBot}
        initialJob={connection.latestJob}
      />
    </>
  );
}
