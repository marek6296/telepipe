import { PageSkeleton } from "@/components/app/skeleton";

/**
 * Fallback pre celý `/app`. Sidebar aj hlavička sú v layoute, takže tie
 * ostávajú na mieste a vymení sa len obsah — presne ako v natívnej appke.
 */
export default function Loading() {
  return <PageSkeleton cards={2} rows={2} />;
}
