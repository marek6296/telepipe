import { Suspense } from "react";
import type { Metadata } from "next";
import { Bot } from "lucide-react";

import { AddModelDialog } from "@/components/app/add-model-dialog";
import { ModelCardsSkeleton } from "@/components/app/loading-skeletons";
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
  const statsPromise = getModelStats(modelIds);
  const connectedPromise = getConnectedMap(models);
  const pausedPromise = getPausedMap(modelIds);

  return (
    <>
      <PageHeader
        eyebrow="Your roster"
        title="Models"
        description="Each model is one Telegram account with her own persona, photos and conversations."
        actions={models.length > 0 ? <AddModelDialog /> : undefined}
      />

      <Suspense fallback={<ModelCardsSkeleton count={Math.min(4, Math.max(1, models.length))} />}>
        <ModelsGrid
          models={models}
          statsPromise={statsPromise}
          connectedPromise={connectedPromise}
          pausedPromise={pausedPromise}
        />
      </Suspense>
    </>
  );
}

async function ModelsGrid({
  models,
  statsPromise,
  connectedPromise,
  pausedPromise,
}: {
  models: ModelRow[];
  statsPromise: ReturnType<typeof getModelStats>;
  connectedPromise: ReturnType<typeof getConnectedMap>;
  pausedPromise: ReturnType<typeof getPausedMap>;
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

  const [stats, connected, paused] = await Promise.all([
    statsPromise,
    connectedPromise,
    pausedPromise,
  ]);

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
