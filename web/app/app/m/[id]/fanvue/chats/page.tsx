import type { Metadata } from "next";
import Link from "next/link";
import { MessageSquare, Search } from "lucide-react";

import { FvStageBadge } from "@/components/app/fv-stage-badge";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, EmptyState } from "@/components/app/ui";
import { compactNumber } from "@/lib/format";
import { centsToUsd, fvChatTitle, FV_USER_COLUMNS, type FvUserRow } from "@/lib/fv-chats";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Fanvue chats",
};

const PAGE_SIZE = 50;

/**
 * Konverzácie na Fanvue (`fv_users`). Čítanie, nič viac — písať sa tam dá len
 * cez ich API a robí to worker; policy z migrácie 012 dáva majiteľovi SELECT
 * a nič iné.
 */
export default async function FanvueChatsPage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/fanvue/chats">) {
  const { id } = await params;
  const query = await searchParams;
  const model = await requireModelSubTab(id, "fanvue", "chats");

  const search = typeof query?.q === "string" ? query.q.trim() : "";
  const take = Math.min(Number(query?.take ?? PAGE_SIZE) || PAGE_SIZE, 500);

  const supabase = await createClient();
  let request = supabase
    .from("fv_users")
    .select(FV_USER_COLUMNS)
    .eq("model_id", model.id)
    // Index `fv_users_active_idx` je presne na tomto poradí.
    .order("last_incoming_at", { ascending: false, nullsFirst: false })
    .limit(take);

  if (search) {
    // PostgREST `or` — hodnotu treba zbaviť čiarok, inak rozbije filter.
    const safe = search.replace(/[,()]/g, " ").trim();
    request = request.or(`handle.ilike.%${safe}%,display_name.ilike.%${safe}%`);
  }

  const { data } = await request;
  const chats = (data ?? []) as unknown as FvUserRow[];

  return (
    <div className="space-y-4">
      <form className="relative max-w-sm" action={`/app/m/${model.id}/fanvue/chats`}>
        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-text-4)]" />
        <input
          name="q"
          type="search"
          defaultValue={search}
          placeholder="Search by name or @handle"
          className="app-input pl-11!"
        />
      </form>

      {chats.length === 0 ? (
        <EmptyState
          icon={<MessageSquare className="h-[18px] w-[18px]" strokeWidth={1.5} />}
          title={search ? "Nobody matches that" : "No Fanvue conversations yet"}
          description={
            search
              ? "Try a different name or clear the search."
              : "Once her Fanvue agent is connected and switched on, every subscriber she talks to shows up here — with the full history and what he has spent."
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-[var(--app-border)]">
            {chats.map((chat) => (
              <li key={chat.fan_uuid}>
                <Link
                  href={`/app/m/${model.id}/fanvue/chats/${encodeURIComponent(chat.fan_uuid)}`}
                  className="flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-[var(--app-surface-hover)] sm:px-5"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--app-border)] bg-[#111111] text-[13px] font-semibold text-[var(--app-text-2)]">
                    {fvChatTitle(chat).replace("@", "").slice(0, 1).toUpperCase()}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-[14px] font-medium text-[var(--app-text)]">
                        {fvChatTitle(chat)}
                      </span>
                      <FvStageBadge stage={chat.stage} />
                      {chat.human_takeover && (
                        <span className="rounded-full border border-[var(--app-border)] px-2 py-0.5 text-[10px] uppercase tracking-[0.08em] text-[var(--app-text-3)]">
                          You took over
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block truncate text-[12px] text-[var(--app-text-4)]">
                      {chat.handle ? `@${chat.handle} · ` : ""}
                      {compactNumber(chat.msg_count)} messages
                      {chat.spent_cents > 0 ? ` · ${centsToUsd(chat.spent_cents)} spent` : ""}
                    </span>
                  </span>

                  <span className="shrink-0 text-right text-[11.5px] text-[var(--app-text-4)]">
                    <RelativeTime iso={chat.last_incoming_at} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {chats.length === take && (
        <div className="flex justify-center">
          <Link
            href={`/app/m/${model.id}/fanvue/chats?take=${take + PAGE_SIZE}${
              search ? `&q=${encodeURIComponent(search)}` : ""
            }`}
            className="app-btn app-btn-ghost h-9 px-4"
          >
            Show more
          </Link>
        </div>
      )}
    </div>
  );
}
