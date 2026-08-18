import type { Metadata } from "next";

import { SeoPage } from "@/components/marketing/seo-page";
import { marketingMetadata } from "@/lib/seo";

export const metadata: Metadata = marketingMetadata({
  title: "Virtual Number for Telegram OTP Verification",
  description:
    "Choose an available country, buy a one-time virtual number for Telegram with Telepipe credit and receive the OTP code inside your secure dashboard.",
  path: "/virtual-number-for-telegram",
});

const FAQ = [
  {
    q: "Is this a permanent virtual SIM?",
    a: "No. Telepipe currently offers temporary, one-time OTP numbers for Telegram verification. The number is reserved for the activation window shown in the dashboard.",
  },
  {
    q: "Can I choose the country?",
    a: "Yes. The dashboard loads the live Telegram country catalog, including the United States when provider stock is available. Availability and price can change in real time.",
  },
  {
    q: "Where does the Telegram code arrive?",
    a: "The number and its incoming OTP status appear in the Telepipe Virtual SIM page. When the provider receives the code, it is displayed on that order.",
  },
  {
    q: "What happens if provisioning fails?",
    a: "Definitive provider failures are reconciled with the order and the reserved Telepipe credit is refunded. The order history shows the resulting state.",
  },
  {
    q: "Can I use the number for another service?",
    a: "The current Telepipe flow purchases a Telegram-specific OTP activation. It should not be treated as a general phone line or reused for unrelated services.",
  },
];

export default function VirtualNumberForTelegramPage() {
  return (
    <SeoPage
      path="/virtual-number-for-telegram"
      eyebrow="Telegram OTP numbers"
      title="A virtual number for Telegram."
      dim="Delivered inside Telepipe."
      lead="Choose a country from live provider stock, pay with your Telepipe balance and receive the one-time Telegram verification code in the same dashboard."
      highlights={[
        {
          title: "Live country availability",
          body: "Available destinations and prices come from the current Telegram OTP catalog, not a stale hard-coded list.",
        },
        {
          title: "Protected purchase flow",
          body: "Credit is reserved server-side before provisioning so repeated clicks cannot create free or duplicate orders.",
        },
        {
          title: "Code and refund status",
          body: "The number, incoming OTP, expiry and any refund remain visible in your Telepipe order history.",
        },
      ]}
      sections={[
        {
          title: "How to get a virtual number for Telegram verification",
          paragraphs: [
            "Open Virtual SIM after signing in to Telepipe. The page loads every country currently offered for Telegram OTP activation and puts available destinations first, including the United States whenever stock exists.",
            "Select a country and confirm the live Pipe Coin price. Once the provider reserves a number, copy it into Telegram and request the verification code. The code appears on the Telepipe order as soon as the SMS is received.",
          ],
          points: [
            "Choose from the live Telegram catalog",
            "See the full price before purchase",
            "Copy the provisioned number",
            "Read the OTP in the dashboard",
          ],
        },
        {
          title: "Temporary OTP activation, not a permanent phone plan",
          paragraphs: [
            "The service is designed for a one-time Telegram verification window. It is not a permanent SIM, monthly mobile plan or general inbox for ongoing personal messages.",
            "Complete Telegram setup while the order is active and immediately enable Telegram two-step verification. Do not rely on a temporary number as the only long-term recovery method for an important account.",
          ],
        },
        {
          title: "Why countries and prices change",
          paragraphs: [
            "Virtual-number inventory is live. A country can sell out, return later or change price according to the upstream network supply. Telepipe requests a fresh quote immediately before reserving customer credit.",
            "The displayed retail price includes Telepipe's service margin and rounds upward to a clear customer price. The purchase only continues if the account has enough balance for that current quote.",
          ],
        },
        {
          title: "What happens when a code does not arrive",
          paragraphs: [
            "Orders can move through provisioning, waiting, code received, completed, cancelled, expired or failed states. Telepipe reconciles uncertain provider responses instead of assuming that a timed-out request never created an order.",
            "When the provider confirms a failure or an eligible cancellation, the refund is written back through the protected credit ledger and appears in the order history. Network delivery is not guaranteed, so the status shown in the dashboard remains the source of truth.",
          ],
        },
        {
          title: "Use virtual numbers responsibly",
          paragraphs: [
            "Only create and operate accounts you are authorized to control. Follow Telegram's terms, local law and any platform rules that apply to your business or creator activity.",
            "Telepipe's OTP product is a setup tool. It does not remove Telegram's security controls and it should not be used for impersonation, spam, fraud or attempts to evade platform enforcement.",
          ],
        },
      ]}
      faq={FAQ}
      related={[
        {
          href: "/guides/telegram-virtual-number-verification",
          label: "Verification guide",
          description: "A careful step-by-step Telegram OTP checklist.",
        },
        {
          href: "/how-it-works",
          label: "Connect Telegram",
          description: "See how the account is connected after verification.",
        },
        {
          href: "/pricing",
          label: "Telepipe credit",
          description: "Review the Pipe Coin balance used for OTP purchases and AI work.",
        },
      ]}
      ctaTitle="Get the Telegram number from your Telepipe dashboard."
      ctaBody="Create an account, add Telepipe credit and choose from the countries that are available at the moment you buy."
      ctaNote="Live availability · One-time Telegram OTP · Eligible failures refunded"
    />
  );
}
