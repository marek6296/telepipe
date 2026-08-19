import { redirect } from "next/navigation";

import { LiveUnlock } from "@/components/app/live-unlock";
import { RequestAccessForm } from "@/components/app/request-access-form";
import { isUnlocked } from "@/lib/access";
import { getAccount } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

type RequestRow = {
  status: string;
  created_at: string;
  decided_note: string;
};

export default async function LockedPage() {
  const account = await getAccount();
  if (!account) redirect("/login");
  // Odomknutý sem nemá čo pozerať — inak by mu `/locked` ostalo v histórii ako
  // strašiak.
  if (isUnlocked(account)) redirect("/app");

  // RLS pustí len vlastné žiadosti, takže filter na account_id netreba.
  const supabase = await createClient();
  const { data } = await supabase
    .from("access_requests")
    .select("status, created_at, decided_note")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const request = (data as RequestRow | null) ?? null;

  return (
    <div className="app-panel p-7">
      {/* Keď Marek schváli, stránka sa prepne sama — bez refreshu. */}
      <LiveUnlock />
      <p className="text-[11px] tracking-[0.14em] text-[var(--app-text-4)] uppercase">
        TelePipe
      </p>
      <h1 className="mt-3 text-[22px] font-medium">Your account is waiting for approval</h1>

      {request?.status === "pending" ? (
        <p className="mt-4 text-[14px] leading-relaxed text-[var(--app-text-2)]">
          Request sent. We review every account by hand, so this is usually hours,
          not days — you&apos;ll hear from us as soon as it&apos;s approved.
        </p>
      ) : request?.status === "rejected" ? (
        <>
          <p className="mt-4 text-[14px] leading-relaxed text-[var(--app-text-2)]">
            Your last request wasn&apos;t approved
            {request.decided_note ? ` — ${request.decided_note}` : "."}
          </p>
          <p className="mt-2 text-[13px] text-[var(--app-text-3)]">
            You can send another one with more detail.
          </p>
          <RequestAccessForm />
        </>
      ) : (
        <>
          <p className="mt-4 text-[14px] leading-relaxed text-[var(--app-text-2)]">
            TelePipe is invite-only while we scale. Tell us briefly what you want
            to run and we&apos;ll open your account.
          </p>
          <RequestAccessForm />
        </>
      )}

      <p className="mt-8 border-t border-[var(--app-border)] pt-5 text-[12.5px] text-[var(--app-text-4)]">
        Signed in as {account.email}
      </p>
    </div>
  );
}
