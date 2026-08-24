import { ModelHeader } from "@/components/app/model-header";
import { ModelTabs } from "@/components/app/model-tabs";
import { getViewerRole } from "@/lib/admin";
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
  // `isAiPaused` potrebuje len id, nie celý riadok modelky — nemusí teda čakať
  // na `requireModel`. Pri ~114 ms na okruh do databázy je to jeden ušetrený
  // okruh pri KAŽDOM prepnutí karty modelky.
  // Rola sa ťahá spolu so zvyškom, nie sériovo — rozhoduje len o tom, či sa
  // vykreslí karta vo výstavbe (Instagram), a nemá za to stáť ďalší okruh.
  const [model, aiPaused, rola] = await Promise.all([
    requireModel(id),
    isAiPaused(id),
    getViewerRole(),
  ]);
  const connection = await getTelegramConnection(model);

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
        isSuperadmin={rola === "superadmin"}
      />
      {children}
    </>
  );
}
