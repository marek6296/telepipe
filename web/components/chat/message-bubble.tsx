"use client";

import { motion } from "framer-motion";
import { Trash2 } from "lucide-react";

import { messageTime, type ChatMessage } from "@/lib/chat-ui";
import { cn } from "@/lib/utils";

export type Author = { name: string; isAdmin: boolean };

/**
 * Jedna bublina. Pruží zvnútra a prilieta zo strany svojho autora — cudzia
 * zľava, moja sprava.
 *
 * Farby sú monochromatické podľa zvyšku appky: moja správa je svetlá plocha
 * s tmavým textom, cudzia tmavá s orámovaním. Žiadne gradienty.
 */
export function MessageBubble({
  message,
  mine,
  author,
  showAuthor,
  canModerate,
  onDelete,
}: {
  message: ChatMessage;
  mine: boolean;
  author?: Author;
  /** Prvá správa v sérii od toho istého človeka — meno sa neopakuje. */
  showAuthor: boolean;
  canModerate: boolean;
  onDelete?: (id: string) => void;
}) {
  const removed = Boolean(message.deleted_at);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.97, x: mine ? 14 : -14 }}
      animate={{ opacity: 1, y: 0, scale: 1, x: 0 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      className={cn("group flex w-full", mine ? "justify-end" : "justify-start")}
    >
      <div className={cn("flex max-w-[82%] flex-col", mine ? "items-end" : "items-start")}>
        {showAuthor && !mine && (
          <span className="mb-1 flex items-center gap-1.5 pl-1 text-[11px] text-[var(--app-text-4)]">
            {author?.name ?? "…"}
            {author?.isAdmin && (
              <span className="rounded border border-[var(--app-border)] px-1 text-[9.5px] tracking-wide text-[var(--app-text-3)] uppercase">
                team
              </span>
            )}
          </span>
        )}

        <div className={cn("flex items-end gap-1.5", mine && "flex-row-reverse")}>
          <motion.div
            layout
            className={cn(
              "rounded-2xl px-3.5 py-2 text-[13.5px] leading-relaxed break-words",
              removed
                ? "border border-dashed border-[var(--app-border)] text-[var(--app-text-4)] italic"
                : mine
                  ? "rounded-br-md bg-[var(--app-text)] text-[var(--app-bg)]"
                  : "rounded-bl-md border border-[var(--app-border)] bg-[var(--app-surface)] text-[var(--app-text)]",
            )}
          >
            {removed ? (
              "Message removed"
            ) : (
              <>
                {message.image_path && (
                  // Privátny bucket — `/api/chat/image` podpíše a presmeruje.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={`/api/chat/image?path=${encodeURIComponent(message.image_path)}`}
                    alt=""
                    className="mb-1.5 max-h-64 w-full rounded-lg object-cover"
                    loading="lazy"
                  />
                )}
                {message.body}
              </>
            )}
          </motion.div>

          {canModerate && !removed && (
            <button
              type="button"
              onClick={() => onDelete?.(message.id)}
              aria-label="Remove message"
              className="app-tap rounded p-1 text-[var(--app-text-4)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-[#fca5a5]"
            >
              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
            </button>
          )}
        </div>

        <span className="mt-0.5 px-1 text-[10.5px] text-[var(--app-text-4)]">
          {messageTime(message.created_at)}
        </span>
      </div>
    </motion.div>
  );
}
