import Image from "next/image";
import Link from "next/link";

export function LandingFooter() {
  return (
    <footer className="relative border-t border-white/[0.07] px-6 py-14">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-xs">
          <Image
            src="/logo-white.png"
            alt="Telepipe"
            width={148}
            height={47}
            className="h-7 w-auto"
          />
          <p className="mt-4 text-[13.5px] leading-relaxed text-white/35">
            AI chat agents that keep every fan talking — and turn conversations
            into subscribers.
          </p>
        </div>

        <div className="flex gap-14">
          <div>
            <p className="lp-eyebrow text-[10.5px]">Product</p>
            <ul className="mt-4 space-y-2.5 text-[13.5px]">
              <li>
                <a
                  href="#features"
                  className="text-white/50 transition-colors hover:text-white"
                >
                  Features
                </a>
              </li>
              <li>
                <a
                  href="#how-it-works"
                  className="text-white/50 transition-colors hover:text-white"
                >
                  How it works
                </a>
              </li>
              <li>
                <a
                  href="#pricing"
                  className="text-white/50 transition-colors hover:text-white"
                >
                  Pricing
                </a>
              </li>
            </ul>
          </div>

          <div>
            <p className="lp-eyebrow text-[10.5px]">Account</p>
            <ul className="mt-4 space-y-2.5 text-[13.5px]">
              <li>
                <Link
                  href="/login"
                  className="text-white/50 transition-colors hover:text-white"
                >
                  Sign in
                </Link>
              </li>
              <li>
                <Link
                  href="/register"
                  className="text-white/50 transition-colors hover:text-white"
                >
                  Get Started
                </Link>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div className="mx-auto mt-12 max-w-6xl border-t border-white/[0.06] pt-6 text-[12px] text-white/30">
        © {new Date().getFullYear()} Telepipe. All rights reserved.
      </div>
    </footer>
  );
}
