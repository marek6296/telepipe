"use client";

import { useId, useState, type ReactNode } from "react";

import {
  useAutoSaveField,
  useOptionalAutoSaveField,
  type SavePatch,
} from "@/components/app/forms/auto-save";
import { hhMmToMinutes, minutesToHhMm } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Polia formulárov s auto-save. Každé si drží vlastnú hodnotu a pri zmene ju
 * pošle do bufferu (`set`); pri opustení poľa vynúti zápis (`flush`).
 *
 * Dve z nich (`SliderField`, `SelectField`) vedia aj druhú rolu: s `onChange`
 * sa neukladajú vôbec a hodnotu len ohlásia von. Slúži to štúdiu hlasu, kde
 * sa nastavenie najprv skúša sluchom a ukladá až na výslovný pokyn.
 */

/** Bez `onChange` musí pole stáť vo formulári — inak nemá kam zapísať. */
function requireForm(api: {
  set: (name: string, value: SavePatch[string]) => void;
  flush: () => void;
} | null) {
  if (!api) {
    throw new Error("Pole formulára musí byť vnútri <AutoSaveForm> alebo dostať onChange.");
  }
  return api;
}

function Shell({
  label,
  help,
  htmlFor,
  children,
  className,
  action,
}: {
  label: string;
  help?: string;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <div className={className}>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <label
          htmlFor={htmlFor}
          className="app-label"
        >
          {label}
        </label>
        {action}
      </div>
      {children}
      {help && <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">{help}</p>}
    </div>
  );
}

export function TextField({
  name,
  label,
  help,
  defaultValue,
  placeholder,
  type = "text",
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: string;
  placeholder?: string;
  type?: string;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          setValue(event.target.value);
          set(name, event.target.value);
        }}
        onBlur={flush}
        className="app-input"
      />
    </Shell>
  );
}

export function TextAreaField({
  name,
  label,
  help,
  defaultValue,
  placeholder,
  rows = 4,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: string;
  placeholder?: string;
  rows?: number;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <textarea
        id={id}
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          setValue(event.target.value);
          set(name, event.target.value);
        }}
        onBlur={flush}
        className="app-input resize-y leading-relaxed"
      />
    </Shell>
  );
}

export function NumberField({
  name,
  label,
  help,
  defaultValue,
  min,
  max,
  step = 1,
  suffix,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: number | null;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue === null ? "" : String(defaultValue));

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <div className="relative">
        <input
          id={id}
          type="number"
          inputMode="numeric"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(event) => {
            const raw = event.target.value;
            setValue(raw);
            if (raw === "") {
              set(name, null);
              return;
            }
            const parsed = Number(raw);
            if (Number.isFinite(parsed)) set(name, clamp(parsed, min, max));
          }}
          onBlur={flush}
          className={cn("app-input", suffix && "pr-16!")}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-[var(--app-text-4)]">
            {suffix}
          </span>
        )}
      </div>
    </Shell>
  );
}

export function SliderField({
  name,
  label,
  help,
  defaultValue,
  min = 0,
  max = 1,
  step = 0.01,
  format = (value: number) => `${Math.round(value * 100)}%`,
  className,
  onChange,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: number;
  min?: number;
  max?: number;
  step?: number;
  format?: (value: number) => string;
  className?: string;
  /**
   * Keď je zadané, pole sa NEUKLADÁ — hodnotu len ohlási von. Tak ho používa
   * štúdio hlasu, kde sa najprv počúva a ukladá až potom. Bez toho by každé
   * posunutie posuvníka prepísalo nastavenie, ktoré ide fanúšikom.
   */
  onChange?: (value: number) => void;
}) {
  const id = useId();
  const auto = useOptionalAutoSaveField();
  const [value, setValue] = useState(defaultValue);
  const emit = (next: number) =>
    onChange ? onChange(next) : requireForm(auto).set(name, next);
  const flush = () => {
    if (!onChange) requireForm(auto).flush();
  };

  return (
    <Shell
      label={label}
      help={help}
      htmlFor={id}
      className={className}
      action={
        <span className="tabular-nums text-[12.5px] font-medium text-[var(--app-text)]">
          {format(value)}
        </span>
      }
    >
      <input
        id={id}
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          const next = Number(event.target.value);
          setValue(next);
          emit(next);
        }}
        onPointerUp={flush}
        onBlur={flush}
        className="h-1 w-full cursor-pointer appearance-none rounded-full bg-[#26262a] accent-white"
        style={{ accentColor: "#fafafa" }}
      />
    </Shell>
  );
}

/**
 * JEDINÝ vypínač v celej appke. Nikde inde sa `role="switch"` nepíše ručne.
 *
 * PREČO TAKTO
 * -----------
 * Predtým boli vypínače dva — tento a vlastný vo fanvue karte pripojenia — a ani
 * jeden nebolo poznať. Ten druhý mal v zapnutom stave bielu dráhu AJ biely
 * gombík, čiže gombík úplne zmizol a ostala len biela pilulka; tento mal gombík
 * čierny, ale na 20 px sa aj tak čítal ako biela machuľa. Marek doslova nevedel,
 * čo je zapnuté.
 *
 * Stav preto nesú TRI nezávislé signály naraz, nie jeden:
 *   1. výplň dráhy — vypnuté je duté (tmavé + obrys), zapnuté je plné biele;
 *   2. poloha gombíka — vľavo / vpravo;
 *   3. slovo „On" / „Off" vedľa — jediné, čo netreba lúštiť z grafiky.
 *
 * Gombík má v oboch stavoch kontrast proti SVOJEJ dráhe (svetlosivý na tmavej,
 * takmer čierny na bielej) — to je presne to, čo fanvue verzia porušila.
 *
 * Farby ostávajú monochromatické podľa redesignu: signálna zelená/červená sú
 * vyhradené pre delty a stavové bodky, vypínač ich nepoužíva.
 */
export function Switch({
  checked,
  onCheckedChange,
  label,
  describedBy,
  disabled = false,
  id,
  className,
}: {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  /** Prístupný názov. Povinný — samotný vypínač o sebe nepovie nič. */
  label: string;
  /** `id` textu s vysvetlením, aby ho čítačka prečítala spolu s názvom. */
  describedBy?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
}) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        // Klikacia plocha je celá — dráha aj slovo. Na dotyku ju `app-tap`
        // dotiahne na bezpečných 44 px bez toho, aby narástla samotná dráha
        // (tá je vnútri, takže `min-height` na nej nesadá).
        "app-tap group inline-flex shrink-0 items-center gap-2.5 rounded-md",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/65",
        disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer",
        className,
      )}
    >
      {/* Dráha: vypnuté = duté s obrysom, zapnuté = plné biele.
          Farba obrysu MUSÍ byť `!` — `globals.css` má nezaradené (unlayered)
          pravidlo `* { border-color: var(--hairline) }`, a nezaradené CSS bije
          Tailwind utility v `@layer utilities`. Bez výkričníka by dráha dostala
          rgba(255,255,255,0.08) a vo vypnutom stave by na čiernom zmizla. */}
      <span
        aria-hidden
        className={cn(
          "relative block h-6 w-11 rounded-full border",
          "transition-[background-color,border-color] duration-150 ease-out motion-reduce:transition-none",
          // #6b6b75 nie je náhodné — je to najtmavšia šedá, ktorá proti #0a0a0a
          // ešte prejde 3:1 (WCAG pre netextové prvky). Tmavšie a obrys zmizne.
          checked ? "border-[#fafafa]! bg-[#fafafa]" : "border-[#6b6b75]! bg-[#141414]",
          !disabled &&
            (checked
              ? "group-hover:border-white! group-hover:bg-white"
              : "group-hover:border-[#9a9aa4]! group-hover:bg-[#1c1c1c]"),
        )}
      >
        {/* `left-0` nie je kozmetika. Bez neho sa absolútny gombík umiestni na
            svoju statickú pozíciu, a tú `<button>` centruje (UA dáva buttonu
            `text-align: center`) — gombík potom štartoval v strede dráhy a
            v zapnutom stave trčal 17 px von. Presne to bola tá „biela machuľa".
            Posun je v px: 42 px vnútra − 16 px gombík − 3 px medzera = 23 px. */}
        <span
          className={cn(
            "absolute top-[3px] left-0 h-4 w-4 rounded-full",
            "transition-[translate,background-color] duration-150 ease-out motion-reduce:transition-none",
            checked ? "translate-x-[23px] bg-[#0a0a0a]" : "translate-x-[3px] bg-[#8a8a94]",
          )}
        />
      </span>

      {/* Stav slovom. `aria-hidden`, lebo čítačke ho už povedalo `aria-checked`
          — inak by zaznelo dvakrát. Pevná šírka, aby „On"/„Off" neposúvalo
          okolie. */}
      <span
        aria-hidden
        className={cn(
          "w-[21px] text-left text-[11.5px] font-medium select-none",
          "transition-colors duration-150 ease-out motion-reduce:transition-none",
          checked ? "text-[var(--app-text)]" : "text-[var(--app-text-4)]",
        )}
      >
        {checked ? "On" : "Off"}
      </span>
    </button>
  );
}

export function SwitchField({
  name,
  label,
  help,
  defaultValue,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: boolean;
  className?: string;
}) {
  const helpId = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3",
        className,
      )}
    >
      <div className="min-w-0">
        <p className="text-[13px] text-[var(--app-text)]">{label}</p>
        {help && (
          <p id={helpId} className="mt-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
            {help}
          </p>
        )}
      </div>
      <Switch
        checked={value}
        label={label}
        describedBy={help ? helpId : undefined}
        className="mt-0.5"
        onCheckedChange={(next) => {
          setValue(next);
          set(name, next);
          flush();
        }}
      />
    </div>
  );
}

export function SelectField({
  name,
  label,
  help,
  defaultValue,
  options,
  className,
  onChange,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: string;
  options: { value: string; label: string }[];
  className?: string;
  /** Viď `SliderField` — s `onChange` sa pole neukladá, len hlási hodnotu. */
  onChange?: (value: string) => void;
}) {
  const id = useId();
  const auto = useOptionalAutoSaveField();
  const [value, setValue] = useState(defaultValue);

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <select
        id={id}
        value={value}
        onChange={(event) => {
          const next = event.target.value;
          setValue(next);
          if (onChange) {
            onChange(next);
            return;
          }
          const form = requireForm(auto);
          form.set(name, next);
          form.flush();
        }}
        className="app-input app-select"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Shell>
  );
}

/** Čas ako `hh:mm`, do DB ide počet minút od polnoci. */
export function TimeField({
  name,
  label,
  help,
  defaultValue,
  className,
}: {
  name: string;
  label: string;
  help?: string;
  defaultValue: number;
  className?: string;
}) {
  const id = useId();
  const { set, flush } = useAutoSaveField();
  const [value, setValue] = useState(minutesToHhMm(defaultValue));

  return (
    <Shell label={label} help={help} htmlFor={id} className={className}>
      <input
        id={id}
        type="time"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          const minutes = hhMmToMinutes(event.target.value);
          if (minutes !== null) set(name, minutes);
        }}
        onBlur={flush}
        className="app-input"
      />
    </Shell>
  );
}

/** Dvojica min/max v jednom riadku — v chovaní je takých párov veľa. */
export function RangeRow({
  label,
  help,
  minField,
  maxField,
  suffix,
  step = 1,
}: {
  label: string;
  help?: string;
  minField: { name: string; value: number };
  maxField: { name: string; value: number };
  suffix?: string;
  step?: number;
}) {
  return (
    <div>
      <p className="app-label mb-2">{label}</p>
      <div className="grid grid-cols-2 gap-3">
        <NumberField
          name={minField.name}
          label="from"
          defaultValue={minField.value}
          min={0}
          step={step}
          suffix={suffix}
        />
        <NumberField
          name={maxField.name}
          label="to"
          defaultValue={maxField.value}
          min={0}
          step={step}
          suffix={suffix}
        />
      </div>
      {help && <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">{help}</p>}
    </div>
  );
}

/** Zamknutá sekcia — fáza 3 (ElevenLabs). */
export function LockedSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-[#0c0c0c] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-[14px] font-medium text-[var(--app-text-2)]">{title}</h3>
          <p className="mt-1.5 max-w-lg text-[12.5px] leading-relaxed text-[var(--app-text-4)]">
            {description}
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-[var(--app-border-strong)] px-2.5 py-1 text-[10.5px] font-medium text-[var(--app-text-3)]">
          Coming soon
        </span>
      </div>
      {children && <div className="pointer-events-none mt-4 opacity-35">{children}</div>}
    </div>
  );
}

function clamp(value: number, min?: number, max?: number): number {
  if (typeof min === "number" && value < min) return min;
  if (typeof max === "number" && value > max) return max;
  return value;
}

/* -------------------------------------------------------------------------- */
/*  Rozsah — dve hranice jednej veličiny                                       */
/* -------------------------------------------------------------------------- */

/**
 * Dolná a horná hranica ako jedno pole.
 *
 * PREČO ROZSAH A NIE HODNOTA. Hlasovky sa nesmú opakovať — každá si z rozsahu
 * vylosuje vlastné číslo a práve to ich odlišuje od výstupu zo stroja. Keby to
 * bola jedna hodnota, séria by znela zakaždým rovnako.
 *
 * Hranice sa navzájom tlačia: keď dolnú posunieš nad hornú, horná ustúpi. Bez
 * toho by sa dal nastaviť prevrátený rozsah a losovalo by sa z niečoho iného,
 * než čo je na obrazovke. Rovnaké dolné aj horné číslo je legitímne — vtedy je
 * hodnota pevná a náhoda vypnutá, ale je to rozhodnutie klienta.
 */
export function RangeField({
  nameMin,
  nameMax,
  label,
  help,
  defaultMin,
  defaultMax,
  min = 0,
  max = 1,
  step = 0.01,
  format = (value: number) => `${Math.round(value * 100)}%`,
  className,
}: {
  nameMin: string;
  nameMax: string;
  label: string;
  help?: string;
  defaultMin: number;
  defaultMax: number;
  min?: number;
  max?: number;
  step?: number;
  format?: (value: number) => string;
  className?: string;
}) {
  const auto = useOptionalAutoSaveField();
  const [lo, setLo] = useState(defaultMin);
  const [hi, setHi] = useState(defaultMax);

  const flush = () => requireForm(auto).flush();
  const posun = (kto: "lo" | "hi", raw: number) => {
    const form = requireForm(auto);
    if (kto === "lo") {
      setLo(raw);
      form.set(nameMin, raw);
      if (raw > hi) {
        setHi(raw);
        form.set(nameMax, raw);
      }
      return;
    }
    setHi(raw);
    form.set(nameMax, raw);
    if (raw < lo) {
      setLo(raw);
      form.set(nameMin, raw);
    }
  };

  return (
    <Shell
      label={label}
      help={help}
      className={className}
      action={
        <span className="tabular-nums text-[12.5px] font-medium text-[var(--app-text)]">
          {format(lo)} – {format(hi)}
        </span>
      }
    >
      <div className="space-y-2.5">
        {(
          [
            ["lo", lo, "Quietest"],
            ["hi", hi, "Loudest"],
          ] as const
        ).map(([kto, hodnota]) => (
          <input
            key={kto}
            type="range"
            aria-label={`${label} — ${kto === "lo" ? "lower" : "upper"} bound`}
            value={hodnota}
            min={min}
            max={max}
            step={step}
            onChange={(event) => posun(kto, Number(event.target.value))}
            onPointerUp={flush}
            onBlur={flush}
            className="h-1 w-full cursor-pointer appearance-none rounded-full bg-[#26262a] accent-white"
            style={{ accentColor: "#fafafa" }}
          />
        ))}
      </div>
    </Shell>
  );
}
