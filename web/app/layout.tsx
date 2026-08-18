import type { Metadata, Viewport } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";

import { SITE_NAME, SITE_URL } from "@/lib/seo";

// Poppins cez next/font — self-hosted, žiadny externý request
const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "AI Telegram Chatbot for Creators & Agencies | Telepipe",
    template: `%s | ${SITE_NAME}`,
  },
  description:
    "Automate Telegram DMs with persistent AI personas, human-like replies, voice messages and conversion-ready links. Built for creators and model agencies.",
  applicationName: SITE_NAME,
  category: "business",
  openGraph: {
    title: "AI Telegram Chatbot for Creators & Agencies | Telepipe",
    description:
      "Persistent AI chat personas that handle Telegram conversations, voice messages and follow-ups around the clock.",
    url: "/",
    type: "website",
    siteName: SITE_NAME,
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Telegram Chatbot for Creators & Agencies | Telepipe",
    description:
      "Persistent AI chat personas that handle Telegram conversations, voice messages and follow-ups around the clock.",
  },
};

export const viewport: Viewport = {
  themeColor: "#000000",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${poppins.variable} h-full antialiased`}>
      <body className="min-h-full bg-black text-white flex flex-col">
        {children}
      </body>
    </html>
  );
}
