import type { Metadata } from "next";
import Link from "next/link";
import { Sparkles } from "lucide-react";

import { PersonaForm, type PersonaRow } from "@/components/app/persona-form";
import { Callout } from "@/components/app/ui";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Persona",
};

const PERSONA_COLUMNS =
  "model_id, name, age, city, language, languages, lang_primary, lang_extra, " +
  "backstory, tone, msg_style, boundaries, funnel_rules, cta_link, extra_rules, examples";

/**
 * Identita — KTO je. Ako sa správa, sedí o podkartu ďalej (`/persona/behavior`):
 * je to tá istá osoba z dvoch strán, preto jedna karta a dve záložky.
 */
export default async function PersonaPage({ params }: PageProps<"/app/m/[id]/persona">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "persona", "index");

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

  const persona = data as unknown as PersonaRow;

  return (
    <>
      {isBlank(persona) && (
        // `mb-12`, nie `mb-4`: `AutoSaveForm` ťahá obsah o `-mt-8` hore pod
        // lepiaci indikátor ukladania, takže menší odstup by karta prekryla.
        <div className="mb-12 flex flex-col gap-3 rounded-lg border border-[var(--app-border-strong)] bg-[#0e0e0e] px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-[13px] font-medium text-[var(--app-text)]">
              <Sparkles className="h-3.5 w-3.5 text-[var(--app-text-4)]" strokeWidth={1.75} />
              Nothing here yet
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-3)]">
              Answer seven quick questions and we write all of this for you — you can edit
              every word afterwards, right here.
            </p>
          </div>
          <Link
            href={`/app/m/${model.id}/persona/build`}
            className="app-btn app-btn-primary h-9 shrink-0 px-4"
          >
            Build her with AI
          </Link>
        </div>
      )}
      <PersonaForm persona={persona} />
    </>
  );
}

/**
 * Nedotknutá persona — všetky štyri polia, ktoré rozhodujú o tom, ako znie,
 * sú prázdne (DB default). Meno a mesto sa nerátajú: meno vypĺňa trigger a
 * mesto si klient často doplní skôr, než čokoľvek napíše.
 */
function isBlank(persona: PersonaRow): boolean {
  return (
    !persona.backstory.trim() &&
    !persona.tone.trim() &&
    !persona.msg_style.trim() &&
    !persona.examples.trim()
  );
}
