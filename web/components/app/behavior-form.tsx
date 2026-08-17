"use client";


import { saveBehaviorAction } from "@/app/app/m/[id]/behavior/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import {
  NumberField,
  RangeRow,
  SelectField,
  SliderField,
  SwitchField,
  TimeField,
} from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";

export type BehaviorRow = {
  model_id: string;
  mode: string;
  heat: string;
  slang: string;
  no_diacritics: boolean;
  activity_waves: boolean;
  active_tz: string;
  active_start_min: number;
  active_end_min: number;
  debounce_min_s: number;
  debounce_max_s: number;
  read_delay_min_s: number;
  read_delay_max_s: number;
  reply_delay_min_s: number;
  reply_delay_max_s: number;
  quick_reply_chance: number | string;
  quick_read_max_s: number;
  quick_reply_min_s: number;
  quick_reply_max_s: number;
  seen_only_chance: number | string;
  seen_only_min_s: number;
  seen_only_max_s: number;
  long_pause_chance: number | string;
  long_pause_min_s: number;
  long_pause_max_s: number;
  defer_reply_chance: number | string;
  defer_min_s: number;
  defer_max_s: number;
  question_chance: number | string;
  gag_chance: number | string;
  greeting_gap_hours: number;
  summary_every: number;
  max_replies_per_hour: number;
  max_links_per_hour: number;
  photo_cooldown_min: number;
  morning_enabled: boolean;
  morning_max_per_day: number;
  max_outreach_per_hour: number;
  max_active_chats: number;
  chat_slot_min: number;
};

/** Časové zóny, ktoré agentúry reálne používajú. Aktuálnu vždy doplníme. */
const TIME_ZONES = [
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Lisbon",
  "Europe/Madrid",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Prague",
  "Europe/Bratislava",
  "Europe/Warsaw",
  "Europe/Bucharest",
  "Europe/Kyiv",
  "Europe/Moscow",
  "Asia/Dubai",
  "Asia/Bangkok",
  "Asia/Manila",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const num = (value: number | string): number =>
  typeof value === "number" ? value : Number.parseFloat(value) || 0;

const percent = (value: number) => `${Math.round(value * 100)}%`;

/**
 * Chovanie = ako sa správa, nie čo hovorí. Skupiny kopírujú menu kontrolného
 * bota v predlohe (Chovanie → Časovanie / Náhodnosť / Bezpečnosť), polia sedia
 * na stĺpce tabuľky `behavior`.
 */
export function BehaviorForm({ behavior }: { behavior: BehaviorRow }) {
  const tzOptions = Array.from(new Set([behavior.active_tz, ...TIME_ZONES]))
    .filter(Boolean)
    .map((zone) => ({ value: zone, label: zone.replace(/_/g, " ") }));

  return (
    <AutoSaveForm save={(patch) => saveBehaviorAction(behavior.model_id, patch)}>
      {/* --- Štýl chatu ------------------------------------------------------ */}
      <Card>
        <CardHeader
          title="Chat style"
          description="How openly she talks and how human her typing looks."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <SelectField
            name="mode"
            label="Mode"
            defaultValue={behavior.mode}
            options={[
              { value: "real", label: "Real person" },
              { value: "ai", label: "Admits being an AI" },
            ]}
            help="In “real person” mode she never admits to being an AI. In the other mode she says so when asked."
          />
          <SelectField
            name="heat"
            label="Spice level"
            defaultValue={behavior.heat}
            options={[
              { value: "mild", label: "Mild — friendly" },
              { value: "medium", label: "Medium — flirty" },
              { value: "hot", label: "Hot — very open" },
            ]}
            help="How far she goes in text. Explicit content always stays on your platform, never in Telegram."
          />
          <SelectField
            name="slang"
            label="Slang"
            defaultValue={behavior.slang}
            options={[
              { value: "none", label: "None — clean writing" },
              { value: "light", label: "Light — lol, btw, u" },
              { value: "medium", label: "Medium — heavy texting slang" },
            ]}
            help="How casual her spelling gets."
          />
          <SliderField
            name="question_chance"
            label="Asks a question back"
            defaultValue={num(behavior.question_chance)}
            format={percent}
            help="How often she ends a reply with a question. Keeps a chat alive; too high feels like an interview. For the first 20 messages of a chat she asks at least 80% of the time whatever this says — that phase is for getting to know him. Set it to 0 and she never asks, not even then."
          />
          <SliderField
            name="gag_chance"
            label="Cheeky joke"
            defaultValue={num(behavior.gag_chance)}
            format={percent}
            help="Chance of a teasing one-liner instead of a straight answer."
          />
          <div className="space-y-3 sm:col-span-2">
            <SwitchField
              name="no_diacritics"
              label="Type without accents"
              defaultValue={behavior.no_diacritics}
              help="Strips accents from her messages the way people actually text. Handled in code, not by the model."
            />
            <SwitchField
              name="activity_waves"
              label="Waves of activity"
              defaultValue={behavior.activity_waves}
              help="Some hours she answers almost instantly, others she is slow — like a real phone habit."
            />
          </div>
        </div>
      </Card>

      {/* --- Aktívne okno ---------------------------------------------------- */}
      <Card>
        <CardHeader
          title="Active hours"
          description="Outside this window she does not reply — messages wait and get answered when she wakes up."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-3">
          <TimeField
            name="active_start_min"
            label="Awake from"
            defaultValue={behavior.active_start_min}
          />
          <TimeField
            name="active_end_min"
            label="Until"
            defaultValue={behavior.active_end_min}
            help="Can pass midnight — 12:12 to 02:30 is a normal night owl."
          />
          <SelectField
            name="active_tz"
            label="Her time zone"
            defaultValue={behavior.active_tz}
            options={tzOptions}
            help="Her local time drives the whole day — what she is doing, when she says good night."
          />
          <div className="sm:col-span-3">
            <SwitchField
              name="morning_enabled"
              label="Morning messages"
              defaultValue={behavior.morning_enabled}
              help="She reaches out first to quiet chats when her day starts."
            />
          </div>
          <NumberField
            name="morning_max_per_day"
            label="Morning messages per day"
            defaultValue={behavior.morning_max_per_day}
            min={0}
            max={500}
            help="Across all her chats."
          />
          <NumberField
            name="greeting_gap_hours"
            label="Greets again after"
            defaultValue={behavior.greeting_gap_hours}
            min={0}
            max={168}
            suffix="h"
            help="Below this gap she just carries on — no “hey” at the start of every message."
          />
        </div>
      </Card>

      {/* --- Časovanie -------------------------------------------------------- */}
      <Card>
        <CardHeader
          title="Timing"
          description="Nothing is instant. Every delay is picked at random inside these ranges."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <RangeRow
            label="Waits for him to finish typing"
            minField={{ name: "debounce_min_s", value: behavior.debounce_min_s }}
            maxField={{ name: "debounce_max_s", value: behavior.debounce_max_s }}
            suffix="s"
            help="If he sends three messages in a row, she answers all of them at once."
          />
          <RangeRow
            label="Before she reads"
            minField={{ name: "read_delay_min_s", value: behavior.read_delay_min_s }}
            maxField={{ name: "read_delay_max_s", value: behavior.read_delay_max_s }}
            suffix="s"
            help="Delay before the message gets marked as seen."
          />
          <RangeRow
            label="Before she replies"
            minField={{ name: "reply_delay_min_s", value: behavior.reply_delay_min_s }}
            maxField={{ name: "reply_delay_max_s", value: behavior.reply_delay_max_s }}
            suffix="s"
            help="Time between reading and the first message landing, typing indicator included."
          />
          <div className="space-y-4">
            <SliderField
              name="quick_reply_chance"
              label="Attentive mode"
              defaultValue={num(behavior.quick_reply_chance)}
              format={percent}
              help="How often she is glued to her phone and answers within seconds."
            />
            <RangeRow
              label="Attentive reply after"
              minField={{ name: "quick_reply_min_s", value: behavior.quick_reply_min_s }}
              maxField={{ name: "quick_reply_max_s", value: behavior.quick_reply_max_s }}
              suffix="s"
            />
            <NumberField
              name="quick_read_max_s"
              label="Attentive: seen within"
              defaultValue={behavior.quick_read_max_s}
              min={0}
              max={600}
              suffix="s"
            />
          </div>
        </div>
      </Card>

      {/* --- Náhodnosť -------------------------------------------------------- */}
      <Card>
        <CardHeader
          title="Randomness"
          description="The little inconsistencies that make her look like a person with a life."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <div className="space-y-4">
            <SliderField
              name="seen_only_chance"
              label="Leaves him on read"
              defaultValue={num(behavior.seen_only_chance)}
              format={percent}
              help="Sometimes she reads the message and replies a few minutes later."
            />
            <RangeRow
              label="…then answers after"
              minField={{ name: "seen_only_min_s", value: behavior.seen_only_min_s }}
              maxField={{ name: "seen_only_max_s", value: behavior.seen_only_max_s }}
              suffix="s"
            />
          </div>
          <div className="space-y-4">
            <SliderField
              name="long_pause_chance"
              label="Walks away from the phone"
              defaultValue={num(behavior.long_pause_chance)}
              format={percent}
              help="A longer gap in the middle of a conversation."
            />
            <RangeRow
              label="…for"
              minField={{ name: "long_pause_min_s", value: behavior.long_pause_min_s }}
              maxField={{ name: "long_pause_max_s", value: behavior.long_pause_max_s }}
              suffix="s"
            />
          </div>
          <div className="space-y-4 sm:col-span-2">
            <SliderField
              name="defer_reply_chance"
              label="Forgets to reply for hours"
              defaultValue={num(behavior.defer_reply_chance)}
              format={percent}
              help="Rare on purpose. She comes back with a “sorry, fell asleep” style opener."
            />
            <RangeRow
              label="…comes back after"
              minField={{ name: "defer_min_s", value: behavior.defer_min_s }}
              maxField={{ name: "defer_max_s", value: behavior.defer_max_s }}
              suffix="s"
            />
          </div>
        </div>
      </Card>

      {/* --- Limity ----------------------------------------------------------- */}
      <Card>
        <CardHeader
          title="Limits and memory"
          description="Guardrails that keep her account safe and her memory sharp."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-3">
          <NumberField
            name="max_replies_per_hour"
            label="Replies per hour"
            defaultValue={behavior.max_replies_per_hour}
            min={1}
            max={500}
            help="Across all chats. The strongest anti-ban setting there is."
          />
          <NumberField
            name="max_links_per_hour"
            label="Links per hour"
            defaultValue={behavior.max_links_per_hour}
            min={0}
            max={50}
            help="Counted from the database, so it survives a restart."
          />
          <NumberField
            name="photo_cooldown_min"
            label="Gap between photos"
            defaultValue={behavior.photo_cooldown_min}
            min={0}
            max={1440}
            suffix="min"
            help="Per fan. Stops her from dumping the whole library at once."
          />
          <NumberField
            name="summary_every"
            label="Summarise every"
            defaultValue={behavior.summary_every}
            min={1}
            max={200}
            suffix="msgs"
            help="How often she rewrites her rolling summary of a chat. Lower means sharper memory and slightly higher cost."
          />
        </div>

        {/* Tri stropy, ktoré rozhodujú o tom, či účet pôsobí ako človek alebo
            ako rozposielač. Worker ich čítal od začiatku (`userbot._smie_oslovit`,
            `_aktivne_rozhovory`), nastaviť sa dali len kontrolným botom. */}
        <div className="border-t border-[var(--app-border)] px-5 pb-5 pt-5">
          <p className="app-group-label mb-3">Looking like one person</p>
          <div className="grid gap-5 sm:grid-cols-3">
            <NumberField
              name="max_active_chats"
              label="Conversations at once"
              defaultValue={behavior.max_active_chats}
              min={0}
              max={100}
              help="Nobody holds twenty chats at the same time. Whoever does not fit waits and gets answered as soon as a slot frees up — no message is lost. 0 turns the limit off."
            />
            <NumberField
              name="chat_slot_min"
              label="A slot frees up after"
              defaultValue={behavior.chat_slot_min}
              min={1}
              max={1440}
              suffix="min"
              help="Counted from the last message in that chat, hers or his — waiting for his answer is still a live conversation."
            />
            <NumberField
              name="max_outreach_per_hour"
              label="People she writes to first"
              defaultValue={behavior.max_outreach_per_hour}
              min={0}
              max={200}
              suffix="/h"
              help="Replies do not count — answering someone who wrote first bothers nobody. An account that starts conversations on its own is the suspicious one, so the cap sits here. 0 turns it off."
            />
          </div>
        </div>
      </Card>

      <Callout tone="neutral">
        Every change saves itself and applies from her next reply. Timing values are ranges —
        the exact delay is rolled fresh each time, so two fans never see the same pattern.
      </Callout>
    </AutoSaveForm>
  );
}
