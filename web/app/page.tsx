import { CinematicHero } from "@/components/landing/cinematic-hero";
import { Features } from "@/components/landing/features";
import { LandingFooter } from "@/components/landing/footer";
import { HowItWorks } from "@/components/landing/how-it-works";
import { LandingNav } from "@/components/landing/nav";

export default function Home() {
  return (
    <>
      <LandingNav />
      <main className="flex-1">
        <CinematicHero />
        <Features />
        <HowItWorks />
      </main>
      <LandingFooter />
    </>
  );
}
