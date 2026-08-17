"use client";

import { useRef, useState, useTransition } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  EyeOff,
  Flame,
  ImagePlus,
  Loader2,
  Send,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import {
  createPhotoAction,
  deletePhotoAction,
  updatePhotoAction,
} from "@/app/app/m/[id]/photos/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { SwitchField, TextField } from "@/components/app/forms/fields";
import { Callout, EmptyState } from "@/components/app/ui";
import { relativeTime } from "@/lib/format";
import {
  DAY_PARTS,
  DAY_PART_HOURS,
  DAY_PART_LABEL,
  type DayPart,
  type PhotoRow,
} from "@/lib/photos";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const MAX_BYTES = 12 * 1024 * 1024;
const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

export function PhotoLibrary({
  modelId,
  photos,
}: {
  modelId: string;
  photos: PhotoRow[];
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [openPhoto, setOpenPhoto] = useState<PhotoRow | null>(null);

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setError(null);
    setUploading(list.length);

    const supabase = createClient();
    let failures = 0;

    for (const file of list) {
      if (!ACCEPTED.includes(file.type)) {
        failures += 1;
        setError("Only JPG, PNG and WebP images are supported.");
        continue;
      }
      if (file.size > MAX_BYTES) {
        failures += 1;
        setError("Each photo must be under 12 MB.");
        continue;
      }

      const extension = file.name.split(".").pop()?.toLowerCase() ?? "jpg";
      // Cesta musí začínať model_id — storage policy pustí zápis len tam.
      const path = `${modelId}/${crypto.randomUUID()}.${extension}`;

      const { error: uploadError } = await supabase.storage
        .from("photos")
        .upload(path, file, { cacheControl: "3600", upsert: false });

      if (uploadError) {
        failures += 1;
        setError(uploadError.message);
        continue;
      }

      const {
        data: { publicUrl },
      } = supabase.storage.from("photos").getPublicUrl(path);

      const result = await createPhotoAction(modelId, { url: publicUrl });
      if (result.error) {
        failures += 1;
        setError(result.error);
      }
      setUploading((count) => Math.max(0, count - 1));
    }

    setUploading(0);
    if (failures < list.length) router.refresh();
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="space-y-5">
      {/* --- Upload ---------------------------------------------------------- */}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void upload(event.dataTransfer.files);
        }}
        className={cn(
          "relative flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
          dragging
            ? "border-[var(--app-border-strong)] bg-[var(--app-surface-hover)]"
            : "border-[var(--app-border-strong)] bg-[#0c0c0c]",
        )}
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--app-border)] text-[var(--app-text-4)]">
          {uploading > 0 ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Upload className="h-5 w-5" />
          )}
        </span>
        <p className="mt-4 text-[14px] font-medium text-[var(--app-text-2)]">
          {uploading > 0 ? `Uploading ${uploading}…` : "Drop her photos here"}
        </p>
        <p className="mt-1 text-[12.5px] text-[var(--app-text-4)]">
          JPG, PNG or WebP, up to 12 MB each. She never sends the same photo to the same fan
          twice.
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading > 0}
          className="app-btn app-btn-primary mt-5 h-9 px-4"
        >
          <ImagePlus className="h-4 w-4" />
          Choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          multiple
          hidden
          onChange={(event) => event.target.files && void upload(event.target.files)}
        />
      </div>

      {error && (
        <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
          {error}
        </Callout>
      )}

      {/* --- Mriežka ---------------------------------------------------------- */}
      {photos.length === 0 ? (
        <EmptyState
          icon={<ImagePlus className="h-[18px] w-[18px]" strokeWidth={1.5} />}
          title="No photos yet"
          description="Upload a handful of everyday selfies. She only ever sends one when there is a reason — he asked, she is warming up a quiet chat, or it is her first selfie of the conversation."
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {photos.map((photo) => (
            <button
              key={photo.id}
              type="button"
              onClick={() => setOpenPhoto(photo)}
              className="group relative aspect-[3/4] overflow-hidden rounded-lg border border-[var(--app-border)] bg-[#0b0b0b] text-left transition-colors hover:border-[var(--app-border-strong)]"
            >
              <Image
                src={photo.url}
                alt={photo.caption || "Model photo"}
                fill
                sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 260px"
                className={cn(
                  "object-cover transition-transform duration-500 group-hover:scale-[1.04]",
                  !photo.active && "opacity-35 grayscale",
                )}
              />
              <span className="pointer-events-none absolute inset-x-0 bottom-0 h-2/3 bg-[linear-gradient(to_top,rgba(0,0,0,0.85),transparent)]" />

              <span className="absolute left-2 top-2 flex flex-wrap gap-1">
                {photo.spicy && (
                  <Badge className="border-[#7a3b23]/60 bg-[#2a140d]/90 text-[#ffb38f]">
                    <Flame className="h-3 w-3" />
                    Spicy
                  </Badge>
                )}
                {!photo.active && (
                  <Badge className="border-[var(--app-border-strong)] bg-black/70 text-[var(--app-text-2)]">
                    <EyeOff className="h-3 w-3" />
                    Off
                  </Badge>
                )}
              </span>

              <span className="absolute inset-x-0 bottom-0 p-2.5">
                <span className="line-clamp-2 block text-[12px] leading-snug text-[var(--app-text)]">
                  {photo.caption || "No caption"}
                </span>
                <span className="mt-1 flex items-center gap-2 text-[10.5px] text-[var(--app-text-3)]">
                  <Send className="h-3 w-3" />
                  {photo.sent_count} sent
                  <span>· {relativeTime(photo.created_at)}</span>
                </span>
              </span>
            </button>
          ))}
        </div>
      )}

      <AnimatePresence>
        {openPhoto && (
          <PhotoEditor
            key={openPhoto.id}
            modelId={modelId}
            photo={openPhoto}
            onClose={() => setOpenPhoto(null)}
            onDeleted={() => {
              setOpenPhoto(null);
              router.refresh();
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function Badge({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium backdrop-blur-sm",
        className,
      )}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/*  Editor jednej fotky                                                        */
/* -------------------------------------------------------------------------- */

function PhotoEditor({
  modelId,
  photo,
  onClose,
  onDeleted,
}: {
  modelId: string;
  photo: PhotoRow;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [parts, setParts] = useState<string[]>(photo.parts ?? []);
  const [confirming, setConfirming] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const save = (patch: Record<string, unknown>) => updatePhotoAction(modelId, photo.id, patch);

  const togglePart = (part: DayPart) => {
    const next = parts.includes(part)
      ? parts.filter((value) => value !== part)
      : [...parts, part];
    setParts(next);
    startTransition(async () => {
      const result = await save({ parts: next });
      if (result.error) setError(result.error);
    });
  };

  const remove = () => {
    startTransition(async () => {
      const result = await deletePhotoAction(modelId, photo.id);
      if (result.error) {
        setError(result.error);
        return;
      }
      onDeleted();
    });
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/75"
      />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Photo details"
        initial={{ opacity: 0, scale: 0.97, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: 8 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className="app-panel relative grid max-h-[88svh] w-full max-w-4xl grid-cols-1 overflow-y-auto md:grid-cols-[minmax(0,320px)_1fr]"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-3 z-10 rounded-md border border-[var(--app-border-strong)] bg-black/70 p-1.5 text-[var(--app-text-2)] backdrop-blur transition-colors hover:text-[var(--app-text)]"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="relative min-h-[280px] bg-[#070707] md:min-h-full">
          <Image
            src={photo.url}
            alt={photo.caption || "Model photo"}
            fill
            sizes="320px"
            className="object-cover md:rounded-l-3xl"
          />
        </div>

        <div className="p-6">
          <AutoSaveForm save={save} sticky={false}>
            <TextField
              name="caption"
              label="Caption"
              defaultValue={photo.caption}
              placeholder="just got out of the shower"
              help="What she says when she sends it. Also how the model knows what is in the picture."
            />
            <TextField
              name="situation"
              label="Situation"
              defaultValue={photo.situation}
              placeholder="at home on the couch, no makeup"
              help="Where and when it was taken, so the message around it fits."
            />
            <TextField
              name="collection"
              label="Set"
              defaultValue={photo.collection}
              placeholder="beach day"
              help="Photos from the same moment share a set — she keeps sending from it while the chat is still about that moment."
            />

            <div>
              <p className="mb-2 text-[12.5px] font-medium tracking-tight text-[var(--app-text-2)]">
                Good times of day
              </p>
              <div className="flex flex-wrap gap-2">
                {DAY_PARTS.map((part) => {
                  const active = parts.includes(part);
                  return (
                    <button
                      key={part}
                      type="button"
                      onClick={() => togglePart(part)}
                      className={cn(
                        "rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
                        active
                          ? "border-[var(--app-border-strong)] bg-[var(--app-active)] text-[var(--app-text)]"
                          : "border-[var(--app-border-strong)] text-[var(--app-text-3)] hover:text-[var(--app-text)]",
                      )}
                      title={DAY_PART_HOURS[part]}
                    >
                      {DAY_PART_LABEL[part]}
                    </button>
                  );
                })}
              </div>
              <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
                Leave all off and the photo fits any hour. A beach shot at 2 a.m. is the
                fastest way to break the illusion.
              </p>
            </div>

            <SwitchField
              name="spicy"
              label="Spicy"
              defaultValue={photo.spicy}
              help="Picked first when the conversation heats up."
            />
            <SwitchField
              name="active"
              label="In rotation"
              defaultValue={photo.active}
              help="Switch off to keep the photo but stop sending it."
            />
          </AutoSaveForm>

          {error && (
            <div className="mt-4">
              <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
                {error}
              </Callout>
            </div>
          )}

          <div className="mt-5 flex items-center justify-between gap-3 border-t border-[var(--app-border)] pt-4">
            <span className="text-[11.5px] text-[var(--app-text-4)]">
              Sent {photo.sent_count}× · added {relativeTime(photo.created_at)}
            </span>
            {confirming ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  className="text-[12.5px] text-[var(--app-text-3)] hover:text-[var(--app-text)]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={remove}
                  disabled={pending}
                  className="app-btn app-btn-danger h-9 px-4"
                >
                  {pending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  Delete for good
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--app-text-4)] transition-colors hover:text-[#fca5a5]"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
