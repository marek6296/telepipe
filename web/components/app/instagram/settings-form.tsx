"use client";

import { saveInstagramSettingsAction } from "@/app/app/m/[id]/instagram/settings/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { SelectField, SwitchField, TextField } from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import type { InstagramRow } from "@/lib/instagram";

export function InstagramSettingsForm({ row }: { row: InstagramRow }) {
  return (
    <AutoSaveForm save={(patch) => saveInstagramSettingsAction(row.model_id, patch)}>
      {!row.connected && (
        <Callout tone="gold">
          Instagram is not connected yet, so nothing here has an effect. You can still set it
          up now — it applies the moment you connect.
        </Callout>
      )}

      <Card>
        <CardHeader
          title="Replying"
          description="Off until you are sure. Semi sends every reply to your control bot for approval first — the same as Telegram."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <SelectField
            name="reply_mode"
            label="Instagram replies"
            defaultValue={row.reply_mode}
            options={[
              { value: "off", label: "Off — she does not answer" },
              { value: "auto", label: "Auto — she answers on her own" },
              { value: "semi", label: "Semi — you approve each reply" },
            ]}
            help="Semi queues a reply after your approval. Both modes still follow her shared daily schedule, the messaging window and delivery limits."
          />
          <SelectField
            name="heat"
            label="How far she goes"
            defaultValue={row.heat}
            options={[
              { value: "mild", label: "Mild — friendly, light flirting" },
              { value: "medium", label: "Medium — flirty, suggestive" },
            ]}
            help="Instagram conversations stay non-explicit. Her established persona and writing style remain shared."
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Where she sends people"
          description="Telegram: at most 4 invitations, at least 2 hours apart. Linkovne: at most 2, at least 4 hours apart. Both LA-day and rolling 24-hour limits apply; all links stay at least 1 hour apart."
        />
        <div className="space-y-5 p-5">
          <SelectField
            name="funnel_target"
            label="She points people to"
            defaultValue={row.funnel_target}
            options={[
              { value: "telegram", label: "Her Telegram" },
              { value: "bio_link", label: "Her Linkovne page" },
              { value: "both", label: "Telegram or Linkovne, by context" },
            ]}
            help="One URL per person across both destinations. Invitations require relevant context and confirmed adult status. She keeps talking normally when an invitation is unavailable."
          />
          <TextField
            name="telegram_handle"
            label="Her Telegram username"
            defaultValue={row.telegram_handle}
            placeholder="simona_here"
            help="Without the @. The server inserts this exact Telegram link when the invitation is allowed."
          />
          <TextField
            name="bio_link"
            label="Her link page"
            defaultValue={row.bio_link}
            placeholder="https://linkovne.com/yourname"
            help="Your HTTPS linkovne.com profile. Direct Fanvue links are not sent on Instagram."
          />
        </div>
      </Card>

      <Card>
        <CardHeader title="History and interactions" description="Shared day and timezone come from Persona. Delays and quotas are conservative product limits, not a guarantee against platform restrictions." />
        <div className="space-y-5 p-5">
          <SwitchField name="sync_enabled" label="Import conversation history, including while replies are Off" defaultValue={row.sync_enabled} help="Imports available recent Meta messages with their original times. Importing old conversations does not send replies. Meta may expose only the latest 20 message details per chat." />
          <SwitchField name="highlights_link" label="Her Highlights contain the link" defaultValue={row.highlights_link} help="When the account URL allowance is spent, she may naturally point to Highlights in her own voice. This also has a per-person reminder limit." />
          <SwitchField name="reactions_enabled" label="React to emoji replies in DMs" defaultValue={row.reactions_enabled} help="Delayed heart reactions to incoming messages, including story replies delivered as DMs. Bare story likes and public comment likes are not available with this connection." />
          <SwitchField name="photos_enabled" label="Allow one approved SFW photo per person" defaultValue={row.photos_enabled} help="Choose the photo below first. No voices or videos on Instagram; no repeated photo sends." />
          <SwitchField name="typo_enabled" label="Occasional small spelling variation" defaultValue={row.typo_enabled} help="About one eligible reply in twenty. Never changes links, names, numbers or negations. The intended word is remembered for a correction." />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Comments"
          description="Public replies under her posts, not DMs."
        />
        <div className="p-5">
          <SwitchField
            name="reply_comments"
            label="Reply to comments on her posts"
            defaultValue={row.reply_comments}
            help="Selects a minority of suitable comments, with questions more likely to get a reply. At least 10 minutes apart, at most 3 per hour and 12 per day. No private conversation history or links in public replies."
          />
        </div>
      </Card>
    </AutoSaveForm>
  );
}
