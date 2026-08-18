"use client";

import { saveReplyModeAction } from "@/app/app/m/[id]/reply-mode-actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { NumberField, SelectField } from "@/components/app/forms/fields";
import { Card, CardHeader } from "@/components/app/ui";

/**
 * Prepínač režimu odpovedania pre jeden kanál (Telegram alebo Fanvue).
 * Off / Auto / Semi + čas do auto-odoslania (len pri Semi). Auto-save cez
 * `saveReplyModeAction`; worker číta tie isté stĺpce.
 */
export function ReplyModeForm({
  modelId,
  channel,
  mode,
  fallbackMinutes,
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
            help="Semi-automatic sends every draft to your Telegram control bot: pick one of three suggestions, write your own, or attach a photo or voice note. Everything you send is saved with full context, so switching back to Automatic continues seamlessly."
          />
          <NumberField
            name="fallback_minutes"
            label="Auto-send after (minutes)"
            defaultValue={fallbackMinutes ?? 0}
            min={0}
            max={1440}
            help="Semi-automatic only: if you don't decide within this many minutes, she sends the top suggestion herself. 0 = wait forever until you decide."
          />
        </div>
      </Card>
    </AutoSaveForm>
  );
}
