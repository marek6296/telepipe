import type { Metadata } from "next";

import { ChatDockMount } from "@/components/chat/chat-dock-mount";

export const metadata: Metadata = {
  title: "Awaiting approval",
  robots: { index: false, follow: false, noarchive: true, nocache: true },
};

/**
 * Vlastný minimálny shell — žiadny sidebar, žiadna workspace navigácia.
 *
 * `/locked` je zámerne mimo `/app`: layout `/app` posiela zamknutých sem, takže
 * keby táto stránka pod ním žila, redirect by sa zacyklil.
 */
export default function LockedLayout({ children }: LayoutProps<"/locked">) {
  return (
    <div className="min-h-dvh bg-[var(--app-bg)] px-5 py-16 text-[var(--app-text)]">
      <div className="mx-auto w-full max-w-lg">{children}</div>
      {/* Zamknutý má mať Community aj možnosť napísať priamo Marekovi. */}
      <ChatDockMount />
    </div>
  );
}
