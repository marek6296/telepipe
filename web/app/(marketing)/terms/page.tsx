import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage, Section } from "@/components/marketing/legal-page";
import { BRAND } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: `The agreement between you and ${BRAND} — what the service does, what it costs, and what each side is responsible for.`,
};

/**
 * Terms of Service.
 *
 * Tri veci, ktoré tu MUSIA byť a v šablónach chýbajú:
 *   1. Coiny sú predplatený kredit, nie peniaze — inak by boli elektronickými
 *      peniazmi a to je regulovaná činnosť.
 *   2. Kto zodpovedá za to, čo agent napíše fanúšikovi (klient, nie my).
 *   3. Že Telegram môže účet zablokovať a nie je to naša chyba — je to reálne
 *      riziko produktu a zamlčať ho by bolo nefér aj právne slabé.
 */
export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      intro={`The agreement between you and ${BRAND}. Plain language, no traps — but read the parts about account bans and refunds, because they matter.`}
    >
      <Section title="What the service is">
        <p>
          {BRAND} runs AI chat agents on accounts you already own — your Telegram account,
          your Fanvue account. You connect them, you configure the persona, and the agent
          replies on your behalf. We provide the software; the accounts and the audience
          stay yours.
        </p>
        <p>
          You must be at least 18 and allowed to enter a contract. The service is for business
          use.
        </p>
      </Section>

      <Section title="Pipe Coins">
        <p>
          Pipe Coins are prepaid credit for using the service. They are{" "}
          <strong className="text-white/80">not money, not a currency and not a stored-value
          instrument</strong>. They cannot be transferred between accounts, exchanged for
          cash, or withdrawn.
        </p>
        <p>
          Coins do not expire. They are spent as the agent works — every reply, photo and
          voice note costs coins, at rates shown in the app before you spend them.
        </p>
        <p>
          You can top up with cryptocurrency or with Telegram Stars. The price differs between
          the two because Telegram and the app stores take a share of Stars payments. The
          exact amount is always shown before you pay.
        </p>
      </Section>

      <Section title="Refunds">
        <p>
          Unused coins can be refunded within 14 days of purchase if you have not used the
          service meaningfully. Coins already spent on generated replies cannot be refunded —
          the cost was incurred at that moment.
        </p>
        <p>
          Telegram Stars payments can also be refunded through Telegram. If that happens, the
          corresponding coins are removed from your balance, which may leave it negative until
          you top up again.
        </p>
        <p>
          If we fail to deliver the service, you get your money back. That is not negotiable
          and no clause below limits it.
        </p>
      </Section>

      <Section title="What you are responsible for">
        <p>
          <strong className="text-white/80">Everything the agent sends is sent as you.</strong>{" "}
          It goes out from your account, to your audience, in a persona you configured. You
          are responsible for that content and for complying with the rules of Telegram,
          Fanvue, and any law that applies to you.
        </p>
        <p>You must not use {BRAND} to:</p>
        <p>
          impersonate a real person without their consent · involve anyone under 18 in any way ·
          send unsolicited bulk messages · deceive people into payments they did not agree to ·
          break the terms of the platforms you connect.
        </p>
        <p>
          You are also the data controller for the people your agent talks to. See the{" "}
          <Link href="/privacy" className="text-white/80 underline underline-offset-2">
            Privacy Policy
          </Link>{" "}
          for what that means in practice.
        </p>
      </Section>

      <Section title="Platform bans">
        <p>
          This one deserves its own section because it is the most likely thing to go wrong.
        </p>
        <p>
          Telegram, Fanvue and similar platforms restrict automated behaviour. {BRAND} is built
          to stay well inside those limits — human pacing, hourly and daily caps, a warm-up
          period for new accounts, and a hard stop if the platform signals a problem. It works,
          but it is not a guarantee.
        </p>
        <p>
          <strong className="text-white/80">
            If a platform restricts or bans your account, we are not liable for it
          </strong>{" "}
          and it is not grounds for a refund of coins already spent. Raising the limits above
          our defaults is your decision and your risk.
        </p>
      </Section>

      <Section title="What we are responsible for">
        <p>
          Keeping the service running, keeping your data safe as described in the Privacy
          Policy, and charging you only what you actually used.
        </p>
        <p>
          AI output is not predictable. We do not warrant that a reply will be accurate,
          appropriate or effective — you keep control through the persona settings and the
          semi-automatic mode, where every reply waits for your approval.
        </p>
        <p>
          Except where the law does not allow it, our total liability is limited to what you
          paid us in the three months before the claim. We are not liable for lost profit or
          lost audience.
        </p>
      </Section>

      <Section title="Suspension and ending the agreement">
        <p>
          You can stop at any time — disconnect the accounts or delete yours. Unused coins are
          handled as described above.
        </p>
        <p>
          We can suspend an account that breaks these terms, puts other customers at risk, or
          is used for something illegal. Where we reasonably can, we will tell you first and
          give you a chance to fix it.
        </p>
      </Section>

      <Section title="Changes">
        <p>
          If we change these terms in a way that matters, we will tell you in the app before
          it takes effect. Continuing to use the service after that means you accept the new
          version.
        </p>
      </Section>
    </LegalPage>
  );
}
