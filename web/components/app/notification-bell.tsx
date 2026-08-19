"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Bell } from "lucide-react";

import { useNotificationStream } from "@/components/app/use-notification-stream";
import { NOTIFICATION_COLUMNS, type NotificationRow } from "@/lib/notifications-ui";
import { cn } from "@/lib/utils";

/**
 * Zvonček. Iba červená bodka — žiadny toast, žiadny zvuk (Marekova voľba).
 *
 * Počiatočný počet neprečítaných príde zo servera, aby bodka svietila hneď pri
 * prvom vykreslení a neblikla až po klientskom dotaze. Zoznam sa doťahuje až
 * pri otvorení — väčšina ľudí ho neotvorí a zbytočný dotaz pri každom načítaní
 * stránky by bol škoda.
 */
export function NotificationBell({ initialUnread }: { initialUnread: number }) {
  const [unread, setUnread] = useState(initialUnread);
  const [rows, setRows] = useState<NotificationRow[] | null>(null);

  const onInsert = useCallback((row: NotificationRow) => {
    setUnread((count) => count + 1);
    setRows((prev) => (prev ? [row, ...prev].slice(0, 20) : prev));
  }, []);

  const supabase = useNotificationStream("notification-bell", onInsert);

  const load = useCallback(async () => {
    const { data } = await supabase
      .from("notifications")
      .select(NOTIFICATION_COLUMNS)
      .order("created_at", { ascending: false })
      .limit(20);
    setRows((data ?? []) as NotificationRow[]);
  }, [supabase]);

  const markAllRead = useCallback(async () => {
    const now = new Date().toISOString();
    // RLS pustí update len na `read_at` a len na vlastných riadkoch, takže
    // stačí filter na neprečítané — cudzie sa aj tak nedotkne.
    await supabase.from("notifications").update({ read_at: now }).is("read_at", null);
    setRows((prev) => prev?.map((row) => (row.read_at ? row : { ...row, read_at: now })) ?? null);
    setUnread(0);
  }, [supabase]);

  function onOpenChange(open: boolean) {
    if (!open) return;
    void load();
    if (unread > 0) void markAllRead();
  }

  return (
    <DropdownMenu.Root onOpenChange={onOpenChange}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={unread > 0 ? `Notifications (${unread} unread)` : "Notifications"}
          className="app-tap relative rounded-md p-2 text-[var(--app-text-2)] transition-colors hover:bg-[var(--app-surface-hover)] hover:text-[var(--app-text)]"
        >
          <Bell className="h-4 w-4" strokeWidth={1.75} />
          {unread > 0 && (
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[#f87171]" />
          )}
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-[var(--app-border)] bg-[var(--app-surface)] shadow-xl"
        >
          <p className="border-b border-[var(--app-border)] px-4 py-2.5 text-[11px] tracking-[0.14em] text-[var(--app-text-4)] uppercase">
            Notifications
          </p>

          <div className="max-h-[22rem] overflow-y-auto">
            {rows === null ? (
              <p className="px-4 py-8 text-center text-[13px] text-[var(--app-text-4)]">Loading…</p>
            ) : rows.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-[var(--app-text-4)]">
                Nothing yet.
              </p>
            ) : (
              rows.map((row) => (
                <NotificationItem key={row.id} row={row} />
              ))
            )}
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function NotificationItem({ row }: { row: NotificationRow }) {
  const body = (
    <>
      <p
        className={cn(
          "text-[13px]",
          row.read_at ? "text-[var(--app-text-2)]" : "font-medium text-[var(--app-text)]",
        )}
      >
        {row.title}
      </p>
      {row.body && (
        <p className="mt-0.5 text-[12.5px] leading-relaxed text-[var(--app-text-3)]">{row.body}</p>
      )}
      <p className="mt-1 text-[11.5px] text-[var(--app-text-4)]">
        {new Date(row.created_at).toLocaleString()}
      </p>
    </>
  );

  const className =
    "block border-b border-[var(--app-border)] px-4 py-3 transition-colors last:border-b-0 hover:bg-[var(--app-surface-hover)]";

  // `href` je prázdny pri notifikáciách, ktoré nemajú kam viesť — vtedy to nesmie
  // byť odkaz, inak by klik skočil na `/`.
  if (!row.href) return <div className={className}>{body}</div>;

  return (
    <DropdownMenu.Item asChild>
      <Link href={row.href} className={cn(className, "cursor-pointer outline-none")}>
        {body}
      </Link>
    </DropdownMenu.Item>
  );
}
