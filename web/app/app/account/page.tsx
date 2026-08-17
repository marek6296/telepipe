import type { Metadata } from "next";
import { AtSign, KeyRound, ShieldCheck, Trash2, Wallet } from "lucide-react";

import {
  ChangePasswordForm,
  SignOutEverywhereButton,
} from "@/components/app/account-forms";
import { Callout, Card, CardHeader, PageHeader } from "@/components/app/ui";
import { RelativeTime } from "@/components/app/relative-time";
import { toNumber, usd } from "@/lib/format";
import { getAccount, requireUser } from "@/lib/models";

export const metadata: Metadata = {
  title: "Account",
};

export default async function AccountPage() {
  const user = await requireUser();
  const account = await getAccount();

  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Account"
        description="Your sign-in details and credit balance."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            icon={<AtSign className="h-4 w-4" />}
            title="Sign-in"
            description="Email and password. Google sign-in is coming soon."
          />
          <dl className="divide-y divide-white/[0.05]">
            <Row label="Email">{account?.email ?? user.email}</Row>
            <Row label="Member since">
              <RelativeTime iso={account?.created_at ?? user.created_at} />
            </Row>
            <Row label="Signed in with">
              {user.app_metadata?.provider === "google" ? "Google" : "Email and password"}
            </Row>
          </dl>
        </Card>

        <Card gold>
          <CardHeader
            icon={<Wallet className="h-4 w-4" />}
            title="Credit balance"
            description="Top-ups are handled by us while we are in early access."
          />
          <div className="p-5">
            <p className="text-[36px] font-semibold leading-none tracking-tight text-gradient-gold">
              {usd(toNumber(account?.credit_balance_usd))}
            </p>
            <a
              href="mailto:support@telepipe.app?subject=Telepipe%20top-up"
              className="btn-modern-light mt-5 h-10 px-5 text-[13px]"
            >
              Contact us to top up
            </a>
          </div>
        </Card>

        <Card>
          <CardHeader
            icon={<KeyRound className="h-4 w-4" />}
            title="Change password"
            description="You will need your current password."
          />
          <ChangePasswordForm />
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              icon={<ShieldCheck className="h-4 w-4" />}
              title="Sessions"
              description="Signed in on a device you no longer have? Kick every session out."
            />
            <div className="p-5">
              <SignOutEverywhereButton />
            </div>
          </Card>

          <Card>
            <CardHeader
              icon={<Trash2 className="h-4 w-4" />}
              title="Delete account"
              description="Removes your models, conversations and history for good."
            />
            <div className="space-y-4 p-5">
              <Callout tone="neutral">
                Self-service deletion is not live yet. Write to us and we will wipe
                everything within 24 hours.
              </Callout>
              <button type="button" disabled className="btn-modern-dark h-10 px-5 text-[13px]">
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
      <dt className="text-white/40">{label}</dt>
      <dd className="truncate text-white/85">{children}</dd>
    </div>
  );
}
