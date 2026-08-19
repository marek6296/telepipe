import type { Metadata } from "next";
import Link from "next/link";
import { AudioLines } from "lucide-react";

import {
  ChangePasswordForm,
  ElevenLabsCard,
  SignOutEverywhereButton,
} from "@/components/app/account-forms";
import { HelpGuideButton } from "@/components/app/onboarding/guide";
import { Callout, Card, CardHeader, PageHeader } from "@/components/app/ui";
import { RelativeTime } from "@/components/app/relative-time";
import { COINS_PER_USD, COIN_NAME_PLURAL, coins } from "@/lib/coins";
import { getAccount, requireUser } from "@/lib/models";
import { getAppConfig } from "@/lib/slots";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Account",
};

export default async function AccountPage() {
  const user = await requireUser();
  const account = await getAccount();

  // Von z databázy ide jediný bit. `accounts.eleven_key_enc` si prihlásený
  // používateľ prečítať nevie (migrácia 017) a ani nemá prečo.
  const supabase = await createClient();
  const [{ data: hasEleven }, config] = await Promise.all([
    supabase.rpc("has_account_eleven_key"),
    getAppConfig(),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Account"
        description="Your sign-in details, Pipe Coin balance and the integrations shared by all your models."
        // Návod patrí sem, lebo sem chodí človek, keď nevie ďalej — nie na
        // dashboard, kde je len prehľad toho, čo už beží.
        actions={
          <HelpGuideButton
            startCoins={Math.round(config.signup_credit_usd * COINS_PER_USD)}
            label="Getting started"
          />
        }
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Sign-in"
            description="Email and password. Google sign-in is coming soon."
          />
          <dl className="divide-y divide-[var(--app-border)]">
            <Row label="Email">{account?.email ?? user.email}</Row>
            <Row label="Member since">
              <RelativeTime iso={account?.created_at ?? user.created_at} />
            </Row>
            <Row label="Signed in with">
              {user.app_metadata?.provider === "google" ? "Google" : "Email and password"}
            </Row>
          </dl>
        </Card>

        <Card>
          <CardHeader
            title="Pipe Coin balance"
            description="No subscription — you buy Pipe Coins and spend them as she works. Top up with crypto on the Billing page."
          />
          <div className="p-5">
            <p className="text-[32px] font-semibold leading-none tracking-[-0.03em] tabular-nums text-[var(--app-text)]">
              {coins(account?.credit_balance_usd)}
            </p>
            <p className="mt-2 text-[12.5px] text-[var(--app-text-3)]">
              {COIN_NAME_PLURAL} left · they never expire
            </p>
            <Link href="/app/billing" className="app-btn app-btn-primary mt-5 h-9 px-4">
              Buy Pipe Coins
            </Link>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="ElevenLabs"
            description="Her own voice. Connect the account once here — then pick a voice for each model on its Voice tab."
            icon={<AudioLines className="h-4 w-4" strokeWidth={1.75} />}
          />
          <ElevenLabsCard connected={Boolean(hasEleven)} />
        </Card>

        <Card>
          <CardHeader
            title="Change password"
            description="You will need your current password."
          />
          <ChangePasswordForm />
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Sessions"
              description="Signed in on a device you no longer have? Kick every session out."
            />
            <div className="p-5">
              <SignOutEverywhereButton />
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Delete account"
              description="Removes your models, conversations and history for good."
            />
            <div className="space-y-4 p-5">
              <Callout tone="neutral">
                Self-service deletion is not live yet. Write to us and we will wipe
                everything within 24 hours.
              </Callout>
              <button type="button" disabled className="app-btn app-btn-ghost h-9 px-4">
                Delete account
              </button>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-3.5 text-[13px]">
      <dt className="text-[var(--app-text-3)]">{label}</dt>
      <dd className="truncate text-[var(--app-text)]">{children}</dd>
    </div>
  );
}
