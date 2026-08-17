import { LandingFooter } from "@/components/landing/footer";
import { LandingNav } from "@/components/landing/nav";

// Monochrómne triedy landingu + marketing stránok. Zámerne NIE v globals.css —
// ten vlastní appka (`.app-*`) a marketing sa doňho nesmie miešať.
import "../landing.css";

/**
 * Spoločný layout pre `/`, `/features`, `/how-it-works` a `/pricing`.
 *
 * Nav aj footer žijú tu, aby sa medzi stránkami neduplikovali. `LandingNav` si
 * variant (cinematic vs. sticky) určuje sám z `usePathname()` — na `/` ostáva
 * skrytý kým ho neodhalí intro timeline v `CinematicScene`, inde je to bežná
 * fixná hlavička.
 */
export default function MarketingLayout({ children }: LayoutProps<"/">) {
  return (
    // `contents` = wrapper nevytvára box, takže flex layout <body> ostáva presne
    // ako predtým; slúži len na scope `.lp-*` tried a CSS premenných.
    <div className="lp-scope contents">
      <LandingNav />
      <main className="flex-1">{children}</main>
      <LandingFooter />
    </div>
  );
}
