export default function SocialLoading() {
  return <div role="status" aria-label="Loading Social sites" className="animate-pulse space-y-5"><div className="h-6 w-36 rounded bg-[var(--app-surface-hover)]" /><div className="grid gap-3 sm:grid-cols-3">{[0, 1, 2].map(item => <div key={item} className="app-card h-40" />)}</div><div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]"><div className="app-card h-[450px]" /><div className="app-card hidden h-[450px] lg:block" /></div></div>;
}
