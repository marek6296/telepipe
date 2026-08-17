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

/** Fixná blur navigácia zo SaaS predlohy — biele logo, zlaté CTA. */
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
        "fixed inset-x-0 top-0 z-[80] transition-all duration-300",
        scrolled
          ? "border-b border-white/[0.07] bg-black/60 backdrop-blur-xl supports-[backdrop-filter]:bg-black/45"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <nav className="mx-auto flex h-[72px] max-w-7xl items-center justify-between px-5 sm:px-8">
        <Link href="/" className="flex items-center" aria-label="Telepipe home">
          <Image
            src="/logo-white.png"
            alt="Telepipe"
            width={148}
            height={47}
            priority
            className="h-7 w-auto"
          />
        </Link>

        <ul className="hidden items-center gap-9 md:flex">
          {LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="text-[13.5px] font-medium text-white/60 transition-colors hover:text-[var(--gold-light)]"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="hidden items-center gap-3 md:flex">
          <Link href="/login" className="btn-ghost-gold h-10 px-4 text-[13.5px]">
            Sign in
          </Link>
          <Link href="/register" className="btn-modern-light h-10 px-5 text-[13.5px]">
            Get Started
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          className="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 text-white/80 md:hidden"
        >
          {open ? <X className="h-4.5 w-4.5" /> : <Menu className="h-4.5 w-4.5" />}
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
                className="block rounded-xl px-3 py-3 text-[15px] font-medium text-white/75 hover:bg-white/[0.04] hover:text-[var(--gold-light)]"
              >
                {link.label}
              </a>
            </li>
          ))}
          <li className="flex flex-col gap-3 pt-4">
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="btn-modern-dark h-12 w-full text-[14px]"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              onClick={() => setOpen(false)}
              className="btn-modern-light h-12 w-full text-[14px]"
            >
              Get Started
            </Link>
          </li>
        </ul>
      </div>
    </header>
  );
}
