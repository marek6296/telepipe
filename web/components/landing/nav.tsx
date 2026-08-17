"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/features", label: "Features" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
];

/**
 * Fixná blur navigácia v štýle dashboardu — monochróm, zlatá len v logu.
 *
 * Dva varianty, jeden komponent (markup sa neduplikuje):
 *
 * - **cinematic** (`/`): prvky s `data-nav-reveal` štartujú skryté a odhalí ich
 *   intro timeline v `CinematicScene` (nie scroll timeline — objaví sa teda
 *   hneď po načítaní, až keď dosadne intro text). Pozadie je priehľadné, kým
 *   používateľ nezascrolluje. Pri `prefers-reduced-motion` GSAP nebeží vôbec
 *   a `.lp-nav-reveal` si viditeľnosť vynúti cez CSS v `landing.css`.
 * - **sticky** (podstránky): bežná hlavička — vždy viditeľná, vždy s hairline
 *   borderom a blurom, žiadny GSAP. Aktívna položka je zvýraznená.
 */
export function LandingNav() {
  const pathname = usePathname();
  const cinematic = pathname === "/";

  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Mobilné menu zatvára každá jeho položka vo svojom `onClick` — netreba naň
  // efekt na `pathname` (a ten by len spustil kaskádový render navyše).

  // Zamknúť scroll pod otvoreným mobilným menu
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  // Na `/` sú tieto atribúty háčik pre GSAP intro reveal; inde nesmú byť vôbec,
  // aby nav ostal viditeľný (a aby ho scéna po SPA prechode nehľadala).
  const revealAttr = cinematic ? { "data-nav-reveal": "" } : {};
  const revealClass = cinematic ? "lp-nav-reveal" : "";

  const solid = scrolled || !cinematic;

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-[80] transition-colors duration-300",
        solid
          ? "border-b border-white/[0.07] bg-black/60 backdrop-blur-xl supports-[backdrop-filter]:bg-black/45"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <nav className="mx-auto flex h-[68px] max-w-7xl items-center justify-between px-5 sm:px-8">
        <Link
          href="/"
          {...revealAttr}
          className={cn("flex items-center", revealClass)}
          aria-label="Telepipe home"
        >
          <Image
            src="/logo-white.png"
            alt="Telepipe"
            width={148}
            height={47}
            priority
            className="h-7 w-auto"
          />
        </Link>

        <ul
          {...revealAttr}
          className={cn("hidden items-center gap-8 md:flex", revealClass)}
        >
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative text-[13.5px] font-medium transition-colors",
                    active ? "text-white" : "text-white/55 hover:text-white",
                  )}
                >
                  {link.label}
                  {active && (
                    <span
                      aria-hidden
                      className="absolute -bottom-1.5 left-0 h-px w-full bg-white/45"
                    />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>

        <div
          {...revealAttr}
          className={cn("hidden items-center gap-2.5 md:flex", revealClass)}
        >
          <Link href="/login" className="lp-btn lp-btn-quiet h-9 px-3.5 text-[13.5px]">
            Sign in
          </Link>
          <Link href="/register" className="lp-btn lp-btn-primary h-9 px-4 text-[13.5px]">
            Get Started
          </Link>
        </div>

        <button
          type="button"
          {...revealAttr}
          onClick={() => setOpen((value) => !value)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          className={cn(
            "lp-hairline flex h-9 w-9 items-center justify-center rounded-lg text-white/75 transition-colors hover:text-white md:hidden",
            revealClass,
          )}
        >
          {open ? (
            <X className="h-4.5 w-4.5" strokeWidth={1.5} />
          ) : (
            <Menu className="h-4.5 w-4.5" strokeWidth={1.5} />
          )}
        </button>
      </nav>

      {/* Mobilné menu */}
      <div
        className={cn(
          "overflow-hidden border-t border-white/[0.06] bg-black/95 backdrop-blur-xl transition-[max-height,opacity] duration-300 md:hidden",
          open ? "max-h-[420px] opacity-100" : "max-h-0 opacity-0",
        )}
      >
        <ul className="space-y-1 px-5 py-5">
          {LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "block rounded-lg px-3 py-3 text-[15px] font-medium transition-colors hover:bg-white/[0.04] hover:text-white",
                    active ? "bg-white/[0.05] text-white" : "text-white/70",
                  )}
                >
                  {link.label}
                </Link>
              </li>
            );
          })}
          <li className="flex flex-col gap-2.5 pt-4">
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="lp-btn lp-btn-ghost h-11 w-full text-[14px]"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              onClick={() => setOpen(false)}
              className="lp-btn lp-btn-primary h-11 w-full text-[14px]"
            >
              Get Started
            </Link>
          </li>
        </ul>
      </div>
    </header>
  );
}
