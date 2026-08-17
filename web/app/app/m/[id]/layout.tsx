import { ModelHeader } from "@/components/app/model-header";
import { ModelTabs } from "@/components/app/model-tabs";
import { requireModel } from "@/lib/models";
import { getTelegramConnection } from "@/lib/telegram";

/**
 * Spoločný rám všetkých stránok modelky — hlavička so stavom a taby.
 * `requireModel` ide cez RLS, takže cudzie id skončí 404, nie odhalením dát.
 */
export default async function ModelLayout({ children, params }: LayoutProps<"/app/m/[id]">) {
  const { id } = await params;
  const model = await requireModel(id);
  const connection = await getTelegramConnection(model);

  return (
    <>
      <ModelHeader
        modelId={model.id}
        name={model.name}
        status={model.status}
        statusReason={model.status_reason}
        connected={connection.connected}
      />
      <ModelTabs modelId={model.id} needsSetup={!connection.connected} />
      {children}
    </>
  );
}
