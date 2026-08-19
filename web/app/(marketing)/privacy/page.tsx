import type { Metadata } from "next";
import Link from "next/link";

import { DataTable, LegalPage, Section } from "@/components/marketing/legal-page";
import { BRAND } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: `How ${BRAND} handles personal data — what we store, who we send it to, and how long we keep it.`,
};

/**
 * Privacy Policy.
 *
 * Napísaná podľa toho, čo systém NAOZAJ robí — tabuľky a príjemcovia sú overené
 * v schéme a v kóde, nie opísané zo šablóny. Preto je konkrétna: kto ju číta,
 * má z nej vedieť, čo o ňom vieme, a nie sa prebrodiť frázami.
 *
 * Dve veci, ktoré ju odlišujú od bežnej SaaS politiky a nesmú sa stratiť:
 *   1. Spracúvame údaje FANÚŠIKOV, ktorí sa u nás neregistrovali. Voči nim je
 *      prevádzkovateľom klient, my sme sprostredkovateľ.
 *   2. Obsah konverzácií môže spadať pod čl. 9 GDPR (údaje o sexuálnom živote).
 *      Je to tu priznané otvorene, nie schované.
 */
export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      intro={`What ${BRAND} stores, why, who else sees it, and how long we keep it. Written to be specific rather than reassuring.`}
    >
      <Section title="Two kinds of people in this policy">
        <p>
          {BRAND} is a tool creators use to run AI chat agents on their own Telegram and
          Fanvue accounts. That means two very different groups appear in our systems:
        </p>
        <p>
          <strong className="text-white/80">Customers</strong> — creators and agencies who
          sign up, pay and operate the agents. For their data we are the controller.
        </p>
        <p>
          <strong className="text-white/80">Fans</strong> — people who message a customer&apos;s
          account. They never signed up with us and have no relationship with {BRAND}. For
          their data <strong className="text-white/80">the customer is the controller and we
          are only a processor</strong>: we store and process it on the customer&apos;s
          instructions and do not use it for our own purposes.
        </p>
      </Section>

      <Section title="What we store about customers">
        <DataTable
          rows={[
            ["Email address", "Account login, receipts, service notices", "Until the account is deleted"],
            ["Password", "Login. Stored hashed by our auth provider — we never see it", "Until the account is deleted"],
            ["Telegram session", "Lets the agent reply from the account. Encrypted at rest", "Until disconnected or deleted"],
            ["ElevenLabs API key", "Voice notes, if the customer connects one. Encrypted at rest", "Until removed or deleted"],
            ["Fanvue tokens", "Reading and sending Fanvue messages. Encrypted at rest", "Until disconnected"],
            ["Payments and balance", "Billing, refunds, accounting obligations", "As long as tax law requires"],
            ["Telegram user ID", "Only if paying with Telegram Stars — so invoices can be sent to the right chat", "Until the account is deleted"],
            ["Usage records", "Charging Pipe Coins and showing spend", "As long as tax law requires"],
          ]}
        />
      </Section>

      <Section title="What we store about fans">
        <p>
          This is stored on behalf of the customer whose account the fan wrote to. We do not
          combine it across customers and we do not use it to build our own profiles.
        </p>
        <DataTable
          rows={[
            ["Telegram ID, username, first name", "Telling conversations apart", "Until the customer deletes the model or the conversation"],
            ["Message history", "The agent needs the conversation to reply in context", "Until the customer deletes it"],
            ["Facts extracted from messages", "Remembering what the fan said, so the agent doesn't ask twice", "Until the customer deletes it"],
            ["Conversation summaries and notes", "Keeping long conversations coherent", "Until the customer deletes it"],
            ["Photos and voice notes sent", "Record of what has already been sent", "Until the customer deletes it"],
          ]}
        />
      </Section>

      <Section title="Sensitive content">
        <p>
          Conversations handled by {BRAND} are often flirtatious or sexual. Under the GDPR,
          information about a person&apos;s sex life or sexual orientation is a{" "}
          <strong className="text-white/80">special category of personal data</strong> with
          stricter rules than ordinary data.
        </p>
        <p>
          We do not analyse this content for our own purposes, do not sell it, and do not use
          it to train models. It is processed only to generate replies for the customer whose
          account the conversation belongs to, and it is encrypted in transit and at rest.
        </p>
        <p>
          Customers using {BRAND} are responsible for having a lawful basis for these
          conversations on their own platforms, and for meeting the transparency duties those
          platforms and the law place on them.
        </p>
      </Section>

      <Section title="Who else sees the data">
        <p>
          We use the following providers. Each one sees only what it needs to do its job, and
          each is bound by a data processing agreement.
        </p>
        <DataTable
          rows={[
            ["Supabase", "Database, file storage and login. Hosted in the EU (eu-west-1)", "—"],
            ["Vercel", "Runs the website and API", "—"],
            ["Railway", "Runs the agents", "—"],
            ["Atlas Cloud, OpenRouter", "Generate replies. Receive conversation context", "—"],
            ["ElevenLabs", "Generates voice notes, if enabled. Receives the text to speak", "—"],
            ["Telegram", "Delivers messages and processes Stars payments", "—"],
            ["Fanvue", "Delivers messages on Fanvue, if connected", "—"],
            ["Plisio", "Processes cryptocurrency payments", "—"],
            ["VRNUM", "Supplies phone numbers for verification, if used", "—"],
          ]}
        />
        <p>
          Some of these providers are outside the EU. Where that is the case, transfers rely
          on the European Commission&apos;s standard contractual clauses.
        </p>
        <p>
          We do not sell personal data and we do not share it for advertising.
        </p>
      </Section>

      <Section title="Your rights">
        <p>
          If you are in the EU or UK you can ask for access to your data, correction,
          deletion, restriction, a copy in a portable format, or object to processing. You can
          also complain to your national data protection authority.
        </p>
        <p>
          <strong className="text-white/80">Fans:</strong> because the customer is the
          controller of your data, requests are usually fastest through the account you were
          messaging. If you contact us instead, we will pass the request to that customer and
          help them act on it.
        </p>
        <p>Contact details are at the bottom of this page.</p>
      </Section>

      <Section title="Deletion">
        <p>
          Deleting a model removes its conversations, extracted facts, photos and voice notes.
          Deleting an account removes the account and everything attached to it.
        </p>
        <p>
          Two things survive deletion on purpose: payment and usage records we are required to
          keep for tax and accounting, and backups, which roll off on their own schedule.
        </p>
      </Section>

      <Section title="Security">
        <p>
          Telegram sessions, Fanvue tokens and API keys are encrypted at rest. Access to
          customer data is enforced at the database level, so one account cannot read
          another&apos;s data even if the application had a bug. Traffic is encrypted in
          transit.
        </p>
      </Section>

      <Section title="Changes">
        <p>
          If we change this policy in a way that matters, we will say so in the app before it
          takes effect. The date at the top always reflects the current version.
        </p>
        <p>
          See also our <Link href="/terms" className="text-white/80 underline underline-offset-2">Terms of Service</Link>.
        </p>
      </Section>
    </LegalPage>
  );
}
