import Image from "next/image";

// Dočasná holding stránka — plnú landing page dodáva task W5.
export default function Home() {
  return (
    <main className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-6 text-center">
      <div className="pointer-events-none absolute inset-0 bg-grid" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 gold-halo" />
      <div className="film-grain-fixed" />

      <div className="relative z-10 flex flex-col items-center">
        <Image
          src="/logo-white.png"
          alt="Telepipe"
          width={260}
          height={83}
          priority
          className="animate-element animate-delay-100"
        />
        <h1 className="animate-element animate-delay-300 mt-10 text-4xl font-semibold text-balance-tight sm:text-6xl">
          <span className="text-gradient-gold">Your models never sleep.</span>
        </h1>
        <p className="animate-element animate-delay-500 mt-5 max-w-xl text-base text-white/55">
          AI chat personas that reply to fans 24/7 and turn Telegram
          conversations into paying subscribers.
        </p>
      </div>
    </main>
  );
}
