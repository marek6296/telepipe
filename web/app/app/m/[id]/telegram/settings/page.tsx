import type { Metadata } from "next";
import Link from "next/link";

import {
  TelegramLimitsForm,
  type TelegramLimitsRow,
} from "@/components/app/telegram/limits-form";
import { Callout, PageHeader } from "@/components/app/ui";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Telegram settings",
};

/**
 * Anti-ban stropy, a nič viac.
 *
 * PREČO TU UŽ NIE JE KONTROLNÝ BOT. Bol tu aj na karte Connection, zakaždým
 * inými slovami — a klient tak musel medzi dvoma podkartami preklikávať, aby
 * zistil, čo je vlastne nastavené. Bot aj súkromný Telegram sú stavy jedného
 * pripojenia, takže sedia pri ňom (`/telegram`), ako druhý a tretí blok. Tu
 * ostali tri čísla, ktoré s pripojením nesúvisia vôbec: chránia účet pred
 * banom bez ohľadu na to, kto dostáva notifikácie.
 */
export default async function TelegramSettingsPage({
  params,
}: PageProps<"/app/m/[id]/telegram/settings">) {
  const { id } = await params;
  const model = await requireModelSubTab(id, "telegram", "settings");

  const supabase = await createClient();
  const { data } = await supabase
    .from("behavior")
    .select("model_id, max_active_chats, chat_slot_min, max_outreach_per_hour")
    .eq("model_id", model.id)
    .maybeSingle();

  return (
    <>
      <PageHeader
        eyebrow="Telegram agent"
        title="Telegram settings"
        description="The caps that keep her account out of Telegram's sights. The connection itself, your control bot and your private Telegram are all on the Telegram tab; how she talks lives on the Persona tab."
      />

      <div className="flex flex-col gap-5">
        {data ? (
          <TelegramLimitsForm limits={data as unknown as TelegramLimitsRow} />
        ) : (
          <Callout tone="danger">
            Her behaviour row is missing, so the limits cannot be shown. Reload the page,
            and contact us if it stays empty.
          </Callout>
        )}

        <p className="text-[12.5px] text-[var(--app-text-3)]">
          Looking for the control bot or the pairing with your own Telegram?{" "}
          <Link
            href={`/app/m/${model.id}/telegram`}
            className="underline underline-offset-2 transition-colors hover:text-[var(--app-text)]"
          >
            They live on the Telegram tab
          </Link>
          , each with its own block.
        </p>
      </div>
    </>
  );
}
