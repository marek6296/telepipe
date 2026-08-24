import Link from "next/link";
import { Check, CircleAlert, ExternalLink } from "lucide-react";

import { Callout, Card, CardHeader } from "@/components/app/ui";
import { daysLeft, type InstagramRow } from "@/lib/instagram";

/**
 * Stav pripojenia + návod, čo má klient urobiť.
 *
 * NÁVOD JE SÚČASŤ PRODUKTU, nie výplň. Väčšina modeliek má osobný Instagram
 * účet a o „profesionálnom účte" nikdy nepočula — bez týchto štyroch krokov
 * klikne Connect, Meta ho odmietne a on to vzdá. Preto sú kroky napísané
 * presne tak, ako vyzerajú v aplikácii Instagramu.
 *
 * Serverový komponent: nič sa tu neklika okrem odkazu na `/api/instagram/start`,
 * ktorý sám presmeruje na Metu.
 */
export function InstagramConnect({
  modelId,
  row,
  configured,
}: {
  modelId: string;
  row: InstagramRow;
  configured: boolean;
}) {
  const dni = daysLeft(row.token_expires_at);

  return (
    <div className="flex flex-col gap-5">
      {!configured && (
        <Callout tone="danger">
          Instagram is not switched on for this deployment — the Meta app id and secret
          are missing. Connecting will not work until they are set.
        </Callout>
      )}

      {row.last_error && (
        <Callout tone="danger">
          Instagram last said: {row.last_error}
        </Callout>
      )}

      <Card>
        <CardHeader
          title={row.connected ? "Connected" : "Not connected yet"}
          description={
            row.connected
              ? "Her Instagram DMs come to us through Instagram's own API — no password, no logging in as her."
              : "This uses Instagram's official API. She keeps her password, and the account is not at risk of a ban for automation."
          }
        />
        <div className="p-5">
          {row.connected ? (
            <div className="space-y-3">
              <Riadok label="Account" value={row.username ? `@${row.username}` : "—"} />
              <Riadok
                label="Account type"
                value={row.account_type ? row.account_type.toLowerCase() : "—"}
              />
              <Riadok
                label="Access expires"
                value={
                  dni === null
                    ? "unknown"
                    : dni > 14
                      ? `in ${dni} days — renews itself`
                      : `in ${dni} days`
                }
              />
              <p className="pt-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
                Instagram access lasts 60 days and we renew it for you every night. It only
                dies if this dashboard cannot reach Instagram for two months straight — then
                you simply connect again.
              </p>
              <div className="pt-2">
                <a
                  href={`/api/instagram/start?model=${modelId}`}
                  className="app-btn app-btn-ghost h-9 px-4"
                >
                  Reconnect
                </a>
              </div>
            </div>
          ) : (
            <a
              href={configured ? `/api/instagram/start?model=${modelId}` : undefined}
              aria-disabled={!configured}
              className={`app-btn app-btn-primary h-10 px-5 ${
                configured ? "" : "pointer-events-none opacity-50"
              }`}
            >
              Connect Instagram
              <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} />
            </a>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Before you connect"
          description="Instagram only lets apps into professional accounts. Two minutes in the Instagram app, and it is free."
        />
        <ol className="divide-y divide-[var(--app-border)]">
          <Krok
            cislo={1}
            title="Switch her account to professional"
            text="In the Instagram app: Settings → Account type and tools → Switch to professional account. Pick Creator — it is meant for exactly this and keeps the profile looking personal."
          />
          <Krok
            cislo={2}
            title="You do not need a Facebook page"
            text="Instagram asks about linking one during the switch. Skip it. This connection works without it — we use Instagram's own login, not Facebook's."
          />
          <Krok
            cislo={3}
            title="Make sure DMs from strangers are allowed"
            text="Settings → Messages and story replies → Message controls. If her account only accepts messages from people she follows, the agent will have nothing to answer."
          />
          <Krok
            cislo={4}
            title="Come back here and press Connect"
            text="Instagram will ask her to log in and approve access to messages and comments. She keeps her password — we never see it."
          />
        </ol>
      </Card>

      <Card>
        <CardHeader
          title="What her Instagram agent will and will not do"
          description="Instagram is a public platform with much tighter rules than Telegram. The agent is built to survive there, not to push."
        />
        <ul className="space-y-2.5 p-5 text-[13px] leading-relaxed text-[var(--app-text-2)]">
          <Bod ano>Answers DMs in her voice — the same persona as her Telegram agent</Bod>
          <Bod ano>Points people to your Telegram or your link in bio</Bod>
          <Bod ano>Keeps it flirty at most, never explicit</Bod>
          <Bod>Never sends your Fanvue or OnlyFans link — that is how accounts get banned</Bod>
          <Bod>Never sends photos or voice notes here</Bod>
          <Bod>Never messages people first</Bod>
        </ul>
      </Card>

      <p className="px-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
        Her persona, languages and daily life are shared with the other agents — set them on{" "}
        <Link
          href={`/app/m/${modelId}/persona`}
          className="underline underline-offset-2 transition-colors hover:text-[var(--app-text-2)]"
        >
          the Persona tab
        </Link>
        . Only what is on this tab is Instagram-specific.
      </p>
    </div>
  );
}

function Riadok({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-[12.5px] text-[var(--app-text-3)]">{label}</span>
      <span className="text-[13px] text-[var(--app-text)]">{value}</span>
    </div>
  );
}

function Krok({ cislo, title, text }: { cislo: number; title: string; text: string }) {
  return (
    <li className="flex gap-3.5 p-5">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--app-border-strong)] text-[11.5px] text-[var(--app-text-3)]">
        {cislo}
      </span>
      <span className="min-w-0">
        <span className="block text-[13px] font-medium text-[var(--app-text)]">{title}</span>
        <span className="mt-1 block text-[12.5px] leading-relaxed text-[var(--app-text-3)]">
          {text}
        </span>
      </span>
    </li>
  );
}

function Bod({ children, ano = false }: { children: React.ReactNode; ano?: boolean }) {
  return (
    <li className="flex items-start gap-2.5">
      {ano ? (
        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--app-up)]" strokeWidth={2} />
      ) : (
        <CircleAlert
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--app-text-4)]"
          strokeWidth={2}
        />
      )}
      <span>{children}</span>
    </li>
  );
}
