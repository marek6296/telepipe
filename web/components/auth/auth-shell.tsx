import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, Quote } from "lucide-react";

/**
 * Dvojstĺpcový layout — vľavo formulár, vpravo vizuálny panel s ukážkovými
 * testimonialmi. Split ostáva, farby idú do monochrómu (zlatá len v logu).
 */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-svh w-full flex-1">
      <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
      <div className="film-grain-fixed" />

      {/* --- Ľavý stĺpec: formulár ---------------------------------------- */}
      <div className="relative flex w-full flex-col px-6 py-6 sm:px-12 lg:w-1/2 lg:px-16">
        <div className="animate-element animate-delay-100 flex items-center justify-between">
          <Link href="/" className="flex items-center" aria-label="Telepipe home">
            <Image
              src="/logo-white.png"
              alt="Telepipe"
              width={148}
              height={47}
              priority
              className="h-7 w-auto"
            />
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-[12.5px] text-white/40 transition-colors hover:text-white"
          >
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
            Back to site
          </Link>
        </div>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[26rem]">{children}</div>
        </div>

        <p className="animate-element animate-delay-1200 text-center text-[11.5px] text-white/25">
          © {new Date().getFullYear()} Telepipe
        </p>
      </div>

      {/* --- Pravý stĺpec: vizuál + testimonials --------------------------- */}
      <div className="relative hidden p-4 lg:block lg:w-1/2">
        <div className="lp-depth-card relative h-full w-full overflow-hidden rounded-[24px]">
          <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
          <div className="lp-halo pointer-events-none absolute -right-32 -top-32 h-[520px] w-[520px]" />
          <div className="lp-halo pointer-events-none absolute -bottom-40 -left-24 h-[440px] w-[440px] opacity-70" />

          <div className="relative flex h-full flex-col justify-between p-10 xl:p-14">
            <div className="animate-element animate-delay-300">
              <Image
                src="/logo-white.png"
                alt="Telepipe"
                width={220}
                height={70}
                className="h-9 w-auto"
              />
              <h2 className="mt-10 max-w-md text-[clamp(1.65rem,2.4vw,2.4rem)] font-semibold leading-[1.12] lp-tight">
                <span className="lp-text-dim">Your models never sleep.</span>
                <br />
                <span className="lp-text-bright">Neither does your funnel.</span>
              </h2>
              <p className="mt-5 max-w-sm text-[14.5px] leading-relaxed text-white/45">
                One agent per model, answering every Telegram DM in seconds — with
                her voice, her tone, and your link.
              </p>
            </div>

            <div className="space-y-3">
              <Testimonial
                quote="We stopped paying for a night shift entirely. The agent keeps the tone we spent months training chatters on."
                name="Mara V."
                role="Agency owner · 6 models"
                initials="MV"
              />
              <Testimonial
                quote="Voice notes were the unlock. Conversion from chat to subscriber roughly doubled in the first month."
                name="Dominik R."
                role="Chat team lead"
                initials="DR"
                delay="animate-delay-900"
              />
              <p className="animate-element animate-delay-1000 pt-1 text-[10.5px] leading-relaxed text-white/25">
                Illustrative examples of the kind of results agencies aim for — not
                real customer quotes.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Testimonial({
  quote,
  name,
  role,
  initials,
  delay = "animate-delay-700",
}: {
  quote: string;
  name: string;
  role: string;
  initials: string;
  delay?: string;
}) {
  return (
    <figure className={`lp-glass animate-element ${delay} rounded-2xl p-5`}>
      <Quote className="h-4 w-4 text-white/30" strokeWidth={1.5} />
      <blockquote className="mt-3 text-[13.5px] leading-relaxed text-white/70">
        {quote}
      </blockquote>
      <figcaption className="mt-4 flex items-center gap-3">
        <span className="lp-hairline flex h-9 w-9 items-center justify-center rounded-full bg-white/[0.06] text-[12px] font-semibold text-white/80">
          {initials}
        </span>
        <span>
          <span className="block text-[13px] font-semibold text-white">{name}</span>
          <span className="block text-[11px] text-white/40">{role}</span>
        </span>
      </figcaption>
    </figure>
  );
}
