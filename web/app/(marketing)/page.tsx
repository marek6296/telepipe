import { CinematicHero } from "@/components/landing/cinematic-hero";

/**
 * Landing (`/`) — len kinematická scéna.
 *
 * Sekcie Features / How it works / Pricing sa presunuli na vlastné stránky
 * (`/features`, `/how-it-works`, `/pricing`), takže pod pinnutou scénou už nič
 * nie je — po dobehnutí timeline sa odopne pin a odkryje footer z layoutu.
 * Nav a footer poskytuje `app/(marketing)/layout.tsx`.
 */
export default function Home() {
  return <CinematicHero />;
}
