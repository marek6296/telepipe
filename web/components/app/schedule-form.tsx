"use client";

import { useState } from "react";
import { ArrowDown, ArrowUp, Plus, RotateCcw, Trash2 } from "lucide-react";

import {
  resetScheduleAction,
  saveScheduleAction,
} from "@/app/app/m/[id]/persona/day/actions";
import { ScheduleDescribe } from "@/components/app/schedule-describe";
import { DayPreview } from "@/components/app/schedule-preview";
import { AutoSaveForm, useAutoSaveField } from "@/components/app/forms/auto-save";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { hhMmToMinutes, minutesToHhMm } from "@/lib/format";
import {
  ALL_DAYS,
  MAX_ACTIVITIES,
  MAX_DURATION,
  MAX_TEXT,
  MIN_DURATION,
  PACE_OPTIONS,
  PLACES,
  PLACE_LABEL,
  WEEKDAYS,
  blankActivity,
  type Place,
  type ScheduleActivity,
  type ScheduleRow,
} from "@/lib/schedule";
import { cn } from "@/lib/utils";

/**
 * Denný život modelky — z čoho vyplýva, čo o sebe povie, ako rýchlo odpisuje
 * a odkiaľ znie jej hlasovka.
 *
 * PREČO NEPOUŽÍVA `fields.tsx`. Tie polia sú neriadené (`defaultValue` +
 * vlastný stav), čo je pre formulár správne, ale tu by to znamenalo, že ukážka
 * dňa nevie, čo klient práve napísal. Ukážka je pritom to jediné, čo z rozvrhu
 * robí pochopiteľnú vec — takže celý rozvrh drží jeden stav a polia sú riadené.
 * Vzhľad je zámerne ten istý (`app-input`, `app-label`).
 */

type State = {
  wake_weekday_start_min: number;
  wake_weekday_end_min: number;
  wake_weekend_start_min: number;
  wake_weekend_end_min: number;
  night_place: Place;
  night_what: string;
  night_pace: number;
  night_arrival: string;
  activities: ScheduleActivity[];
};

export function ScheduleForm({
  modelId,
  schedule,
}: {
  modelId: string;
  schedule: ScheduleRow;
}) {
  const [state, setState] = useState<State>(() => ({
    wake_weekday_start_min: schedule.wake_weekday_start_min,
    wake_weekday_end_min: schedule.wake_weekday_end_min,
    wake_weekend_start_min: schedule.wake_weekend_start_min,
    wake_weekend_end_min: schedule.wake_weekend_end_min,
    night_place: schedule.night_place,
    night_what: schedule.night_what,
    // ZÁMERNE BEZ `nearestPace`: Simona má nočnú odozvu 0.6 a v ponuke je 0.5
    // a 0.8. Prilepiť ju na najbližšiu by znamenalo, že samotné otvorenie karty
    // jej zmení rytmus — a to je presne to, čo sa stať nesmie. Hodnotu mimo
    // ponuky ukáže `PaceSelect` ako vlastnú položku.
    night_pace: Number(schedule.night_pace) || 1,
    night_arrival: schedule.night_arrival,
    activities: schedule.activities.map((activity) => ({ ...activity })),
  }));

  return (
    <>
      <ScheduleDescribe modelId={modelId} />
      <AutoSaveForm save={(patch) => saveScheduleAction(modelId, patch)}>
        <Editor modelId={modelId} state={state} setState={setState} />
      </AutoSaveForm>
    </>
  );
}

function Editor({
  modelId,
  state,
  setState,
}: {
  modelId: string;
  state: State;
  setState: (next: State) => void;
}) {
  const { set, flush } = useAutoSaveField();

  /** Zmena poľa mimo zoznamu — uloží sa hneď (výber) alebo po debounce (text). */
  function patch<K extends keyof State>(key: K, value: State[K], now = false): void {
    setState({ ...state, [key]: value });
    set(key, value);
    if (now) flush();
  }

  /** Zmena zoznamu činností. Ukladá sa celé pole — poradie JE tá informácia. */
  function patchList(activities: ScheduleActivity[], now = false): void {
    setState({ ...state, activities });
    set("activities", activities);
    if (now) flush();
  }

  function updateAt(index: number, change: Partial<ScheduleActivity>, now = false): void {
    patchList(
      state.activities.map((item, i) => (i === index ? { ...item, ...change } : item)),
      now,
    );
  }

  function move(index: number, delta: number): void {
    const target = index + delta;
    if (target < 0 || target >= state.activities.length) return;
    const next = [...state.activities];
    [next[index], next[target]] = [next[target], next[index]];
    patchList(next, true);
  }

  const full = state.activities.length >= MAX_ACTIVITIES;

  return (
    <>
      <Card>
        <CardHeader
          title="When she gets up"
          description="A window, not an alarm — she wakes somewhere inside it, a different minute every day."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <TimeRange
            label="Monday to Friday"
            from={state.wake_weekday_start_min}
            to={state.wake_weekday_end_min}
            onChange={(from, to) => {
              setState({
                ...state,
                wake_weekday_start_min: from,
                wake_weekday_end_min: to,
              });
              set("wake_weekday_start_min", from);
              set("wake_weekday_end_min", to);
            }}
            onCommit={flush}
          />
          <TimeRange
            label="Saturday and Sunday"
            from={state.wake_weekend_start_min}
            to={state.wake_weekend_end_min}
            onChange={(from, to) => {
              setState({
                ...state,
                wake_weekend_start_min: from,
                wake_weekend_end_min: to,
              });
              set("wake_weekend_start_min", from);
              set("wake_weekend_end_min", to);
            }}
            onCommit={flush}
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Her day"
          description="Everything she does, in order. Each entry lasts somewhere inside its range, so no two days line up the same way."
          actions={
            <button
              type="button"
              disabled={full}
              onClick={() => patchList([...state.activities, blankActivity()], true)}
              className="app-btn app-btn-ghost h-8 px-3 text-[12px]"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={1.75} />
              Add
            </button>
          }
        />
        <div className="divide-y divide-[var(--app-border)]">
          {state.activities.map((activity, index) => (
            <ActivityRow
              key={index}
              index={index}
              activity={activity}
              first={index === 0}
              last={index === state.activities.length - 1}
              onChange={(change, now) => updateAt(index, change, now)}
              onMove={(delta) => move(index, delta)}
              onRemove={
                state.activities.length > 1
                  ? () => patchList(state.activities.filter((_, i) => i !== index), true)
                  : undefined
              }
            />
          ))}
        </div>
        {full && (
          <div className="border-t border-[var(--app-border)] px-5 py-3">
            <Callout>A day holds at most {MAX_ACTIVITIES} entries.</Callout>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader
          title="And then she is in bed"
          description="The last stretch of the day. It has no length — it runs until she falls asleep, and it is when she is easiest to reach."
        />
        <div className="grid gap-5 p-5 sm:grid-cols-2">
          <Field label="Where she is">
            <select
              value={state.night_place}
              onChange={(event) => patch("night_place", event.target.value as Place, true)}
              className="app-input app-select"
            >
              {PLACES.map((place) => (
                <option key={place} value={place}>
                  {PLACE_LABEL[place]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="How fast she replies">
            <PaceSelect
              value={state.night_pace}
              onChange={(value) => patch("night_pace", value, true)}
            />
          </Field>
          <Field label="What she is doing" help="She leans on this when a fan asks what she is up to.">
            <input
              value={state.night_what}
              maxLength={MAX_TEXT}
              onChange={(event) => patch("night_what", event.target.value)}
              onBlur={flush}
              className="app-input"
            />
          </Field>
          <Field
            label="What she says when she gets there"
            help="Leave it empty and she does not mention going to bed at all."
          >
            <input
              value={state.night_arrival}
              maxLength={MAX_TEXT}
              onChange={(event) => patch("night_arrival", event.target.value)}
              onBlur={flush}
              className="app-input"
            />
          </Field>
        </div>
      </Card>

      <DayPreview day={state} seed={modelId} />

      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <p className="text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
          This is what she tells fans she is doing, how fast she answers them, and what her
          voice notes sound like behind her. Changes save themselves and reach her within a
          few minutes — no restart needed.
        </p>
        <ResetButton modelId={modelId} />
      </div>
    </>
  );
}

/* --------------------------------------------------------------------------
   Jedna činnosť
--------------------------------------------------------------------------- */

function ActivityRow({
  index,
  activity,
  first,
  last,
  onChange,
  onMove,
  onRemove,
}: {
  index: number;
  activity: ScheduleActivity;
  first: boolean;
  last: boolean;
  onChange: (change: Partial<ScheduleActivity>, now?: boolean) => void;
  onMove: (delta: number) => void;
  onRemove?: () => void;
}) {
  return (
    <div className="p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <span className="app-group-label">Step {index + 1}</span>
        <div className="flex items-center gap-1">
          <IconButton label="Move up" disabled={first} onClick={() => onMove(-1)}>
            <ArrowUp className="h-3.5 w-3.5" strokeWidth={1.75} />
          </IconButton>
          <IconButton label="Move down" disabled={last} onClick={() => onMove(1)}>
            <ArrowDown className="h-3.5 w-3.5" strokeWidth={1.75} />
          </IconButton>
          <IconButton label="Remove" disabled={!onRemove} onClick={() => onRemove?.()}>
            <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
          </IconButton>
        </div>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Where she is" help="This is what her voice notes sound like behind her.">
          <select
            value={activity.place}
            onChange={(event) => onChange({ place: event.target.value as Place }, true)}
            className="app-input app-select"
          >
            {PLACES.map((place) => (
              <option key={place} value={place}>
                {PLACE_LABEL[place]}
              </option>
            ))}
          </select>
        </Field>

        <Field label="How fast she replies from there">
          <PaceSelect
            value={activity.pace}
            onChange={(value) => onChange({ pace: value }, true)}
          />
        </Field>

        <Field
          label="What she is doing"
          help="One short line. She says it only when a fan asks."
          className="sm:col-span-2"
        >
          <input
            value={activity.what}
            maxLength={MAX_TEXT}
            placeholder="she is at the gym, checking her phone between sets"
            onChange={(event) => onChange({ what: event.target.value })}
            className="app-input"
          />
        </Field>

        <Field
          label="How long it usually lasts"
          help="A range, never a fixed time — a real person leaves the gym at 15:22, not at 15:30."
        >
          <div className="flex items-center gap-2">
            <MinutesInput
              value={activity.min_minutes}
              onChange={(value) => onChange({ min_minutes: value })}
            />
            <span className="text-[12px] text-[var(--app-text-4)]">to</span>
            <MinutesInput
              value={activity.max_minutes}
              onChange={(value) => onChange({ max_minutes: value })}
            />
            <span className="shrink-0 text-[12px] text-[var(--app-text-4)]">min</span>
          </div>
        </Field>

        <Field
          label="What she says when she has just got there"
          help="Leave it empty and the move passes unmentioned."
        >
          <input
            value={activity.arrival}
            maxLength={MAX_TEXT}
            placeholder="just got out of the gym"
            onChange={(event) => onChange({ arrival: event.target.value })}
            className="app-input"
          />
        </Field>

        <Field label="Which days" className="sm:col-span-2">
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAYS.map((day) => {
              const on = activity.days.includes(day.value);
              return (
                <button
                  key={day.value}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    const days = on
                      ? activity.days.filter((value) => value !== day.value)
                      : ALL_DAYS.filter(
                          (value) => value === day.value || activity.days.includes(value),
                        );
                    // Bez jediného dňa by to bola činnosť, ktorá sa nikdy
                    // nestane — a databáza by taký riadok aj tak odmietla.
                    if (days.length === 0) return;
                    onChange({ days }, true);
                  }}
                  className={cn(
                    "app-tap rounded-md border px-2.5 py-1.5 text-[11.5px] transition-colors",
                    on
                      ? "border-[var(--app-text-3)] bg-[#161616] text-[var(--app-text)]"
                      : "border-[var(--app-border)] text-[var(--app-text-4)] hover:text-[var(--app-text-2)]",
                  )}
                >
                  {day.short}
                </button>
              );
            })}
          </div>
        </Field>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------
   Drobnosti
--------------------------------------------------------------------------- */

/**
 * Rýchlosť odpisovania. Klient si vyberá vetu, worker dostane násobič.
 *
 * PREČO SA NEPRILEPÍ NA NAJBLIŽŠIU MOŽNOSŤ. Napísaná šablóna v `den.py` je
 * vyladená na desatiny (0.9 pri chystaní, 1.7 po fitku, 1.9 v aute) a v ponuke
 * také čísla nie sú — je ich šesť, lebo klient si má vyberať zo zrozumiteľných
 * viet, nie ladiť koeficient. Keby sa hodnota mimo ponuky prilepila na
 * najbližšiu, samotné otvorenie karty by Simone prepísalo dvanásť z tridsiatich
 * deviatich činností a jej rytmus by sa zmenil bez toho, aby klient čokoľvek
 * klikol. Preto sa taká hodnota ukáže ako vlastná položka: vidno ju, dá sa
 * z nej odísť na niektorú z ponúkaných, ale sama od seba sa nezmení.
 *
 * `nearestPace` má miesto inde — v `schedule-draft.ts`, kde zužuje odpoveď
 * modelu na to, čo sme mu ponúkli. Tam sa nič vyladené neprepisuje.
 */
function PaceSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  const listed = PACE_OPTIONS.some((option) => option.value === value);
  return (
    <select
      value={String(value)}
      onChange={(event) => onChange(Number(event.target.value))}
      className="app-input app-select"
    >
      {!listed && (
        <option value={String(value)}>{`Fine-tuned — ×${value} reply delay`}</option>
      )}
      {PACE_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function Field({
  label,
  help,
  className,
  children,
}: {
  label: string;
  help?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <p className="app-label mb-2">{label}</p>
      {children}
      {help && (
        <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">{help}</p>
      )}
    </div>
  );
}

function TimeRange({
  label,
  from,
  to,
  onChange,
  onCommit,
}: {
  label: string;
  from: number;
  to: number;
  onChange: (from: number, to: number) => void;
  onCommit: () => void;
}) {
  return (
    <Field label={label} help="Any minute inside this window — a different one every day.">
      <div className="flex items-center gap-2">
        <input
          type="time"
          value={minutesToHhMm(from)}
          onChange={(event) => {
            const minutes = hhMmToMinutes(event.target.value);
            if (minutes !== null) onChange(minutes, to);
          }}
          onBlur={onCommit}
          className="app-input"
        />
        <span className="text-[12px] text-[var(--app-text-4)]">to</span>
        <input
          type="time"
          value={minutesToHhMm(to)}
          onChange={(event) => {
            const minutes = hhMmToMinutes(event.target.value);
            if (minutes !== null) onChange(from, minutes);
          }}
          onBlur={onCommit}
          className="app-input"
        />
      </div>
    </Field>
  );
}

function MinutesInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <input
      type="number"
      inputMode="numeric"
      value={value}
      min={MIN_DURATION}
      max={MAX_DURATION}
      onChange={(event) => {
        const next = Number(event.target.value);
        if (Number.isFinite(next)) {
          onChange(Math.min(MAX_DURATION, Math.max(MIN_DURATION, Math.round(next))));
        }
      }}
      className="app-input"
    />
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="app-tap rounded-md border border-[var(--app-border)] p-1.5 text-[var(--app-text-4)] transition-colors hover:text-[var(--app-text)] disabled:pointer-events-none disabled:opacity-35"
    >
      {children}
    </button>
  );
}

function ResetButton({ modelId }: { modelId: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <span className="flex items-center gap-3">
      {error && <span className="text-[11.5px] text-[#fca5a5]">{error}</span>}
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          if (!window.confirm("Replace her day with the default schedule?")) return;
          setBusy(true);
          const result = await resetScheduleAction(modelId);
          setBusy(false);
          if (result.error) {
            setError(result.error);
            return;
          }
          window.location.reload();
        }}
        className="app-btn app-btn-quiet h-8 shrink-0 px-3 text-[12px]"
      >
        <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
        Restore the default day
      </button>
    </span>
  );
}
