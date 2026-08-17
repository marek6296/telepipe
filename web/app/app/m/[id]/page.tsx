import { redirect } from "next/navigation";

import { requireModel } from "@/lib/models";
import { getTelegramConnection } from "@/lib/telegram";

/**
 * `/app/m/[id]` samo o sebe nič nezobrazuje — nepripojenú modelku pošleme do
 * wizardu, pripojenú na personu (tam sa ladí najčastejšie).
 */
export default async function ModelIndexPage({ params }: PageProps<"/app/m/[id]">) {
  const { id } = await params;
  const model = await requireModel(id);
  const connection = await getTelegramConnection(model);

  redirect(connection.connected ? `/app/m/${id}/persona` : `/app/m/${id}/telegram`);
}
