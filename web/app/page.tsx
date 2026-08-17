import { CinematicHero } from "@/components/landing/cinematic-hero";
import { Features } from "@/components/landing/features";
import { LandingFooter } from "@/components/landing/footer";
import { HowItWorks } from "@/components/landing/how-it-works";
import { LandingNav } from "@/components/landing/nav";

// Monochrómne triedy landingu + auth. Zámerne NIE v globals.css — ten vlastní
// appka (`.app-*`) a landing sa doňho nesmie miešať.
import "./landing.css";

export default function Home() {
  return (
    // `contents` = wrapper nevytvára box, takže flex layout <body> ostáva presne
    // ako predtým; slúži len na scope `.lp-*` tried a CSS premenných.
    <div className="lp-scope contents">
      <LandingNav />
      <main className="flex-1">
        <CinematicHero />
        <Features />
        <HowItWorks />
      </main>
      <LandingFooter />
    </div>
  );
}
