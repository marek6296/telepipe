"use client";

export default function SocialError({ reset }: { reset: () => void }) {
  return <div role="alert" className="app-card px-6 py-12 text-center"><h2 className="text-[17px] font-medium">The inbox could not be loaded</h2><p className="mx-auto mt-3 max-w-sm text-[12px] leading-6 text-[var(--app-text-3)]">Your conversations are still saved. Try loading the page again.</p><button type="button" onClick={reset} className="app-btn app-btn-ghost mx-auto mt-5 min-h-9 px-4">Try again</button></div>;
}
