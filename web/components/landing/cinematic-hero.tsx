"use client";

import { useEffect, useLayoutEffect, useRef } from "react";
import Link from "next/link";
import { ArrowRight, Clock, Sparkles, TrendingUp } from "lucide-react";
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

/** Dĺžka pinnutého scrollu v px — priamo z predlohy CinematicHero. */
const SCENE_SCROLL = 7000;

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
      const introLines = qa("[data-intro-line]");
      const introKicker = q("[data-intro-kicker]")!;
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

      /* --- Pinnutá scroll scéna (scrub) ------------------------------------ */
      const counter = { value: 0 };

      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: scene,
          start: "top top",
          end: `+=${SCENE_SCROLL}`,
          pin: true,
          scrub: 1,
          anticipatePin: 1,
          invalidateOnRefresh: true,
        },
      });

      tl
        // 1) Intro odchádza
        .to(intro, { opacity: 0, y: -90, filter: "blur(12px)", duration: 1.1 }, 0)
        .to(scrollHint, { opacity: 0, duration: 0.4 }, 0)
        .to(halo, { scale: 1.35, opacity: 0.85, duration: 2.4 }, 0)

        // 2) Karta priletí zdola
        .to(card, { y: 0, opacity: 1, rotateX: 0, duration: 1.7, ease: "power3.out" }, 0.6)

        // 3) Roztiahne sa na celú obrazovku
        .to(
          card,
          { width: "100vw", height: "100vh", borderRadius: 0, duration: 1.2, ease: "power2.inOut" },
          2.3,
        )

        // 4) Obsah karty sa odhalí
        .to(cardInner, { opacity: 1, scale: 1, duration: 0.9 }, 2.7)
        .to(cardCopy, { opacity: 1, y: 0, filter: "blur(0px)", stagger: 0.14, duration: 0.7 }, 2.9)
        .to(phoneWrap, { opacity: 1, y: 0, duration: 1.1, ease: "power2.out" }, 2.85)

        // 5) Príbeh v telefóne — bubliny, ring counter, widgety
        .to(bubbles, { opacity: 1, y: 0, scale: 1, stagger: 0.17, duration: 0.5 }, 3.5)
        .to(
          ringArc,
          {
            strokeDashoffset: RING_CIRCUMFERENCE * (1 - RING_PROGRESS),
            duration: 1.3,
            ease: "power1.inOut",
          },
          4.3,
        )
        .to(
          counter,
          {
            value: RING_TARGET,
            duration: 1.3,
            ease: "power1.inOut",
            onUpdate: () => {
              ringValue.textContent = String(Math.round(counter.value));
            },
          },
          4.3,
        )
        .to(widgets, { opacity: 1, y: 0, stagger: 0.28, duration: 0.5 }, 4.7)
        .to(badges, { opacity: 1, scale: 1, stagger: 0.2, duration: 0.5, ease: "back.out(2)" }, 5.0)

        // 6) Pullback na 85vw × 85vh so zaoblením
        .to(
          card,
          { width: "85vw", height: "85vh", borderRadius: 36, duration: 1.3, ease: "power2.inOut" },
          6.4,
        )

        // 7) Karta odplávala, prichádza CTA
        .to(card, { y: -140, scale: 0.9, opacity: 0, duration: 1.1, ease: "power2.in" }, 7.9)
        .set(cta, { pointerEvents: "auto" }, 8.2)
        .to(cta, { opacity: 1, y: 0, filter: "blur(0px)", duration: 1.0 }, 8.25)
        .to(ctaItems, { opacity: 1, y: 0, stagger: 0.16, duration: 0.6 }, 8.5)
        .to({}, { duration: 0.5 }, 9.4); // doznenie na konci pinu

      /* --- Intro reveal (blur + clip-path, stagger) ------------------------- */
      gsap.from(introKicker, {
        opacity: 0,
        y: 18,
        duration: 0.8,
        ease: "power3.out",
        delay: 0.1,
      });
      gsap.from(introLines, {
        opacity: 0,
        y: 44,
        filter: "blur(16px)",
        clipPath: "inset(108% 0% -8% 0%)",
        duration: 1.25,
        stagger: 0.16,
        ease: "power4.out",
        delay: 0.25,
      });
      gsap.from(introSub, {
        opacity: 0,
        y: 26,
        filter: "blur(10px)",
        duration: 1,
        ease: "power3.out",
        delay: 0.85,
      });
      gsap.from(scrollHint, {
        opacity: 0,
        y: 14,
        duration: 0.8,
        ease: "power2.out",
        delay: 1.4,
      });

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
        <div className="pointer-events-none absolute inset-0 bg-grid" />
        <div
          data-halo
          className="gold-halo pointer-events-none absolute left-1/2 top-1/2 h-[820px] w-[820px] -translate-x-1/2 -translate-y-1/2 opacity-50"
        />
        <div className="film-grain-fixed" />

        {/* --- Scéna 1: intro tagline ------------------------------------- */}
        <div
          data-intro
          className="absolute inset-0 z-20 flex flex-col items-center justify-center px-6 text-center"
        >
          <p
            data-intro-kicker
            className="mb-7 inline-flex items-center gap-2 rounded-full border border-[rgba(212,175,55,0.28)] bg-[rgba(212,175,55,0.06)] px-4 py-1.5 text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--gold-light)]"
          >
            <Sparkles className="h-3 w-3" />
            AI chat agents for creators
          </p>

          <h1 className="max-w-[68rem] text-[clamp(1.95rem,5.4vw,4.4rem)] font-semibold leading-[1.04] text-balance-tight">
            <span data-intro-line className="block text-gradient-white">
              Your models never sleep.
            </span>
            <span data-intro-line className="block text-gradient-gold">
              Chats become subscribers.
            </span>
          </h1>

          <p
            data-intro-sub
            className="mt-7 max-w-xl text-[clamp(0.95rem,1.7vw,1.15rem)] leading-relaxed text-white/50"
          >
            Telepipe runs your Telegram DMs on autopilot — human-sounding replies,
            real voice messages, and the right link at the perfect moment.
          </p>

          <div
            data-scroll-hint
            className="absolute bottom-10 left-1/2 flex -translate-x-1/2 flex-col items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-white/30"
          >
            Scroll
            <span className="relative h-9 w-[1px] overflow-hidden bg-white/15">
              <span className="absolute inset-x-0 top-0 h-3 animate-pulse-gold bg-[var(--gold)]" />
            </span>
          </div>
        </div>

        {/* --- Scéna 2: letiaca karta ------------------------------------- */}
        <div
          data-card
          className="premium-depth-card absolute z-30 overflow-hidden opacity-0"
        >
          <div className="pointer-events-none absolute inset-0 bg-grid-fine" />
          <div className="pointer-events-none absolute -left-40 top-1/3 h-[420px] w-[420px] gold-halo opacity-40" />

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
                  className="text-[clamp(2.6rem,5vw,4.2rem)] font-extrabold leading-none tracking-[-0.045em] text-gradient-gold"
                >
                  TELEPIPE
                </p>
                <h2
                  data-card-copy
                  className="mt-5 text-[clamp(1.5rem,2.6vw,2.3rem)] font-semibold leading-tight text-white text-balance-tight"
                >
                  One agent. Every fan.
                  <br />
                  Answered in seconds.
                </h2>
                <p
                  data-card-copy
                  className="mt-4 text-[15px] leading-relaxed text-white/50"
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
                      className="widget-depth rounded-full px-3.5 py-1.5 text-[11.5px] font-medium text-white/70"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Pravý stĺpec — telefón + floating badges */}
              <div className="relative">
                <div data-phone-wrap className="relative">
                  <PhoneMockup animated />
                </div>

                <div
                  data-badge
                  className="widget-depth widget-depth-gold absolute -left-14 -top-11 hidden animate-float-slow items-center gap-2.5 rounded-2xl px-4 py-3 sm:flex"
                >
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

                <div
                  data-badge
                  className="widget-depth widget-depth-gold absolute -bottom-12 -right-24 hidden animate-float-slow items-center gap-2.5 rounded-2xl px-4 py-3 sm:flex"
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

        {/* --- Scéna 3: CTA ------------------------------------------------ */}
        <div
          data-cta
          className="absolute inset-0 z-40 flex flex-col items-center justify-center px-6 text-center opacity-0"
        >
          <h2
            data-cta-item
            className="max-w-4xl text-[clamp(2.2rem,6.4vw,4.8rem)] font-semibold leading-[1.05] text-balance-tight"
          >
            <span className="text-gradient-gold">Put your DMs on autopilot.</span>
          </h2>
          <p data-cta-item className="mt-6 max-w-xl text-base text-white/50">
            Connect Telegram, describe your model, and let Telepipe turn every
            conversation into revenue.
          </p>
          <div
            data-cta-item
            className="mt-11 flex flex-col items-center gap-4 sm:flex-row"
          >
            <Link href="/register" className="btn-modern-light h-14 px-9 text-[15px]">
              Get Started
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/login" className="btn-modern-dark h-14 px-9 text-[15px]">
              Sign In
            </Link>
          </div>
          <p data-cta-item className="mt-7 text-xs text-white/30">
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
      <div className="pointer-events-none absolute inset-0 bg-grid" />
      <div className="gold-halo pointer-events-none absolute left-1/2 top-40 h-[620px] w-[620px] -translate-x-1/2 opacity-40" />

      <div className="relative mx-auto max-w-5xl text-center">
        <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-[rgba(212,175,55,0.28)] bg-[rgba(212,175,55,0.06)] px-4 py-1.5 text-[11px] font-medium uppercase tracking-[0.22em] text-[var(--gold-light)]">
          <Sparkles className="h-3 w-3" />
          AI chat agents for creators
        </p>
        <h1 className="text-[clamp(2.2rem,6.4vw,4.6rem)] font-semibold leading-[1.05] text-balance-tight">
          <span className="block text-gradient-white">Your models never sleep.</span>
          <span className="block text-gradient-gold">Chats become subscribers.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-white/50">
          Telepipe runs your Telegram DMs on autopilot — human-sounding replies,
          real voice messages, and the right link at the perfect moment.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
          <Link href="/register" className="btn-modern-light h-14 px-9 text-[15px]">
            Get Started
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link href="/login" className="btn-modern-dark h-14 px-9 text-[15px]">
            Sign In
          </Link>
        </div>
      </div>

      <div className="premium-depth-card relative mx-auto mt-20 max-w-6xl overflow-hidden rounded-[36px] px-8 py-14">
        <div className="pointer-events-none absolute inset-0 bg-grid-fine" />
        <div className="relative flex flex-col items-center gap-12 lg:flex-row lg:justify-between">
          <div className="max-w-md text-center lg:text-left">
            <p className="text-[clamp(2.2rem,4.4vw,3.6rem)] font-extrabold leading-none tracking-[-0.045em] text-gradient-gold">
              TELEPIPE
            </p>
            <h2 className="mt-5 text-2xl font-semibold leading-tight text-white">
              One agent. Every fan. Answered in seconds.
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-white/50">
              Your model&apos;s persona, tone and boundaries — learned once, then
              applied to every conversation, day and night.
            </p>
            <ul className="mt-7 flex flex-wrap justify-center gap-2.5 lg:justify-start">
              {["24/7 auto-replies", "Real voice notes", "+38 subscribers this week"].map(
                (item) => (
                  <li
                    key={item}
                    className="widget-depth rounded-full px-3.5 py-1.5 text-[11.5px] font-medium text-white/70"
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
