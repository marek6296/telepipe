"use client";

import { Quote } from "lucide-react";

import { savePersonaAction } from "@/app/app/m/[id]/persona/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { NumberField, TextAreaField, TextField } from "@/components/app/forms/fields";
import { LanguagePicker } from "@/components/app/forms/language-picker";
import { normalizeExtra, normalizePrimary } from "@/lib/languages";
import { Card, CardHeader } from "@/components/app/ui";

export type PersonaRow = {
  model_id: string;
  name: string;
  age: number | null;
  city: string | null;
  /** Voľné pole z čias pred štruktúrou. Do promptu už nejde — jazyk určuje
   *  `lang_primary`. Ostáva v type, lebo stĺpec v databáze stále existuje. */
  language: string;
  languages: string;
  lang_primary: string;
  lang_extra: unknown;
  backstory: string;
  tone: string;
  msg_style: string;
  boundaries: string;
  funnel_rules: string;
  cta_link: string;
  extra_rules: string;
  examples: string;
};

/**
 * Persona = kto je a ako píše. Polia sedia 1:1 na stĺpce tabuľky `persona`
 * (migrácia 003), popisy vychádzajú z toho, ako ich používa prompt v predlohe.
 */
export function PersonaForm({ persona }: { persona: PersonaRow }) {
  return (
    <AutoSaveForm save={(patch) => savePersonaAction(persona.model_id, patch)}>
      <Card>
        <CardHeader
          title="Who she is"
          description="The basics every message leans on. She never contradicts these."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <TextField
            name="name"
            label="Name"
            defaultValue={persona.name ?? ""}
            placeholder="Simona"
            help="The name she introduces herself with."
          />
          <NumberField
            name="age"
            label="Age"
            defaultValue={persona.age}
            min={18}
            max={99}
            help="Adults only — 18 or older."
          />
          <TextField
            name="city"
            label="City"
            defaultValue={persona.city ?? ""}
            placeholder="Los Angeles"
            help="Where she says she lives. Drives her local time and small talk."
          />
          <LanguagePicker
            primary={normalizePrimary(persona.lang_primary)}
            extra={normalizeExtra(persona.lang_extra, normalizePrimary(persona.lang_primary))}
          />
          {/* Doplnok, nie ďalší jazyk. Zoznam vyššie hovorí ČO vie; sem patrí,
              AKO s tým narába („s Nemcami radšej po anglicky, hanbí sa"). Prompt
              to pripája pod štruktúru, takže to tvrdé fakty neprepíše. */}
          <TextAreaField
            name="languages"
            label="Anything else about languages"
            defaultValue={persona.languages}
            rows={2}
            className="sm:col-span-2"
            placeholder="Learned Spanish on holiday, still shy about it."
            help="Optional. A note in her own words — it does not add a language, the picker above does that."
          />
          <TextAreaField
            name="backstory"
            label="Backstory"
            defaultValue={persona.backstory}
            rows={4}
            placeholder="Studies design, runs in the mornings, lives alone with a cat."
            className="sm:col-span-2"
            help="Job, studies, hobbies, pets — the facts she can talk about without inventing new ones."
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="How she writes"
          description="Tone and shape of her messages. This is what makes her read as a person."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <TextAreaField
            name="tone"
            label="Tone"
            defaultValue={persona.tone}
            rows={3}
            placeholder="playful, a little cheeky, flirty but never vulgar"
            help="The mood of her replies."
          />
          <TextAreaField
            name="msg_style"
            label="Message style"
            defaultValue={persona.msg_style}
            rows={3}
            placeholder="short 1–2 sentence messages, lowercase, an emoji now and then, no full stop at the end"
            help="Length, punctuation, capitalisation, emoji habits."
          />
          <TextAreaField
            name="boundaries"
            label="What she never does"
            defaultValue={persona.boundaries}
            rows={3}
            placeholder="never promises to meet up or video call, never mentions other fans"
            help="Hard limits. She phrases them as her own choice, never as “I can't”."
          />
          <TextAreaField
            name="extra_rules"
            label="Extra instructions"
            defaultValue={persona.extra_rules}
            rows={3}
            placeholder="anything else she should keep in mind"
            help="Free-form additions to her prompt."
          />
          <TextAreaField
            name="examples"
            label="Examples of her writing"
            defaultValue={persona.examples}
            rows={5}
            placeholder={"heyy sorry just got out of the shower\nlol you're too much\nwhat are u up to tonight"}
            className="sm:col-span-2"
            help="Paste a handful of her real messages, one per line. A sample teaches her voice far better than any list of rules."
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Your funnel"
          description="How a conversation turns into a subscriber."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <TextField
            name="cta_link"
            label="Your link"
            defaultValue={persona.cta_link}
            placeholder="https://fanvue.com/yourprofile"
            type="url"
            help="Leave this empty and she never sends a link at all. Hard limits still apply: never before the 6th message, at most once per fan every 48 hours, and never more than the “Links per hour” cap you set on the Behavior tab."
          />
          <TextAreaField
            name="funnel_rules"
            label="How she leads to it"
            defaultValue={persona.funnel_rules}
            rows={3}
            placeholder="chat first and get to know him, mention the platform only when he pushes for more"
            help="She never sends the link before the 6th message, and only once the chat is warm."
          />
        </div>
      </Card>

      <p className="flex items-start gap-2 px-1 text-[11.5px] text-[var(--app-text-4)]">
        <Quote className="mt-px h-3.5 w-3.5 shrink-0" />
        Changes save themselves and take effect from her next reply — no restart needed.
      </p>
    </AutoSaveForm>
  );
}
