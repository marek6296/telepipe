/**
 * Kostry obrazoviek pre `loading.tsx`.
 *
 * PREČO TO VÔBEC EXISTUJE: bez `loading.tsx` Next router čaká na KOMPLETNÝ
 * serverový payload, kým vymení čo i len pixel. Pri piatich dotazoch do
 * databázy to znamená, že človek klikne na kartu a pol sekundy sa nedeje nič —
 * appka pôsobí ako web, ktorý načítava stránku. S kostrou sa obsah vymení
 * OKAMŽITE a dáta dotečú do pripraveného tvaru.
 *
 * Kostra preto musí mať PRIBLIŽNE ROVNAKÝ TVAR ako skutočný obsah. Keď sa
 * rozmery líšia, obsah po dotečení poskočí a je to horšie než čakanie.
 */

/** Jeden pruh. `animate-pulse` na rodičovi rozhýbe všetky naraz — nie každý
 *  zvlášť, aby to nevyzeralo ako blikajúca vianočná reťaz. */
export function Bar({ className = "" }: { className?: string }) {
  return <div className={`rounded-md bg-[var(--app-surface-hover)] ${className}`} />;
}

/** Hlavička stránky — eyebrow, titulok, popis. */
export function HeaderSkeleton() {
  return (
    <div className="mb-6">
      <Bar className="h-2.5 w-24" />
      <Bar className="mt-3 h-7 w-52" />
      <Bar className="mt-3 h-3.5 w-full max-w-md" />
    </div>
  );
}

/** Karta s hlavičkou a niekoľkými riadkami polí. */
export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="app-card overflow-hidden">
      <div className="border-b border-[var(--app-border)] p-5">
        <Bar className="h-4 w-40" />
        <Bar className="mt-2.5 h-3 w-full max-w-sm" />
      </div>
      <div className="grid gap-5 p-5 sm:grid-cols-2">
        {Array.from({ length: rows * 2 }).map((_, i) => (
          <div key={i}>
            <Bar className="h-3 w-24" />
            <Bar className="mt-2 h-9 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Celá obrazovka: hlavička + karty. */
export function PageSkeleton({ cards = 2, rows = 2 }: { cards?: number; rows?: number }) {
  return (
    <div className="animate-pulse" aria-hidden>
      <HeaderSkeleton />
      <div className="grid gap-4">
        {Array.from({ length: cards }).map((_, i) => (
          <CardSkeleton key={i} rows={rows} />
        ))}
      </div>
      <span className="sr-only">Loading</span>
    </div>
  );
}
