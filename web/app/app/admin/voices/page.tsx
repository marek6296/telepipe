import type { Metadata } from "next";

import { VoicesManager, type ManagedVoice } from "@/components/app/admin/voices-manager";
import { Callout, PageHeader } from "@/components/app/ui";
import { requireSuperadmin } from "@/lib/admin";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Voices",
};

/**
 * Katalóg našich ElevenLabs hlasov.
 *
 * Klient, ktorý nechce pripájať vlastný kľúč, si vyberie jeden odtiaľto a
 * platí za každú odoslanú hlasovku (cena je na karte Pricing). Hlasy sú
 * v databáze, nie v kóde — výmena za nové znamená zmenu ID, nie deploy.
 */
export default async function AdminVoicesPage() {
  await requireSuperadmin();

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("managed_voices")
    .select("id, label, eleven_voice_id, description, active")
    .order("sort")
    .order("label");

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        title="Voices"
        description="Voices from our own ElevenLabs account. Clients pick one instead of connecting their own key."
      />

      {error ? (
        <Callout tone="danger">Could not load voices: {error.message}</Callout>
      ) : (
        <VoicesManager voices={(data ?? []) as ManagedVoice[]} />
      )}
    </>
  );
}
