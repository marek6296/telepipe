import type { Metadata } from "next";

import { PricingForm, type ConfigRow } from "@/components/app/admin/pricing-form";
import { Callout, PageHeader } from "@/components/app/ui";
import { requireSuperadmin } from "@/lib/admin";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Pricing",
};

/**
 * Ceny a marže celej platformy.
 *
 * Jediné miesto, kde tieto čísla žijú, je tabuľka `app_config` — číta ju aj
 * worker (pri účtovaní) aj klientske UI (pri zobrazení ceny). Preto sa tu
 * nemení kód a netreba deploy: uložením sa mení správanie oboch naraz.
 *
 * Superadmin-only. Bežný admin spravuje účty, nie cenník celej platformy.
 */
export default async function AdminPricingPage() {
  await requireSuperadmin();

  const supabase = await createClient();
  const { data, error } = await supabase
    .from("app_config")
    .select("key, value, note")
    .order("key");

  const config: ConfigRow[] = (data ?? []).map((row) => ({
    key: String(row.key),
    value: Number(row.value),
    note: String(row.note ?? ""),
  }));

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        title="Pricing"
        description="Margins and fees for the whole platform. Changes apply to the next reply — no deploy needed."
      />

      {error ? (
        <Callout tone="danger">Could not load pricing: {error.message}</Callout>
      ) : (
        <PricingForm config={config} />
      )}
    </>
  );
}
