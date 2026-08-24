"use client";

import { useSyncExternalStore } from "react";

import { PLACE_LABEL, type Place } from "@/lib/schedule";
import type { DayPlan } from "@/lib/models";

/**
 * Jej deň na jednom pohľade: koľko je u nej hodín, kde v dni sa nachádza a čo
 * práve robí.
 *
 * PREČO. Klient sedí v inom pásme než modelka a mlčanie si nemá ako vysvetliť.
 * Naostro sa to už stalo: majiteľ posunul začiatok okna na skoršie, modelka
 * neodpisovala a nedalo sa rozoznať, či je chyba v nastavení, alebo že u nej
 * ešte nie je ráno. Krivka odpovedá na obe otázky naraz — vidno na nej celý
 * deň, teda aj to, čo príde o hodinu.
 *
 * ČO KRIVKA UKAZUJE. Nie „náladu" a nie výmysel: výšku počítame z tempa
 * odpovedí toho bloku (`odozva`), teda ako rýchlo je z daného miesta k
 * zastihnutiu. Doma na gauči je hore, na fotení pri zemi, v spánku na nule.
 *
 * ODKIAĽ SÚ DÁTA. Deň si losuje worker (`worker/src/den.py`) a raz denne si ho
 * zapíše do `model_schedule.today_plan`. Tu ho len čítame. Prehliadač by ten
 * istý deň nevylosoval — je to Python `random` so seedom — a odhad namiesto
 * pravdy je na tomto mieste horší než nič.
 *
 * Čas je vonkajší zdroj, ktorý sa mení sám, preto `useSyncExternalStore` a nie
 * `useState` v efekte. Na serveri je snapshot `null`, takže sa nevykreslí nič
 * a nemá ako vzniknúť nesúlad medzi serverom a prehliadačom.
 */

const TIK_MS = 30_000;
const DEN = 1440;

function subscribe(callback: () => void): () => void {
  const id = window.setInterval(callback, TIK_MS);
  return () => window.clearInterval(id);
}

/** Minúta epochy — prekresľuje sa raz za minútu, nie pri každom tiku. */
function snapshot(): number {
  return Math.floor(Date.now() / 60_000);
}

export function HerDay({ plan, className = "" }: { plan: DayPlan; className?: string }) {
  const minuta = useSyncExternalStore(subscribe, snapshot, () => null);
  if (minuta === null) return null;

  const teraz = jejCas(minuta, plan.tz);
  // Neznáme pásmo je vec nastavenia, nie dôvod, aby spadla celá karta.
  if (!teraz) return null;

  const bloky = plan.blocks;
  const cerstvy = plan.date === teraz.datum;
  const aktivny = cerstvy ? najdiBlok(bloky, teraz.minuta) : null;
  const hore = jeVOkne(teraz.minuta, plan.startMin, plan.endMin);

  return (
    <div
      className={`rounded-lg border border-[var(--app-border)] bg-[#0b0b0b] px-3.5 py-3 ${className}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="text-[17px] font-semibold tabular-nums tracking-[-0.02em] text-[var(--app-text)]">
            {teraz.hodiny}
          </span>
          <span className="truncate text-[11.5px] text-[var(--app-text-4)]">
            her time · {mestoZPasma(plan.tz)}
          </span>
        </div>
        <div className="flex min-w-0 items-center gap-1.5">
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              hore ? "bg-[var(--app-up)]" : "bg-[var(--app-text-4)]"
            }`}
          />
          <span
            className={`truncate text-[12px] ${
              hore ? "text-[var(--app-up)]" : "text-[var(--app-text-3)]"
            }`}
          >
            {hore ? "awake — replying" : `asleep until ${format12(plan.startMin)}`}
          </span>
        </div>
      </div>

      {bloky.length > 0 ? (
        <>
          <Krivka bloky={bloky} teraz={cerstvy ? teraz.minuta : null} />
          <p className="mt-2 text-[12.5px] leading-[1.45] text-[var(--app-text-2)]">
            {aktivny ? (
              <>
                <span className="text-[var(--app-text-4)]">Right now: </span>
                {aktivny.co || PLACE_LABEL[(aktivny.kde as Place) ?? "home"]}
                <span className="text-[var(--app-text-4)]">
                  {" · "}
                  {tempo(aktivny.odozva)} until {format12(aktivny.do)}
                </span>
              </>
            ) : (
              <span className="text-[var(--app-text-3)]">{tichoText(bloky, cerstvy, teraz.minuta)}</span>
            )}
          </p>
        </>
      ) : (
        <p className="mt-2 text-[12.5px] leading-[1.45] text-[var(--app-text-3)]">
          Her day shows up here once she has been running for a day. What she is doing at what
          time comes from <span className="text-[var(--app-text-2)]">Persona → Daily life</span>.
        </p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------
   Krivka
-------------------------------------------------------------------------- */

const V_SIRKA = 1000;
const V_VYSKA = 120;
const SPODOK = V_VYSKA - 14; // miesto na popisky hodín
const KROK = 10; // minúty medzi bodmi krivky

function Krivka({ bloky, teraz }: { bloky: { od: number; do: number; odozva: number }[]; teraz: number | null }) {
  // Deň kreslíme od prvej činnosti po poslednú, nie od polnoci: prázdna
  // dopoludňajšia polovica grafu nehovorí nič a stlačí to, na čom záleží.
  const zaciatok = Math.floor((bloky[0].od - 45) / 60) * 60;
  const koniec = Math.ceil((bloky[bloky.length - 1].do + 45) / 60) * 60;
  const rozsah = Math.max(60, koniec - zaciatok);
  const x = (minuta: number) => ((minuta - zaciatok) / rozsah) * V_SIRKA;

  const body: [number, number][] = [];
  for (let m = zaciatok; m <= koniec; m += KROK) {
    const blok = najdiBlok(bloky, m);
    body.push([x(m), SPODOK - vyska(blok?.odozva ?? null) * (SPODOK - 8)]);
  }

  const ciara = hladkaCiara(body);
  const plocha = `${ciara} L ${V_SIRKA} ${SPODOK} L 0 ${SPODOK} Z`;

  // Po polnoci je jej minúta zas malá — plán ide ďalej (02:30 = 1590), tak
  // hľadáme aj o deň posunutú, inak by značka „teraz" skočila na začiatok.
  const teraz2 =
    teraz === null
      ? null
      : teraz >= zaciatok && teraz <= koniec
        ? teraz
        : teraz + DEN >= zaciatok && teraz + DEN <= koniec
          ? teraz + DEN
          : null;

  const hodiny: number[] = [];
  for (let h = Math.ceil(zaciatok / 180) * 180; h <= koniec; h += 180) hodiny.push(h);

  return (
    <svg
      viewBox={`0 0 ${V_SIRKA} ${V_VYSKA}`}
      preserveAspectRatio="none"
      className="mt-2.5 h-[68px] w-full"
      role="img"
      aria-label="Her day — how reachable she is hour by hour"
    >
      <defs>
        <linearGradient id="herday-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--app-accent)" stopOpacity="0.30" />
          <stop offset="100%" stopColor="var(--app-accent)" stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {hodiny.map((h) => (
        <g key={h}>
          <line
            x1={x(h)}
            y1={4}
            x2={x(h)}
            y2={SPODOK}
            stroke="var(--app-border)"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          {/* Popisky sú v jej čase a s am/pm — kvôli tomu celá krivka vznikla. */}
          <text
            x={x(h)}
            y={V_VYSKA - 2}
            textAnchor="middle"
            fontSize="11"
            fill="var(--app-text-4)"
          >
            {format12(h)}
          </text>
        </g>
      ))}

      <path d={plocha} fill="url(#herday-fill)" />
      <path
        d={ciara}
        fill="none"
        stroke="var(--app-accent)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />

      {teraz2 !== null && (
        <>
          <line
            x1={x(teraz2)}
            y1={2}
            x2={x(teraz2)}
            y2={SPODOK}
            stroke="var(--app-text)"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
          {/* `preserveAspectRatio="none"` ťahá viewBox do šírky, takže kruh by
              bol elipsa. Krátka zvislá čiarka drží tvar pri každej šírke. */}
          <line
            x1={x(teraz2)}
            y1={SPODOK - vyska(najdiBlok(bloky, teraz2)?.odozva ?? null) * (SPODOK - 8) - 4}
            x2={x(teraz2)}
            y2={SPODOK - vyska(najdiBlok(bloky, teraz2)?.odozva ?? null) * (SPODOK - 8) + 4}
            stroke="var(--app-text)"
            strokeWidth="5"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </>
      )}
    </svg>
  );
}

/**
 * Výška bodu z tempa odpovedí. `odozva` je násobič oneskorenia (1 = bežne,
 * 4 = telefón odložený), takže dostupnosť je jeho prevrátená hodnota. Spodná
 * hranica nie je nula: bdelá modelka na fotení musí byť aj tak vidieť nad
 * spánkom, inak krivka klame.
 */
function vyska(odozva: number | null): number {
  if (odozva === null) return 0;
  const v = 1 / (Math.max(0.1, odozva) * 2);
  return Math.min(1, Math.max(0.12, v));
}

/** Catmull-Rom → bezier. Schody medzi blokmi tým dostanú plynulý prechod. */
function hladkaCiara(body: [number, number][]): string {
  if (body.length === 0) return "";
  if (body.length < 3) return `M ${body.map(([x, y]) => `${x} ${y}`).join(" L ")}`;

  let d = `M ${body[0][0]} ${body[0][1]}`;
  for (let i = 0; i < body.length - 1; i += 1) {
    const p0 = body[Math.max(0, i - 1)];
    const p1 = body[i];
    const p2 = body[i + 1];
    const p3 = body[Math.min(body.length - 1, i + 2)];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2[0]} ${p2[1]}`;
  }
  return d;
}

/* --------------------------------------------------------------------------
   Čas a text
-------------------------------------------------------------------------- */

type Cas = { minuta: number; hodiny: string; datum: string };

/** Koľko je u nej — minúta dňa, čitateľný čas a JEJ dátum (nie serverový). */
function jejCas(minutaEpochy: number, tz: string): Cas | null {
  const kedy = new Date(minutaEpochy * 60_000);
  try {
    const casti = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(kedy);

    const kus = (typ: string) => casti.find((c) => c.type === typ)?.value ?? "";
    // `hour12: false` vracia o polnoci „24" v niektorých prostrediach.
    const h = Number(kus("hour")) % 24;
    const m = Number(kus("minute"));
    if (!Number.isFinite(h) || !Number.isFinite(m)) return null;

    return {
      minuta: h * 60 + m,
      hodiny: format12(h * 60 + m),
      datum: `${kus("year")}-${kus("month")}-${kus("day")}`,
    };
  } catch {
    return null;
  }
}

/** Blok, v ktorom je daná minúta. Ráta aj s plánom presahujúcim polnoc. */
function najdiBlok<T extends { od: number; do: number }>(bloky: T[], minuta: number): T | null {
  for (const b of bloky) {
    if (minuta >= b.od && minuta < b.do) return b;
    if (minuta + DEN >= b.od && minuta + DEN < b.do) return b;
  }
  return null;
}

/** To isté pravidlo ako vo workeri (`behavior.in_active_window`). */
function jeVOkne(minuty: number, start: number, end: number): boolean {
  if (start === end) return true; // 24/7
  if (start < end) return minuty >= start && minuty < end;
  return minuty >= start || minuty < end; // okno cez polnoc: 22:00 → 02:00
}

/** 14:05 → „2:05 PM". Práve tento tvar chýbal — z 24-hodinového sa nedalo
 *  poznať, či je nastavené ráno alebo večer. */
export function format12(minuty: number): string {
  const cele = ((minuty % DEN) + DEN) % DEN;
  const h24 = Math.floor(cele / 60);
  const m = cele % 60;
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${h24 < 12 ? "AM" : "PM"}`;
}

/** „Los Angeles" z „America/Los_Angeles" — pásmo s podčiarkovníkmi nie je meno. */
function mestoZPasma(tz: string): string {
  const kus = tz.split("/").pop() ?? tz;
  return kus.replace(/_/g, " ");
}

function tempo(odozva: number): string {
  if (odozva <= 0.6) return "replying in seconds";
  if (odozva <= 0.9) return "replying quickly";
  if (odozva <= 1.2) return "replying normally";
  if (odozva <= 1.8) return "slow to reply";
  if (odozva <= 3) return "replying between other things";
  return "phone away";
}

/** Čo napísať, keď v pláne práve nie je žiadny blok. */
function tichoText(
  bloky: { od: number; do: number }[],
  cerstvy: boolean,
  minuta: number,
): string {
  if (!cerstvy) return "Today's plan has not been drawn yet — she picks it when her day starts.";
  const dalsi = bloky.find((b) => b.od > minuta || b.od > minuta + DEN);
  if (dalsi) return `Asleep — her day starts at ${format12(dalsi.od)}.`;
  return "Her day is over — she is asleep.";
}
