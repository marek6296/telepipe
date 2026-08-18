import type { Metadata } from "next";
import { Bot } from "lucide-react";

import { AddModelDialog } from "@/components/app/add-model-dialog";
import { ModelCard } from "@/components/app/model-card";
import { EmptyState, PageHeader } from "@/components/app/ui";
import { getModelStats, getPausedMap, listModels, type ModelRow } from "@/lib/models";
import { getConnectedMap } from "@/lib/telegram";

export const metadata: Metadata = {
  title: "Models",
};

export default async function ModelsPage() {
  const models = await listModels();
  const modelIds = models.map((model) => model.id);
  const [stats, connected, paused] = await Promise.all([
    getModelStats(modelIds),
    getConnectedMap(models),
    getPausedMap(modelIds),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Your roster"
        title="Models"
        description="Each model is one Telegram account with her own persona, photos and conversations."
        actions={models.length > 0 ? <AddModelDialog /> : undefined}
      />

      <ModelsGrid models={models} stats={stats} connected={connected} paused={paused} />
    </>
  );
}

function ModelsGrid({
  models,
  stats,
  connected,
  paused,
}: {
  models: ModelRow[];
  stats: Awaited<ReturnType<typeof getModelStats>>;
  connected: Awaited<ReturnType<typeof getConnectedMap>>;
  paused: Awaited<ReturnType<typeof getPausedMap>>;
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
        />
      ))}
    </div>
  );
}
