"use client";

import { saveInstagramSettingsAction } from "@/app/app/m/[id]/instagram/settings/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { SelectField, SwitchField, TextField } from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import type { InstagramRow } from "@/lib/instagram";

/**
 * Nastavenia Instagram agenta.
 *
 * ČO TU ZÁMERNE NIE JE: časovanie, hlasovky, fotky, ranné oslovenie ani nič
 * z Telegramu. Instagram je iná platforma s inými pravidlami a klient nemá
 * dostať štyridsať čísel, ktoré tu aj tak neplatia. Persona, jazyky a denný
 * život sú spoločné a nastavujú sa na karte Persona.
 *
 * Pikantnosť má LEN dva stupne. Explicitný obsah je na Instagrame dôvod na
 * zrušenie účtu, takže `hot` nie je voľba, ktorú by sme chceli klientovi
 * ponúknuť a potom mu vysvetľovať, prečo prišiel o profil.
 */
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
            help="Start on Semi. Instagram is public and a single odd reply is visible to anyone who screenshots it."
          />
          <SelectField
            name="heat"
            label="How far she goes"
            defaultValue={row.heat}
            options={[
              { value: "mild", label: "Mild — friendly, light flirting" },
              { value: "medium", label: "Medium — flirty, suggestive" },
            ]}
            help="There is no hot option here on purpose. Explicit talk in Instagram DMs is how creator accounts get deleted, and the account is worth more than one hot message."
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Where she sends people"
          description="Never straight to your paid page. A Fanvue or OnlyFans link in an Instagram DM is the fastest way to lose the account."
        />
        <div className="space-y-5 p-5">
          <SelectField
            name="funnel_target"
            label="She points people to"
            defaultValue={row.funnel_target}
            options={[
              { value: "telegram", label: "Her Telegram" },
              { value: "bio_link", label: "The link in her bio" },
            ]}
            help="Telegram is the stronger move: the conversation continues there with her full agent, and Instagram never sees where it leads."
          />
          <TextField
            name="telegram_handle"
            label="Her Telegram username"
            defaultValue={row.telegram_handle}
            placeholder="simona_here"
            help="Without the @. She names it in her own words — she never pastes a t.me link, because links in DMs get flagged."
          />
          <TextField
            name="bio_link"
            label="Her link page"
            defaultValue={row.bio_link}
            placeholder="https://linkovne.com/yourname"
            help="A link page (linkovne.com, Linktree, Beacons) that holds the real links. She only ever says it is in her bio — Instagram does not mind that."
          />
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
            help="Short, friendly, never flirty and never mentioning any link — comments are visible to everyone, including Instagram's own review. Off by default."
          />
        </div>
      </Card>
    </AutoSaveForm>
  );
}
