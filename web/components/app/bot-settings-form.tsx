"use client";

import { Bell } from "lucide-react";

import { saveBotSettingsAction } from "@/app/app/m/[id]/telegram/bot/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { SwitchField } from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";

export type BotSettingsRow = {
  model_id: string;
  notify_fanvue_subscribe: boolean;
  notify_fanvue_payment: boolean;
  notify_fanvue_follow: boolean;
  notify_fanvue_like: boolean;
  notify_fanvue_comment: boolean;
  notify_credits_low: boolean;
  notify_startup: boolean;
  notify_crash: boolean;
  notify_hot_lead: boolean;
  daily_report: boolean;
  weekly_report: boolean;
};

/**
 * Čo má control bot hlásiť.
 *
 * Fanvue sekcia sa ukáže len keď je Fanvue pripojené — prepínače pre
 * notifikácie, ktoré nemajú z čoho vzniknúť, sú horšie než ich neponúknuť.
 */
export function BotSettingsForm({
  settings,
  fanvueConnected,
  paired,
}: {
  settings: BotSettingsRow;
  fanvueConnected: boolean;
  paired: boolean;
}) {
  return (
    <AutoSaveForm save={(patch) => saveBotSettingsAction(settings.model_id, patch)}>
      {!paired && (
        <Callout tone="gold">
          Your control bot is not paired yet, so nothing can be delivered. Finish it on the{" "}
          <strong>Connection</strong> tab — these settings are kept and start working the moment
          you pair it.
        </Callout>
      )}

      {/* Bez pripojeného Fanvue sa karta NEZOBRAZÍ vôbec. Prepínače pre
          notifikácie, ktoré nemajú z čoho vzniknúť, sú horšie než ich
          neponúknuť — klient si ich zapne a čaká na správy, čo neprídu. */}
      {fanvueConnected ? (
        <Card>
          <CardHeader
            title="Fanvue notifications"
            description="Sent to your control bot the moment Fanvue tells us."
          />
          <div className="space-y-3 p-5">
            <SwitchField
              name="notify_fanvue_subscribe"
              label="New subscriber"
              defaultValue={settings.notify_fanvue_subscribe}
              help="Someone started paying for her page."
            />
            <SwitchField
              name="notify_fanvue_payment"
              label="Payment received"
              defaultValue={settings.notify_fanvue_payment}
              help="A paid post, tip or unlock. The amount is in the message."
            />
            {/* Follow je zámerne s poznámkou: nemáme overené, že ho Fanvue
                vôbec posiela. Sľubovať notifikáciu, ktorá nemusí nikdy prísť,
                by bolo horšie než ju priznať ako neistú. */}
            <SwitchField
              name="notify_fanvue_follow"
              label="New follower"
              defaultValue={settings.notify_fanvue_follow}
              help="Only if Fanvue sends this event — we have never seen one, so it may stay quiet."
            />
            <SwitchField
              name="notify_fanvue_like"
              label="Post liked"
              defaultValue={settings.notify_fanvue_like}
              help="Off by default — a busy page can produce dozens a day."
            />
            <SwitchField
              name="notify_fanvue_comment"
              label="New comment"
              defaultValue={settings.notify_fanvue_comment}
            />
          </div>
        </Card>
      ) : (
        <Callout>
          Fanvue is not connected, so there is nothing to report from it yet. Connect it on her
          <strong> Fanvue</strong> tab and these notifications appear here.
        </Callout>
      )}

      <Card>
        <CardHeader
          title="Status and balance"
          description="Things about your account and the agent itself, not about her chats."
        />
        <div className="space-y-3 p-5">
          {/* Prvé v sekcii zámerne: je to jediná notifikácia, ktorá hovorí,
              že služba NEFUNGUJE. Ostatné sú informatívne. */}
          <SwitchField
            name="notify_crash"
            label="She stopped replying"
            defaultValue={settings.notify_crash}
            help="Sent when the agent crashes and has to restart. Deploys and planned restarts are not reported — those are not faults."
          />
          <SwitchField
            name="notify_startup"
            label="Agent started"
            defaultValue={settings.notify_startup}
            help="Sent every time the agent boots — which includes every update we deploy. Useful while setting things up, noisy afterwards."
          />
          <SwitchField
            name="notify_credits_low"
            label="Pipe Coins running low"
            defaultValue={settings.notify_credits_low}
            help="One message when you drop under about 3,000 coins — roughly 50 replies left. It comes once, and again only after you top up and run low a second time."
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Chats worth your attention"
          description="Most chats run themselves. This is the one moment where stepping in is worth it."
        />
        <div className="space-y-3 p-5">
          <SwitchField
            name="notify_hot_lead"
            label="Someone is pushing for more"
            defaultValue={settings.notify_hot_lead}
            help="Sent when a fan asks where to find you, or pushes for something explicit — the moment he is closest to paying. At most once every 12 hours per conversation, so a single hot chat cannot flood you. She keeps replying either way; this only tells you it is happening."
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Daily summary"
          description="A short read of her day, sent when her active hours end."
        />
        <div className="space-y-3 p-5">
          <SwitchField
            name="daily_report"
            label="Send a daily summary"
            defaultValue={settings.daily_report}
            help="Who is warming up, who went cold, who is new. Arrives at the end of her active window in her own time zone — not at midnight UTC. Off by default because it costs a small amount of Pipe Coins each day."
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Weekly numbers"
          description="Monday morning, in her time zone: did the week actually earn anything?"
        />
        <div className="space-y-3 p-5">
          <SwitchField
            name="weekly_report"
            label="Send weekly numbers"
            defaultValue={settings.weekly_report}
            help="New conversations, how many of them got your link, how many she wrapped up, and what is left on your balance. Costs nothing — it is counting, not writing — so it is on by default. A quiet week is reported too: that is the week worth knowing about."
          />
        </div>
      </Card>

      <p className="flex items-start gap-2 px-1 text-[11.5px] text-[var(--app-text-4)]">
        <Bell className="mt-px h-3.5 w-3.5 shrink-0" />
        Everything here goes to your own control bot — the one you paired, not her account.
      </p>
    </AutoSaveForm>
  );
}
