import type { Metadata } from "next";

import { PersonaWizard } from "@/components/app/persona-wizard";
import { PageHeader } from "@/components/app/ui";
import { OUT_OF_CREDITS_MSG, creditState, hasCredit } from "@/lib/credits";
import { llmConfigured } from "@/lib/llm";
import { requireModelTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Build with AI",
};

/**
 * Asistovaná tvorba persony. Sedí pod kartou Persona, lebo píše presne to, čo
 * je na nej — klient sa po „Apply" pozerá na tú istú obrazovku, len vyplnenú.
 *
 * Dôvod, prečo sa nedá generovať, sa zisťuje TU (server), nie v prehliadači:
 * chýbajúci kľúč aj prázdny kredit sú veci, o ktorých klientský kód nič nevie
 * a vedieť nemá. Wizard dostane hotovú vetu a tlačidlo rovno nepustí.
 */
export default async function PersonaBuildPage({
  params,
}: PageProps<"/app/m/[id]/persona/build">) {
  const { id } = await params;
  const model = await requireModelTab(id, "persona");

  // Prepisuje sa niečo, čo už existuje? Odkedy sa dá builder spustiť kedykoľvek,
  // je to bežný prípad — a klient to musí vedieť skôr, než odpovie na osem
  // otázok, nie až keď mu z karty zmizne text, ktorý si sám vypísal.
  const supabase = await createClient();
  const { data: persona } = await supabase
    .from("persona")
    .select("backstory, tone, msg_style, examples")
    .eq("model_id", model.id)
    .maybeSingle();
  const filled = Boolean(
    persona &&
      [persona.backstory, persona.tone, persona.msg_style, persona.examples].some(
        (value) => String(value ?? "").trim(),
      ),
  );

  const credit = await creditState();
  const blockedReason = !llmConfigured()
    ? "The AI helper is not switched on for this deployment. Fill her tabs in manually for now."
    : hasCredit(credit)
      ? ""
      : OUT_OF_CREDITS_MSG;

  return (
    <>
      <PageHeader
        eyebrow="Persona"
        title="Build with AI"
        description="A few questions about her, and we write the whole persona — story, tone, texting style, limits, funnel and the rhythm she answers in. Nothing is saved until you approve it."
      />
      <PersonaWizard
        modelId={model.id}
        modelName={model.name}
        blockedReason={blockedReason}
        overwrites={filled}
      />
    </>
  );
}
