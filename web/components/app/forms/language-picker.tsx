"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";

import { useAutoSaveField } from "@/components/app/forms/auto-save";
import {
  LANGUAGES,
  LEVELS,
  MAX_EXTRA,
  DEFAULT_LEVEL,
  type ExtraLanguage,
  type Level,
} from "@/lib/languages";
import { cn } from "@/lib/utils";

/**
 * Jazyky modelky: jeden hlavný + najviac tri ďalšie s úrovňou.
 *
 * PREČO ÚROVEŇ A NIE LEN ZOZNAM: bez nej model predpokladá dokonalosť a modelka
 * odpovie po španielsky ako rodená Španielka. To je pri dievčati z Los Angeles
 * okamžité prezradenie. Úroveň je jediné, čo z toho spraví človeka, ktorý sa
 * jazyk kedysi učil — vrátane občasnej chyby.
 *
 * Ukladá sa cez `AutoSaveForm` ako dve polia: `lang_primary` (kód) a
 * `lang_extra` (pole). Server ich očistí ešte raz — tento komponent je
 * pohodlie, nie hranica.
 */
export function LanguagePicker({
  primary: initialPrimary,
  extra: initialExtra,
}: {
  primary: string;
  extra: ExtraLanguage[];
}) {
  const { set, flush } = useAutoSaveField();
  const [primary, setPrimary] = useState(initialPrimary);
  const [extra, setExtra] = useState<ExtraLanguage[]>(initialExtra);

  /** Ukladá sa VŽDY oboje naraz. Server potrebuje hlavný jazyk, aby vedel
   *  vyhodiť duplicitu z vedľajších — a keby prišiel len jeden, hádal by. */
  function uloz(novyPrimary: string, noveExtra: ExtraLanguage[]) {
    set("lang_primary", novyPrimary);
    set("lang_extra", noveExtra);
    flush();
  }

  function zmenPrimary(code: string) {
    // Nový hlavný jazyk nesmie ostať aj medzi vedľajšími — databáza to odmietne
    // a klient by videl chybu za niečo, čo spravil úplne rozumne.
    const ocistene = extra.filter((item) => item.code !== code);
    setPrimary(code);
    setExtra(ocistene);
    uloz(code, ocistene);
  }

  function zmenExtra(index: number, patch: Partial<ExtraLanguage>) {
    const next = extra.map((item, i) => (i === index ? { ...item, ...patch } : item));
    setExtra(next);
    uloz(primary, next);
  }

  function pridaj() {
    const volny = LANGUAGES.find(
      (l) => l.code !== primary && !extra.some((e) => e.code === l.code),
    );
    if (!volny) return;
    const next = [...extra, { code: volny.code, level: DEFAULT_LEVEL }];
    setExtra(next);
    uloz(primary, next);
  }

  function odober(index: number) {
    const next = extra.filter((_, i) => i !== index);
    setExtra(next);
    uloz(primary, next);
  }

  const mozeVieduPridat = extra.length < MAX_EXTRA && extra.length + 1 < LANGUAGES.length;

  return (
    <div className="sm:col-span-2">
      <label className="block">
        <span className="text-[12.5px] text-[var(--app-text-2)]">Main language</span>
        <select
          value={primary}
          onChange={(event) => zmenPrimary(event.target.value)}
          className="app-input mt-1.5 w-full"
        >
          {LANGUAGES.map((language) => (
            <option key={language.code} value={language.code}>
              {language.name}
            </option>
          ))}
        </select>
      </label>
      <p className="mt-1.5 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        What she writes in with everyone. She is not a native speaker in it either — she writes
        simply, the way a real person types on a phone.
      </p>

      <div className="mt-5">
        <span className="text-[12.5px] text-[var(--app-text-2)]">Other languages</span>
        <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
          If a fan writes in one of these, she answers in it — at exactly this level, mistakes and
          all. Ask her what she speaks and she will tell you the truth. Up to {MAX_EXTRA}.
        </p>

        {extra.length > 0 && (
          <div className="mt-2.5 space-y-2">
            {extra.map((item, index) => (
              <div key={`${item.code}-${index}`} className="flex items-center gap-2">
                <select
                  value={item.code}
                  onChange={(event) => zmenExtra(index, { code: event.target.value })}
                  className="app-input min-w-0 flex-1"
                  aria-label="Language"
                >
                  {LANGUAGES.filter(
                    (l) =>
                      l.code === item.code ||
                      (l.code !== primary && !extra.some((e) => e.code === l.code)),
                  ).map((language) => (
                    <option key={language.code} value={language.code}>
                      {language.name}
                    </option>
                  ))}
                </select>
                <select
                  value={item.level}
                  onChange={(event) =>
                    zmenExtra(index, { level: event.target.value as Level })
                  }
                  className="app-input min-w-0 flex-[1.4]"
                  aria-label="Level"
                >
                  {LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {level.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => odober(index)}
                  aria-label={`Remove ${item.code}`}
                  className="app-tap shrink-0 rounded-md p-2 text-[var(--app-text-4)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
                >
                  <X className="h-4 w-4" strokeWidth={1.75} />
                </button>
              </div>
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={pridaj}
          disabled={!mozeVieduPridat}
          className={cn("app-btn app-btn-ghost mt-2.5 h-9 px-3.5", !mozeVieduPridat && "hidden")}
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={1.75} />
          Add a language
        </button>

        {extra.length === 0 && (
          <p className="mt-2 text-[11.5px] text-[var(--app-text-4)]">
            None yet — she will say she only speaks {LANGUAGES.find((l) => l.code === primary)?.name}.
          </p>
        )}
      </div>
    </div>
  );
}
