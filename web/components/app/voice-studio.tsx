"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { AlertTriangle, Loader2, RotateCcw, Sparkles, Wand2 } from "lucide-react";

import { saveBehaviorAction } from "@/app/app/m/[id]/persona/behavior/actions";
import {
  recentPreviewsAction,
  startVoicePreviewAction,
  voicePreviewStatusAction,
  type PreviewClip,
} from "@/app/app/m/[id]/voice/actions";
import { SelectField, SliderField } from "@/components/app/forms/fields";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { relativeTime } from "@/lib/format";
import {
  PREVIEW_TEXT_MAX,
  SAMPLE_LINES,
  TEMPO_MAX,
  TEMPO_MIN,
  VOICE_AMBIENCES,
  VOICE_STRENGTHS,
  ambienceLabel,
  strengthLabel,
  voiceJobError,
  type VoiceSound,
} from "@/lib/voice";
import { cn } from "@/lib/utils";

/**
 * Štúdio hlasu — vypočuť si presne to, čo dostane fanúšik.
 *
 * Miešanie (pozadie, telefónny mikrofón, kolísanie hlasitosti, opus) beží na
 * ffmpegu vo workeri, nie v prehliadači. Preto sa tu nič nevyrába: vloží sa
 * riadok do `voice_jobs`, worker si ho do štyroch sekúnd vezme a dopíše
 * adresu hotového súboru. Chodí to TÝM ISTÝM reťazcom ako ostrá hlasovka
 * (`userbot._voice_jobs_once` → `livevoice.speak`), takže to, čo tu klient
 * počuje, nie je aproximácia — je to ten istý výstup.
 *
 * Ukážka sa NIKOMU neposiela. Worker ju len uloží do archívu s
 * `kind="preview"` a bez `tg_id`; do žiadneho chatu sa nedostane.
 *
 * Posuvníky sú zámerne oddelené od auto-save karty vyššie. Ladiť zvuk
 * znamená skúšať aj to, čo sa nakoniec nepoužije — a keby sa každý posun
 * hneď ukladal, menil by nastavenie, ktoré práve teraz ide fanúšikom.
 * Preto: skúšaj koľko chceš, „Save" až keď to sedí.
 */

/* Prvý pohľad má čas: hlas z ElevenLabs, pozadie z ElevenLabs, potom ffmpeg. */
const FIRST_POLL_MS = 2_500;
const POLL_MS = 2_000;
/** Dokedy sa čaká, kým to vyhlásime za nedoručené. Worker má vlastné stropy
 *  (90 s reč, 120 s mix), takže kratší strop by klamal skôr, než sa to vzdá. */
const GIVE_UP_MS = 240_000;

type Stage = "idle" | "queued" | "working" | "ready" | "failed";

export type StudioSaved = VoiceSound & { hasVoice: boolean };

export function VoiceStudio({
  modelId,
  saved,
  clips: initialClips,
}: {
  modelId: string;
  saved: StudioSaved;
  clips: PreviewClip[];
}) {
  const [text, setText] = useState<string>(SAMPLE_LINES[0]);
  const [base, setBase] = useState<VoiceSound>(sound(saved));
  const [live, setLive] = useState<VoiceSound>(sound(saved));
  const [stage, setStage] = useState<Stage>("idle");
  const [url, setUrl] = useState("");
  const [problem, setProblem] = useState("");
  const [clips, setClips] = useState(initialClips);
  const [saving, startSave] = useTransition();
  const [savedNote, setSavedNote] = useState(false);

  // Posuvníky sa remountujú kľúčom, lebo `SliderField` si drží vlastný stav
  // z `defaultValue` — bez toho by „Reset" prepísal hodnotu, ale ručička by
  // ostala tam, kam ju klient odtiahol.
  const [controlsKey, setControlsKey] = useState(0);

  const timer = useRef<number | null>(null);
  const started = useRef(0);

  const stop = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);

  // Rozrobené čakanie sa nesmie preniesť na inú stránku.
  useEffect(() => stop, [stop]);

  const dirty = !sameSound(base, live);

  const refreshClips = useCallback(async () => {
    try {
      setClips(await recentPreviewsAction(modelId));
    } catch {
      // Zoznam je bonus — keď sa nenačíta, ukážka sa aj tak dá prehrať vyššie.
    }
  }, [modelId]);

  // Opakovanie cez ref, aby sa `poll` nemusela odkazovať sama na seba pred
  // vlastnou deklaráciou — rovnaký zápis ako `flushRef` v `auto-save.tsx`.
  const pollRef = useRef<(jobId: number, attempt: number) => void>(() => {});

  const poll = useCallback(
    (jobId: number, attempt: number) => {
      timer.current = window.setTimeout(
        async () => {
          let state;
          try {
            state = await voicePreviewStatusAction(modelId, jobId);
          } catch {
            // Jeden výpadok siete ešte nič neznamená — skúsi sa znova, kým
            // beží strop. Vzdať to na prvom zakašľaní by bolo horšie.
            state = { status: "working" as const, url: "", error: "" };
          }

          if (state.status === "done" && state.url) {
            setUrl(state.url);
            setStage("ready");
            void refreshClips();
            return;
          }
          if (state.status === "error") {
            setProblem(voiceJobError(state.error) || "The preview failed.");
            setStage("failed");
            return;
          }
          if (state.status === "working") setStage("working");
          if (Date.now() - started.current > GIVE_UP_MS) {
            setProblem(
              "Her agent never picked this up. Check that she is running on the Telegram tab, then try again.",
            );
            setStage("failed");
            return;
          }
          pollRef.current(jobId, attempt + 1);
        },
        attempt === 0 ? FIRST_POLL_MS : POLL_MS,
      );
    },
    [modelId, refreshClips],
  );

  useEffect(() => {
    pollRef.current = poll;
  });

  const generate = () => {
    stop();
    setUrl("");
    setProblem("");
    setStage("queued");
    started.current = Date.now();
    void (async () => {
      const out = await startVoicePreviewAction(modelId, { text, ...live });
      if (out.error || !out.jobId) {
        setProblem(out.error ?? "Could not queue the preview.");
        setStage("failed");
        return;
      }
      poll(out.jobId, 0);
    })();
  };

  const save = () => {
    startSave(async () => {
      const out = await saveBehaviorAction(modelId, {
        voice_ambience: live.ambience,
        voice_strength: live.strength,
        voice_tempo: live.tempo,
        voice_ambience_level: live.ambience_level,
      });
      if (out?.error) {
        setProblem(out.error);
        return;
      }
      setBase(live);
      setSavedNote(true);
      window.setTimeout(() => setSavedNote(false), 2400);
    });
  };

  const reset = () => {
    setLive(base);
    setControlsKey((n) => n + 1);
  };

  const busy = stage === "queued" || stage === "working";

  return (
    <Card>
      <CardHeader
        title="Studio"
        description="Hear exactly what lands in his chat — her voice, the room behind her, the phone microphone, all of it. Nothing here is ever delivered to anyone."
        icon={<Wand2 className="h-4 w-4" strokeWidth={1.75} />}
      />

      <div className="space-y-5 p-5">
        {!saved.hasVoice && (
          <Callout tone="danger" icon={<AlertTriangle className="h-4 w-4" strokeWidth={1.75} />}>
            Pick her voice above first — there is nothing to speak with yet.
          </Callout>
        )}

        <div>
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <label htmlFor="studio-text" className="app-label">
              What she says
            </label>
            <span
              className={cn(
                "tabular-nums text-[11.5px]",
                text.length > PREVIEW_TEXT_MAX
                  ? "text-[#fca5a5]"
                  : "text-[var(--app-text-4)]",
              )}
            >
              {text.length}/{PREVIEW_TEXT_MAX}
            </span>
          </div>
          <textarea
            id="studio-text"
            rows={3}
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="app-input resize-y"
            placeholder="hey you, i was just thinking about you"
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {SAMPLE_LINES.map((line, index) => (
              <button
                key={line}
                type="button"
                onClick={() => setText(line)}
                className="app-btn app-btn-ghost h-7 px-2.5 text-[11.5px]"
              >
                <Sparkles className="h-3 w-3" strokeWidth={1.75} />
                Line {index + 1}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            She rewrites this into spoken form before recording — fillers, a
            stumble, the way people actually talk. That rewrite is the only part
            of a preview that costs Pipe Coins.
          </p>
        </div>

        <div key={controlsKey} className="grid gap-5 sm:grid-cols-2">
          <SelectField
            name="voice_ambience"
            label="Where she is recording"
            defaultValue={live.ambience}
            options={[...VOICE_AMBIENCES]}
            onChange={(value) => setLive((s) => ({ ...s, ambience: value }))}
            help="Each room gets its own background sound and its own filter under her voice."
          />
          <SelectField
            name="voice_strength"
            label="Recording quality"
            defaultValue={live.strength}
            options={[...VOICE_STRENGTHS]}
            onChange={(value) => setLive((s) => ({ ...s, strength: value }))}
            help="How much phone-microphone character gets mixed in."
          />
          <SliderField
            name="voice_tempo"
            label="Speaking tempo"
            defaultValue={live.tempo}
            min={TEMPO_MIN}
            max={TEMPO_MAX}
            step={0.01}
            format={(value) => `${value.toFixed(2)}×`}
            onChange={(value) => setLive((s) => ({ ...s, tempo: value }))}
            help="Above 1 she talks faster. Around 1.10 sounds natural on a phone recording."
          />
          <SliderField
            name="voice_ambience_level"
            label="Background volume"
            defaultValue={live.ambience_level}
            onChange={(value) => setLive((s) => ({ ...s, ambience_level: value }))}
            help="This is a ceiling, not a fixed level — every recording sits a little under it."
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={generate}
            disabled={
              busy || !text.trim() || text.length > PREVIEW_TEXT_MAX || !saved.hasVoice
            }
            className="app-btn app-btn-primary h-9 px-4"
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            ) : (
              <Wand2 className="h-3.5 w-3.5" strokeWidth={1.75} />
            )}
            {busy ? "Making it…" : "Generate preview"}
          </button>

          {dirty && (
            <>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="app-btn app-btn-ghost h-9 px-3"
              >
                {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />}
                Save these settings
              </button>
              <button
                type="button"
                onClick={reset}
                className="app-btn app-btn-ghost h-9 px-3"
              >
                <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
                Back to saved
              </button>
            </>
          )}

          <span className="text-[11.5px] text-[var(--app-text-4)]">
            {savedNote
              ? "Saved — from her next voice note on."
              : dirty
                ? "Trying values that are not saved yet."
                : "Using her saved settings."}
          </span>
        </div>

        <Stage stage={stage} problem={problem} url={url} />
      </div>

      <RecentPreviews clips={clips} />
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Stav výroby                                                                */
/* -------------------------------------------------------------------------- */

function Stage({ stage, problem, url }: { stage: Stage; problem: string; url: string }) {
  if (stage === "idle") return null;

  if (stage === "failed") {
    return (
      <Callout tone="danger" icon={<AlertTriangle className="h-4 w-4" strokeWidth={1.75} />}>
        {problem || "The preview failed."}
      </Callout>
    );
  }

  if (stage === "ready" && url) {
    return (
      <div className="rounded-lg border border-[var(--app-border-strong)] bg-[#0c0c0c] p-4">
        <p className="mb-3 text-[11.5px] uppercase tracking-[0.08em] text-[var(--app-text-4)]">
          Exactly as he would hear it
        </p>
        <audio controls src={url} preload="metadata" className="w-full" />
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block text-[11.5px] text-[var(--app-text-3)] underline underline-offset-2 hover:text-[var(--app-text)]"
        >
          Open the file
        </a>
      </div>
    );
  }

  return (
    <Callout tone="neutral" icon={<Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />}>
      {stage === "queued"
        ? "Queued — her agent picks this up within a few seconds."
        : "Recording her voice, generating the room, mixing it down. Usually under a minute."}
    </Callout>
  );
}

/* -------------------------------------------------------------------------- */
/*  Posledné ukážky                                                            */
/* -------------------------------------------------------------------------- */

/**
 * Bez zoznamu sa dve nastavenia porovnať nedajú — druhá ukážka prepíše prvú
 * a klient si má pamätať, ako znela. Preto tu stojí aj to, čím bola vyrobená:
 * `voice_clips` si miestnosť, kvalitu aj tempo pamätá pri každom riadku.
 */
function RecentPreviews({ clips }: { clips: PreviewClip[] }) {
  if (clips.length === 0) return null;

  return (
    <div className="border-t border-[var(--app-border)]">
      <div className="px-5 py-3">
        <p className="text-[11.5px] uppercase tracking-[0.08em] text-[var(--app-text-4)]">
          Recent previews
        </p>
      </div>
      <div className="divide-y divide-[var(--app-border)]">
        {clips.map((clip) => (
          <div key={clip.id} className="space-y-2 px-5 py-4">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-[var(--app-text-4)]">
              <span className="text-[var(--app-text-3)]">{ambienceLabel(clip.ambience)}</span>
              <span aria-hidden>·</span>
              <span>{strengthLabel(clip.strength)}</span>
              <span aria-hidden>·</span>
              <span className="tabular-nums">{Number(clip.tempo).toFixed(2)}×</span>
              {clip.bytes ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="tabular-nums">{Math.round(clip.bytes / 1024)} kB</span>
                </>
              ) : null}
              <span aria-hidden>·</span>
              <span>{relativeTime(clip.created_at)}</span>
            </div>
            {clip.text && (
              <p className="text-[12.5px] leading-relaxed text-[var(--app-text-2)]">
                {clip.text}
              </p>
            )}
            <audio controls src={clip.url} preload="none" className="w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function sound(saved: VoiceSound): VoiceSound {
  return {
    ambience: saved.ambience,
    strength: saved.strength,
    tempo: saved.tempo,
    ambience_level: saved.ambience_level,
  };
}

function sameSound(a: VoiceSound, b: VoiceSound): boolean {
  return (
    a.ambience === b.ambience &&
    a.strength === b.strength &&
    a.tempo === b.tempo &&
    a.ambience_level === b.ambience_level
  );
}
