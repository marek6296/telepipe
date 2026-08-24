import type { Metadata } from "next";
import { Bot } from "lucide-react";

import { AddModelDialog } from "@/components/app/add-model-dialog";
import { ModelCard } from "@/components/app/model-card";
import { ModelSlots } from "@/components/app/model-slots";
import { EmptyState, PageHeader } from "@/components/app/ui";
import {
  getAccount,
  getDayPlans,
  getModelStats,
  getPausedMap,
  listModels,
  type DayPlan,
  type ModelRow,
} from "@/lib/models";
import { getAppConfig, isSlotExempt } from "@/lib/slots";
import { getConnectedMap } from "@/lib/telegram";

export const metadata: Metadata = {
  title: "Models",
};

export default async function ModelsPage() {
  const models = await listModels();
  const modelIds = models.map((model) => model.id);
  const [stats, connected, paused, days, account, config] = await Promise.all([
    getModelStats(modelIds),
    getConnectedMap(models),
    getPausedMap(modelIds),
    getDayPlans(modelIds),
    getAccount(),
    getAppConfig(),
  ]);

  // Vyňaté účty (admin, superadmin, VIP) strop nemajú — panel by im ukazoval
  // číslo, ktoré na ne neplatí.
  const showSlots = account !== null && !isSlotExempt(account);

  return (
    <>
      <PageHeader
        eyebrow="Your roster"
        title="Models"
        description="Each model is one Telegram account with her own persona, photos and conversations."
        actions={models.length > 0 ? <AddModelDialog /> : undefined}
      />

      {showSlots && (
        <div className="mb-5">
          <ModelSlots
            slots={account.model_slots}
            used={models.length}
            balanceUsd={Number(account.credit_balance_usd)}
            slotPriceUsd={config.model_slot_usd}
            maxSlots={config.max_model_slots}
          />
        </div>
      )}

      <ModelsGrid
        models={models}
        stats={stats}
        connected={connected}
        paused={paused}
        days={days}
      />
    </>
  );
}

function ModelsGrid({
  models,
  stats,
  connected,
  paused,
  days,
}: {
  models: ModelRow[];
  stats: Awaited<ReturnType<typeof getModelStats>>;
  connected: Awaited<ReturnType<typeof getConnectedMap>>;
  paused: Awaited<ReturnType<typeof getPausedMap>>;
  days: Record<string, DayPlan>;
}) {
  if (models.length === 0) {
    return (
      <EmptyState
        icon={<Bot className="h-[18px] w-[18px]" strokeWidth={1.5} />}
        title="Your roster is empty"
        description="Add a model to get started. You will need her Telegram account and a phone that can receive the login code."
        action={<AddModelDialog label="Add your first model" />}
      />
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {models.map((model) => (
        <ModelCard
          key={model.id}
          model={model}
          stats={stats[model.id] ?? { chats: 0, converted: 0, spentToday: 0 }}
          connected={connected[model.id] ?? false}
          aiPaused={paused[model.id] ?? false}
          day={days[model.id] ?? null}
        />
      ))}
    </div>
  );
}
