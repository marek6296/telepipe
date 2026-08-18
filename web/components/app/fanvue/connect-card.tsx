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

import {
  disconnectFanvueAction,
  setFanvueEnabledAction,
} from "@/app/app/m/[id]/fanvue/actions";
import { Callout, Card, CardHeader } from "@/components/app/ui";
import { dateTime, isPast } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FanvueConnection } from "@/lib/fanvue";

/**
 * Karta pripojenia Fanvue účtu.
 *
 * Pripojenie je celé v OAuth redirecte (`/api/fanvue/start`), takže tu nie je
 * formulár — len odkaz tam, tlačidlo späť a vypínač agenta. Tokeny sa
 * v prehliadači nikdy neobjavia; server posiela iba to, čo je vidieť nižšie.
 *
 * Vypínač je ZÁMERNE samostatný krok po pripojení a default je vypnutý:
 * pripojiť účet znamená „telepipe má prístup", nie „píš mojim fanúšikom".
 * Prepína ho server action so service kľúčom — klient na `fanvue.enabled`
 * zápisový grant nemá (migrácia 011).
 *
 * ČO JE TU PORUCHA A ČO NIE
 * -------------------------
 * Vypršaný prístupový token porucha NIE JE. Fanvue mu dáva hodinu a obnovuje sa
 * z obnovovacieho tokenu — donedávna až pri prvom volaní ich API, takže modelke
 * s vypnutým agentom svietilo červené „vypršal pred hodinou" nad úplne zdravým
 * pripojením (Marek to skúšal riešiť opätovným pripojením; vydržalo hodinu).
 * Worker si ho po novom obnovuje sám, ale hlavná oprava je tu: nekričať na
 * niečo, čo je normálna prevádzka.
 *
 * Červené je preto len to, s čím musí človek naozaj niečo spraviť:
 *   * účet nie je pripojený;
 *   * Fanvue vrátilo chybu (`last_error`);
 *   * chýba obnovovací token (`canRefresh`) — vtedy sa už nemá čím obnoviť
 *     a jediná cesta je pripojiť účet znova.
 */
export function FanvueConnectCard({
  modelId,
  fanvue,
  canRefresh,
  configured,
  error,
}: {
  modelId: string;
  fanvue: FanvueConnection;
  /** Je v DB obnovovací token? RPC `has_fanvue_refresh` (migrácia 019). */
  canRefresh: boolean;
  configured: boolean;
  error: string;
}) {
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState<string | null>(null);
  // Optimistický stav prepínača: server action prekreslí stránku, ale
  // prepínač musí odpovedať hneď — inak to vyzerá, že klik nič neurobil.
  const [enabled, setEnabled] = useState(fanvue.enabled);

  const disconnect = () => {
    setFailed(null);
    startTransition(async () => {
      const result = await disconnectFanvueAction(modelId);
      if (result?.error) setFailed(result.error);
    });
  };

  const toggleAgent = () => {
    const next = !enabled;
    setFailed(null);
    setEnabled(next);
    startTransition(async () => {
      const result = await setFanvueEnabledAction(modelId, next);
      if (result?.error) {
        setEnabled(!next); // späť tam, kde to naozaj je
        setFailed(result.error);
      }
    });
  };

  const scopes = fanvue.scope.split(/\s+/).filter(Boolean);
  const expired = isPast(fanvue.expires_at);
  const healthy = fanvue.connected && canRefresh && !fanvue.last_error;

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
                {canRefresh ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(74,222,128,0.28)] px-2.5 py-1 text-[11px] font-medium text-[#86efac]">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Connected
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(248,113,113,0.28)] px-2.5 py-1 text-[11px] font-medium text-[#fca5a5]">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Reconnect required
                  </span>
                )}
                <span className="text-[15px] font-semibold text-white">
                  {fanvue.handle ? `@${fanvue.handle}` : fanvue.display_name || "Fanvue creator"}
                </span>
                {fanvue.handle && fanvue.display_name && (
                  <span className="text-[13px] text-[var(--app-text-3)]">{fanvue.display_name}</span>
                )}
              </div>

              <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
                <Row label="Access">
                  {healthy ? (
                    <span>
                      Renews automatically
                      <span className="text-[var(--app-text-4)]">
                        {" · "}
                        {/* Relatívny čas tu nesedí: `relativeTime` počíta len do
                            minulosti, takže platný token by hlásil „just now". */}
                        {expired || !fanvue.expires_at
                          ? "renewing on the next check"
                          : `valid until ${dateTime(fanvue.expires_at)}`}
                      </span>
                    </span>
                  ) : canRefresh ? (
                    // Pripojené, obnovovací token je, ale Fanvue niečo vrátilo —
                    // konkrétnu vetu ukazuje callout nižšie, tu netreba druhú.
                    <span className="text-[var(--app-text-3)]">Checking with Fanvue</span>
                  ) : (
                    <span className="text-[#fca5a5]">
                      Reconnect required — no refresh token
                    </span>
                  )}
                </Row>
                <Row label="Connected at">
                  {fanvue.updated_at ? dateTime(fanvue.updated_at) : "—"}
                </Row>
                <Row label="Creator ID">
                  <code className="break-all font-mono text-[11.5px] text-[var(--app-text-3)]">
                    {fanvue.creator_uuid || "—"}
                  </code>
                </Row>
              </dl>

              <div className="flex items-start justify-between gap-4 rounded-xl border border-[var(--app-border)] bg-[#0c0c0c] px-4 py-3">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-[var(--app-text-2)]">Agent enabled</p>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
                    When enabled, the AI replies to Fanvue messages using this
                    model&apos;s persona and credits.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={enabled}
                  aria-label="Agent enabled"
                  onClick={toggleAgent}
                  disabled={pending}
                  className={cn(
                    "relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-60",
                    enabled ? "bg-[var(--app-text)]" : "bg-[#2e2e2e]",
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
                      enabled ? "translate-x-[22px]" : "translate-x-0.5",
                    )}
                  />
                </button>
              </div>

              {scopes.length > 0 && (
                <div>
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--app-text-4)]">
                    Permissions granted
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {scopes.map((scope) => (
                      <span
                        key={scope}
                        className="rounded-md border border-[var(--app-border)] bg-[#0c0c0c] px-2 py-1 font-mono text-[11px] text-[var(--app-text-3)]"
                      >
                        {scope}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {!canRefresh && (
                <Callout tone="danger" icon={<AlertTriangle className="h-4 w-4" />}>
                  There is no refresh token for this account, so access cannot be renewed
                  once it runs out. Reconnect Fanvue to get a new one.
                </Callout>
              )}

              {fanvue.last_error && (
                <Callout tone="danger" icon={<AlertTriangle className="h-4 w-4" />}>
                  Last error from Fanvue: {fanvue.last_error}
                </Callout>
              )}

              <div className="flex flex-wrap items-center gap-2.5">
                <a href={`/api/fanvue/start?model=${modelId}`} className="app-btn app-btn-ghost h-9 px-4">
                  <ExternalLink className="h-3.5 w-3.5" />
                  Reconnect
                </a>
                <button
                  type="button"
                  onClick={disconnect}
                  disabled={pending}
                  className="app-btn app-btn-ghost h-9 px-4"
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
                <p role="alert" className="text-[11.5px] text-[#fca5a5]">
                  {failed}
                </p>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-5">
              <p className="max-w-xl text-[13.5px] leading-relaxed text-[var(--app-text-3)]">
                Not connected. You will be sent to Fanvue to sign in and approve the
                permissions. Nothing is posted or sent until you turn the Fanvue agent on.
              </p>

              {configured ? (
                <div>
                  <a
                    href={`/api/fanvue/start?model=${modelId}`}
                    className="app-btn app-btn-primary h-9 px-4"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Connect Fanvue
                  </a>
                </div>
              ) : (
                <Callout tone="danger" icon={<AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} />}>
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
      <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--app-text-4)]">
        {label}
      </dt>
      <dd className="mt-1 text-[13.5px] text-[var(--app-text-2)]">{children}</dd>
    </div>
  );
}
