import { Coins, MessagesSquare, Mic, TrendingUp } from "lucide-react";

const FEATURES = [
  {
    icon: MessagesSquare,
    title: "AI Chat Persona",
    body: "Give every model a backstory, tone, boundaries and slang. Telepipe stays in character across thousands of parallel conversations — and remembers what each fan already told her.",
    meta: "Persona · memory · boundaries",
  },
  {
    icon: Mic,
    title: "Voice Messages",
    body: "Real voice notes with her own cloned voice, tempo and ambience — bedroom, street or café. Fans hear a person, not a bot, and conversion jumps.",
    meta: "Cloned voice · ambience · tempo",
  },
  {
    icon: TrendingUp,
    title: "Smart Funnel",
    body: "Every chat is scored cold → warm → link sent → converted. The agent drops your Fanvue link only when the moment is right, never on the first message.",
    meta: "Funnel stages · timing rules",
  },
  {
    icon: Coins,
    title: "Usage-based Credits",
    body: "No seats, no monthly minimum. You pay for the tokens, transcriptions and voice seconds you actually use — visible per model, per day, to the cent.",
    meta: "Per-model usage · live balance",
  },
];

export function Features() {
  return (
    <section id="features" className="relative scroll-mt-24 px-6 py-28 sm:py-36">
      <div className="pointer-events-none absolute inset-0 bg-grid-fine" />

      <div className="relative mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.26em] text-[var(--gold)]">
            Features
          </p>
          <h2 className="mt-4 text-[clamp(2rem,4.4vw,3.2rem)] font-semibold leading-[1.1] text-balance-tight text-white">
            Everything a chatter does.
            <span className="text-gradient-gold"> Without the payroll.</span>
          </h2>
          <p className="mt-5 text-base leading-relaxed text-white/50">
            Telepipe replaces the night shift, the weekend shift and the
            &ldquo;sorry, I was asleep&rdquo; shift — with one agent per model that
            never breaks character.
          </p>
        </div>

        <div className="mt-14 grid gap-5 sm:grid-cols-2">
          {FEATURES.map((feature, index) => (
            <article
              key={feature.title}
              className="widget-depth group relative overflow-hidden rounded-3xl p-7 transition-transform duration-300 hover:-translate-y-1"
            >
              <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-[radial-gradient(circle,rgba(212,175,55,0.16),transparent_66%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100" />

              <div className="relative flex items-start gap-4">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-[rgba(212,175,55,0.24)] bg-[rgba(212,175,55,0.09)]">
                  <feature.icon className="h-5 w-5 text-[var(--gold)]" />
                </span>
                <div>
                  <div className="flex items-baseline gap-3">
                    <h3 className="text-lg font-semibold text-white">
                      {feature.title}
                    </h3>
                    <span className="text-[10px] font-mono text-white/20">
                      0{index + 1}
                    </span>
                  </div>
                  <p className="mt-2.5 text-[14.5px] leading-relaxed text-white/50">
                    {feature.body}
                  </p>
                  <p className="mt-4 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--gold-dark)]">
                    {feature.meta}
                  </p>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
