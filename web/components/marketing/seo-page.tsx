import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { CtaBand, PageHeader } from "@/components/marketing/page-shell";
import { SITE_URL, structuredData } from "@/lib/seo";

export type SeoHighlight = {
  title: string;
  body: string;
};

export type SeoSection = {
  title: string;
  paragraphs: string[];
  points?: string[];
};

export type SeoFaq = {
  q: string;
  a: string;
};

export type SeoRelatedLink = {
  href: string;
  label: string;
  description: string;
};

type SeoPageProps = {
  path: `/${string}`;
  eyebrow: string;
  title: string;
  dim?: string;
  lead: string;
  highlights: SeoHighlight[];
  sections: SeoSection[];
  faq: SeoFaq[];
  related: SeoRelatedLink[];
  ctaTitle: string;
  ctaBody: string;
  ctaNote?: string;
};

/**
 * Dlhé vyhľadávacie landingy zdieľajú rytmus, nie text. Každá stránka má
 * vlastný search intent, vlastné sekcie a vlastné FAQ; tak sa z nich nestanú
 * tenké doorway stránky s vymeneným kľúčovým slovom.
 */
export function SeoPage({
  path,
  eyebrow,
  title,
  dim,
  lead,
  highlights,
  sections,
  faq,
  related,
  ctaTitle,
  ctaBody,
  ctaNote,
}: SeoPageProps) {
  const schema = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebPage",
        "@id": `${SITE_URL}${path}#webpage`,
        url: `${SITE_URL}${path}`,
        name: title,
        description: lead,
        isPartOf: { "@id": `${SITE_URL}/#website` },
        inLanguage: "en",
      },
      {
        "@type": "BreadcrumbList",
        "@id": `${SITE_URL}${path}#breadcrumb`,
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: "Telepipe",
            item: SITE_URL,
          },
          {
            "@type": "ListItem",
            position: 2,
            name: title,
            item: `${SITE_URL}${path}`,
          },
        ],
      },
      {
        "@type": "FAQPage",
        "@id": `${SITE_URL}${path}#faq`,
        mainEntity: faq.map((item) => ({
          "@type": "Question",
          name: item.q,
          acceptedAnswer: {
            "@type": "Answer",
            text: item.a,
          },
        })),
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: structuredData(schema) }}
      />

      <section className="relative overflow-hidden px-6 pb-16 pt-[112px] sm:pb-20 sm:pt-[132px]">
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          aria-hidden
          className="lp-halo pointer-events-none absolute left-1/2 top-4 h-[560px] w-[900px] -translate-x-1/2 opacity-30"
        />
        <div className="relative mx-auto max-w-6xl">
          <PageHeader eyebrow={eyebrow} title={title} dim={dim} lead={lead} />

          <div className="mt-14 grid gap-4 md:grid-cols-3">
            {highlights.map((item, index) => (
              <article key={item.title} className="lp-card p-6 sm:p-7">
                <p className="font-mono text-[11px] text-white/25">
                  {String(index + 1).padStart(2, "0")}
                </p>
                <h2 className="mt-6 text-[17px] font-semibold text-white">{item.title}</h2>
                <p className="mt-3 text-[13.5px] leading-relaxed text-white/45">{item.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="relative px-6 pb-24">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="space-y-5">
            {sections.map((section) => (
              <article key={section.title} className="lp-seo-section lp-card p-7 sm:p-9">
                <h2 className="lp-tight text-[clamp(1.35rem,2.4vw,1.8rem)] font-semibold text-white">
                  {section.title}
                </h2>
                <div className="mt-5 space-y-4">
                  {section.paragraphs.map((paragraph) => (
                    <p key={paragraph} className="text-[14.5px] leading-7 text-white/50">
                      {paragraph}
                    </p>
                  ))}
                </div>
                {section.points && (
                  <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                    {section.points.map((point) => (
                      <li key={point} className="flex gap-3 text-[13.5px] leading-6 text-white/55">
                        <span className="lp-icon-chip mt-0.5 h-5 w-5 shrink-0 rounded-md">
                          <Check className="h-3 w-3" strokeWidth={1.8} />
                        </span>
                        {point}
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>

          <aside className="h-fit lg:sticky lg:top-24">
            <div className="lp-card p-6">
              <p className="lp-eyebrow">Explore Telepipe</p>
              <div className="mt-5 space-y-3">
                {related.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="group block rounded-xl border border-white/[0.07] p-4 transition-colors hover:border-white/[0.16] hover:bg-white/[0.025]"
                  >
                    <span className="flex items-center justify-between gap-3 text-[13.5px] font-medium text-white/75 group-hover:text-white">
                      {item.label}
                      <ArrowRight className="h-3.5 w-3.5 shrink-0" strokeWidth={1.6} />
                    </span>
                    <span className="mt-2 block text-[12px] leading-5 text-white/35">
                      {item.description}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </section>

      <section className="relative px-6 pb-24">
        <div className="mx-auto max-w-4xl">
          <div className="text-center">
            <p className="lp-eyebrow">Questions</p>
            <h2 className="lp-tight mt-4 text-[clamp(1.8rem,3.4vw,2.5rem)] font-semibold text-white">
              What people ask before they start.
            </h2>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {faq.map((item) => (
              <article key={item.q} className="lp-seo-section lp-card p-6">
                <h3 className="text-[14.5px] font-semibold text-white">{item.q}</h3>
                <p className="mt-3 text-[13px] leading-6 text-white/45">{item.a}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <CtaBand title={ctaTitle} body={ctaBody} note={ctaNote} />
    </>
  );
}
