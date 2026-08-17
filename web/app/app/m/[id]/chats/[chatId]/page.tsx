import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";

import { FunnelBadge } from "@/components/app/funnel-badge";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, CardHeader, StatTile } from "@/components/app/ui";
import {
  chatTitle,
  DM_USER_COLUMNS,
  FUNNEL_HINT,
  type DmMessageRow,
  type DmUserRow,
} from "@/lib/chats";
import { compactNumber } from "@/lib/format";
import { requireModel } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Conversation",
};

const PAGE_SIZE = 50;

export default async function ChatDetailPage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/chats/[chatId]">) {
  const { id, chatId } = await params;
  const query = await searchParams;
  const model = await requireModel(id);

  const tgId = Number(chatId);
  if (!Number.isSafeInteger(tgId)) notFound();

  const take = Math.min(Number(query?.take ?? PAGE_SIZE) || PAGE_SIZE, 1000);

  const supabase = await createClient();
  const [{ data: userRow }, { data: messageRows }, { data: factRows }] = await Promise.all([
    supabase
      .from("dm_users")
      .select(DM_USER_COLUMNS)
      .eq("model_id", model.id)
      .eq("tg_id", tgId)
      .maybeSingle(),
    supabase
      .from("dm_messages")
      .select("id, role, content, created_at")
      .eq("model_id", model.id)
      .eq("tg_id", tgId)
      .order("id", { ascending: false })
      .limit(take),
    supabase
      .from("facts")
      .select("id, key, value, last_confirmed")
      .eq("model_id", model.id)
      .eq("tg_id", tgId)
      .is("superseded_by", null)
      .order("last_confirmed", { ascending: false })
      .limit(40),
  ]);

  if (!userRow) notFound();

  const chat = userRow as unknown as DmUserRow;
  // Najnovšie ťaháme prvé (index na to má), zobrazujeme chronologicky.
  const messages = ((messageRows ?? []) as unknown as DmMessageRow[]).slice().reverse();
  const facts = (factRows ?? []) as { id: number; key: string; value: string }[];
  const hasMore = (messageRows ?? []).length === take;

  return (
    <div className="space-y-5">
      <Link
        href={`/app/m/${model.id}/chats`}
        className="inline-flex items-center gap-1 text-[12.5px] text-[var(--app-text-4)] transition-colors hover:text-[var(--app-text)]"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        All conversations
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[20px] font-semibold text-white">{chatTitle(chat)}</h2>
        <FunnelBadge stage={chat.funnel_stage} />
        {chat.paid && (
          <span className="rounded-full border border-[var(--app-border-strong)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--app-text-2)]">
            Paid
          </span>
        )}
      </div>
      <p className="-mt-2 text-[12.5px] text-[var(--app-text-4)]">
        {FUNNEL_HINT[chat.funnel_stage] ?? ""}
      </p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Messages" value={compactNumber(chat.msg_count)} />
        <StatTile
          label="Last message"
          value={<RelativeTime iso={chat.last_incoming_at} />}
          hint="from him"
        />
        <StatTile
          label="Last reply"
          value={<RelativeTime iso={chat.last_reply_at} />}
          hint="from her"
        />
        <StatTile
          label="First seen"
          value={<RelativeTime iso={chat.created_at} />}
        />
      </div>

      {(chat.summary || chat.style_note || facts.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {(chat.summary || chat.style_note) && (
            <Card>
              <CardHeader
                title="What she remembers"
                description="Her rolling summary of this conversation."
              />
              <div className="space-y-3 p-5 text-[13px] leading-relaxed text-[var(--app-text-2)]">
                {chat.summary ? (
                  <p className="whitespace-pre-wrap">{chat.summary}</p>
                ) : (
                  <p className="text-[var(--app-text-4)]">Nothing summarised yet.</p>
                )}
                {chat.style_note && (
                  <p className="rounded-xl border border-[var(--app-border)] bg-[#0c0c0c] px-3.5 py-2.5 text-[12.5px] text-[var(--app-text-3)]">
                    <span className="text-[var(--app-text-4)]">How he writes: </span>
                    {chat.style_note}
                  </p>
                )}
              </div>
            </Card>
          )}

          {facts.length > 0 && (
            <Card>
              <CardHeader
                title="What she knows about him"
                description="Facts she picked up along the way."
              />
              <ul className="divide-y divide-[var(--app-border)]">
                {facts.map((fact) => (
                  <li key={fact.id} className="flex gap-3 px-5 py-2.5 text-[12.5px]">
                    <span className="w-32 shrink-0 truncate text-[var(--app-text-4)]">{fact.key}</span>
                    <span className="min-w-0 flex-1 text-[var(--app-text-2)]">{fact.value}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      <Card>
        <CardHeader
          title="Conversation"
          description="Read-only — replying happens in Telegram through your control bot."
        />
        <div className="space-y-3 p-5">
          {hasMore && (
            <div className="flex justify-center pb-2">
              <Link
                href={`/app/m/${model.id}/chats/${chat.tg_id}?take=${take + PAGE_SIZE}`}
                className="app-btn app-btn-ghost h-9 px-4"
              >
                Load older messages
              </Link>
            </div>
          )}

          {messages.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-[var(--app-text-4)]">No messages yet.</p>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "flex",
                  message.role === "assistant" ? "justify-end" : "justify-start",
                )}
              >
                <div
                  className={cn(
                    "max-w-[78%] rounded-lg px-3.5 py-2.5 text-[13.5px] leading-relaxed",
                    message.role === "assistant"
                      ? "rounded-br-sm bg-[#1f1f1f] text-[var(--app-text)]"
                      : "rounded-bl-md bg-[#141414] text-[var(--app-text-2)]",
                  )}
                >
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  <p
                    className={cn(
                      "mt-1 text-[10.5px]",
                      message.role === "assistant" ? "text-[#f7e9c4]/45" : "text-[var(--app-text-4)]",
                    )}
                  >
                    <RelativeTime iso={message.created_at} />
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
