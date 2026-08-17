import type { ReactNode } from "react";
import { ExternalLink } from "lucide-react";

/**
 * Textové návody wizardu. Sú zámerne na jednom mieste — Marek ich bude ladiť
 * podľa toho, kde sa klienti zaseknú.
 */

export function GuideList({ children }: { children: ReactNode }) {
  return (
    <ol className="space-y-2.5 text-[13px] leading-relaxed text-[var(--app-text-2)]">{children}</ol>
  );
}

export function GuideStep({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[10.5px] font-medium text-[var(--app-text-2)]">
        {n}
      </span>
      <span className="min-w-0">{children}</span>
    </li>
  );
}

export function GuideLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-medium text-[var(--app-text)] underline decoration-[var(--app-border-strong)] underline-offset-2 transition-colors hover:decoration-[var(--app-text-2)]"
    >
      {children}
      <ExternalLink className="h-3 w-3" />
    </a>
  );
}

export function ApiKeysGuide() {
  return (
    <GuideList>
      <GuideStep n={1}>
        Open <GuideLink href="https://my.telegram.org">my.telegram.org</GuideLink> and log
        in with <strong className="font-medium text-[var(--app-text-2)]">her</strong> phone number —
        Telegram sends a confirmation code to that account.
      </GuideStep>
      <GuideStep n={2}>
        Click <strong className="font-medium text-[var(--app-text-2)]">API development tools</strong>.
      </GuideStep>
      <GuideStep n={3}>
        Fill in the short form — app title and short name can be anything (e.g. “chat”),
        platform <em>Other</em> — and submit it.
      </GuideStep>
      <GuideStep n={4}>
        Copy <code className="rounded bg-[#1a1a1a] px-1 py-0.5 text-[12px]">api_id</code>{" "}
        (a number) and{" "}
        <code className="rounded bg-[#1a1a1a] px-1 py-0.5 text-[12px]">api_hash</code> (32
        characters) into the fields below.
      </GuideStep>
    </GuideList>
  );
}

export function BotFatherGuide() {
  return (
    <GuideList>
      <GuideStep n={1}>
        In Telegram, open <GuideLink href="https://t.me/BotFather">@BotFather</GuideLink> and
        send <code className="rounded bg-[#1a1a1a] px-1 py-0.5 text-[12px]">/newbot</code>.
      </GuideStep>
      <GuideStep n={2}>
        Give it any name, then a username that ends with{" "}
        <strong className="font-medium text-[var(--app-text-2)]">bot</strong>.
      </GuideStep>
      <GuideStep n={3}>
        Copy the token BotFather sends back — it looks like{" "}
        <code className="rounded bg-[#1a1a1a] px-1 py-0.5 text-[12px]">
          123456789:AAE…
        </code>
      </GuideStep>
      <GuideStep n={4}>
        Open your new bot and press <strong className="font-medium text-[var(--app-text-2)]">Start</strong>
        {" "}— otherwise Telegram will not let it message you.
      </GuideStep>
    </GuideList>
  );
}

export function OwnerChatGuide() {
  return (
    <GuideList>
      <GuideStep n={1}>
        Open <GuideLink href="https://t.me/userinfobot">@userinfobot</GuideLink> from{" "}
        <strong className="font-medium text-[var(--app-text-2)]">your own</strong> Telegram account and
        press Start.
      </GuideStep>
      <GuideStep n={2}>
        It replies with your numeric <em>Id</em> — paste it below. Notifications and takeover
        buttons land in that chat.
      </GuideStep>
    </GuideList>
  );
}
