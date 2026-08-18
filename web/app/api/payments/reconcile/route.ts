import { NextResponse, type NextRequest } from "next/server";

import { cronSecret } from "@/lib/env";
import { reconcileOpenPayments } from "@/lib/payments";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

/**
 * Backstop reconciler (Vercel cron, `web/vercel.json`). Webhook sa môže
 * stratiť a browser poller beží len s otvoreným checkoutom — toto zaručuje,
 * že zaplatená faktúra VŽDY dôjde k pripísaniu, aj o hodiny neskôr (okno
 * 72 h od založenia). Krypto potvrdenia trvajú; klient môže stránku pokojne
 * zavrieť.
 */
function authorized(request: NextRequest): boolean {
  const secret = cronSecret();
  if (!secret) return true; // nenakonfigurované (dev) → povoliť
  if (request.headers.get("authorization") === `Bearer ${secret}`) return true;
  if (request.nextUrl.searchParams.get("secret") === secret) return true;
  return false;
}

export async function GET(request: NextRequest) {
  if (!authorized(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const out = await reconcileOpenPayments();
  return NextResponse.json({ ok: true, ...out });
}
