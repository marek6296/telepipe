"use client";

import { saveReplyModeAction } from "@/app/app/m/[id]/reply-mode-actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { SelectField } from "@/components/app/forms/fields";
import { Card, CardHeader } from "@/components/app/ui";

/**
 * Prepínač režimu odpovedania pre jeden kanál (Telegram alebo Fanvue).
 * Off / Auto / Semi; Semi vždy čaká na majiteľa. Auto-save cez
 * `saveReplyModeAction`; worker číta tie isté stĺpce.
 */
export function ReplyModeForm({
  modelId,
  channel,
  mode,
}: {
  modelId: string;
  channel: "telegram" | "fanvue";
  mode: string;
  fallbackMinutes: number | null;
}) {
  const platform = channel === "telegram" ? "Telegram" : "Fanvue";
  return (
    <AutoSaveForm
      save={(patch) => saveReplyModeAction(modelId, channel, patch)}
      sticky={false}
    >
      <Card>
        <CardHeader
          title="Reply mode"
          description={`How she handles incoming ${platform} messages. This is set separately for each channel.`}
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <SelectField
            name="mode"
            label="How she replies"
            defaultValue={mode}
            options={[
              { value: "off", label: "Off — she doesn't reply" },
              { value: "auto", label: "Automatic — she replies on her own" },
              { value: "semi", label: "Semi-automatic — you approve every reply" },
            ]}
            help="Automatic follows her daily schedule. Semi prepares drafts in Social sites and waits for your approval, with no automatic timeout. Your Telegram bot can notify you with a link to the conversation. Context is saved across modes."
          />
        </div>
      </Card>
    </AutoSaveForm>
  );
}
