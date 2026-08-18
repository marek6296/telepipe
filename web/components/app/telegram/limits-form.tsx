"use client";

import { saveBehaviorAction } from "@/app/app/m/[id]/persona/behavior/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { NumberField } from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";

/**
 * Tri stropy, ktoré rozhodujú o tom, či účet pôsobí ako človek alebo ako
 * rozposielač. Worker ich číta od začiatku (`userbot._smie_oslovit`,
 * `_aktivne_rozhovory`), nastaviť sa dali najprv len kontrolným botom, potom
 * na karte Behavior.
 *
 * Teraz sedia tu, lebo nehovoria nič o jej povahe — chránia jeden konkrétny
 * telegramový účet pred banom. Je to tá istá tabuľka `behavior` a to isté
 * auto-save; validáciu rozsahov drží `saveBehaviorAction`, nie tento formulár.
 */
export type TelegramLimitsRow = {
  model_id: string;
  max_active_chats: number;
  chat_slot_min: number;
  max_outreach_per_hour: number;
};

export function TelegramLimitsForm({ limits }: { limits: TelegramLimitsRow }) {
  return (
    <AutoSaveForm save={(patch) => saveBehaviorAction(limits.model_id, patch)} sticky={false}>
      <Card>
        <CardHeader
          title="Looking like one person"
          description="Telegram does not ban accounts for what they say — it bans them for behaving like software. These three caps are what keeps hers looking human."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-3">
          <NumberField
            name="max_active_chats"
            label="Conversations at once"
            defaultValue={limits.max_active_chats}
            min={0}
            max={100}
            help="Nobody holds twenty chats at the same time. Whoever does not fit waits and gets answered as soon as a slot frees up — no message is lost. 0 turns the limit off."
          />
          <NumberField
            name="chat_slot_min"
            label="A slot frees up after"
            defaultValue={limits.chat_slot_min}
            min={1}
            max={1440}
            suffix="min"
            help="Counted from the last message in that chat, hers or his — waiting for his answer is still a live conversation."
          />
          <NumberField
            name="max_outreach_per_hour"
            label="People she writes to first"
            defaultValue={limits.max_outreach_per_hour}
            min={0}
            max={200}
            suffix="/h"
            help="Replies do not count — answering someone who wrote first bothers nobody. An account that starts conversations on its own is the suspicious one, so the cap sits here. 0 turns it off."
          />
        </div>
      </Card>

      <Callout tone="neutral">
        Everything here saves itself and applies from her next reply — no restart, and her
        Telegram session stays connected.
      </Callout>
    </AutoSaveForm>
  );
}
