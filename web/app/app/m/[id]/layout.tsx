import { Suspense } from "react";

import { ModelChromeSkeleton } from "@/components/app/loading-skeletons";
import { ModelHeader } from "@/components/app/model-header";
import { ModelTabs } from "@/components/app/model-tabs";
import { isAiPaused, requireModel } from "@/lib/models";
import { getTelegramConnection } from "@/lib/telegram";

/**
 * Spoločný rám všetkých stránok modelky — hlavička so stavom a taby.
 * `requireModel` ide cez RLS, takže cudzie id skončí 404, nie odhalením dát.
 *
 * Ktoré taby sa vykreslia, rozhoduje `model.model_type` (mapa v
 * `lib/model-types.ts`); `ai_paused` je globálna pauza odpovedania, ktorú
 * dashboard doteraz nevedel ukázať.
 */
export default async function ModelLayout({ children, params }: LayoutProps<"/app/m/[id]">) {
  const { id } = await params;
  const model = await requireModel(id);
  const connectionPromise = getTelegramConnection(model);
  const pausedPromise = isAiPaused(model.id);

  return (
    <>
      <Suspense fallback={<ModelChromeSkeleton />}>
        <ModelChrome
          model={model}
          connectionPromise={connectionPromise}
          pausedPromise={pausedPromise}
        />
      </Suspense>
      {children}
    </>
  );
}

async function ModelChrome({
  model,
  connectionPromise,
  pausedPromise,
}: {
  model: Awaited<ReturnType<typeof requireModel>>;
  connectionPromise: ReturnType<typeof getTelegramConnection>;
  pausedPromise: ReturnType<typeof isAiPaused>;
}) {
  const [connection, aiPaused] = await Promise.all([connectionPromise, pausedPromise]);

  return (
    <>
      <ModelHeader
        modelId={model.id}
        name={model.name}
        modelType={model.model_type}
        status={model.status}
        statusReason={model.status_reason}
        connected={connection.connected}
        aiPaused={aiPaused}
      />
      <ModelTabs
        modelId={model.id}
        modelType={model.model_type}
        needsSetup={!connection.connected}
      />
    </>
  );
}
