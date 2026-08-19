import Image from "next/image";
import Link from "next/link";

const PRODUCT_LINKS = [
  { href: "/features", label: "Features" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/telegram-ai-chatbot", label: "Telegram AI chatbot" },
  { href: "/fanvue-ai-chatbot", label: "Fanvue AI chatbot" },
  { href: "/virtual-number-for-telegram", label: "Telegram virtual number" },
];

const RESOURCE_LINKS = [
  { href: "/guides", label: "Guides" },
  { href: "/telegram-automation", label: "Telegram automation" },
  { href: "/ai-chatter", label: "AI chatter" },
  { href: "/ai-model-chatbot", label: "AI model chatbot" },
  { href: "/ai-chatbot-for-creators", label: "For creators" },
  { href: "/ai-chatbot-for-model-agencies", label: "For agencies" },
];

const LEGAL_LINKS = [
  { href: "/contact", label: "Contact" },
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
];

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
            className="brand-logo-neutral h-7 w-auto"
          />
          <p className="mt-4 text-[13.5px] leading-relaxed text-white/35">
            AI chat agents that keep every fan talking — and turn conversations
            into subscribers.
          </p>
        </div>

        <div className="flex flex-wrap gap-10 sm:gap-14">
          <div>
            <p className="lp-eyebrow text-[10.5px]">Product</p>
            <ul className="mt-4 space-y-2.5 text-[13.5px]">
              {PRODUCT_LINKS.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-white/50 transition-colors hover:text-white"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="lp-eyebrow text-[10.5px]">Resources</p>
            <ul className="mt-4 space-y-2.5 text-[13.5px]">
              {RESOURCE_LINKS.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-white/50 transition-colors hover:text-white"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
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

      <div className="mx-auto mt-12 flex max-w-6xl flex-col gap-3 border-t border-white/[0.06] pt-6 text-[12px] text-white/30 sm:flex-row sm:items-center sm:justify-between">
        <span>© {new Date().getFullYear()} Telepipe. All rights reserved.</span>
        {/* Právne odkazy patria do pätičky, nie len do sitemapy — je to prvé
            miesto, kde ich hľadá človek aj hodnotiaci automat. */}
        <span className="flex flex-wrap gap-x-5 gap-y-2">
          {LEGAL_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="transition-colors hover:text-white/70"
            >
              {link.label}
            </Link>
          ))}
        </span>
      </div>
    </footer>
  );
}
