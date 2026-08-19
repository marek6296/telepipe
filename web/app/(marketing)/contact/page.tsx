import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage, Section } from "@/components/marketing/legal-page";
import { BRAND, LEGAL_READY, OPERATOR } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Contact",
  description: `How to reach ${BRAND} — support, billing questions and privacy requests.`,
};

export default function ContactPage() {
  return (
    <LegalPage
      title="Contact"
      intro={`Real people, usually the same day. Here is where to write depending on what you need.`}
    >
      <Section title="Already using TelePipe">
        <p>
          The fastest way is the chat inside the app — bottom-right corner of every page. It
          reaches us directly and we can see your account, so nothing needs explaining twice.
        </p>
      </Section>

      <Section title="Not signed up yet">
        <p>
          {LEGAL_READY ? (
            <>
              Write to{" "}
              <a
                href={`mailto:${OPERATOR.email}`}
                className="text-white/80 underline underline-offset-2"
              >
                {OPERATOR.email}
              </a>
              {OPERATOR.telegram ? (
                <>
                  {" "}
                  or message us on Telegram at{" "}
                  <span className="text-white/80">{OPERATOR.telegram}</span>
                </>
              ) : null}
              .
            </>
          ) : (
            <>Contact details are being finalised and will be published here shortly.</>
          )}
        </p>
        <p>
          Questions about whether {BRAND} fits what you do are welcome — it does not fit
          everyone and we would rather say so up front.
        </p>
      </Section>

      <Section title="Privacy requests">
        <p>
          Asking for access to your data, correction or deletion? Write to the address above
          and say what you are asking for.
        </p>
        <p>
          <strong className="text-white/80">If you were messaging a creator</strong> and want
          your data removed, the creator controls it, not us — reaching out to them directly
          is usually faster. If you write to us instead, we will pass it on and make sure it
          gets done. The{" "}
          <Link href="/privacy" className="text-white/80 underline underline-offset-2">
            Privacy Policy
          </Link>{" "}
          explains why it works that way.
        </p>
      </Section>

      <Section title="Payments">
        <p>
          Every crypto payment is verifiable on the blockchain and every Telegram Stars
          payment has a transaction ID, so nothing gets lost. If coins have not appeared a few
          hours after a payment, write to us with the date and amount and we will trace it.
        </p>
      </Section>
    </LegalPage>
  );
}
