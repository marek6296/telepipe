import { cn } from "@/lib/utils";

function Skeleton({ className }: { className?: string }) {
  return <span className={cn("app-skeleton block", className)} />;
}

function HeaderSkeleton() {
  return (
    <div className="mb-8 flex items-start justify-between gap-4" aria-hidden>
      <div className="w-full max-w-xl">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="mt-3 h-7 w-52" />
        <Skeleton className="mt-3 h-3 w-full max-w-md" />
      </div>
      <Skeleton className="hidden h-9 w-28 sm:block" />
    </div>
  );
}

export function StatsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 min-[460px]:grid-cols-2 sm:gap-4 lg:grid-cols-4" aria-hidden>
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="app-card px-5 py-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-7 w-20" />
          <Skeleton className="mt-3 h-3 w-28" />
        </div>
      ))}
    </div>
  );
}

export function ChartsSkeleton() {
  return (
    <div className="mt-4 grid gap-4 xl:grid-cols-2" aria-hidden>
      {Array.from({ length: 2 }, (_, index) => (
        <div key={index} className="app-card overflow-hidden">
          <div className="border-b border-[var(--app-border)] px-5 py-4">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="mt-2 h-3 w-44" />
          </div>
          <div className="px-5 py-5">
            <Skeleton className="h-[196px] w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ModelCardsSkeleton({ count = 2 }: { count?: number }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2" aria-hidden>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="app-card p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="mt-3 h-3 w-full max-w-sm" />
            </div>
            <Skeleton className="h-8 w-20" />
          </div>
          <div className="mt-6 grid grid-cols-3 gap-5">
            {Array.from({ length: 3 }, (_, metric) => (
              <div key={metric}>
                <Skeleton className="h-3 w-14" />
                <Skeleton className="mt-2 h-5 w-12" />
              </div>
            ))}
          </div>
          <Skeleton className="mt-5 h-9 w-full" />
        </div>
      ))}
    </div>
  );
}

export function AppRouteSkeleton() {
  return (
    <div role="status" aria-label="Loading dashboard" className="app-loading-enter">
      <span className="sr-only">Loading dashboard…</span>
      <HeaderSkeleton />
      <StatsSkeleton />
      <ChartsSkeleton />
    </div>
  );
}

export function ModelRouteSkeleton() {
  return (
    <div role="status" aria-label="Loading model page" className="app-loading-enter">
      <span className="sr-only">Loading model page…</span>
      <HeaderSkeleton />
      <div className="grid gap-4 lg:grid-cols-2" aria-hidden>
        <div className="app-card p-5">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="mt-3 h-3 w-5/6" />
          <Skeleton className="mt-7 h-10 w-full" />
          <Skeleton className="mt-3 h-24 w-full" />
        </div>
        <div className="app-card p-5">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="mt-3 h-3 w-3/4" />
          <Skeleton className="mt-7 h-32 w-full" />
        </div>
      </div>
    </div>
  );
}
