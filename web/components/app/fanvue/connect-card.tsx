"use client";

import { useState, useTransition } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Link2,
  Loader2,
  Unlink,
} from "lucide-react";

import { disconnectFanvueAction } from "@/app/app/m/[id]/fanvue/actions";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { RelativeTime } from "@/components/app/relative-time";
import { dateTime, isPast } from "@/lib/format";
import type { FanvueConnection } from "@/lib/fanvue";

/**
 * Karta pripojenia Fanvue účtu.
 *
 * Pripojenie je celé v OAuth redirecte (`/api/fanvue/start`), takže tu nie je
 * formulár — len odkaz tam a tlačidlo späť. Tokeny sa v prehliadači nikdy
 * neobjavia; server posiela iba to, čo je vidieť nižšie.
 */
export function FanvueConnectCard({
  modelId,
  fanvue,
  configured,
  error,
}: {
  modelId: string;
  fanvue: FanvueConnection;
  configured: boolean;
  error: string;
}) {
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState<string | null>(null);

  const disconnect = () => {
    setFailed(null);
    startTransition(async () => {
      const result = await disconnectFanvueAction(modelId);
      if (result?.error) setFailed(result.error);
    });
  };

  const scopes = fanvue.scope.split(/\s+/).filter(Boolean);
  const expired = isPast(fanvue.expires_at);

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <Callout tone="danger" icon={<AlertTriangle className="h-4 w-4" />}>
          {error}
        </Callout>
      )}

      <Card>
        <CardHeader
          title="Fanvue account"
          description="Connect her Fanvue creator account so the agent can read chats and reply there."
          icon={<Link2 className="h-4 w-4" />}
        />

        <div className="px-5 py-5">
          {fanvue.connected ? (
            <div className="flex flex-col gap-5">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[#2e7d52]/45 bg-[#0f2a1d] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8ff0bb]">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Connected
                </span>
                <span className="text-[15px] font-semibold text-white">
                  {fanvue.handle ? `@${fanvue.handle}` : fanvue.display_name || "Fanvue creator"}
                </span>
                {fanvue.handle && fanvue.display_name && (
                  <span className="text-[13px] text-white/40">{fanvue.display_name}</span>
                )}
              </div>

              <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                <Row label="Access token expires">
                  {fanvue.expires_at ? (
                    <span className={expired ? "text-[#ffb3a7]" : undefined}>
                      <RelativeTime iso={fanvue.expires_at} />
                      {expired && " — the worker will refresh it"}
                    </span>
                  ) : (
                    "—"
                  )}
                </Row>
                <Row label="Connected at">
                  {fanvue.updated_at ? dateTime(fanvue.updated_at) : "—"}
                </Row>
                <Row label="Creator ID">
                  <code className="break-all font-mono text-[11.5px] text-white/50">
                    {fanvue.creator_uuid || "—"}
                  </code>
                </Row>
                <Row label="Replies on Fanvue">
                  {fanvue.enabled ? "On" : "Off — coming with the Fanvue agent"}
                </Row>
              </dl>

              {scopes.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-white/35">
                    Permissions granted
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {scopes.map((scope) => (
                      <span
                        key={scope}
                        className="rounded-md border border-white/[0.08] bg-white/[0.03] px-2 py-1 font-mono text-[11px] text-white/50"
                      >
                        {scope}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {fanvue.last_error && (
                <Callout tone="danger" icon={<AlertTriangle className="h-4 w-4" />}>
                  Last error from Fanvue: {fanvue.last_error}
                </Callout>
              )}

              <div className="flex flex-wrap items-center gap-2.5">
                <a href={`/api/fanvue/start?model=${modelId}`} className="btn-modern-dark h-10 px-5 text-[13px]">
                  <ExternalLink className="h-3.5 w-3.5" />
                  Reconnect
                </a>
                <button
                  type="button"
                  onClick={disconnect}
                  disabled={pending}
                  className="btn-modern-dark h-10 px-5 text-[13px]"
                >
                  {pending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Unlink className="h-3.5 w-3.5" />
                  )}
                  Disconnect
                </button>
              </div>
              {failed && (
                <p role="alert" className="text-[11.5px] text-[#ffb3a7]">
                  {failed}
                </p>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-5">
              <p className="max-w-xl text-[13.5px] leading-relaxed text-white/45">
                Not connected. You will be sent to Fanvue to sign in and approve the
                permissions. Nothing is posted or sent until you turn the Fanvue agent on.
              </p>

              {configured ? (
                <div>
                  <a
                    href={`/api/fanvue/start?model=${modelId}`}
                    className="btn-modern-light h-10 px-5 text-[13px]"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Connect Fanvue
                  </a>
                </div>
              ) : (
                <Callout tone="gold" icon={<AlertTriangle className="h-4 w-4" />}>
                  Fanvue is not configured on this deployment yet
                  (<code className="font-mono">FANVUE_CLIENT_ID</code> /{" "}
                  <code className="font-mono">FANVUE_CLIENT_SECRET</code>).
                </Callout>
              )}
            </div>
          )}
        </div>
      </Card>

      <Callout tone="neutral">
        Fanvue sends every event (new message, new subscriber, payment) to one shared
        webhook address. Telepipe stores them per model and the worker answers from the
        queue — so a slow reply never makes Fanvue drop a delivery.
      </Callout>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-white/35">
        {label}
      </dt>
      <dd className="mt-1 text-[13.5px] text-white/70">{children}</dd>
    </div>
  );
}
