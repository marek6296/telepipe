"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import {
  AlertTriangle,
  Check,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Settings2,
} from "lucide-react";
import Link from "next/link";

import { saveBehaviorAction } from "@/app/app/m/[id]/behavior/actions";
import { reloadVoicesAction } from "@/app/app/m/[id]/voice/actions";
import { AutoSaveForm, useAutoSaveField } from "@/components/app/forms/auto-save";
import {
  SelectField,
  SliderField,
  SwitchField,
} from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import type { VoiceCatalog } from "@/lib/eleven";
import { cn } from "@/lib/utils";

/**
 * Karta hlasu jednej modelky.
 *
 * Pripojenie účtu ElevenLabs tu NIE JE zámerne — kľúč je jeden na celý účet
 * a býva v nastaveniach účtu (migrácia 017). Kto má päť modeliek, nemá ho
 * lepiť päťkrát. Tu sa vyberá hlas a nastavuje, kedy a ako sa používa.
 *
 * Všetky polia sedia na stĺpce tabuľky `behavior` a ukladá ich to isté
 * auto-save ako kartu Behavior (`saveBehaviorAction`).
 */

export type VoiceRow = {
  model_id: string;
  voices_enabled: boolean;
  eleven_voice_id: string;
  voice_ambience: string;
  voice_strength: string;
  voice_chance: number | string;
  voice_tempo: number | string;
  voice_ambience_level: number | string;
  voice_when_asked: boolean;
  voice_when_doubted: boolean;
  voice_when_he_voices: boolean;
  voice_when_away: boolean;
  voice_on_goodnight: boolean;
  voice_when_hot: boolean;
};

const AMBIENCE = [
  { value: "home", label: "At home" },
  { value: "bedroom", label: "Bedroom" },
  { value: "kitchen", label: "Kitchen" },
  { value: "bathroom", label: "Bathroom" },
  { value: "car", label: "In the car" },
  { value: "outside", label: "Outside" },
  { value: "cafe", label: "Café" },
  { value: "gym", label: "Gym" },
  { value: "none", label: "Silent" },
];

const num = (value: number | string): number =>
  typeof value === "number" ? value : Number.parseFloat(value) || 0;

const percent = (value: number) => `${Math.round(value * 100)}%`;

export function VoiceForm({
  voice,
  catalog: initial,
}: {
  voice: VoiceRow;
  catalog: VoiceCatalog;
}) {
  // Zoznam prišiel zo servera; „Reload" ho vymení bez prekreslenia stránky.
  // Synchronizovať stav späť na prop netreba — po pripojení kľúča sa sem človek
  // dostane novou navigáciou, teda novým mountom, a ten prop prevezme.
  const [catalog, setCatalog] = useState(initial);
  const [reloading, startReload] = useTransition();

  const reload = () =>
    startReload(async () => setCatalog(await reloadVoicesAction()));

  if (!catalog.connected) {
    return <NotConnected voice={voice} />;
  }

  return (
    <AutoSaveForm save={(patch) => saveBehaviorAction(voice.model_id, patch)}>
      {catalog.error && (
        <Callout tone="danger" icon={<AlertTriangle className="h-4 w-4" />}>
          {catalog.error}
        </Callout>
      )}

      <Card>
        <CardHeader
          title="Her voice"
          description="Every voice on your ElevenLabs account. Pick the one she speaks with."
          actions={
            <button
              type="button"
              onClick={reload}
              disabled={reloading}
              className="app-btn app-btn-ghost h-8 px-3"
            >
              {reloading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} />
              )}
              Reload
            </button>
          }
        />
        <VoicePicker voices={catalog.voices} selected={voice.eleven_voice_id} />
      </Card>

      <VoiceSettings voice={voice} />

      <Callout tone="neutral">
        Every change saves itself and applies from her next voice note. The
        ElevenLabs account is shared by all your models — swap the key in{" "}
        <Link href="/app/account" className="underline underline-offset-2">
          Account settings
        </Link>
        .
      </Callout>
    </AutoSaveForm>
  );
}

/* -------------------------------------------------------------------------- */
/*  Bez kľúča                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Účet nemá pripojené ElevenLabs. Nastavenia sa ukazujú, ale sú v zamknutom
 * `fieldset` — vidieť, čo tu bude, a nedá sa nastaviť niečo, čo aj tak nemá
 * čím zaznieť.
 */
function NotConnected({ voice }: { voice: VoiceRow }) {
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Her voice"
          description="Voice notes need an ElevenLabs account. It is connected once for your whole account, not per model."
        />
        <div className="space-y-4 p-5">
          <Callout tone="neutral" icon={<Settings2 className="h-4 w-4" strokeWidth={1.75} />}>
            No ElevenLabs key on this account yet. Connect it once and every model
            you have can pick a voice.
          </Callout>
          <Link href="/app/account" className="app-btn app-btn-primary h-9 px-4">
            Go to Account settings
          </Link>
        </div>
      </Card>

      <fieldset disabled className="space-y-5 opacity-40">
        <AutoSaveForm save={async () => ({})} sticky={false}>
          <VoiceSettings voice={voice} />
        </AutoSaveForm>
      </fieldset>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Výber hlasu                                                                */
/* -------------------------------------------------------------------------- */

function VoicePicker({
  voices,
  selected,
}: {
  voices: { id: string; name: string; preview: string }[];
  selected: string;
}) {
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(selected);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  // Prehrávač je jeden na celú kartu: kliknutie na druhú ukážku prvú zastaví,
  // inak by sa dva hlasy prekrývali. Pri odchode zo stránky musí stíchnuť.
  useEffect(() => {
    return () => {
      audio.current?.pause();
      audio.current = null;
    };
  }, []);

  if (voices.length === 0) {
    return (
      <p className="px-5 py-6 text-[13px] text-[var(--app-text-3)]">
        No voices to show — see the message above.
      </p>
    );
  }

  const preview = (url: string, id: string) => {
    audio.current?.pause();
    if (playing === id) {
      setPlaying(null);
      return;
    }
    const player = new Audio(url);
    player.onended = () => setPlaying(null);
    player.onerror = () => setPlaying(null);
    audio.current = player;
    setPlaying(id);
    void player.play().catch(() => setPlaying(null));
  };

  const choose = (id: string) => {
    setValue(id);
    set("eleven_voice_id", id);
    flush();
  };

  return (
    <div className="max-h-[420px] divide-y divide-[var(--app-border)] overflow-y-auto">
      {voices.map((item) => {
        const active = item.id === value;
        return (
          <div
            key={item.id}
            className={cn(
              "flex items-center gap-3 px-5 py-3 transition-colors",
              active ? "bg-[#0f0f0f]" : "hover:bg-[#0c0c0c]",
            )}
          >
            <button
              type="button"
              onClick={() => choose(item.id)}
              aria-pressed={active}
              className="flex min-w-0 flex-1 items-center gap-3 text-left"
            >
              <span
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                  active
                    ? "border-[var(--app-text)] bg-[var(--app-text)]"
                    : "border-[var(--app-border-strong)]",
                )}
              >
                {active && <Check className="h-2.5 w-2.5 text-[#0a0a0a]" strokeWidth={3} />}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] text-[var(--app-text)]">
                  {item.name}
                </span>
                <span className="block truncate font-mono text-[11px] text-[var(--app-text-4)]">
                  {item.id}
                </span>
              </span>
            </button>

            {item.preview && (
              <button
                type="button"
                onClick={() => preview(item.preview, item.id)}
                aria-label={playing === item.id ? `Stop ${item.name}` : `Play ${item.name}`}
                className="app-btn app-btn-ghost h-8 w-8 shrink-0 p-0"
              >
                {playing === item.id ? (
                  <Pause className="h-3.5 w-3.5" strokeWidth={1.75} />
                ) : (
                  <Play className="h-3.5 w-3.5" strokeWidth={1.75} />
                )}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Nastavenia hlasoviek                                                       */
/* -------------------------------------------------------------------------- */

/** Presunuté 1:1 z karty Behavior — texty sú Marekove, nemenili sa. */
function VoiceSettings({ voice }: { voice: VoiceRow }) {
  return (
    <>
      <Card>
        <CardHeader
          title="Voice messages"
          description="Voice notes convert better than text — and they are the hardest thing to fake."
        />
        <div className="space-y-5 p-5">
          <SwitchField
            name="voices_enabled"
            label="Send voice messages"
            defaultValue={voice.voices_enabled}
            help="Turn off and she stays text-only."
          />
          <div className="grid gap-5 sm:grid-cols-2">
            <SliderField
              name="voice_chance"
              label="How often she sends one"
              defaultValue={num(voice.voice_chance)}
              format={percent}
              help="Chance that a reply becomes a voice note instead of text."
            />
            <SliderField
              name="voice_tempo"
              label="Speaking tempo"
              defaultValue={num(voice.voice_tempo)}
              min={0.5}
              max={2}
              step={0.01}
              format={(value) => `${value.toFixed(2)}×`}
              help="Above 1 she talks faster. Around 1.10 sounds natural on a phone recording."
            />
            <SelectField
              name="voice_ambience"
              label="Where she is recording"
              defaultValue={voice.voice_ambience}
              options={AMBIENCE}
              help="Default background. If the chat says she is at the gym, the recording follows the chat."
            />
            <SelectField
              name="voice_strength"
              label="Recording quality"
              defaultValue={voice.voice_strength}
              options={[
                { value: "soft", label: "Soft — clean studio" },
                { value: "real", label: "Real — like a phone" },
                { value: "rough", label: "Rough — noisy room" },
              ]}
              help="How much phone-microphone character gets mixed in."
            />
            <SliderField
              name="voice_ambience_level"
              label="Background volume"
              defaultValue={num(voice.voice_ambience_level)}
              format={percent}
              help="Too loud and it sounds staged. A few percent is plenty."
            />
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Moments worth her voice"
          description="Normally a voice note is a dice roll. In these moments she sends one anyway — each one costs credits, so turn off what you do not want to pay for."
        />
        <div className="grid gap-3 p-5 sm:grid-cols-2">
          <SwitchField
            name="voice_when_asked"
            label="He asks for one"
            defaultValue={voice.voice_when_asked}
            help="The strongest one there is — he already wants it."
          />
          <SwitchField
            name="voice_when_doubted"
            label="He doubts she is real"
            defaultValue={voice.voice_when_doubted}
            help="A voice note ends that conversation faster than any sentence."
          />
          <SwitchField
            name="voice_when_he_voices"
            label="He sends voice notes himself"
            defaultValue={voice.voice_when_he_voices}
            help="She answers in kind instead of typing back."
          />
          <SwitchField
            name="voice_when_away"
            label="She is out and busy"
            defaultValue={voice.voice_when_away}
            help="“Cannot really type right now” — the excuse writes itself."
          />
          <SwitchField
            name="voice_on_goodnight"
            label="Saying good night"
            defaultValue={voice.voice_on_goodnight}
            help="The last message of her day."
          />
          <SwitchField
            name="voice_when_hot"
            label="He is pushing and still has not converted"
            defaultValue={voice.voice_when_hot}
            help="The link is out, he keeps going — this is the nudge."
          />
        </div>
      </Card>
    </>
  );
}
