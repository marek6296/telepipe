import type { Metadata } from "next";
import Link from "next/link";
import { MessageSquare, Search } from "lucide-react";

import { FunnelBadge } from "@/components/app/funnel-badge";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, EmptyState } from "@/components/app/ui";
import { chatTitle, DM_USER_COLUMNS, type DmUserRow } from "@/lib/chats";
import { compactNumber } from "@/lib/format";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Telegram chats",
};

const PAGE_SIZE = 50;

/**
 * Telegramové konverzácie (`dm_users`/`dm_messages`). Fanvue má vlastné pod
 * `/fanvue/chats` — sú to dvaja agenti a dve histórie, nie jeden zoznam
 * s prepínačom.
 */
export default async function ChatsPage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/telegram/chats">) {
  const { id } = await params;
  const query = await searchParams;
  const model = await requireModelSubTab(id, "telegram", "chats");

  const search = typeof query?.q === "string" ? query.q.trim() : "";
  const take = Math.min(Number(query?.take ?? PAGE_SIZE) || PAGE_SIZE, 500);

  const supabase = await createClient();
  let request = supabase
    .from("dm_users")
    .select(DM_USER_COLUMNS)
    .eq("model_id", model.id)
    .order("last_incoming_at", { ascending: false, nullsFirst: false })
    .limit(take);

  if (search) {
    // PostgREST `or` — hodnotu treba zbaviť čiarok, inak rozbije filter.
    const safe = search.replace(/[,()]/g, " ").trim();
    request = request.or(
      `username.ilike.%${safe}%,first_name.ilike.%${safe}%,partner_name.ilike.%${safe}%`,
    );
  }

  const { data } = await request;
  const chats = (data ?? []) as unknown as DmUserRow[];

  return (
    <div className="space-y-4">
      <form className="relative max-w-sm" action={`/app/m/${model.id}/telegram/chats`}>
        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-text-4)]" />
        <input
          name="q"
          type="search"
          defaultValue={search}
          placeholder="Search by name or @username"
          className="app-input pl-11!"
        />
      </form>

      {chats.length === 0 ? (
        <EmptyState
          icon={<MessageSquare className="h-[18px] w-[18px]" strokeWidth={1.5} />}
          title={search ? "Nobody matches that" : "No conversations yet"}
          description={
            search
              ? "Try a different name or clear the search."
              : "Once she is live, every fan who writes to her shows up here — with the full history and what she remembers about him."
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-[var(--app-border)]">
            {chats.map((chat) => (
              <li key={chat.tg_id}>
                <Link
                  href={`/app/m/${model.id}/telegram/chats/${chat.tg_id}`}
                  className="flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-[var(--app-surface-hover)] sm:px-5"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--app-border)] bg-[#111111] text-[13px] font-semibold text-[var(--app-text-2)]">
                    {chatTitle(chat).replace("@", "").slice(0, 1).toUpperCase()}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-[14px] font-medium text-[var(--app-text)]">
                        {chatTitle(chat)}
                      </span>
                      <FunnelBadge stage={chat.funnel_stage} />
                      {chat.human_takeover && (
                        <span className="rounded-full border border-[var(--app-border)] px-2 py-0.5 text-[10px] uppercase tracking-[0.08em] text-[var(--app-text-3)]">
                          You took over
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block truncate text-[12px] text-[var(--app-text-4)]">
                      {chat.username ? `@${chat.username} · ` : ""}
                      {compactNumber(chat.msg_count)} messages
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
            href={`/app/m/${model.id}/telegram/chats?take=${take + PAGE_SIZE}${
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
