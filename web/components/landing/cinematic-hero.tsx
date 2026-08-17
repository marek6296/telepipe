"use client";

import { useEffect, useLayoutEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, Clock, TrendingUp } from "lucide-react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import {
  PhoneMockup,
  RING_CIRCUMFERENCE,
  RING_PROGRESS,
  RING_TARGET,
} from "@/components/landing/phone-mockup";

// useLayoutEffect na serveri varuje — na klientovi ho chceme (zabráni bliknutiu)
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

/**
 * Dĺžka pinnutého scrollu.
 *
 * Pôvodne fixných 7000 px. Vnímané tempo scrollu ale závisí od výšky okna —
 * na 1080p obrazovke je 7000 px „6,5 obrazovky", na notebooku 8,7. Preto je
 * vzdialenosť odvodená od `innerHeight` a clampnutá, aby ostala v rozumnom
 * rozsahu. Timeline má 9,35 jednotky, takže na typickom 1280×800 vychádza
 * ~445 px scrollu na jednotku.
 */
const SCENE_SCROLL_VH = 5.2;
const SCENE_SCROLL_MIN = 3600;
const SCENE_SCROLL_MAX = 5200;

const sceneScroll = () =>
  Math.round(
    gsap.utils.clamp(
      SCENE_SCROLL_MIN,
      SCENE_SCROLL_MAX,
      window.innerHeight * SCENE_SCROLL_VH,
    ),
  );

export function CinematicHero() {
  return (
    <>
      {/* Plná GSAP scéna — skrytá pri prefers-reduced-motion (CSS, bez bliknutia) */}
      <div className="motion-only">
        <CinematicScene />
      </div>
      {/* Statická alternatíva pri prefers-reduced-motion */}
      <div className="reduced-motion-only">
        <StaticHero />
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/*  Animovaná scéna                                                            */
/* -------------------------------------------------------------------------- */

function CinematicScene() {
  const sceneRef = useRef<HTMLDivElement>(null);

  useIsomorphicLayoutEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    // Pri reduced-motion je scéna display:none — nič nenastavujeme
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    gsap.registerPlugin(ScrollTrigger);

    const ctx = gsap.context(() => {
      const q = <T extends Element = HTMLElement>(sel: string) =>
        scene.querySelector<T>(sel);
      const qa = <T extends Element = HTMLElement>(sel: string) =>
        gsap.utils.toArray<T>(scene.querySelectorAll<T>(sel));

      const intro = q("[data-intro]")!;
      // Dva riadky nadpisu majú každý VLASTNÚ animáciu (predloha .text-track /
      // .text-days): prvý sa zaostrí a nadvihne, druhý sa „píše" zľava doprava.
      const introTrack = q("[data-intro-track]")!;
      const introDays = q("[data-intro-days]")!;
      const introSub = q("[data-intro-sub]")!;
      const scrollHint = q("[data-scroll-hint]")!;
      const halo = q("[data-halo]")!;
      const card = q("[data-card]")!;
      const cardInner = q("[data-card-inner]")!;
      const cardCopy = qa("[data-card-copy]");
      const phoneWrap = q("[data-phone-wrap]")!;
      const badges = qa("[data-badge]");
      const bubbles = qa("[data-bubble]");
      const widgets = qa("[data-widget]");
      const ringArc = q<SVGCircleElement>("[data-ring-arc]")!;
      const ringValue = q("[data-ring-value]")!;
      const cta = q("[data-cta]")!;
      const ctaItems = qa("[data-cta-item]");

      // Navigácia žije mimo scény (fixed header), preto ju hľadáme v dokumente.
      const navGroups = gsap.utils.toArray<HTMLElement>(
        document.querySelectorAll<HTMLElement>("[data-nav-reveal]"),
      );

      /* --- Počiatočné stavy ------------------------------------------------ */
      gsap.set(card, {
        left: "50%",
        top: "50%",
        xPercent: -50,
        yPercent: -50,
        width: "64vw",
        height: "48vh",
        borderRadius: 44,
        opacity: 0,
        rotateX: 14,
        transformPerspective: 1600,
        y: () => window.innerHeight * 0.85,
      });
      gsap.set(cardInner, { opacity: 0, scale: 0.94 });
      gsap.set(cardCopy, { opacity: 0, y: 34, filter: "blur(10px)" });
      gsap.set(phoneWrap, { opacity: 0, y: 70, transformPerspective: 1200 });
      gsap.set(badges, { opacity: 0, scale: 0.78 });
      gsap.set(bubbles, { opacity: 0, y: 16, scale: 0.94 });
      gsap.set(widgets, { opacity: 0, y: 14 });
      gsap.set(ringArc, { strokeDashoffset: RING_CIRCUMFERENCE });
      gsap.set(cta, { opacity: 0, y: 48, filter: "blur(16px)", pointerEvents: "none" });
      gsap.set(ctaItems, { opacity: 0, y: 26 });
      // Nav je skrytá až kým nedobehne intro text (reveal je na intro timeline).
      gsap.set(navGroups, { opacity: 0, y: -14, pointerEvents: "none" });

      /* --- Intro reveal (beží na load, nezávisle od scrollu) ----------------
         Presne dvojdielny reveal z predlohy:
           1. riadok — autoAlpha + y + scale + blur + rotationX, expo.out 1.8 s
           2. riadok — clip-path wipe zľava doprava, power4.inOut 1.4 s,
              prekrytý o 1 s, takže sa „píše" ešte kým prvý riadok dosadá.
         Počiatočné stavy sú cez `gsap.set` a tweeny sú `.to()` (teda
         `immediateRender: false`) — nič ich nemôže prekresliť späť na štart. */
      gsap.set(introTrack, {
        autoAlpha: 0,
        y: 60,
        scale: 0.85,
        filter: "blur(20px)",
        rotationX: -20,
      });
      gsap.set(introDays, { autoAlpha: 1, clipPath: "inset(0 100% 0 0)" });
      gsap.set(introSub, { autoAlpha: 0, y: 22, filter: "blur(10px)" });
      gsap.set(scrollHint, { autoAlpha: 0, y: 12 });

      const introTl = gsap.timeline({ delay: 0.3 });

      introTl
        .to(introTrack, {
          duration: 1.8,
          autoAlpha: 1,
          y: 0,
          scale: 1,
          filter: "blur(0px)",
          rotationX: 0,
          ease: "expo.out",
        })
        .to(
          introDays,
          { duration: 1.4, clipPath: "inset(0 0% 0 0)", ease: "power4.inOut" },
          "-=1.0",
        )
        // Od tohto miesta sú pozície absolútne, aby ich nič vyššie neposúvalo.
        .to(
          introSub,
          { autoAlpha: 1, y: 0, filter: "blur(0px)", duration: 0.9, ease: "power3.out" },
          1.5,
        )
        // Navigácia + Sign in / Get Started sa objavia až keď text dosadne.
        .to(
          navGroups,
          { opacity: 1, y: 0, duration: 0.7, stagger: 0.09, ease: "power2.out" },
          1.95,
        )
        .set(navGroups, { pointerEvents: "auto" })
        .to(
          scrollHint,
          { autoAlpha: 1, y: 0, duration: 0.7, ease: "power2.out" },
          2.35,
        );

      /* --- Pinnutá scroll scéna (scrub) ------------------------------------
         Tempo: každý beat dostane scroll úmerný tomu, koľko sa v ňom vizuálne
         deje. Prázdne `.to({}, …)` držania sú zrezané na krátke nádychy
         (0,15–0,25 jednotky), aby scroll nikde „nezomrel".
         Mapa beatov je v komentároch nižšie.

         POZOR — prečo tu NIE JE `invalidateOnRefresh`:
         ScrollTrigger refreshuje na load, pri načítaní fontu aj pri každom
         resize (v Safari to spustí už len schovanie adresného riadku).
         S `invalidateOnRefresh` sa timeline invaliduje a prekreslí na t=0,
         čím prepíše `intro` naspäť na štartovacie hodnoty — a keďže intro
         reveal v tej chvíli ešte beží, text viditeľne cukne dozadu.
         Funkčné `end: () => …` sa pritom prepočíta pri každom refreshi aj bez
         `invalidateOnRefresh`, takže responzívna dĺžka scény ostáva. */
      const counter = { value: 0 };

      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: scene,
          start: "top top",
          end: () => `+=${sceneScroll()}`,
          pin: true,
          scrub: 0.8,
          anticipatePin: 1,
          // Keby používateľ zascrolloval ešte počas intra, dobehne okamžite —
          // takto sa scroll timeline a intro nikdy neprekrývajú.
          // Prah je na `scroll()`, nie na `progress`: `start` vychádza aj -0.001,
          // takže progress je hore nenulový (~3e-7) a `> 0` by intro zabilo hneď
          // pri prvom update.
          onUpdate: (self) => {
            if (self.scroll() > 8 && introTl.progress() < 1) introTl.progress(1);
          },
        },
      });

      tl
        /* Beat 1 — intro odchádza (0.00 → 0.95)
           `immediateRender: false` na oboch tweenoch, ktoré sa dotýkajú intra:
           vytvorenie/refresh scroll timeline nesmie zapísať ich štartovací
           stav cez prebiehajúci intro reveal. */
        .to(
          intro,
          {
            opacity: 0,
            y: -84,
            filter: "blur(12px)",
            duration: 0.95,
            immediateRender: false,
          },
          0,
        )
        .to(scrollHint, { opacity: 0, duration: 0.3, immediateRender: false }, 0)
        .to(halo, { scale: 1.3, opacity: 0.8, duration: 2.2 }, 0)

        /* Beat 2 — karta priletí zdola (0.55 → 2.05) */
        .to(card, { y: 0, opacity: 1, rotateX: 0, duration: 1.5, ease: "power3.out" }, 0.55)

        /* Beat 3 — roztiahne sa na celú obrazovku (2.05 → 3.15) */
        .to(
          card,
          {
            width: "100vw",
            height: "100vh",
            borderRadius: 0,
            duration: 1.1,
            ease: "power2.inOut",
          },
          2.05,
        )

        /* Beat 4 — obsah karty sa odhalí (2.85 → 4.04) */
        .to(cardInner, { opacity: 1, scale: 1, duration: 0.8 }, 2.85)
        .to(
          cardCopy,
          { opacity: 1, y: 0, filter: "blur(0px)", stagger: 0.13, duration: 0.65 },
          3.0,
        )
        .to(phoneWrap, { opacity: 1, y: 0, duration: 0.95, ease: "power2.out" }, 2.95)

        /* Beat 5 — konverzácia v telefóne (3.95 → 5.04) */
        .to(bubbles, { opacity: 1, y: 0, scale: 1, stagger: 0.16, duration: 0.45 }, 3.95)

        /* Beat 6 — ring counter, widgety, badges (4.85 → 6.18) */
        .to(
          ringArc,
          {
            strokeDashoffset: RING_CIRCUMFERENCE * (1 - RING_PROGRESS),
            duration: 1.05,
            ease: "power1.inOut",
          },
          4.85,
        )
        .to(
          counter,
          {
            value: RING_TARGET,
            duration: 1.05,
            ease: "power1.inOut",
            onUpdate: () => {
              ringValue.textContent = String(Math.round(counter.value));
            },
          },
          4.85,
        )
        .to(widgets, { opacity: 1, y: 0, stagger: 0.25, duration: 0.45 }, 5.15)
        .to(badges, { opacity: 1, scale: 1, stagger: 0.18, duration: 0.45, ease: "back.out(2)" }, 5.55)

        /* nádych 6.18 → 6.35 */

        /* Beat 7 — pullback na 85vw × 85vh (6.35 → 7.40) */
        .to(
          card,
          {
            width: "85vw",
            height: "85vh",
            borderRadius: 32,
            duration: 1.05,
            ease: "power2.inOut",
          },
          6.35,
        )

        /* nádych 7.40 → 7.55 */

        /* Beat 8 — karta odplávala, prichádza CTA (7.55 → 9.10) */
        .to(card, { y: -140, scale: 0.9, opacity: 0, duration: 0.95, ease: "power2.in" }, 7.55)
        .set(cta, { pointerEvents: "auto" }, 7.8)
        .to(cta, { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.85 }, 7.85)
        .to(ctaItems, { opacity: 1, y: 0, stagger: 0.15, duration: 0.55 }, 8.1)

        /* Beat 9 — krátke doznenie, nech CTA nezmizne hneď s koncom pinu */
        .to({}, { duration: 0.25 }, 9.1);

      /* --- Mouse paralaxa telefónu (rAF lerp, ±12°) ------------------------- */
      const target = { rx: 0, ry: 0 };
      const current = { rx: 0, ry: 0 };
      let rafId = 0;
      let pointerFine = window.matchMedia("(pointer: fine)").matches;

      const onMove = (event: MouseEvent) => {
        if (!pointerFine) return;
        const nx = (event.clientX / window.innerWidth) * 2 - 1;
        const ny = (event.clientY / window.innerHeight) * 2 - 1;
        target.ry = gsap.utils.clamp(-12, 12, nx * 12);
        target.rx = gsap.utils.clamp(-12, 12, -ny * 12);
      };

      const tick = () => {
        current.rx += (target.rx - current.rx) * 0.075;
        current.ry += (target.ry - current.ry) * 0.075;
        gsap.set(phoneWrap, { rotationX: current.rx, rotationY: current.ry });
        rafId = requestAnimationFrame(tick);
      };

      if (pointerFine) {
        window.addEventListener("mousemove", onMove, { passive: true });
        rafId = requestAnimationFrame(tick);
      }

      const pointerQuery = window.matchMedia("(pointer: fine)");
      const onPointerChange = (e: MediaQueryListEvent) => {
        pointerFine = e.matches;
      };
      pointerQuery.addEventListener("change", onPointerChange);

      return () => {
        window.removeEventListener("mousemove", onMove);
        pointerQuery.removeEventListener("change", onPointerChange);
        if (rafId) cancelAnimationFrame(rafId);
      };
    }, sceneRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={sceneRef} className="relative">
      <section
        aria-label="Telepipe — product story"
        className="relative h-[100svh] w-full overflow-hidden bg-black"
      >
        {/* Pozadie */}
        <div className="pointer-events-none absolute inset-0 lp-grid" />
        <div
          data-halo
          className="lp-halo pointer-events-none absolute left-1/2 top-1/2 h-[820px] w-[820px] -translate-x-1/2 -translate-y-1/2 opacity-50"
        />
        <div className="film-grain-fixed" />

        {/* --- Scéna 1: intro tagline ------------------------------------- */}
        <div
          data-intro
          className="absolute inset-0 z-20 flex flex-col items-center justify-center px-6 text-center"
        >
          <h1 className="lp-intro-3d max-w-[68rem] text-[clamp(1.95rem,5.4vw,4.4rem)] font-semibold leading-[1.04] lp-tight">
            <span data-intro-track className="block lp-text-dim">
              Your models never sleep.
            </span>
            {/* Wipe sedí na obale (inline-block ⇒ box lícuje s textom), gradient
                na vnútornom spane. V Safari sa `clip-path` a `background-clip:
                text` na tom istom elemente bijú — takto sa nestretnú. */}
            <span data-intro-days className="lp-wipe inline-block">
              <span className="lp-text-bright inline-block">
                Chats become subscribers.
              </span>
            </span>
          </h1>

          <p
            data-intro-sub
            className="mt-7 max-w-xl text-[clamp(0.95rem,1.7vw,1.15rem)] leading-relaxed text-white/45"
          >
            Telepipe runs your Telegram DMs on autopilot — human-sounding replies,
            real voice messages, and the right link at the perfect moment.
          </p>

          <div
            data-scroll-hint
            className="absolute bottom-10 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-white/30"
          >
            Scroll
            <span className="relative h-9 w-[1px] overflow-hidden bg-white/12">
              <span className="lp-scroll-tick absolute inset-x-0 top-0 h-3 bg-white/80" />
            </span>
          </div>
        </div>

        {/* --- Scéna 2: letiaca karta -------------------------------------
            Karta a jej sheen sú zámerne neutrálne — jediný farebný prvok na
            celej stránke je telefón vo vnútri, a ten nesmie mať konkurenciu. */}
        <div data-card className="lp-depth-card absolute z-30 overflow-hidden opacity-0">
          <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
          <div className="lp-halo pointer-events-none absolute -left-40 top-1/3 h-[420px] w-[420px] opacity-40" />

          <div
            data-card-inner
            className="relative flex h-full w-full items-center justify-center overflow-hidden px-6"
          >
            {/* Mobile scale wrapper — presne ako v predlohe */}
            <div className="flex w-full max-w-6xl scale-[0.56] flex-col items-center justify-center gap-8 sm:scale-[0.72] lg:scale-[0.88] lg:flex-row lg:gap-16">
              {/* Ľavý stĺpec — brand + copy */}
              <div className="max-w-md text-center lg:text-left">
                <p
                  data-card-copy
                  className="text-[clamp(2.6rem,5vw,4.2rem)] font-extrabold leading-none tracking-[-0.045em] lp-text-bright"
                >
                  TELEPIPE
                </p>
                <h2
                  data-card-copy
                  className="mt-5 text-[clamp(1.5rem,2.6vw,2.3rem)] font-semibold leading-tight text-white lp-tight"
                >
                  One agent. Every fan.
                  <br />
                  Answered in seconds.
                </h2>
                <p
                  data-card-copy
                  className="mt-4 text-[15px] leading-relaxed text-white/45"
                >
                  Your model&apos;s persona, tone and boundaries — learned once, then
                  applied to every conversation, day and night.
                </p>

                <ul
                  data-card-copy
                  className="mt-7 flex flex-wrap justify-center gap-2.5 lg:justify-start"
                >
                  {[
                    "Human-sounding replies",
                    "Real voice notes",
                    "Funnel-aware links",
                  ].map((item) => (
                    <li
                      key={item}
                      className="lp-glass rounded-full px-3.5 py-1.5 text-[11.5px] font-medium text-white/70"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Pravý stĺpec — telefón + floating badges.
                  Telefón aj badges ostávajú zlaté (Marek: „nech je telefón jediná
                  farebná vec, je to showcase"). */}
              <div className="relative">
                <div data-phone-wrap className="relative">
                  <PhoneMockup animated />
                </div>

                {/* `data-badge` animuje GSAP (opacity + scale), plávanie je na
                    vnorenom elemente — CSS animácia by inline transform prebila. */}
                <div data-badge className="absolute -left-14 -top-11 hidden sm:block">
                  <div className="widget-depth widget-depth-gold animate-float-slow flex items-center gap-2.5 rounded-2xl px-4 py-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(212,175,55,0.14)]">
                      <Clock className="h-4 w-4 text-[var(--gold)]" />
                    </span>
                    <span className="text-left">
                      <span className="block text-[13px] font-semibold text-white">
                        24/7 auto-replies
                      </span>
                      <span className="block text-[10.5px] text-white/45">
                        never a missed DM
                      </span>
                    </span>
                  </div>
                </div>

                <div data-badge className="absolute -bottom-12 -right-24 hidden sm:block">
                  <div
                    className="widget-depth widget-depth-gold animate-float-slow flex items-center gap-2.5 rounded-2xl px-4 py-3"
                    style={{ animationDelay: "1.6s" }}
                  >
                    <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(212,175,55,0.14)]">
                      <TrendingUp className="h-4 w-4 text-[var(--gold)]" />
                    </span>
                    <span className="text-left">
                      <span className="block text-[13px] font-semibold text-[var(--gold-light)]">
                        +38 subscribers
                      </span>
                      <span className="block text-[10.5px] text-white/45">this week</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* --- Scéna 3: CTA ------------------------------------------------ */}
        <div
          data-cta
          className="absolute inset-0 z-40 flex flex-col items-center justify-center px-6 text-center opacity-0"
        >
          <h2
            data-cta-item
            className="max-w-4xl text-[clamp(2.2rem,6.4vw,4.8rem)] font-semibold leading-[1.05] lp-tight"
          >
            <span className="lp-text-bright">Put your DMs on autopilot.</span>
          </h2>
          <p data-cta-item className="mt-6 max-w-xl text-base text-white/45">
            Connect Telegram, describe your model, and let Telepipe turn every
            conversation into revenue.
          </p>
          <div
            data-cta-item
            className="mt-11 flex flex-col items-center gap-3 sm:flex-row"
          >
            <Link href="/register" className="lp-btn lp-btn-primary h-12 px-7 text-[14.5px]">
              Get Started
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/login" className="lp-btn lp-btn-ghost h-12 px-7 text-[14.5px]">
              Sign In
            </Link>
          </div>
          <p data-cta-item className="mt-8 text-xs text-white/30">
            No card required · Usage-based credits · Cancel anytime
          </p>
        </div>
      </section>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Statická verzia pre prefers-reduced-motion                                 */
/* -------------------------------------------------------------------------- */

function StaticHero() {
  return (
    <section className="relative overflow-hidden bg-black px-6 pb-24 pt-36">
      <div className="pointer-events-none absolute inset-0 lp-grid" />
      <div className="lp-halo pointer-events-none absolute left-1/2 top-40 h-[620px] w-[620px] -translate-x-1/2 opacity-40" />

      <div className="relative mx-auto max-w-5xl text-center">
        <h1 className="text-[clamp(2.2rem,6.4vw,4.6rem)] font-semibold leading-[1.05] lp-tight">
          <span className="block lp-text-dim">Your models never sleep.</span>
          <span className="block lp-text-bright">Chats become subscribers.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-white/45">
          Telepipe runs your Telegram DMs on autopilot — human-sounding replies,
          real voice messages, and the right link at the perfect moment.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href="/register" className="lp-btn lp-btn-primary h-12 px-7 text-[14.5px]">
            Get Started
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link href="/login" className="lp-btn lp-btn-ghost h-12 px-7 text-[14.5px]">
            Sign In
          </Link>
        </div>
      </div>

      <div className="lp-depth-card relative mx-auto mt-20 max-w-6xl overflow-hidden rounded-[32px] px-8 py-14">
        <div className="pointer-events-none absolute inset-0 lp-grid-fine" />
        <div className="relative flex flex-col items-center gap-12 lg:flex-row lg:justify-between">
          <div className="max-w-md text-center lg:text-left">
            <p className="text-[clamp(2.2rem,4.4vw,3.6rem)] font-extrabold leading-none tracking-[-0.045em] lp-text-bright">
              TELEPIPE
            </p>
            <h2 className="mt-5 text-2xl font-semibold leading-tight text-white">
              One agent. Every fan. Answered in seconds.
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-white/45">
              Your model&apos;s persona, tone and boundaries — learned once, then
              applied to every conversation, day and night.
            </p>
            <ul className="mt-7 flex flex-wrap justify-center gap-2.5 lg:justify-start">
              {["24/7 auto-replies", "Real voice notes", "+38 subscribers this week"].map(
                (item) => (
                  <li
                    key={item}
                    className="lp-glass rounded-full px-3.5 py-1.5 text-[11.5px] font-medium text-white/70"
                  >
                    {item}
                  </li>
                ),
              )}
            </ul>
          </div>
          <PhoneMockup />
        </div>
      </div>
    </section>
  );
}
