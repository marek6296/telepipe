import type { Metadata } from "next";
import Link from "next/link";
import { MessageSquare, Search } from "lucide-react";

import { FunnelBadge } from "@/components/app/funnel-badge";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, EmptyState } from "@/components/app/ui";
import { chatTitle, DM_USER_COLUMNS, type DmUserRow } from "@/lib/chats";
import { compactNumber } from "@/lib/format";
import { requireModel } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Chats",
};

const PAGE_SIZE = 50;

export default async function ChatsPage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/chats">) {
  const { id } = await params;
  const query = await searchParams;
  const model = await requireModel(id);

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
      <form className="relative max-w-sm" action={`/app/m/${model.id}/chats`}>
        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-white/25" />
        <input
          name="q"
          type="search"
          defaultValue={search}
          placeholder="Search by name or @username"
          className="glass-input pl-11!"
        />
      </form>

      {chats.length === 0 ? (
        <EmptyState
          icon={<MessageSquare className="h-6 w-6" />}
          title={search ? "Nobody matches that" : "No conversations yet"}
          description={
            search
              ? "Try a different name or clear the search."
              : "Once she is live, every fan who writes to her shows up here — with the full history and what she remembers about him."
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-white/[0.05]">
            {chats.map((chat) => (
              <li key={chat.tg_id}>
                <Link
                  href={`/app/m/${model.id}/chats/${chat.tg_id}`}
                  className="flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-white/[0.03] sm:px-5"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.04] text-[13px] font-semibold text-white/60">
                    {chatTitle(chat).replace("@", "").slice(0, 1).toUpperCase()}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-[14px] font-medium text-white/90">
                        {chatTitle(chat)}
                      </span>
                      <FunnelBadge stage={chat.funnel_stage} />
                      {chat.human_takeover && (
                        <span className="rounded-full border border-white/12 px-2 py-0.5 text-[10px] uppercase tracking-[0.08em] text-white/45">
                          You took over
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block truncate text-[12px] text-white/35">
                      {chat.username ? `@${chat.username} · ` : ""}
                      {compactNumber(chat.msg_count)} messages
                    </span>
                  </span>

                  <span className="shrink-0 text-right text-[11.5px] text-white/30">
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
            href={`/app/m/${model.id}/chats?take=${take + PAGE_SIZE}${
              search ? `&q=${encodeURIComponent(search)}` : ""
            }`}
            className="btn-modern-dark h-10 px-5 text-[13px]"
          >
            Show more
          </Link>
        </div>
      )}
    </div>
  );
}
