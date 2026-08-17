import Image from "next/image";

import { signOutAction } from "@/app/(auth)/actions";
import { getUser } from "@/lib/supabase/server";

/**
 * Dočasný obsah `/app` — plný AppShell so zoznamom modeliek dodáva task W7.
 * Teraz slúži hlavne na overenie, že auth flow a middleware guard fungujú.
 */
export default async function AppHomePage() {
  const user = await getUser();

  return (
    <main className="relative flex flex-1 flex-col items-center justify-center px-6 py-24 text-center">
      <div className="pointer-events-none absolute inset-0 bg-grid-fine" />
      <div className="relative">
        <Image
          src="/logo-white.png"
          alt="Telepipe"
          width={180}
          height={57}
          priority
          className="mx-auto h-8 w-auto"
        />
        <h1 className="mt-10 text-3xl font-semibold text-gradient-gold">
          You are signed in
        </h1>
        <p className="mt-3 text-[14.5px] text-white/45">
          {user?.email} — the dashboard lands in the next step.
        </p>
        <form action={signOutAction} className="mt-9">
          <button type="submit" className="btn-modern-dark h-11 px-7 text-[14px]">
            Sign out
          </button>
        </form>
      </div>
    </main>
  );
}
