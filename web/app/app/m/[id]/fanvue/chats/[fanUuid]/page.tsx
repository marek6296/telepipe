import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";

import { FvStageBadge } from "@/components/app/fv-stage-badge";
import { RelativeTime } from "@/components/app/relative-time";
import { Card, CardHeader, StatTile } from "@/components/app/ui";
import { compactNumber } from "@/lib/format";
import {
  centsToUsd,
  fvChatTitle,
  parseFvFacts,
  FV_STAGE_HINT,
  FV_USER_COLUMNS,
  type FvMessageRow,
  type FvUserRow,
} from "@/lib/fv-chats";
import { requireModelSubTab } from "@/lib/models";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Fanvue conversation",
};

const PAGE_SIZE = 50;

/**
 * Jeden fanvue rozhovor. Rovnaký tvar ako telegramový detail, aby si klient
 * nemusel zvykať dvakrát — len tabuľky sú `fv_*` a namiesto funnelu je tu to,
 * čo u nej minul.
 *
 * `fanUuid` je text z ich API, nie číslo — do URL ide zakódovaný a späť sa
 * dekóduje. Nekontrolujeme jeho tvar; keď taký fanúšik neexistuje, dotaz nič
 * nevráti a stránka je 404.
 */
export default async function FanvueChatDetailPage({
  params,
  searchParams,
}: PageProps<"/app/m/[id]/fanvue/chats/[fanUuid]">) {
  const { id, fanUuid } = await params;
  const query = await searchParams;
  const model = await requireModelSubTab(id, "fanvue", "chats");

  const uuid = decodeURIComponent(fanUuid);
  const take = Math.min(Number(query?.take ?? PAGE_SIZE) || PAGE_SIZE, 1000);

  const supabase = await createClient();
  const [{ data: userRow }, { data: messageRows }] = await Promise.all([
    supabase
      .from("fv_users")
      .select(FV_USER_COLUMNS)
      .eq("model_id", model.id)
      .eq("fan_uuid", uuid)
      .maybeSingle(),
    supabase
      .from("fv_messages")
      .select("id, role, content, created_at")
      .eq("model_id", model.id)
      .eq("fan_uuid", uuid)
      // Index `fv_messages_fan_idx` je na `(model_id, fan_uuid, id desc)`.
      .order("id", { ascending: false })
      .limit(take),
  ]);

  if (!userRow) notFound();

  const chat = userRow as unknown as FvUserRow;
  // Najnovšie ťaháme prvé (index na to má), zobrazujeme chronologicky.
  const messages = ((messageRows ?? []) as unknown as FvMessageRow[]).slice().reverse();
  const facts = parseFvFacts(chat.facts ?? "");
  const hasMore = (messageRows ?? []).length === take;

  return (
    <div className="space-y-5">
      <Link
        href={`/app/m/${model.id}/fanvue/chats`}
        className="inline-flex items-center gap-1 text-[12.5px] text-[var(--app-text-4)] transition-colors hover:text-[var(--app-text)]"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
        All Fanvue conversations
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[20px] font-semibold text-white">{fvChatTitle(chat)}</h2>
        <FvStageBadge stage={chat.stage} />
        {chat.tg_id !== null && (
          <span
            className="rounded-full border border-[var(--app-border-strong)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--app-text-2)]"
            title="She matched him with a Telegram chat, so she remembers what they talked about there."
          >
            Same person on Telegram
          </span>
        )}
        {chat.human_takeover && (
          <span className="rounded-full border border-[var(--app-border)] px-2.5 py-0.5 text-[11px] text-[var(--app-text-3)]">
            You took over
          </span>
        )}
      </div>
      <p className="-mt-2 text-[12.5px] text-[var(--app-text-4)]">
        {FV_STAGE_HINT[chat.stage] ?? ""}
      </p>

      <div className="grid grid-cols-1 gap-3 min-[460px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
        <StatTile label="Messages" value={compactNumber(chat.msg_count)} />
        <StatTile
          label="Spent"
          value={centsToUsd(chat.spent_cents)}
          hint={`${compactNumber(chat.bought_count)} purchases`}
        />
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
      </div>

      {(chat.summary || chat.wants || facts.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {(chat.summary || chat.wants) && (
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
                {chat.wants && (
                  <p className="rounded-xl border border-[var(--app-border)] bg-[#0c0c0c] px-3.5 py-2.5 text-[12.5px] text-[var(--app-text-3)]">
                    <span className="text-[var(--app-text-4)]">What he is here for: </span>
                    {chat.wants}
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
                {facts.map((fact, index) => (
                  <li
                    key={`${fact.key}-${index}`}
                    className="flex gap-3 px-5 py-2.5 text-[12.5px]"
                  >
                    <span className="w-32 shrink-0 truncate text-[var(--app-text-4)]">
                      {fact.key}
                    </span>
                    <span className="min-w-0 flex-1 text-[var(--app-text-2)]">
                      {fact.value}
                    </span>
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
          description="Read-only — replying happens on Fanvue, and only she writes here."
        />
        <div className="space-y-3 p-5">
          {hasMore && (
            <div className="flex justify-center pb-2">
              <Link
                href={`/app/m/${model.id}/fanvue/chats/${encodeURIComponent(
                  chat.fan_uuid,
                )}?take=${take + PAGE_SIZE}`}
                className="app-btn app-btn-ghost h-9 px-4"
              >
                Load older messages
              </Link>
            </div>
          )}

          {messages.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-[var(--app-text-4)]">
              No messages yet.
            </p>
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
                      message.role === "assistant"
                        ? "text-[var(--app-text-3)]"
                        : "text-[var(--app-text-4)]",
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
