"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { gsap } from "gsap";

import { cn } from "@/lib/utils";

// useLayoutEffect na serveri varuje — na klientovi ho chceme (žiadne bliknutie)
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

/* -------------------------------------------------------------------------- */
/*  Clip sady                                                                  */
/* -------------------------------------------------------------------------- */

type Shape = { x: number; y: number; w: number; h: number; r: number };

const VIEW = 600;

/** Zvislé lamely — „roleta". */
function bars(count: number, gap = 5, r = 10): Shape[] {
  const step = VIEW / count;
  return Array.from({ length: count }, (_, i) => ({
    x: i * step + gap / 2,
    y: 0,
    w: step - gap,
    h: VIEW,
    r,
  }));
}

/** Pravidelná mriežka dlaždíc. */
function grid(cols: number, rows: number, gap = 6, r = 18): Shape[] {
  const cw = VIEW / cols;
  const ch = VIEW / rows;
  const out: Shape[] = [];
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      out.push({
        x: col * cw + gap / 2,
        y: row * ch + gap / 2,
        w: cw - gap,
        h: ch - gap,
        r,
      });
    }
  }
  return out;
}

/** Preložené tehly — striedavo delené riadky. */
function bricks(rows = 5, gap = 6, r = 14): Shape[] {
  const rh = VIEW / rows;
  const out: Shape[] = [];
  for (let row = 0; row < rows; row += 1) {
    const cuts = row % 2 ? [0, 0.34, 0.7, 1] : [0, 0.58, 1];
    for (let i = 0; i < cuts.length - 1; i += 1) {
      const x0 = cuts[i] * VIEW;
      const x1 = cuts[i + 1] * VIEW;
      out.push({
        x: x0 + gap / 2,
        y: row * rh + gap / 2,
        w: x1 - x0 - gap,
        h: rh - gap,
        r,
      });
    }
  }
  return out;
}

export type Step = {
  title: string;
  body: string;
  /** Placeholder mockup v `public/how-it-works/` — Marek ich neskôr vymení. */
  image: string;
  alt: string;
};

const CLIP_SETS: Shape[][] = [bars(7), grid(4, 4), bricks()];

/* -------------------------------------------------------------------------- */
/*  Interaktor                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * Zoznam krokov vľavo, obrázok vpravo odhalený cez animovaný `clipPath`.
 *
 * Správanie je prevzaté z predlohy: každá položka má vlastnú sadu tvarov, tá
 * sa pri prepnutí najprv „zloží" dnu (`expo.in`, náhodný stagger), vymení sa
 * obrázok, nová sada sa „rozloží" (`expo.out`) a potom nekonečne dýcha
 * (`sine.inOut`, yoyo).
 *
 * Prístupnosť: predloha reagovala len na hover, čo je pre klávesnicu aj dotyk
 * slepá ulička. Položky sú preto `<button>` a prepínajú sa na `mouseenter`,
 * `focus` **aj** `click`. Pri `prefers-reduced-motion` sa nič neanimuje —
 * clip sada sa vykreslí staticky a obrázok sa len vymení.
 */
export function StepsInteractor({ steps }: { steps: Step[] }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const visualRef = useRef<HTMLDivElement>(null);
  const clipId = "hiw-clip";

  // `active` = čo si používateľ vybral, `shown` = čo je práve vykreslené.
  // Rozdiel drží out-animáciu: prekreslíme až keď sa stará sada zloží.
  const [active, setActive] = useState(0);
  const [shown, setShown] = useState(0);
  const [reduced, setReduced] = useState(false);

  const breatheRef = useRef<gsap.core.Tween | null>(null);
  const outRef = useRef<gsap.core.Tween | null>(null);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  /* --- nová sada prilieta ------------------------------------------------ */
  useIsomorphicLayoutEffect(() => {
    const svg = svgRef.current;
    if (!svg || reduced) return;

    const shapes = gsap.utils.toArray<SVGRectElement>(
      svg.querySelectorAll("[data-clip-shape]"),
    );
    if (!shapes.length) return;

    const ctx = gsap.context(() => {
      shapes.forEach((shape) => {
        // Tvary sa škálujú od vlastného stredu, nie od začiatku súradníc.
        const cx = Number(shape.getAttribute("x")) + Number(shape.getAttribute("width")) / 2;
        const cy = Number(shape.getAttribute("y")) + Number(shape.getAttribute("height")) / 2;
        gsap.set(shape, { svgOrigin: `${cx} ${cy}` });
      });

      gsap.fromTo(
        shapes,
        { scale: 0 },
        {
          scale: 1,
          duration: 1.15,
          ease: "expo.out",
          stagger: { each: 0.045, from: "random" },
          onComplete: () => {
            breatheRef.current = gsap.to(shapes, {
              scale: 1.035,
              duration: 2.4,
              ease: "sine.inOut",
              yoyo: true,
              repeat: -1,
              stagger: { each: 0.13, from: "random" },
            });
          },
        },
      );

      gsap.fromTo(
        svg.querySelector("[data-clip-image]"),
        { opacity: 0 },
        { opacity: 1, duration: 0.85, ease: "power2.out" },
      );
    }, svg);

    return () => {
      breatheRef.current?.kill();
      breatheRef.current = null;
      ctx.revert();
    };
  }, [shown, reduced]);

  /* --- stará sada odchádza ----------------------------------------------- */
  useEffect(() => {
    if (active === shown) return;

    const svg = svgRef.current;
    if (!svg || reduced) {
      setShown(active);
      return;
    }

    const shapes = gsap.utils.toArray<SVGRectElement>(
      svg.querySelectorAll("[data-clip-shape]"),
    );
    if (!shapes.length) {
      setShown(active);
      return;
    }

    breatheRef.current?.kill();
    breatheRef.current = null;
    outRef.current?.kill();
    outRef.current = gsap.to(shapes, {
      scale: 0,
      duration: 0.5,
      ease: "expo.in",
      stagger: { each: 0.03, from: "random" },
      onComplete: () => setShown(active),
    });

    return () => {
      outRef.current?.kill();
    };
  }, [active, shown, reduced]);

  const step = steps[shown];
  const shapes = CLIP_SETS[shown % CLIP_SETS.length];

  /**
   * Na mobile je vizuál nad zoznamom, takže po klepnutí na krok by výsledok
   * ostal mimo obrazovky. Sticky sa tu použiť nedá (sticky grid item je
   * ohraničený vlastnou grid area), preto ho pri klepnutí doscrollujeme.
   * Na desktope sa nedeje nič — vizuál je vedľa a je stále vidieť.
   */
  const revealVisualOnMobile = () => {
    if (!window.matchMedia("(max-width: 1023px)").matches) return;
    visualRef.current?.scrollIntoView({
      block: "center",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  };

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-16">
      {/* Vizuál — sticky, aby pri klepnutí na krok nižšie ostal na očiach */}
      <div
        ref={visualRef}
        className="order-first self-start scroll-mt-24 lg:order-last lg:sticky lg:top-[104px]"
      >
        <div className="lp-panel relative overflow-hidden rounded-[24px] p-2.5">
          <div
            aria-hidden
            className="lp-halo pointer-events-none absolute -right-24 -top-24 h-[360px] w-[360px] opacity-40"
          />
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW} ${VIEW}`}
            role="img"
            aria-label={step.alt}
            className="relative block aspect-square w-full rounded-[16px]"
          >
            <defs>
              <clipPath id={clipId} clipPathUnits="userSpaceOnUse">
                {shapes.map((shape, i) => (
                  <rect
                    key={`${shown}-${i}`}
                    data-clip-shape
                    x={shape.x}
                    y={shape.y}
                    width={shape.w}
                    height={shape.h}
                    rx={shape.r}
                  />
                ))}
              </clipPath>
            </defs>
            <image
              data-clip-image
              href={step.image}
              x={0}
              y={0}
              width={VIEW}
              height={VIEW}
              preserveAspectRatio="xMidYMid slice"
              clipPath={`url(#${clipId})`}
            />
          </svg>
        </div>
        <p className="mt-3 text-center text-[11px] text-white/20 lg:text-right">
          Interface preview — placeholder artwork
        </p>
      </div>

      {/* Zoznam krokov */}
      <ol className="flex flex-col justify-center gap-2">
        {steps.map((item, index) => {
          const current = index === active;
          return (
            <li key={item.title}>
              <button
                type="button"
                aria-current={current ? "step" : undefined}
                onMouseEnter={() => setActive(index)}
                onFocus={() => setActive(index)}
                onClick={() => {
                  setActive(index);
                  revealVisualOnMobile();
                }}
                className={cn(
                  "group flex w-full gap-5 rounded-[18px] border p-5 text-left transition-colors duration-300 sm:p-6",
                  current
                    ? "border-white/[0.14] bg-white/[0.04]"
                    : "border-transparent hover:border-white/[0.08] hover:bg-white/[0.02]",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 font-mono text-[12px] tabular-nums transition-colors duration-300",
                    current ? "text-white/70" : "text-white/25",
                  )}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="min-w-0">
                  <span
                    className={cn(
                      "block text-[17px] font-semibold transition-colors duration-300",
                      current ? "text-white" : "text-white/55",
                    )}
                  >
                    {item.title}
                  </span>
                  <span
                    className={cn(
                      "mt-2 block text-[14px] leading-relaxed transition-colors duration-300",
                      current ? "text-white/50" : "text-white/30",
                    )}
                  >
                    {item.body}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
