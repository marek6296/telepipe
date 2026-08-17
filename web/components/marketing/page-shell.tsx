import Link from "next/link";
import { ArrowRight } from "lucide-react";

/**
 * Spoločné stavebné kamene marketingových podstránok (`/features`,
 * `/how-it-works`, `/pricing`) — hlavička s eyebrow/nadpisom a záverečné CTA.
 *
 * Vďaka nim majú všetky tri stránky rovnaký rytmus a rovnaké odsadenie od
 * fixnej navigácie (68 px), takže sa to nikde nemusí opakovať.
 */

export function PageHeader({
  eyebrow,
  title,
  dim,
  lead,
  align = "center",
}: {
  eyebrow: string;
  /** Prvá časť nadpisu — biela. */
  title: string;
  /** Druhá časť nadpisu — stlmená (gradient). Voliteľná. */
  dim?: string;
  lead?: string;
  align?: "center" | "left";
}) {
  const centered = align === "center";

  return (
    <header
      className={
        centered
          ? "relative mx-auto max-w-2xl text-center"
          : "relative max-w-2xl text-left"
      }
    >
      <p className="lp-eyebrow">{eyebrow}</p>
      <h1 className="lp-tight mt-4 text-[clamp(2.1rem,4.8vw,3.4rem)] font-semibold leading-[1.08] text-white">
        {title}
        {dim && <span className="lp-text-dim"> {dim}</span>}
      </h1>
      {lead && (
        <p
          className={
            centered
              ? "mx-auto mt-5 max-w-xl text-[15.5px] leading-relaxed text-white/45"
              : "mt-5 max-w-xl text-[15.5px] leading-relaxed text-white/45"
          }
        >
          {lead}
        </p>
      )}
    </header>
  );
}

export function CtaBand({
  title,
  body,
  note,
}: {
  title: string;
  body: string;
  note?: string;
}) {
  return (
    <section className="relative px-6 pb-28 pt-4 sm:pb-36">
      <div className="lp-depth-card relative mx-auto max-w-5xl overflow-hidden rounded-[28px] px-8 py-14 text-center sm:px-14">
        <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
        <div className="relative">
          <h2 className="lp-tight mx-auto max-w-2xl text-[clamp(1.7rem,3.4vw,2.5rem)] font-semibold leading-tight text-white">
            {title}
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-white/45">
            {body}
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/register"
              className="lp-btn lp-btn-primary h-12 px-7 text-[14.5px]"
            >
              Get Started
              <ArrowRight className="h-4 w-4" strokeWidth={1.75} />
            </Link>
            <Link href="/login" className="lp-btn lp-btn-ghost h-12 px-7 text-[14.5px]">
              Sign In
            </Link>
          </div>
          {note && <p className="mt-8 text-xs text-white/30">{note}</p>}
        </div>
      </div>
    </section>
  );
}
