import type { ReactNode } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";

/**
 * Návody Telegram sprievodcu — text, nie logika.
 *
 * PÍSANÉ PODĽA JEDNEJ ŠABLÓNY, lebo prvý platiaci klient sa zasekol na kroku,
 * kde bolo napísané „skopíruj api_id a api_hash", ale nie ODKIAĽ presne a ako
 * vyzerajú. Každý krok preto odpovedá na šesť otázok v tomto poradí:
 *
 *   kam ísť → na čo kliknúť → čo uvidím → čo skopírovať → do ktorého políčka →
 *   čo keď to nevyjde
 *
 * Prvých päť je v očíslovaných krokoch a musí sa zmestiť na obrazovku bez
 * scrollovania. Šieste — okrajové prípady — je zabalené v `Troubleshoot`, aby
 * bežnú cestu nezahlcovalo.
 *
 * Pravidlá formy: pokojná druhá osoba, žiadne emoji ani výkričníky, klikací
 * cieľ **tučne**, doslovné hodnoty v `code`, externé odkazy do nového okna.
 */

export function GuideList({ children }: { children: ReactNode }) {
  return (
    <ol className="space-y-2.5 text-[13px] leading-relaxed text-[var(--app-text-2)]">{children}</ol>
  );
}

export function GuideStep({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[10.5px] font-medium text-[var(--app-text-2)]">
        {n}
      </span>
      <span className="min-w-0">{children}</span>
    </li>
  );
}

export function GuideLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-medium text-[var(--app-text)] underline decoration-[var(--app-border-strong)] underline-offset-2 transition-colors hover:decoration-[var(--app-text-2)]"
    >
      {children}
      <ExternalLink className="h-3 w-3" />
    </a>
  );
}

/** Klikací cieľ — to, čo má klient nájsť očami na cudzej stránke. */
function Click({ children }: { children: ReactNode }) {
  return <strong className="font-semibold text-[var(--app-text)]">{children}</strong>;
}

/** Doslovná hodnota — presne to, čo uvidí alebo napíše. */
function Lit({ children }: { children: ReactNode }) {
  return (
    <code className="rounded bg-[#1a1a1a] px-1 py-0.5 font-mono text-[12px] text-[var(--app-text)]">
      {children}
    </code>
  );
}

/**
 * Okrajové prípady. `<details>` zámerne — funguje bez JS, nedrží stav a
 * nezaberá miesto, kým ho klient nepotrebuje.
 */
export function Troubleshoot({ children }: { children: ReactNode }) {
  return (
    <details className="group rounded-lg border border-[var(--app-border)] bg-[#0c0c0c]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3.5 py-2.5 text-[12.5px] font-medium text-[var(--app-text-2)] transition-colors hover:text-[var(--app-text)]">
        Something went wrong?
        <ChevronDown className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-2.5 border-t border-[var(--app-border)] px-3.5 py-3 text-[12.5px] leading-relaxed text-[var(--app-text-3)]">
        {children}
      </div>
    </details>
  );
}

function Problem({ when, children }: { when: string; children: ReactNode }) {
  return (
    <p>
      <span className="font-medium text-[var(--app-text-2)]">{when}</span> {children}
    </p>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 1 — API keys                                                          */
/* -------------------------------------------------------------------------- */

export function ApiKeysGuide() {
  return (
    <div className="space-y-4">
      <GuideList>
        <GuideStep n={1}>
          Open <GuideLink href="https://my.telegram.org">my.telegram.org</GuideLink> and sign in
          with <Click>her</Click> phone number — the account the agent will run as, not your own.
        </GuideStep>
        <GuideStep n={2}>
          Telegram sends a confirmation code <Click>inside Telegram</Click>, as a message from{" "}
          <Lit>Telegram</Lit> on that account. It does not come by SMS. Enter it on the page.
        </GuideStep>
        <GuideStep n={3}>
          On the menu that appears, click <Click>API development tools</Click>.
        </GuideStep>
        <GuideStep n={4}>
          Fill the short form: <Click>App title</Click> and <Click>Short name</Click> can be
          anything (<Lit>chat</Lit> is fine), platform <Click>Other</Click>, the URL may stay
          empty. Then <Click>Create application</Click>.
        </GuideStep>
        <GuideStep n={5}>
          The result page shows <Lit>App api_id</Lit> — a number, usually 7–8 digits — and{" "}
          <Lit>App api_hash</Lit> — 32 characters. Copy each into the matching field here.
        </GuideStep>
      </GuideList>

      <p className="text-[12px] leading-relaxed text-[var(--app-text-3)]">
        These are not the bot token. The token with a colon in it belongs to the Control bot
        step, further along.
      </p>

      <Troubleshoot>
        <Problem when="A red ERROR on the first submit.">
          It happens on a fresh account. Reload the page and submit the same form again, or try
          another browser or a private window. Nothing was created, so nothing is lost.
        </Problem>
        <Problem when="The page already lists an app.">
          Then the keys exist. Reuse the <Lit>api_id</Lit> and <Lit>api_hash</Lit> it shows —
          Telegram gives one set per account and does not let you make a second.
        </Problem>
        <Problem when="You manage several models.">
          Keys belong to a Telegram account, so each model needs her own set, taken while signed
          in as her.
        </Problem>
        <Problem when="No confirmation code arrives.">
          Check that you typed her number in full international form, and look in her Telegram
          app for a chat named <Lit>Telegram</Lit> — the code is a message there.
        </Problem>
      </Troubleshoot>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 2 — telefón                                                           */
/* -------------------------------------------------------------------------- */

export function PhoneGuide() {
  return (
    <div className="space-y-4">
      <GuideList>
        <GuideStep n={1}>
          Type her number in international form: a <Lit>+</Lit>, the country code, then the rest
          without spaces — <Lit>+421901234567</Lit>.
        </GuideStep>
        <GuideStep n={2}>
          It has to be the <Click>same account</Click> the api_id and api_hash came from. A
          different number will be rejected a step later, when the code is checked.
        </GuideStep>
        <GuideStep n={3}>
          Press <Click>Send code</Click>. Telegram delivers it to her Telegram app; if she is not
          signed in anywhere, it comes by SMS instead. Have the phone at hand.
        </GuideStep>
      </GuideList>

      <Troubleshoot>
        <Problem when="Which number should she use?">
          A dedicated one, not a heavily used personal account. Telegram watches automated
          replies on long-standing personal numbers more closely.
        </Problem>
        <Problem when="Telegram does not know that number.">
          The country code is usually the reason — no leading zero after it, and no spaces.
        </Problem>
        <Problem when="Nothing arrives within a minute.">
          Start over and send it again. Repeated attempts in quick succession make Telegram wait
          you out, so give it the full minute first.
        </Problem>
      </Troubleshoot>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 3 — kód                                                               */
/* -------------------------------------------------------------------------- */

export function CodeGuide() {
  return (
    <div className="space-y-4">
      <GuideList>
        <GuideStep n={1}>
          Open her Telegram and find the chat named <Lit>Telegram</Lit>. The code is the 5-digit
          number in the newest message there.
        </GuideStep>
        <GuideStep n={2}>
          Type it here and press <Click>Confirm code</Click>. Use the newest code — an older one
          from an earlier attempt no longer works.
        </GuideStep>
        <GuideStep n={3}>
          If her account has two-step verification, one more field appears. That is her Telegram
          cloud password, the one she set in Telegram itself. It is used for this sign-in only.
        </GuideStep>
      </GuideList>

      <Troubleshoot>
        <Problem when="The attempt expires.">
          Each attempt lives ten minutes. After that, start over and Telegram sends a fresh code.
        </Problem>
        <Problem when="“Invalid code”.">
          The digits did not match. Retype the same code carefully — it stays valid.
        </Problem>
        <Problem when="“Expired code”.">
          Telegram already retired it. Start over to get a new one.
        </Problem>
        <Problem when="Telegram asks you to wait.">
          Too many attempts in a row, so Telegram is rate-limiting this number. Wait out the time
          shown and try again; trying sooner only extends it.
        </Problem>
        <Problem when="She forgot the two-step password.">
          It can only be reset in Telegram, on her account, under Settings → Privacy and Security
          → Two-Step Verification.
        </Problem>
      </Troubleshoot>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 4 — kontrolný bot                                                     */
/* -------------------------------------------------------------------------- */

export function ControlBotGuide() {
  return (
    <div className="space-y-4">
      <GuideList>
        <GuideStep n={1}>
          In Telegram, open <GuideLink href="https://t.me/BotFather">@BotFather</GuideLink> and
          send <Lit>/newbot</Lit>.
        </GuideStep>
        <GuideStep n={2}>
          It asks for a display name — anything, for example <Lit>Lucia control</Lit>.
        </GuideStep>
        <GuideStep n={3}>
          Then a username. It has to be unique across Telegram and end with <Lit>bot</Lit>. If it
          is taken, BotFather says so and you try another.
        </GuideStep>
        <GuideStep n={4}>
          BotFather replies with a token like <Lit>123456789:AAE…</Lit>. Copy the whole line into
          the <Click>Bot token</Click> field here and save.
        </GuideStep>
        <GuideStep n={5}>
          Open your new bot through the <Lit>t.me/…</Lit> link in that same message, then send it
          the pairing code shown here. It replies <Lit>Paired</Lit> and opens the menu.
        </GuideStep>
      </GuideList>

      <Troubleshoot>
        <Problem when="You lost the token.">
          Send <Lit>/mybots</Lit> to BotFather, pick the bot, choose <Click>API Token</Click>,
          then <Click>Revoke</Click>. Paste the new token here — the old one stops working.
        </Problem>
        <Problem when="The bot does not answer the code.">
          Check that you sent it to your own bot in a private chat, that the code has not expired,
          and that the token above is saved. Generate a fresh code and send that.
        </Problem>
        <Problem when="Every username is taken.">
          Add something of your own in front of the ending, like{" "}
          <Lit>lucia_studio_control_bot</Lit>.
        </Problem>
        <Problem when="You want the notifications elsewhere later.">
          Unlink here and pair again from the other Telegram account. The bot itself stays.
        </Problem>
      </Troubleshoot>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Krok 5 — aktivácia                                                          */
/* -------------------------------------------------------------------------- */

export function ActivateGuide() {
  return (
    <Troubleshoot>
      <Problem when="Nothing happens after 30 seconds.">
        Send her a message from a different Telegram account — your own does not count unless
        you switched that on. Replies do not start instantly; she answers like a person does.
      </Problem>
      <Problem when="She went back to an error state.">
        The reason is shown on this page. Most often the sign-in expired, in which case
        reconnect her account from the top of this page.
      </Problem>
      <Problem when="No notifications reach you.">
        That is the control bot, and it is optional. She keeps replying to fans without it.
      </Problem>
    </Troubleshoot>
  );
}
