import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { CtaBand, PageHeader } from "@/components/marketing/page-shell";
import { ALTERNATIVES } from "@/lib/alternatives";
import { marketingMetadata, SITE_URL, structuredData } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "Telepipe vs Other Creator Chat Tools",
  description:
    "How Telepipe compares to creator chat tools like Supercreator, Botly and ChatPersonas — and why the funnel starts on Telegram, not in the paid inbox.",
  path: "/alternatives",
});

/**
 * Rozcestník porovnaní. Existuje z dvoch dôvodov: zbiera široké hľadania
 * („ai chatter alternatives") a prelinkuje jednotlivé stránky, aby každá
 * nestála sama.
 */
const ITEM_LIST = {
  "@context": "https://schema.org",
  "@type": "ItemList",
  "@id": `${SITE_URL}/alternatives#list`,
  name: "Telepipe alternatives and comparisons",
  itemListElement: ALTERNATIVES.map((item, index) => ({
    "@type": "ListItem",
    position: index + 1,
    name: item.title,
    url: `${SITE_URL}/alternatives/${item.slug}`,
  })),
};

export default function AlternativesPage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: structuredData(ITEM_LIST) }}
      />

      <section className="relative overflow-hidden px-6 pb-16 pt-[112px] sm:pb-20 sm:pt-[132px]">
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          aria-hidden
          className="lp-halo pointer-events-none absolute left-1/2 top-0 h-[520px] w-[860px] -translate-x-1/2 opacity-30"
        />
        <div className="relative mx-auto max-w-6xl">
          <PageHeader
            eyebrow="Comparisons"
            title="How Telepipe compares,"
            dim="without the sales pitch."
            lead="Most creator chat tools work the inbox of the paid platform. Telepipe works the step before it — her own Telegram account, on her own schedule, sending people to the page. Here is what that means next to the tools you are probably already looking at."
          />

          <div className="mt-14 grid gap-5 lg:grid-cols-2">
            {ALTERNATIVES.map((item, index) => (
              <Link
                key={item.slug}
                href={`/alternatives/${item.slug}`}
                className="lp-card lp-card-hover group flex min-h-[260px] flex-col p-7"
              >
                <div className="flex items-center justify-between text-[10.5px] uppercase tracking-[0.18em] text-white/30">
                  <span>{item.eyebrow}</span>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                </div>
                <h2 className="lp-tight mt-8 text-[22px] font-semibold leading-tight text-white">
                  {item.title}
                </h2>
                <p className="mt-4 text-[13.5px] leading-6 text-white/45">{item.lead}</p>
                <span className="mt-auto flex items-center justify-end pt-8">
                  <ArrowRight
                    className="h-4 w-4 text-white/35 transition-transform group-hover:translate-x-1"
                    strokeWidth={1.6}
                  />
                </span>
              </Link>
            ))}
          </div>

          <p className="mt-10 max-w-3xl text-[12.5px] leading-6 text-white/30">
            Every product named on these pages is a trademark of its owner.
            Telepipe is independent and is not affiliated with, endorsed by or
            sponsored by any of them. Products change — check their own sites
            for what they offer today.
          </p>
        </div>
      </section>

      <CtaBand
        title="See it on your own account."
        body="Connect a model, write her persona, and read the first conversations in your own control bot before anything goes out."
        note="No card required · Usage-based Pipe Coins · Pause any time"
      />
    </>
  );
}
