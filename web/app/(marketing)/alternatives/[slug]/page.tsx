import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { SeoPage } from "@/components/marketing/seo-page";
import { ALTERNATIVES, findAlternative, trademarkNote } from "@/lib/alternatives";
import { marketingMetadata } from "@/lib/seo";

/**
 * Stránky „X alternative". Jedna route, jeden dátový súbor — pridať konkurenta
 * znamená pridať záznam, nie stránku, takže sa tvar nemôže rozísť.
 *
 * `generateStaticParams` + `dynamicParams = false`: neznámy slug je 404, nie
 * prázdna stránka. Vyhľadávače inak indexujú vygenerované nezmysly.
 */
export const dynamicParams = false;

export function generateStaticParams() {
  return ALTERNATIVES.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({
  params,
}: PageProps<"/alternatives/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const item = findAlternative(slug);
  if (!item) return {};
  return marketingMetadata({
    title: item.title,
    description: item.description,
    path: `/alternatives/${item.slug}`,
  });
}

export default async function AlternativePage({
  params,
}: PageProps<"/alternatives/[slug]">) {
  const { slug } = await params;
  const item = findAlternative(slug);
  if (!item) notFound();

  // Odkazy na ostatné porovnania. Kto číta jedno, často porovnáva viac —
  // a stránky sa tým zároveň prelinkujú medzi sebou.
  const related = ALTERNATIVES.filter((other) => other.slug !== item.slug)
    .slice(0, 3)
    .map((other) => ({
      href: `/alternatives/${other.slug}`,
      label: other.title,
      description: other.description,
    }));

  return (
    <SeoPage
      path={`/alternatives/${item.slug}`}
      eyebrow={item.eyebrow}
      title={item.title}
      lead={item.lead}
      highlights={item.highlights}
      sections={[
        ...item.sections,
        // Vlastníctvo značky je posledná sekcia na KAŽDEJ stránke. Nie preto,
        // že to vyžaduje SEO, ale preto, že bez toho je to problém inde.
        {
          title: "About the name",
          paragraphs: [trademarkNote(item.name)],
        },
      ]}
      faq={item.faq}
      related={[
        ...related,
        {
          href: "/pricing",
          label: "What it costs",
          description:
            "No subscription. Pipe Coins, spent per reply as your models work.",
        },
      ]}
      ctaTitle={`Try it instead of ${item.name}`}
      ctaBody="Connect a model, write her persona, and watch the first conversations in your own control bot before anything goes out."
      ctaNote="No plan, no seat. You buy coins and spend them as she works."
    />
  );
}
