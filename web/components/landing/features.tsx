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
      <div className="pointer-events-none absolute inset-0 lp-grid-fine" />

      <div className="relative mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <p className="lp-eyebrow">Features</p>
          <h2 className="mt-4 text-[clamp(2rem,4.4vw,3.2rem)] font-semibold leading-[1.1] lp-tight text-white">
            Everything a chatter does.
            <span className="lp-text-dim"> Without the payroll.</span>
          </h2>
          <p className="mt-5 text-base leading-relaxed text-white/45">
            Telepipe replaces the night shift, the weekend shift and the
            &ldquo;sorry, I was asleep&rdquo; shift — with one agent per model that
            never breaks character.
          </p>
        </div>

        <div className="mt-14 grid gap-4 sm:grid-cols-2">
          {FEATURES.map((feature, index) => (
            <article
              key={feature.title}
              className="lp-card lp-card-hover group relative overflow-hidden p-7"
            >
              <div className="relative flex items-start gap-4">
                <span className="lp-icon-chip h-10 w-10 shrink-0 transition-colors duration-300 group-hover:border-white/20 group-hover:text-white">
                  <feature.icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
                </span>
                <div>
                  <div className="flex items-baseline gap-3">
                    <h3 className="text-[17px] font-semibold text-white">
                      {feature.title}
                    </h3>
                    <span className="font-mono text-[10px] text-white/20">
                      0{index + 1}
                    </span>
                  </div>
                  <p className="mt-2.5 text-[14.5px] leading-relaxed text-white/45">
                    {feature.body}
                  </p>
                  <p className="mt-4 text-[11px] font-medium uppercase tracking-[0.14em] text-white/25">
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
