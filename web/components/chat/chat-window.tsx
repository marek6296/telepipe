"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { ImagePlus, Loader2, Minus, Send, X } from "lucide-react";

import { MessageBubble, type Author } from "@/components/chat/message-bubble";
import {
  deleteChatMessageAction,
  markRoomReadAction,
  sendChatMessageAction,
} from "@/app/app/chat-actions";
import {
  CHAT_MESSAGE_COLUMNS,
  ROOM_HINT,
  ROOM_LABEL,
  roomAllowsPhotos,
  type ChatMessage,
  type ChatRoom,
} from "@/lib/chat-ui";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const PAGE = 50;

export function ChatWindow({
  room,
  meId,
  isAdmin,
  title,
  onClose,
}: {
  room: ChatRoom;
  meId: string;
  isAdmin: boolean;
  /** Pri DM z admin pohľadu ukazujeme klientov e-mail, nie „Support". */
  title?: string;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [authors, setAuthors] = useState<Record<string, Author>>({});
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const supabase = useMemo(() => createClient(), []);

  const scrollToBottom = useCallback((smooth = true) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);

  /** Mená sa doťahujú dávkovo — RLS cudzí `accounts` riadok nepustí, takže bez
   *  tohto by v Community svietili UUID. */
  const resolveAuthors = useCallback(
    async (ids: string[]) => {
      const missing = [...new Set(ids)].filter((id) => !authors[id]);
      if (missing.length === 0) return;
      const { data } = await supabase.rpc("chat_display_names", { p_ids: missing });
      if (!data) return;
      setAuthors((prev) => {
        const next = { ...prev };
        for (const row of data as { id: string; name: string; is_admin: boolean }[]) {
          next[row.id] = { name: row.name || "someone", isAdmin: row.is_admin };
        }
        return next;
      });
    },
    [authors, supabase],
  );

  // Prvé načítanie
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data } = await supabase
        .from("chat_messages")
        .select(CHAT_MESSAGE_COLUMNS)
        .eq("room_id", room.id)
        .order("created_at", { ascending: false })
        .limit(PAGE);
      if (cancelled) return;
      const rows = ((data ?? []) as ChatMessage[]).reverse();
      setMessages(rows);
      void resolveAuthors(rows.map((row) => row.sender_id));
      void markRoomReadAction(room.id);
      requestAnimationFrame(() => scrollToBottom(false));
    })();
    return () => {
      cancelled = true;
    };
    // `resolveAuthors` sa zámerne nesleduje — mení sa s každým novým menom
    // a znovunačítalo by to celú miestnosť.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room.id, supabase, scrollToBottom]);

  // Realtime
  useEffect(() => {
    let channel: RealtimeChannel | null = null;
    let cancelled = false;

    (async () => {
      const { data } = await supabase.auth.getSession();
      if (cancelled || !data.session) return;
      supabase.realtime.setAuth(data.session.access_token);

      channel = supabase
        .channel(`chat-room-${room.id}`)
        .on(
          "postgres_changes",
          {
            event: "INSERT",
            schema: "public",
            table: "chat_messages",
            filter: `room_id=eq.${room.id}`,
          },
          (payload) => {
            const row = payload.new as ChatMessage;
            setMessages((prev) => {
              if (!prev) return prev;
              // Vlastnú správu sme si už pridali po odoslaní — nesmie zdvojiť.
              if (prev.some((m) => m.id === row.id)) return prev;
              return [...prev, row];
            });
            void resolveAuthors([row.sender_id]);
            void markRoomReadAction(room.id);
            requestAnimationFrame(() => scrollToBottom());
          },
        )
        .subscribe();
    })();

    return () => {
      cancelled = true;
      if (channel) supabase.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room.id, supabase, scrollToBottom]);

  async function send() {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setError("");
    setText("");

    const result = await sendChatMessageAction(room.id, body);
    setSending(false);

    if (result.error) {
      setError(result.error);
      setText(body); // nech o napísané nepríde
      return;
    }
    if (result.message) {
      const created = result.message;
      setMessages((prev) =>
        prev && !prev.some((m) => m.id === created.id) ? [...prev, created] : prev,
      );
      requestAnimationFrame(() => scrollToBottom());
    }
  }

  async function pickPhoto(file: File) {
    setUploading(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    form.append("roomId", room.id);

    const response = await fetch("/api/chat/upload", { method: "POST", body: form });
    const payload = (await response.json().catch(() => ({}))) as { path?: string; error?: string };

    if (!response.ok || !payload.path) {
      setUploading(false);
      setError(payload.error ?? "Upload failed.");
      return;
    }

    const result = await sendChatMessageAction(room.id, text.trim(), payload.path);
    setUploading(false);
    setText("");
    if (result.error) setError(result.error);
    else if (result.message) {
      const created = result.message;
      setMessages((prev) =>
        prev && !prev.some((m) => m.id === created.id) ? [...prev, created] : prev,
      );
      requestAnimationFrame(() => scrollToBottom());
    }
  }

  async function remove(id: string) {
    const before = messages;
    setMessages((prev) =>
      prev?.map((m) => (m.id === id ? { ...m, deleted_at: new Date().toISOString() } : m)) ?? prev,
    );
    const result = await deleteChatMessageAction(id);
    if (result.error) {
      setMessages(before ?? null);
      setError(result.error);
    }
  }

  const photos = roomAllowsPhotos(room.kind);
  const heading = title ?? ROOM_LABEL[room.kind];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 24, scale: 0.97 }}
      transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "pointer-events-auto flex w-[19rem] flex-col overflow-hidden rounded-t-xl border border-b-0 border-[var(--app-border)] bg-[var(--app-bg)] shadow-[0_-8px_40px_-12px_rgba(0,0,0,0.7)]",
        collapsed ? "h-11" : "h-[26rem]",
      )}
    >
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-[var(--app-border)] px-3">
        <button
          type="button"
          onClick={() => setCollapsed((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          <span className="truncate text-[13px] font-medium text-[var(--app-text)]">{heading}</span>
        </button>
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expand" : "Collapse"}
            className="app-tap rounded p-1 text-[var(--app-text-3)] hover:text-[var(--app-text)]"
          >
            <Minus className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="app-tap rounded p-1 text-[var(--app-text-3)] hover:text-[var(--app-text)]"
          >
            <X className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
        </div>
      </div>

      {!collapsed && (
        <>
          <div ref={scrollRef} className="flex-1 space-y-2 overflow-y-auto px-3 py-3">
            {messages === null ? (
              <p className="pt-10 text-center text-[12.5px] text-[var(--app-text-4)]">Loading…</p>
            ) : messages.length === 0 ? (
              <p className="pt-10 text-center text-[12.5px] text-[var(--app-text-4)]">
                {ROOM_HINT[room.kind]}
                <br />
                Say hello.
              </p>
            ) : (
              messages.map((message, index) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  mine={message.sender_id === meId}
                  author={authors[message.sender_id]}
                  showAuthor={messages[index - 1]?.sender_id !== message.sender_id}
                  canModerate={isAdmin && message.sender_id !== meId}
                  onDelete={remove}
                />
              ))
            )}
          </div>

          {error && (
            <p className="px-3 pb-1 text-[11.5px] text-[#fca5a5]" role="alert">
              {error}
            </p>
          )}

          <div className="flex shrink-0 items-end gap-1.5 border-t border-[var(--app-border)] p-2">
            {photos && (
              <>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) void pickPhoto(file);
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  aria-label="Send a photo"
                  className="app-tap rounded-md p-2 text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)] disabled:opacity-40"
                >
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.75} />
                  ) : (
                    <ImagePlus className="h-4 w-4" strokeWidth={1.75} />
                  )}
                </button>
              </>
            )}

            <textarea
              rows={1}
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              placeholder="Write a message…"
              className="max-h-24 min-h-[2.25rem] flex-1 resize-none rounded-md border border-[var(--app-border)] bg-[var(--app-surface)] px-2.5 py-2 text-[13px] text-[var(--app-text)] outline-none transition-colors placeholder:text-[var(--app-text-4)] focus:border-[var(--app-border-strong)]"
            />

            <button
              type="button"
              onClick={() => void send()}
              disabled={!text.trim() || sending}
              aria-label="Send"
              className={cn(
                "app-tap flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors",
                text.trim() && !sending
                  ? "bg-[var(--app-text)] text-[var(--app-bg)]"
                  : "bg-[var(--app-surface)] text-[var(--app-text-4)]",
              )}
            >
              <Send className="h-3.5 w-3.5" strokeWidth={2} />
            </button>
          </div>
        </>
      )}
    </motion.div>
  );
}
