import { PageSkeleton } from "@/components/app/skeleton";

/**
 * Karty modelky. Hlavička so stavom a tab bar sú v layoute modelky, takže pri
 * prepínaní kariet ostávajú stáť a mení sa len telo — to je ten rozdiel medzi
 * „appka" a „stránka sa načítava".
 */
export default function Loading() {
  return <PageSkeleton cards={2} rows={3} />;
}
