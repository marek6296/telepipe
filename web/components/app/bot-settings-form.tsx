"use client";

import Link from "next/link";
import { ArrowUpRight, Bell } from "lucide-react";

import { saveBotSettingsAction } from "@/app/app/m/[id]/telegram/bot/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { SwitchField } from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";

export type BotSettingsRow = {
  model_id: string;
  notify_social_inbound: boolean;
};

export function BotSettingsForm({ settings, paired }: { settings: BotSettingsRow; paired: boolean }) {
  const modelPath = `/app/m/${settings.model_id}`;
  return (
    <AutoSaveForm save={(patch) => saveBotSettingsAction(settings.model_id, patch)}>
      {!paired && (
        <Callout tone="gold">
          Pair your control bot on the{" "}
          <Link href={`${modelPath}/telegram`} className="font-medium underline underline-offset-4">Connection tab</Link>
          {" "}to receive notifications. Your preference is saved while you finish connecting it.
        </Callout>
      )}

      <Card>
        <CardHeader title="New messages" description="A quiet heads-up when a conversation needs you." />
        <div className="space-y-5 p-5">
          <SwitchField
            name="notify_social_inbound"
            label="Notify me about new messages"
            defaultValue={settings.notify_social_inbound}
            help="Send incoming-message alerts from Telegram, Instagram and Fanvue to your paired control bot."
          />
          <div className="space-y-2 border-t border-[var(--app-border)] pt-4 text-[12px] leading-relaxed text-[var(--app-text-3)]">
            <p>Manual and Semi send alerts for new messages. Auto stays quiet unless you have taken over the conversation.</p>
            <p>Each alert opens the right chat in Social sites. Read the history, review a draft, use Say this or send your own reply there.</p>
            <Link href={`${modelPath}/social`} className="inline-flex items-center gap-1.5 pt-1 font-medium text-[var(--app-text-2)] hover:text-[var(--app-text)]">
              Open Social sites<ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </Card>

      <p className="flex items-start gap-2 px-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        <Bell className="mt-px h-3.5 w-3.5 shrink-0" />
        Notifications go to your own paired bot. Manage replies and channel modes in Social sites.
      </p>
    </AutoSaveForm>
  );
}
