import type { Metadata } from "next";

import { pollControlBotAction } from "@/app/app/m/[id]/telegram/actions";
import { TelegramOverview } from "@/components/app/telegram/overview";
import { TelegramWizard } from "@/components/app/telegram/wizard";
import { PageHeader } from "@/components/app/ui";
import { requireModel } from "@/lib/models";
import { getTelegramConnection } from "@/lib/telegram";

export const metadata: Metadata = {
  title: "Telegram",
};

/**
 * Telegram karta — dva režimy, jedna adresa.
 *
 * SPRIEVODCA beží pri prvom nastavení: kým jej účet nie je prihlásený, alebo kým
 * ju klient ani raz nezapol (`status === "draft"` — do draftu sa už žiadny prechod
 * nevracia, viď whitelist v `set_model_status`, takže je to spoľahlivá značka
 * „ešte nikdy nebola spustená"). Je to naozaj postupnosť a stepper tam patrí.
 *
 * PREHĽAD beží potom a je to trvalý stav troch nezávislých vecí: jej účet, tvoj
 * kontrolný bot, tvoj súkromný Telegram. Rozdiel medzi druhou a treťou bol
 * predtým neviditeľný — po spárovaní sa obe zbalili do jedného „Connected as X"
 * a zvyšok stavu bolo treba hľadať na podkarte Settings inými slovami.
 *
 * `?reconnect=1` prepne späť na sprievodcu aj prihlásenej modelke. Je to jediná
 * cesta k prvým trom krokom po pripojení a zároveň adresa, ktorá sa dá poslať.
 */
export default async function TelegramPage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/telegram">) {
  const [{ id }, { reconnect }] = await Promise.all([params, searchParams]);
  const model = await requireModel(id);

  // Stav pripojenia a stav kontrolného bota sú NEZÁVISLÉ — čakať jedno na
  // druhé stálo celý ďalší okruh do databázy. Pri ~114 ms na dotaz je každý
  // ušetrený okruh priamo viditeľný na tom, ako rýchlo sa karta otvorí.
  //
  // `pollControlBotAction` skladá stav bota (uložený token, spárovaný chat,
  // čakajúci kód, `owner_as_client`) server action so service kľúčom — token
  // je šifrovaný a klient naň nevidí.
  const [connection, controlBot] = await Promise.all([
    getTelegramConnection(model),
    pollControlBotAction(model.id),
  ]);

  const reconnecting = Boolean(reconnect);
  const firstTimeSetup = !connection.connected || model.status === "draft";
  const showWizard = firstTimeSetup || reconnecting;

  return (
    <>
      {/* Modelka má dvoch agentov a každý má vlastné nastavenia. Táto karta
          platí LEN pre Telegram — Fanvue má svoje na svojej karte. */}
      <PageHeader
        eyebrow="Telegram agent"
        title="Telegram"
        description={
          showWizard
            ? "Her first agent: it talks to people in Telegram and moves them towards her Fanvue. This is the one-time setup — sign her account in, then decide whether you also want a control bot and notifications on your own phone."
            : "Three separate things: her account, which does the replying and is required; your control bot, which watches it; and your own private Telegram, which is where that bot writes. The anti-ban caps for this account sit one click away in Settings; who she is lives on the Persona tab."
        }
      />

      {showWizard ? (
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
          reconnect={reconnecting}
        />
      ) : (
        <TelegramOverview
          modelId={model.id}
          modelName={model.name || "your model"}
          status={model.status}
          statusReason={model.status_reason}
          phone={connection.phone}
          skipContacts={model.skip_contacts}
          contactExceptions={model.contact_exceptions ?? []}
          controlBot={controlBot}
        />
      )}
    </>
  );
}
