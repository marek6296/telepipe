"use client";

import { useMemo, useState, useTransition } from "react";
import { AlertTriangle, Check, FolderTree, Loader2, RefreshCw } from "lucide-react";

import {
  requestVaultSyncAction,
  saveFolderAction,
  saveMediaAction,
} from "@/app/app/m/[id]/fanvue/actions";
import { RelativeTime } from "@/components/app/relative-time";
import { Callout, Card, CardHeader, EmptyState } from "@/components/app/ui";
import {
  FOLDER_ROLES,
  FOLDER_ROLE_LABEL,
  type FanvueSyncRequest,
  type FolderRole,
  type FvFolder,
  type FvMedia,
} from "@/lib/fanvue-ui";
import { cn } from "@/lib/utils";

/**
 * Vault na Fanvue — sklad je ich, význam je náš.
 *
 * Vlastnú knižnicu fotiek si tu nikto nezakladá: do správy sa dá priložiť len
 * médium, ktoré na Fanvue už existuje, a dve zbierky by sa časom rozišli. Fotky
 * teda Marek nahráva vo Fanvue ako doteraz a tu len povie, na čo je ktorý
 * priečinok, čo na fotke je a koľko stojí. To posledné je celý dôvod tejto
 * obrazovky — bez ceny sa fotka z plateného priečinka neposiela vôbec, aby
 * platený obsah nikdy neodišiel zadarmo.
 */
export function FanvueVault({
  modelId,
  connected,
  folders,
  media,
  lastSync,
  mediaSyncedAt,
}: {
  modelId: string;
  connected: boolean;
  folders: FvFolder[];
  media: FvMedia[];
  lastSync: FanvueSyncRequest | null;
  mediaSyncedAt: string | null;
}) {
  const byFolder = useMemo(() => {
    const map = new Map<string, FvMedia[]>();
    for (const item of media) {
      const list = map.get(item.folder) ?? [];
      list.push(item);
      map.set(item.folder, list);
    }
    return map;
  }, [media]);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          title="Vault"
          description="Photos live in your Fanvue vault. Upload them there as usual — here you only say what each folder is for."
          icon={<FolderTree className="h-4 w-4" />}
          actions={
            <SyncButton modelId={modelId} connected={connected} lastSync={lastSync} />
          }
        />

        <div className="px-5 py-5">
          {!connected ? (
            <p className="text-[13px] leading-relaxed text-[var(--app-text-3)]">
              Connect Fanvue first. The vault is read straight from her account — there is
              no separate library to build here.
            </p>
          ) : folders.length === 0 ? (
            <EmptyState
              icon={<FolderTree className="h-5 w-5" strokeWidth={1.75} />}
              title="No folders yet"
              description="Run a sync and the folders from her Fanvue vault show up here, ready to be given a role."
            />
          ) : (
            <div className="flex flex-col gap-3">
              {folders.map((folder) => (
                <FolderRow
                  key={folder.name}
                  modelId={modelId}
                  folder={folder}
                  photos={byFolder.get(folder.name) ?? []}
                />
              ))}
            </div>
          )}

          {connected && (
            <p className="mt-4 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
              {mediaSyncedAt ? (
                <>
                  Vault last read <RelativeTime iso={mediaSyncedAt} />. New folders arrive
                  as “Not used” — nothing starts sending on its own.
                </>
              ) : (
                <>The vault has never been read yet.</>
              )}
            </p>
          )}
        </div>
      </Card>

      {connected && folders.length > 0 && media.length === 0 && (
        <Callout tone="neutral">
          The folders are here but no photos are. Either the vault is empty, or the sync
          could not read the media — check the connection on the card above.
        </Callout>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/** Tlačidlo „načítať z vaultu".
 *
 * Web vault načítať nevie: prístupový token je šifrovaný a dešifruje ho jediné
 * miesto — worker. Klik teda vloží riadok do fronty a worker si ho vezme. Preto
 * tu nie je hláška „hotovo" hneď po kliku, ale stav poslednej požiadavky. */
function SyncButton({
  modelId,
  connected,
  lastSync,
}: {
  modelId: string;
  connected: boolean;
  lastSync: FanvueSyncRequest | null;
}) {
  const [pending, startTransition] = useTransition();
  const [failed, setFailed] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);

  const waiting = Boolean(lastSync && !lastSync.finished_at) || queued;

  return (
    <div className="flex flex-col items-end gap-1.5">
      <button
        type="button"
        disabled={!connected || pending || waiting}
        onClick={() => {
          setFailed(null);
          startTransition(async () => {
            const result = await requestVaultSyncAction(modelId);
            if (result?.error) setFailed(result.error);
            else setQueued(true);
          });
        }}
        className="app-btn app-btn-ghost h-9 px-4"
      >
        {pending || waiting ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <RefreshCw className="h-3.5 w-3.5" />
        )}
        {waiting ? "Reading vault…" : "Sync vault"}
      </button>

      {failed ? (
        <span role="alert" className="text-[11.5px] text-[#fca5a5]">
          {failed}
        </span>
      ) : waiting ? (
        <span className="text-[11.5px] text-[var(--app-text-4)]">
          Queued — the worker picks it up within seconds.
        </span>
      ) : lastSync?.finished_at && lastSync.ok ? (
        <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--app-text-4)]">
          <Check className="h-3 w-3" />
          {lastSync.folders} folders, {lastSync.media_new} new
        </span>
      ) : lastSync?.finished_at ? (
        <span className="inline-flex max-w-[240px] items-start gap-1.5 text-right text-[11.5px] text-[#fca5a5]">
          <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
          {lastSync.error || "The sync failed."}
        </span>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function FolderRow({
  modelId,
  folder,
  photos,
}: {
  modelId: string;
  folder: FvFolder;
  photos: FvMedia[];
}) {
  const [role, setRole] = useState(folder.role);
  const [open, setOpen] = useState(false);
  const [, startTransition] = useTransition();
  const paid = role === "nsfw";

  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[#0c0c0c]">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-[13.5px] text-[var(--app-text)]">{folder.name}</p>
          <p className="mt-0.5 text-[11.5px] text-[var(--app-text-4)]">
            {photos.length} of {folder.media_count} photos synced
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {FOLDER_ROLES.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setRole(option);
                startTransition(async () => {
                  await saveFolderAction(modelId, folder.name, { role: option });
                });
              }}
              className={cn(
                "rounded-md border px-2.5 py-1.5 text-[11.5px] transition-colors",
                role === option
                  ? "border-[var(--app-text)] bg-[var(--app-text)] font-medium text-[#0a0a0a]"
                  : "border-[var(--app-border-strong)] text-[var(--app-text-3)] hover:text-[var(--app-text)]",
              )}
            >
              {FOLDER_ROLE_LABEL[option as FolderRole] ?? option}
            </button>
          ))}
        </div>
      </div>

      {paid && (
        <div className="border-t border-[var(--app-border)] px-4 py-3">
          <FolderPrice modelId={modelId} folder={folder} />
        </div>
      )}

      {photos.length > 0 && (
        <div className="border-t border-[var(--app-border)]">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="w-full px-4 py-2.5 text-left text-[11.5px] text-[var(--app-text-3)] transition-colors hover:text-[var(--app-text)]"
          >
            {open ? "Hide photos" : `Show ${photos.length} photos`}
          </button>
          {open && (
            <>
              <p className="px-4 pb-3 text-[11.5px] leading-relaxed text-[var(--app-text-4)]">
                The caption is what she matches against the conversation, so write what is
                actually in the photo. Nobody gets the same photo twice — Fanvue does not
                remember that, we do. “Explicit” decides for this one photo and overrides
                the folder: switch it on inside a free folder and the photo is treated as
                explicit anyway, switch it off inside an explicit one and it is not.
              </p>
              <div className="grid gap-3 px-4 pb-4 sm:grid-cols-2 xl:grid-cols-3">
                {photos.map((item) => (
                  <MediaTile
                    key={item.media_uuid}
                    modelId={modelId}
                    item={item}
                    paid={paid}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** Východisková cena priečinka. Nie je to cena obsahu — tú má každá fotka
 *  vlastnú, inak by sa najlepšia predávala za to isté ako najslabšia. Táto sa
 *  použije na fotky, ktoré pribudnú a Fanvue k nim cenu nenavrhne. */
function FolderPrice({ modelId, folder }: { modelId: string; folder: FvFolder }) {
  const [value, setValue] = useState(folder.price_cents);
  const [, startTransition] = useTransition();

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="app-label shrink-0" htmlFor={`price-${folder.name}`}>
        Default price for new photos
      </label>
      <input
        id={`price-${folder.name}`}
        type="number"
        min={0}
        step={50}
        value={value}
        onChange={(event) => setValue(Number(event.target.value))}
        onBlur={() => {
          if (value === folder.price_cents) return;
          startTransition(async () => {
            await saveFolderAction(modelId, folder.name, { price_cents: value });
          });
        }}
        className="app-input w-28 py-1.5 text-[12.5px]"
      />
      <span className="text-[11.5px] text-[var(--app-text-4)]">
        {value > 0
          ? `$${(value / 100).toFixed(2)} — used only when Fanvue suggests none`
          : "No default; a photo without a price is never sent"}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function MediaTile({
  modelId,
  item,
  paid,
}: {
  modelId: string;
  item: FvMedia;
  paid: boolean;
}) {
  const [caption, setCaption] = useState(item.caption);
  const [price, setPrice] = useState(item.price_cents);
  const [active, setActive] = useState(item.active);
  const [spicy, setSpicy] = useState(item.spicy);
  const [, startTransition] = useTransition();

  const save = (patch: Parameters<typeof saveMediaAction>[2]) => {
    startTransition(async () => {
      await saveMediaAction(modelId, item.media_uuid, patch);
    });
  };

  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-[#0a0a0a] p-3">
      <div className="flex gap-3">
        {item.thumb_url ? (
          // Adresa z Fanvue je podpísaná a expiruje; optimalizátor `next/image`
          // by si ju zacacheoval a po expirácii ukazoval prázdne miesto. Navyše
          // je to cudzia doména, ktorú by bolo treba povoliť v konfigurácii.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumb_url}
            alt=""
            className="h-16 w-16 shrink-0 rounded-md object-cover"
            style={{ opacity: active ? 1 : 0.3 }}
          />
        ) : (
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-md border border-[var(--app-border)] text-[10.5px] text-[var(--app-text-4)]">
            {item.kind}
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[11px] text-[var(--app-text-4)]">
              {item.sent_count > 0 ? `sent ${item.sent_count}×` : "never sent"}
              {item.posted_at && " · posted"}
            </span>
            <div className="flex shrink-0 gap-1">
              <Chip
                on={spicy}
                label="Explicit"
                onClick={() => {
                  const next = !spicy;
                  setSpicy(next);
                  save({ spicy: next });
                }}
              />
              <Chip
                on={active}
                label={active ? "On" : "Off"}
                onClick={() => {
                  const next = !active;
                  setActive(next);
                  save({ active: next });
                }}
              />
            </div>
          </div>

          <input
            value={caption}
            onChange={(event) => setCaption(event.target.value)}
            onBlur={() => caption !== item.caption && save({ caption })}
            placeholder="what is in the photo — this is how she picks it"
            className="app-input py-1.5 text-[12.5px]"
          />

          {paid && (
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={0}
                step={50}
                value={price}
                onChange={(event) => setPrice(Number(event.target.value))}
                onBlur={() => price !== item.price_cents && save({ price_cents: price })}
                aria-label="Price in cents"
                className="app-input w-24 py-1.5 text-[12.5px]"
              />
              <span className="text-[11px] text-[var(--app-text-4)]">
                {price > 0 ? `$${(price / 100).toFixed(2)}` : "no price — never sent"}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Chip({
  on,
  label,
  onClick,
}: {
  on: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "rounded-md border px-2 py-1 text-[10.5px] transition-colors",
        on
          ? "border-[var(--app-text)] text-[var(--app-text)]"
          : "border-[var(--app-border-strong)] text-[var(--app-text-4)] hover:text-[var(--app-text-2)]",
      )}
    >
      {label}
    </button>
  );
}
