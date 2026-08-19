"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { MessageCircle, X } from "lucide-react";

import { ChatWindow } from "@/components/chat/chat-window";
import { openDirectMessageAction } from "@/app/app/chat-actions";
import {
  ROOM_HINT,
  ROOM_LABEL,
  type ChatMessage,
  type ChatRoom,
} from "@/lib/chat-ui";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

type DmRow = { room_id: string; account_id: string; email: string; unread: number };

/** Koľko okien sa zmestí vedľa seba, kým začnú liezť cez obrazovku. */
const MAX_OPEN = 3;

/**
 * Dock vľavo dole — bublina, zoznam kanálov a otvorené okná vedľa seba.
 *
 * Mountuje sa v `/app` aj na `/locked`: zamknutý človek má mať Community a DM
 * na Mareka. Ktoré kanály naozaj uvidí, rozhodne RLS, nie tento komponent.
 */
export function ChatDock({
  rooms,
  meId,
  isAdmin,
  initialUnread,
}: {
  rooms: ChatRoom[];
  meId: string;
  isAdmin: boolean;
  initialUnread: number;
}) {
  const [panelOpen, setPanelOpen] = useState(false);
  const [open, setOpen] = useState<ChatRoom[]>([]);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [dms, setDms] = useState<DmRow[] | null>(null);
  const [unread, setUnread] = useState(initialUnread);

  const supabase = useMemo(() => createClient(), []);

  // Realtime handler potrebuje AKTUÁLNY zoznam otvorených okien, ale kanál sa
  // kvôli tomu nesmie otvárať znova pri každom otvorení okna — preto ref,
  // plnený v efekte (nie počas renderu).
  const openIdsRef = useRef<string[]>([]);
  useEffect(() => {
    openIdsRef.current = open.map((room) => room.id);
  }, [open]);

  /** Bodka na bubline: prírastok z realtime, prepočet keď sa niečo prečíta. */
  const refreshUnread = useCallback(async () => {
    const { data } = await supabase.rpc("chat_unread_total");
    setUnread(Number(data ?? 0));
  }, [supabase]);

  useEffect(() => {
    let channel: RealtimeChannel | null = null;
    let cancelled = false;

    (async () => {
      const { data } = await supabase.auth.getSession();
      if (cancelled || !data.session) return;
      supabase.realtime.setAuth(data.session.access_token);

      channel = supabase
        .channel("chat-dock")
        .on(
          "postgres_changes",
          { event: "INSERT", schema: "public", table: "chat_messages" },
          (payload) => {
            const row = payload.new as ChatMessage;
            if (row.sender_id === meId) return;
            // Otvorené okno si správu označí prečítanú samo.
            if (openIdsRef.current.includes(row.room_id)) return;
            setUnread((count) => count + 1);
            setDms((prev) =>
              prev?.map((dm) =>
                dm.room_id === row.room_id ? { ...dm, unread: Number(dm.unread) + 1 } : dm,
              ) ?? prev,
            );
          },
        )
        .subscribe();
    })();

    return () => {
      cancelled = true;
      if (channel) supabase.removeChannel(channel);
    };
  }, [supabase, meId]);

  const loadDms = useCallback(async () => {
    if (!isAdmin) return;
    const { data } = await supabase.rpc("admin_list_dm_rooms");
    setDms((data ?? []) as DmRow[]);
  }, [isAdmin, supabase]);

  function show(room: ChatRoom, title?: string) {
    setPanelOpen(false);
    if (title) setTitles((prev) => ({ ...prev, [room.id]: title }));
    setOpen((prev) => {
      if (prev.some((r) => r.id === room.id)) return prev;
      return [...prev, room].slice(-MAX_OPEN);
    });
    void refreshUnread();
  }

  async function openSupport() {
    const existing = rooms.find((room) => room.kind === "admin_dm");
    if (existing) return show(existing);

    const result = await openDirectMessageAction();
    if (!result.roomId) return;
    show({ id: result.roomId, kind: "admin_dm", owner_account_id: meId });
  }

  const publicRooms = rooms.filter((room) => room.kind !== "admin_dm");

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex items-end gap-2 px-3 sm:px-4">
      {/* Bublina + panel */}
      <div className="pointer-events-auto relative shrink-0 pb-3">
        <AnimatePresence>
          {panelOpen && (
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.96 }}
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              className="absolute bottom-14 left-0 w-[17.5rem] origin-bottom-left overflow-hidden rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] shadow-[0_16px_48px_-12px_rgba(0,0,0,0.7)]"
            >
              <div className="flex items-center justify-between border-b border-[var(--app-border)] px-3.5 py-2.5">
                <span className="text-[11px] tracking-[0.14em] text-[var(--app-text-4)] uppercase">
                  Chat
                </span>
                <button
                  type="button"
                  onClick={() => setPanelOpen(false)}
                  aria-label="Close"
                  className="app-tap rounded p-0.5 text-[var(--app-text-3)] hover:text-[var(--app-text)]"
                >
                  <X className="h-3.5 w-3.5" strokeWidth={2} />
                </button>
              </div>

              <div className="max-h-[24rem] overflow-y-auto py-1">
                {publicRooms.map((room) => (
                  <RoomButton
                    key={room.id}
                    label={ROOM_LABEL[room.kind]}
                    hint={ROOM_HINT[room.kind]}
                    onClick={() => show(room)}
                  />
                ))}

                <RoomButton
                  label={isAdmin ? "My support chat" : "Message the team"}
                  hint={ROOM_HINT.admin_dm}
                  onClick={() => void openSupport()}
                />

                {isAdmin && (
                  <>
                    <p className="mt-1 border-t border-[var(--app-border)] px-3.5 pb-1 pt-2.5 text-[11px] tracking-[0.14em] text-[var(--app-text-4)] uppercase">
                      Inbox
                    </p>
                    {dms === null ? (
                      <p className="px-3.5 py-2 text-[12.5px] text-[var(--app-text-4)]">Loading…</p>
                    ) : dms.length === 0 ? (
                      <p className="px-3.5 py-2 text-[12.5px] text-[var(--app-text-4)]">
                        No conversations yet.
                      </p>
                    ) : (
                      dms.map((dm) => (
                        <RoomButton
                          key={dm.room_id}
                          label={dm.email}
                          hint={Number(dm.unread) > 0 ? `${dm.unread} unread` : "Opened"}
                          highlight={Number(dm.unread) > 0}
                          onClick={() =>
                            show(
                              {
                                id: dm.room_id,
                                kind: "admin_dm",
                                owner_account_id: dm.account_id,
                              },
                              dm.email,
                            )
                          }
                        />
                      ))
                    )}
                  </>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.button
          type="button"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.94 }}
          onClick={() => {
            setPanelOpen((v) => !v);
            if (!panelOpen) {
              void loadDms();
              void refreshUnread();
            }
          }}
          aria-label={unread > 0 ? `Chat (${unread} unread)` : "Chat"}
          className="relative flex h-11 w-11 items-center justify-center rounded-full border border-[var(--app-border)] bg-[var(--app-surface)] text-[var(--app-text)] shadow-[0_8px_24px_-6px_rgba(0,0,0,0.6)] transition-colors hover:border-[var(--app-border-strong)]"
        >
          <MessageCircle className="h-[1.15rem] w-[1.15rem]" strokeWidth={1.75} />
          {unread > 0 && (
            <span className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-[#f87171] ring-2 ring-[var(--app-bg)]" />
          )}
        </motion.button>
      </div>

      {/* Otvorené okná — vedľa seba, na mobile len to posledné */}
      <div className="pointer-events-none flex flex-1 items-end justify-start gap-2 overflow-hidden">
        <AnimatePresence mode="popLayout">
          {open.map((room, index) => (
            <div
              key={room.id}
              className={cn(index < open.length - 1 && "hidden sm:block", "pointer-events-auto")}
            >
              <ChatWindow
                room={room}
                meId={meId}
                isAdmin={isAdmin}
                title={titles[room.id]}
                onClose={() => {
                  setOpen((prev) => prev.filter((r) => r.id !== room.id));
                  void refreshUnread();
                }}
              />
            </div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function RoomButton({
  label,
  hint,
  highlight,
  onClick,
}: {
  label: string;
  hint: string;
  highlight?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full flex-col items-start gap-0.5 px-3.5 py-2.5 text-left transition-colors hover:bg-[var(--app-surface-hover)]"
    >
      <span
        className={cn(
          "truncate text-[13px]",
          highlight ? "font-medium text-[var(--app-text)]" : "text-[var(--app-text-2)]",
        )}
      >
        {label}
      </span>
      <span className="truncate text-[11.5px] text-[var(--app-text-4)]">{hint}</span>
    </button>
  );
}
