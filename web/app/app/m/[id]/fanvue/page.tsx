import type { Metadata } from "next";

import { FanvueConnectCard } from "@/components/app/fanvue/connect-card";
import { PageHeader } from "@/components/app/ui";
import { fanvueConfigured } from "@/lib/env";
import { getFanvueConnection } from "@/lib/fanvue";
import { requireModelSubTab } from "@/lib/models";

export const metadata: Metadata = {
  title: "Fanvue",
};

/**
 * Karta Fanvue, podkarta Connect — len pripojenie účtu.
 *
 * Nastavenia agenta, vault a konverzácie sa odsťahovali na vlastné podkarty
 * (`/fanvue/settings`, `/fanvue/photos`, `/fanvue/chats`); jedna dlhá stránka
 * znamenala scrollovať cez celý vault k jednému prepínaču.
 *
 * Stav sa číta user-scoped klientom, takže RLS cudzí riadok nevráti a šifrované
 * tokeny sa do prehliadača nedostanú ani omylom — na `*_enc` stĺpce
 * `authenticated` grant nemá (migrácia 011).
 *
 * `?error=` sem posiela `/api/fanvue/callback`, keď prihlásenie neprejde. Preto
 * je Connect PRVÁ podkarta a nie `/fanvue/connect`: návratová URL z OAuth
 * ostáva presne tá, ktorá je zaregistrovaná u nich.
 *
 * Fanvue je vec `persona` agenta — firemný ani osobný ho mať nebudú. Tab sa im
 * nevykreslí (`MODEL_TYPE_TABS`), ale ručne zadaná URL musí skončiť rovnako,
 * inak by tá mapa bola len kozmetika.
 */
export default async function FanvuePage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/fanvue">) {
  const { id } = await params;
  const { error } = await searchParams;
  const model = await requireModelSubTab(id, "fanvue", "index");

  const fanvue = await getFanvueConnection(model.id);

  return (
    <>
      <PageHeader
        eyebrow="Fanvue agent"
        title={fanvue.connected ? "Fanvue is connected" : "Connect Fanvue"}
        description="Her second agent. Telegram brings people in; here they have already paid, so she never mentions Fanvue and sells content instead. Same persona and memory, separate settings."
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
