import Image from "next/image";
import Link from "next/link";

/** Značkové 404 — default Next stránka je biela a v tmavej appke bije do očí. */
export default function NotFound() {
  return (
    <main className="relative flex min-h-svh flex-1 flex-col items-center justify-center px-6 text-center">
      <div className="pointer-events-none absolute inset-0 bg-grid-fine" />
      <div className="gold-halo pointer-events-none absolute left-1/2 top-1/3 h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 opacity-60" />

      <div className="relative">
        <Image
          src="/logo-white.png"
          alt="Telepipe"
          width={160}
          height={51}
          priority
          className="mx-auto h-7 w-auto"
        />
        <p className="mt-12 text-[72px] font-semibold leading-none text-gradient-gold">404</p>
        <h1 className="mt-4 text-[19px] font-semibold text-white">
          This page could not be found
        </h1>
        <p className="mt-2 text-[13.5px] text-white/45">
          The link may be old, or the model no longer exists.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link href="/app" className="btn-modern-light h-11 px-6 text-[13.5px]">
            Back to dashboard
          </Link>
          <Link href="/" className="btn-modern-dark h-11 px-6 text-[13.5px]">
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}
