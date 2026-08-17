import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Brain, ChevronLeft, Link2, Sparkles } from "lucide-react";

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
        className="inline-flex items-center gap-1 text-[12.5px] text-white/35 transition-colors hover:text-[var(--gold-light)]"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        All conversations
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[20px] font-semibold text-white">{chatTitle(chat)}</h2>
        <FunnelBadge stage={chat.funnel_stage} />
        {chat.paid && (
          <span className="rounded-full border border-[rgba(212,175,55,0.4)] bg-[rgba(212,175,55,0.1)] px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-[var(--gold-light)]">
            Paid
          </span>
        )}
      </div>
      <p className="-mt-2 text-[12.5px] text-white/35">
        {FUNNEL_HINT[chat.funnel_stage] ?? ""}
      </p>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
          icon={<Link2 className="h-3.5 w-3.5 text-[var(--gold)]/70" />}
        />
      </div>

      {(chat.summary || chat.style_note || facts.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {(chat.summary || chat.style_note) && (
            <Card>
              <CardHeader
                icon={<Brain className="h-4 w-4" />}
                title="What she remembers"
                description="Her rolling summary of this conversation."
              />
              <div className="space-y-3 p-5 text-[13px] leading-relaxed text-white/60">
                {chat.summary ? (
                  <p className="whitespace-pre-wrap">{chat.summary}</p>
                ) : (
                  <p className="text-white/30">Nothing summarised yet.</p>
                )}
                {chat.style_note && (
                  <p className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-2.5 text-[12.5px] text-white/45">
                    <span className="text-white/30">How he writes: </span>
                    {chat.style_note}
                  </p>
                )}
              </div>
            </Card>
          )}

          {facts.length > 0 && (
            <Card>
              <CardHeader
                icon={<Sparkles className="h-4 w-4" />}
                title="What she knows about him"
                description="Facts she picked up along the way."
              />
              <ul className="divide-y divide-white/[0.05]">
                {facts.map((fact) => (
                  <li key={fact.id} className="flex gap-3 px-5 py-2.5 text-[12.5px]">
                    <span className="w-32 shrink-0 truncate text-white/35">{fact.key}</span>
                    <span className="min-w-0 flex-1 text-white/70">{fact.value}</span>
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
                className="btn-modern-dark h-9 px-4 text-[12.5px]"
              >
                Load older messages
              </Link>
            </div>
          )}

          {messages.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-white/30">No messages yet.</p>
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
                    "max-w-[78%] rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed",
                    message.role === "assistant"
                      ? "rounded-br-md bg-[linear-gradient(160deg,rgba(212,175,55,0.22),rgba(212,175,55,0.1))] text-[#f7e9c4]"
                      : "rounded-bl-md bg-white/[0.05] text-white/80",
                  )}
                >
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                  <p
                    className={cn(
                      "mt-1 text-[10.5px]",
                      message.role === "assistant" ? "text-[#f7e9c4]/45" : "text-white/25",
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
