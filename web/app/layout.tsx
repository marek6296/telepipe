import type { Metadata, Viewport } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";

// Poppins cez next/font — self-hosted, žiadny externý request
const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://telepipe.app"),
  title: {
    default: "Telepipe — Your models never sleep",
    template: "%s · Telepipe",
  },
  description:
    "Telepipe turns Telegram DMs into paying subscribers. AI chat personas with voice messages, running 24/7 for creator agencies.",
  applicationName: "Telepipe",
  openGraph: {
    title: "Telepipe — Your models never sleep",
    description:
      "AI chat personas that reply to fans 24/7 and turn conversations into subscribers.",
    type: "website",
    siteName: "Telepipe",
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
