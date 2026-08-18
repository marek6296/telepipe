"use client";

import { useMemo, useRef, useState, useTransition } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  EyeOff,
  Flame,
  ImagePlus,
  Loader2,
  Plus,
  Send,
  Trash2,
  X,
} from "lucide-react";

import { saveBehaviorAction } from "@/app/app/m/[id]/persona/behavior/actions";
import {
  createPhotoAction,
  deletePhotoAction,
  updatePhotoAction,
} from "@/app/app/m/[id]/telegram/photos/actions";
import { AutoSaveForm } from "@/components/app/forms/auto-save";
import { SelectField, Switch, SwitchField, TextField } from "@/components/app/forms/fields";
import { Callout } from "@/components/app/ui";
import { relativeTime } from "@/lib/format";
import {
  FOLDER_HINT,
  FOLDER_LABEL,
  FOLDERS,
  type Folder,
  type PhotoRow,
} from "@/lib/photos";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const MAX_BYTES = 12 * 1024 * 1024;
const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

export function PhotoLibrary({
  modelId,
  photos,
  photosEnabled,
}: {
  modelId: string;
  photos: PhotoRow[];
  photosEnabled: boolean;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busyFolder, setBusyFolder] = useState<Folder | null>(null);
  const [openPhoto, setOpenPhoto] = useState<PhotoRow | null>(null);

  // Fotky rozdelené do pevných albumov; poradie priečinkov drží `FOLDERS`.
  const byFolder = useMemo(() => {
    const map = new Map<Folder, PhotoRow[]>(FOLDERS.map((f) => [f, []]));
    for (const photo of photos) {
      const bucket = map.get(photo.folder as Folder);
      if (bucket) bucket.push(photo);
      else map.get("universal")!.push(photo); // neznámy album (starý riadok) → univerzál
    }
    return map;
  }, [photos]);

  const upload = async (files: FileList | File[], folder: Folder) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setError(null);
    setBusyFolder(folder);

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

      const result = await createPhotoAction(modelId, { url: publicUrl, folder });
      if (result.error) {
        failures += 1;
        setError(result.error);
      }
    }

    setBusyFolder(null);
    if (failures < list.length) router.refresh();
  };

  return (
    <div className="space-y-5">
      <SendPhotosToggle
        modelId={modelId}
        enabled={photosEnabled}
        hasPhotos={photos.length > 0}
      />

      {error && (
        <Callout tone="danger" icon={<AlertCircle className="h-3.5 w-3.5" />}>
          {error}
        </Callout>
      )}

      {FOLDERS.map((folder) => (
        <FolderSection
          key={folder}
          folder={folder}
          photos={byFolder.get(folder) ?? []}
          uploading={busyFolder === folder}
          onUpload={(files) => void upload(files, folder)}
          onOpen={setOpenPhoto}
        />
      ))}

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

/* -------------------------------------------------------------------------- */
/*  Master vypínač                                                             */
/* -------------------------------------------------------------------------- */

function SendPhotosToggle({
  modelId,
  enabled,
  hasPhotos,
}: {
  modelId: string;
  enabled: boolean;
  hasPhotos: boolean;
}) {
  const router = useRouter();
  const [value, setValue] = useState(enabled);
  const [pending, startTransition] = useTransition();

  const toggle = (next: boolean) => {
    setValue(next);
    startTransition(async () => {
      const result = await saveBehaviorAction(modelId, { photos_enabled: next });
      if (result.error) setValue(!next);
      router.refresh();
    });
  };

  return (
    <div className="app-panel flex items-start justify-between gap-4 p-5">
      <div className="min-w-0">
        <p className="text-[14px] font-medium tracking-tight text-[var(--app-text)]">
          Send photos
        </p>
        <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-4)]">
          {hasPhotos
            ? "When on, she sends one photo early in a conversation from the album that matches where she is, then only if he asks or doubts she is real. Each photo and each album goes to a chat only once."
            : "Add at least one photo to an album below to turn this on. With no photos she has nothing to send."}
        </p>
      </div>
      <div className="flex items-center gap-2 pt-0.5">
        {pending && <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--app-text-4)]" />}
        <Switch
          checked={value}
          disabled={!hasPhotos || pending}
          label="Send photos"
          onCheckedChange={toggle}
        />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Jeden album                                                                */
/* -------------------------------------------------------------------------- */

function FolderSection({
  folder,
  photos,
  uploading,
  onUpload,
  onOpen,
}: {
  folder: Folder;
  photos: PhotoRow[];
  uploading: boolean;
  onUpload: (files: FileList | File[]) => void;
  onOpen: (photo: PhotoRow) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        onUpload(event.dataTransfer.files);
      }}
      className={cn(
        "app-panel p-5 transition-colors",
        dragging && "border-[var(--app-border-strong)] bg-[var(--app-surface-hover)]",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-[14px] font-medium tracking-tight text-[var(--app-text)]">
              {FOLDER_LABEL[folder]}
            </h3>
            <span className="rounded-full border border-[var(--app-border)] px-2 py-0.5 text-[10.5px] text-[var(--app-text-4)]">
              {photos.length}
            </span>
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-[var(--app-text-4)]">
            {FOLDER_HINT[folder]}
          </p>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="app-btn app-btn-ghost h-9 shrink-0 px-3"
        >
          {uploading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Add
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          multiple
          hidden
          onChange={(event) => event.target.files && onUpload(event.target.files)}
        />
      </div>

      {photos.length === 0 ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--app-border-strong)] bg-[#0c0c0c] py-6 text-[12.5px] text-[var(--app-text-4)] transition-colors hover:text-[var(--app-text-2)]"
        >
          <ImagePlus className="h-4 w-4" />
          Drop photos here or click to add
        </button>
      ) : (
        <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          {photos.map((photo) => (
            <button
              key={photo.id}
              type="button"
              onClick={() => onOpen(photo)}
              className="group relative aspect-[3/4] overflow-hidden rounded-lg border border-[var(--app-border)] bg-[#0b0b0b] text-left transition-colors hover:border-[var(--app-border-strong)]"
            >
              <Image
                src={photo.url}
                alt={photo.caption || "Model photo"}
                fill
                sizes="(max-width: 640px) 33vw, (max-width: 1024px) 25vw, 170px"
                className={cn(
                  "object-cover transition-transform duration-500 group-hover:scale-[1.04]",
                  !photo.active && "opacity-35 grayscale",
                )}
              />
              <span className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-[linear-gradient(to_top,rgba(0,0,0,0.85),transparent)]" />

              <span className="absolute left-1.5 top-1.5 flex flex-wrap gap-1">
                {photo.spicy && (
                  <Badge className="border-[#7a3b23]/60 bg-[#2a140d]/90 text-[#ffb38f]">
                    <Flame className="h-3 w-3" />
                  </Badge>
                )}
                {!photo.active && (
                  <Badge className="border-[var(--app-border-strong)] bg-black/70 text-[var(--app-text-2)]">
                    <EyeOff className="h-3 w-3" />
                  </Badge>
                )}
              </span>

              <span className="absolute inset-x-0 bottom-0 flex items-center gap-1 p-2 text-[10px] text-[var(--app-text-3)]">
                <Send className="h-2.5 w-2.5" />
                {photo.sent_count}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Badge({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10.5px] font-medium backdrop-blur-sm",
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
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const save = async (patch: Record<string, unknown>) => {
    const result = await updatePhotoAction(modelId, photo.id, patch);
    // Presun do iného albumu mení mriežku — po uložení obnovíme.
    if (!result.error && "folder" in patch) router.refresh();
    return result;
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
        className="app-panel relative grid max-h-[88svh] w-full max-w-3xl grid-cols-1 overflow-y-auto md:grid-cols-[minmax(0,300px)_1fr]"
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
            sizes="300px"
            className="object-cover md:rounded-l-3xl"
          />
        </div>

        <div className="p-6">
          <AutoSaveForm save={save} sticky={false}>
            <SelectField
              name="folder"
              label="Album"
              defaultValue={photo.folder}
              options={FOLDERS.map((f) => ({ value: f, label: FOLDER_LABEL[f] }))}
            />
            <TextField
              name="caption"
              label="Caption"
              defaultValue={photo.caption}
              placeholder="just got out of the shower"
              help="What she says when she sends it — also how she knows what is in the picture."
            />
            <SwitchField
              name="spicy"
              label="Spicy"
              defaultValue={photo.spicy}
              help="Picked first when the conversation has heated up."
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
