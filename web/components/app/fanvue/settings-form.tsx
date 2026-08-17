"use client";

import { saveFanvueSettingsAction } from "@/app/app/m/[id]/fanvue/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import {
  NumberField,
  RangeRow,
  SelectField,
  SwitchField,
  TextAreaField,
  TimeField,
} from "@/components/app/forms/fields";
import { RelativeTime } from "@/components/app/relative-time";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import type { FanvueSettings } from "@/lib/fanvue-ui";

/**
 * Nastavenia FANVUE agenta — nie tie telegramové.
 *
 * Modelka má dvoch agentov a každý má svoje. Telegram sa riadi tabuľkou
 * `behavior` (karta Behavior), Fanvue tabuľkou `fanvue`; spoločná je len
 * persona, pamäť a časová zóna — je to tá istá osoba a nesmie si protirečiť.
 * Rozdiel nie je kozmetický: na Telegrame človek ešte nezaplatil a celý zmysel
 * rozhovoru je dostať ho na Fanvue. Tu už zaplatil, odkaz sa nespomína nikdy
 * a namiesto lákania sa predáva obsah.
 *
 * Skupiny sedia na to, čo kód naozaj číta (`docs/fanvue-settings.md`), nie na
 * to, čo by sa dalo pekne nadpísať.
 */
export function FanvueSettingsForm({
  modelId,
  settings,
  connected,
}: {
  modelId: string;
  settings: FanvueSettings;
  connected: boolean;
}) {
  return (
    <AutoSaveForm save={(patch) => saveFanvueSettingsAction(modelId, patch)}>
      {!connected && (
        <Callout tone="neutral">
          The account is not connected yet, so nothing here applies. You can still set it
          up — the moment you connect, she starts from these values.
        </Callout>
      )}

      {/* --- Rozhovor --------------------------------------------------------- */}
      <Card>
        <CardHeader
          title="Replies"
          description="Her Fanvue side. Everything below is separate from Telegram — same person, different register."
        />
        <div className="space-y-5 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <SwitchField
              name="greet_new"
              label="Greet new subscribers"
              defaultValue={settings.greet_new}
              help="Writes first the moment someone subscribes, before he says anything."
            />
            <SelectField
              name="heat"
              label="Spice level"
              defaultValue={settings.heat}
              options={[
                { value: "mild", label: "Mild — friendly" },
                { value: "medium", label: "Medium — flirty" },
                { value: "hot", label: "Hot — no holding back" },
              ]}
              help="Hot is the default here on purpose: he is a paying subscriber and that is what he pays for."
            />
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <NumberField
              name="discovery_msgs"
              label="Gets to know him for"
              defaultValue={settings.discovery_msgs}
              min={0}
              max={20}
              suffix="msgs"
              help="First messages are not for selling — they are for finding out who he is and what he came for. Ends sooner if he says it himself."
            />
            <NumberField
              name="summary_every"
              label="Summarise every"
              defaultValue={settings.summary_every}
              min={1}
              max={200}
              suffix="msgs"
              help="How often she rewrites her rolling summary of the chat. Lower means sharper memory and slightly higher cost."
            />
            <div className="sm:col-span-2">
              <RangeRow
                label="Waits before replying"
                minField={{ name: "reply_min_s", value: settings.reply_min_s }}
                maxField={{ name: "reply_max_s", value: settings.reply_max_s }}
                suffix="s"
                help="Rolled fresh for every message. Shorter than Telegram — this is a paid chat and nobody waits half an hour in one."
              />
            </div>
          </div>

          <div className="border-t border-[var(--app-border)] pt-5">
            <p className="app-group-label mb-3">Active hours on Fanvue</p>
            <div className="grid gap-5 sm:grid-cols-2">
              <TimeField
                name="active_start_min"
                label="Answers from"
                defaultValue={settings.active_start_min}
              />
              <TimeField
                name="active_end_min"
                label="Until"
                defaultValue={settings.active_end_min}
                help="Set both to the same time and she answers around the clock. The window may cross midnight."
              />
            </div>
            <p className="mt-3 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
              Her own window, separate from Telegram — but the same time zone: it is set
              once on the Behavior tab, because where she lives is a fact about the person,
              not about the platform.
            </p>
          </div>
        </div>
      </Card>

      {/* --- Predaj ----------------------------------------------------------- */}
      <Card>
        <CardHeader
          title="Selling"
          description="Three brakes at once — it has to be switched on, past the getting-to-know phase, and far enough from the last offer. Otherwise it reads as an ad."
        />
        <div className="space-y-5 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <SwitchField
              name="sell_content"
              label="Offers paid content"
              defaultValue={settings.sell_content}
              help="Off and she only chats. She never links to Fanvue here — he is already inside."
            />
            <SwitchField
              name="thank_purchases"
              label="Thanks for every purchase"
              defaultValue={settings.thank_purchases}
              help="Right after payment, in her own words, asking for nothing else. That is why people buy twice."
            />
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <NumberField
              name="offer_after_msgs"
              label="First offer after"
              defaultValue={settings.offer_after_msgs}
              min={0}
              max={200}
              suffix="msgs"
              help="An offer in the second message sounds like a vending machine."
            />
            <NumberField
              name="offer_cooldown_h"
              label="Gap between offers"
              defaultValue={settings.offer_cooldown_h}
              min={0}
              max={720}
              suffix="h"
              help="An unopened offer also blocks the next one — two unlocked ones side by side look like a pushy salesman."
            />
            <NumberField
              name="nudge_after_msgs"
              label="Brings it up herself after"
              defaultValue={settings.nudge_after_msgs}
              min={0}
              max={500}
              suffix="msgs"
              help="Not everyone asks, even when they would buy. Set to 0 and she waits to be asked. Once, then she lets it go."
            />
          </div>

          <div className="border-t border-[var(--app-border)] pt-5">
            <p className="app-group-label mb-3">Voice notes</p>
            <div className="grid gap-5 sm:grid-cols-2">
              <SwitchField
                name="voices_enabled"
                label="Sends voice notes"
                defaultValue={settings.voices_enabled}
                help="Made with her ElevenLabs voice, uploaded to the Fanvue vault, attached with a price. Needs a voice on the Behavior tab."
              />
              <NumberField
                name="voice_price_cents"
                label="Price of an explicit voice note"
                defaultValue={settings.voice_price_cents}
                min={0}
                max={100000}
                step={50}
                suffix="¢"
                help={`${usd(settings.voice_price_cents)}. Teasers always go free — the paid one only lands when the conversation is already hot.`}
              />
            </div>
          </div>
        </div>
      </Card>

      {/* --- Fotky a feed ------------------------------------------------------ */}
      <Card>
        <CardHeader
          title="Photos and feed"
          description="Which photos leave is decided in code, not by the model — otherwise the whole collection would be gone in a day."
        />
        <div className="space-y-5 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <SwitchField
              name="send_photos"
              label="Attaches photos to replies"
              defaultValue={settings.send_photos}
              help="From wherever she says she is: no photo comes out of the gym — she promises it for later and then really sends it."
            />
            <NumberField
              name="free_photo_max"
              label="Free photos per fan"
              defaultValue={settings.free_photo_max}
              min={0}
              max={50}
              help="The introduction — proof she is real. After that only on request, and not even always."
            />
          </div>

          <div className="border-t border-[var(--app-border)] pt-5">
            <p className="app-group-label mb-3">Posting to her feed</p>
            <div className="space-y-5">
              <SwitchField
                name="posting_enabled"
                label="Posts to the feed by herself"
                defaultValue={settings.posting_enabled}
                help="Takes photos from a folder marked “Feed posts” and writes the caption in her own style. A post stays forever, so the same photo never goes up twice."
              />
              <div className="grid gap-5 sm:grid-cols-2">
                <NumberField
                  name="post_every_h"
                  label="How often"
                  defaultValue={settings.post_every_h}
                  min={0}
                  max={720}
                  suffix="h"
                  help="0 means never."
                />
                <SelectField
                  name="post_audience"
                  label="Who sees it"
                  defaultValue={settings.post_audience}
                  options={[
                    { value: "followers-and-subscribers", label: "Followers and subscribers" },
                    { value: "subscribers", label: "Subscribers only" },
                  ]}
                  help="Followers do not pay yet — for them a post is the bait."
                />
              </div>
              {settings.last_post_at && (
                <p className="text-[11.5px] text-[var(--app-text-4)]">
                  Last posted <RelativeTime iso={settings.last_post_at} />.
                </p>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* --- Vlastné pokyny ---------------------------------------------------- */}
      <Card>
        <CardHeader
          title="Extra instructions"
          description="Goes into the prompt on Fanvue only. Her persona stays the same person — this is what she wants out of the conversation here."
        />
        <div className="p-5">
          <TextAreaField
            name="extra_rules"
            label="Fanvue instructions"
            defaultValue={settings.extra_rules}
            rows={6}
            placeholder="e.g. never promise a custom video, always ask what he does for a living"
            help="Leave empty and she runs on her persona plus the rules above."
          />
        </div>
      </Card>
    </AutoSaveForm>
  );
}

function usd(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}
