import type { Metadata } from "next";

import { FanvueConnectCard } from "@/components/app/fanvue/connect-card";
import { PageHeader } from "@/components/app/ui";
import { fanvueConfigured } from "@/lib/env";
import { getFanvueConnection } from "@/lib/fanvue";
import { requireModel } from "@/lib/models";

export const metadata: Metadata = {
  title: "Fanvue",
};

/**
 * Karta Fanvue. Stav sa číta user-scoped klientom, takže RLS cudzí riadok
 * nevráti a šifrované tokeny sa do prehliadača nedostanú ani omylom — na
 * `*_enc` stĺpce `authenticated` grant nemá (migrácia 011).
 *
 * `?error=` sem posiela `/api/fanvue/callback`, keď prihlásenie neprejde.
 */
export default async function FanvuePage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/fanvue">) {
  const { id } = await params;
  const { error } = await searchParams;
  const model = await requireModel(id);
  const fanvue = await getFanvueConnection(model.id);

  return (
    <>
      <PageHeader
        eyebrow="Fanvue"
        title={fanvue.connected ? "Fanvue is connected" : "Connect Fanvue"}
        description="One sign-in links her creator account. Chats, subscribers and payments then arrive as events Telepipe can act on."
      />
      <FanvueConnectCard
        modelId={model.id}
        fanvue={fanvue}
        configured={fanvueConfigured()}
        error={typeof error === "string" ? error : ""}
      />
    </>
  );
}
