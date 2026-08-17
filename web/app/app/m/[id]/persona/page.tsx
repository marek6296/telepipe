import type { Metadata } from "next";

import { PersonaForm, type PersonaRow } from "@/components/app/persona-form";
import { Callout } from "@/components/app/ui";
import { requireModel } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Persona",
};

const PERSONA_COLUMNS =
  "model_id, name, age, city, language, languages, backstory, tone, msg_style, " +
  "boundaries, funnel_rules, cta_link, extra_rules, examples";

export default async function PersonaPage({ params }: PageProps<"/app/m/[id]/persona">) {
  const { id } = await params;
  const model = await requireModel(id);

  const supabase = await createClient();
  const { data } = await supabase
    .from("persona")
    .select(PERSONA_COLUMNS)
    .eq("model_id", model.id)
    .maybeSingle();

  if (!data) {
    // Riadok zakladá trigger `models_provision_rows` — ak chýba, niečo je zle.
    return (
      <Callout tone="danger">
        Her persona row is missing. Reload the page, and contact us if it stays empty.
      </Callout>
    );
  }

  return <PersonaForm persona={data as unknown as PersonaRow} />;
}
