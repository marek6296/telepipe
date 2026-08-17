"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#pricing", label: "Pricing" },
];

/**
 * Fixná blur navigácia v štýle dashboardu — monochróm, zlatá len v logu.
 *
 * Reveal: prvky s `data-nav-reveal` štartujú skryté a odhalí ich intro timeline
 * v `CinematicScene` (nie scroll timeline — objaví sa teda hneď po načítaní,
 * až keď dosadne intro text). Pri `prefers-reduced-motion` GSAP nebeží vôbec
 * a `.lp-nav-reveal` si viditeľnosť vynúti cez CSS v `landing.css`.
 */
export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Zamknúť scroll pod otvoreným mobilným menu
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-[80] transition-colors duration-300",
        scrolled
          ? "border-b border-white/[0.07] bg-black/60 backdrop-blur-xl supports-[backdrop-filter]:bg-black/45"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <nav className="mx-auto flex h-[68px] max-w-7xl items-center justify-between px-5 sm:px-8">
        <Link
          href="/"
          data-nav-reveal
          className="lp-nav-reveal flex items-center"
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

        <ul data-nav-reveal className="lp-nav-reveal hidden items-center gap-8 md:flex">
          {LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="text-[13.5px] font-medium text-white/55 transition-colors hover:text-white"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        <div
          data-nav-reveal
          className="lp-nav-reveal hidden items-center gap-2.5 md:flex"
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
          data-nav-reveal
          onClick={() => setOpen((value) => !value)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          className="lp-nav-reveal lp-hairline flex h-9 w-9 items-center justify-center rounded-lg text-white/75 transition-colors hover:text-white md:hidden"
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
          {LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                onClick={() => setOpen(false)}
                className="block rounded-lg px-3 py-3 text-[15px] font-medium text-white/70 transition-colors hover:bg-white/[0.04] hover:text-white"
              >
                {link.label}
              </a>
            </li>
          ))}
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
