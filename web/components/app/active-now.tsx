"use client";

import { useSyncExternalStore } from "react";

/**
 * Koľko je práve u nej a či je hore.
 *
 * PREČO TO EXISTUJE. Klient nastaví okno v JEJ pásme, ale sedí v inom — a
 * potom nevie, či mlčanie znamená poruchu, alebo že je u nej pol štvrtej ráno.
 * Naostro sa to už stalo: majiteľ posunul začiatok na skoršie, modelka
 * neodpisovala a nedalo sa rozoznať, či je chyba v nastavení, alebo len ešte
 * nie je jej ráno.
 *
 * Čas je vonkajší zdroj, ktorý sa mení sám — preto `useSyncExternalStore` a nie
 * `useState` v efekte. Na serveri je snapshot `null`, takže sa nič nevykreslí a
 * nemá ako vzniknúť nesúlad s prehliadačom.
 */
const TIK_MS = 30_000;

function subscribe(callback: () => void): () => void {
  const id = window.setInterval(callback, TIK_MS);
  return () => window.clearInterval(id);
}

/** Minúta ako číslo — mení sa raz za minútu, takže sa zbytočne neprekresľuje. */
function snapshot(): number {
  return Math.floor(Date.now() / 60_000);
}

export function ActiveNow({
  startMin,
  endMin,
  timeZone,
}: {
  startMin: number;
  endMin: number;
  timeZone: string;
}) {
  const minuta = useSyncExternalStore(subscribe, snapshot, () => null);
  if (minuta === null) return null;

  let jejCas: string;
  try {
    jejCas = new Intl.DateTimeFormat("en-GB", {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(minuta * 60_000));
  } catch {
    // Neznáme pásmo je vec nastavenia, nie dôvod, aby spadla celá karta.
    return null;
  }

  const [h, m] = jejCas.split(":").map(Number);
  const hore = jeVOkne(h * 60 + m, startMin, endMin);

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-[var(--app-border)] bg-[#0b0b0b] px-3 py-2.5 text-[12.5px]">
      <span
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          hore ? "bg-[var(--app-up)]" : "bg-[var(--app-text-4)]"
        }`}
      />
      <span className="text-[var(--app-text-2)]">
        It is <strong className="font-medium text-[var(--app-text)]">{jejCas}</strong> for her
        right now
      </span>
      <span className="text-[var(--app-text-4)]">·</span>
      <span className={hore ? "text-[var(--app-up)]" : "text-[var(--app-text-3)]"}>
        {hore ? "she is awake and replying" : `asleep until ${format24(startMin)}`}
      </span>
    </div>
  );
}

/** To isté pravidlo ako vo workeri (`behavior.in_active_window`). */
function jeVOkne(minuty: number, start: number, end: number): boolean {
  if (start === end) return true; // 24/7
  if (start < end) return minuty >= start && minuty < end;
  // Okno cez polnoc: 22:00 → 02:00.
  return minuty >= start || minuty < end;
}

function format24(minuty: number): string {
  const h = Math.floor(minuty / 60) % 24;
  const m = minuty % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
